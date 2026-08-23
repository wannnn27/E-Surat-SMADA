"""Factory, route, dan facade kompatibilitas E-Surat SMADA."""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from .config import (
    ARCHIVE_CODE_RE,
    AUTO_NUMBER_PREVIEW,
    BASE_DIR,
    CUSTOM_NUMBER_RE,
    DATA_DIR,
    DATA_ROOT,
    DB_PATH,
    MAX_QUERY_LENGTH,
    PROJECT_ROOT,
    TEMPLATE_DIR,
    TEMPLATE_ROOT,
    UNRESOLVED_TOKEN_RE,
    WIB,
    _env_bool,
)
from .database import _connect_db, _mark_letter_status, _reserve_letter, init_db
from .errors import DataValidationError, RequestValidationError
from .letters import (
    _json_error,
    _public_info,
    _public_person,
    _request_value,
    _validate_request,
    get_surat_context,
)
from .master_data import _load_master_state, _validate_templates, validate_master_data
from .registry import JENIS_SURAT
from .rendering import _check_rendered_docx, _render_letter
from .security import _csrf_token, _is_loopback_address, _is_loopback_bind, _password_matches
from .utils import _normalize_text, _now, format_tanggal_indo


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_mapping(
        DATA_DIR=DATA_DIR,
        TEMPLATE_DIR=TEMPLATE_DIR,
        DATABASE=DB_PATH,
        MAX_CONTENT_LENGTH=128 * 1024,
        NOW_FUNC=lambda: datetime.now(WIB),
        KEPSEK_NIP=os.getenv("ESURAT_KEPSEK_NIP", ""),
        AUTH_USERNAME=os.getenv("ESURAT_USERNAME", ""),
        AUTH_PASSWORD=os.getenv("ESURAT_PASSWORD", ""),
        AUTH_PASSWORD_HASH=os.getenv("ESURAT_PASSWORD_HASH", ""),
        AUTH_ENABLED=None,
        ALLOW_PUBLIC_UNAUTHENTICATED=_env_bool("ESURAT_ALLOW_PUBLIC", bool(os.getenv("VERCEL"))),
        BIND_HOST=os.getenv("ESURAT_HOST", "127.0.0.1"),
        BIND_PORT=int(os.getenv("ESURAT_PORT", "5000")),
        SERVER_THREADS=int(os.getenv("ESURAT_THREADS", "4")),
        NUMBER_SUFFIX=os.getenv("ESURAT_NUMBER_SUFFIX", "SMADA"),
        SECRET_KEY=os.getenv("ESURAT_SECRET_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=_env_bool("ESURAT_HTTPS", False),
        INIT_DB_ON_CREATE=False,
    )
    if config:
        app.config.update(config)

    has_username = bool(app.config.get("AUTH_USERNAME"))
    has_password = bool(app.config.get("AUTH_PASSWORD") or app.config.get("AUTH_PASSWORD_HASH"))
    if has_username != has_password:
        raise DataValidationError("Konfigurasi autentikasi harus berisi username dan password/hash")
    if app.config.get("AUTH_ENABLED") is None:
        app.config["AUTH_ENABLED"] = has_username and has_password
    if app.config["AUTH_ENABLED"] and not (has_username and has_password):
        raise DataValidationError("AUTH_ENABLED memerlukan username dan password/hash")
    if app.config["AUTH_ENABLED"] and not app.config.get("SECRET_KEY"):
        raise DataValidationError("ESURAT_SECRET_KEY wajib diatur ketika autentikasi aktif")
    if not app.config.get("SECRET_KEY"):
        # Aman untuk satu proses local-only; production/auth wajib memberi secret stabil.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    if (
        not app.config["AUTH_ENABLED"]
        and not app.config.get("ALLOW_PUBLIC_UNAUTHENTICATED")
        and not _is_loopback_bind(str(app.config["BIND_HOST"]))
    ):
        raise DataValidationError("Aplikasi tanpa autentikasi hanya boleh bind ke loopback")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", str(app.config["NUMBER_SUFFIX"])):
        raise DataValidationError("ESURAT_NUMBER_SUFFIX harus 1-20 karakter huruf/angka/_/-")
    if not 1 <= int(app.config["SERVER_THREADS"]) <= 32:
        raise DataValidationError("ESURAT_THREADS harus berada pada rentang 1-32")

    state = _load_master_state(app)
    app.extensions["esurat_data"] = state
    app.extensions["template_hashes"] = _validate_templates(Path(app.config["TEMPLATE_DIR"]))
    app.jinja_env.globals["csrf_token"] = _csrf_token
    database_lock = threading.Lock()
    app.extensions["database_initialized"] = False

    def ensure_database_initialized() -> None:
        if app.extensions["database_initialized"]:
            return
        with database_lock:
            if not app.extensions["database_initialized"]:
                init_db(Path(app.config["DATABASE"]))
                app.extensions["database_initialized"] = True

    app.extensions["ensure_database"] = ensure_database_initialized
    if app.config["INIT_DB_ON_CREATE"]:
        ensure_database_initialized()

    @app.before_request
    def enforce_access_and_csrf():
        endpoint = request.endpoint or ""
        public_when_authenticated = {"healthz", "api_csrf", "login", "static"}
        if not app.config["AUTH_ENABLED"]:
            if not app.config.get("ALLOW_PUBLIC_UNAUTHENTICATED") and not _is_loopback_address(request.remote_addr):
                return _json_error("Akses tanpa autentikasi hanya diizinkan dari komputer lokal", 403)
        elif endpoint not in public_when_authenticated and not session.get("authenticated"):
            if request.method == "GET" and not request.path.startswith("/api/"):
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return _json_error("Autentikasi diperlukan", 401)

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = (
                request.form.get("_csrf_token")
                or request.form.get("csrf_token")
                or request.headers.get("X-CSRF-Token", "")
                or request.headers.get("X-CSRFToken", "")
            )
            expected = session.get("csrf_token", "")
            if not supplied or not expected or not hmac.compare_digest(str(supplied), str(expected)):
                return _json_error("Token CSRF tidak valid atau kedaluwarsa", 403)
        ensure_database_initialized()
        return None

    @app.after_request
    def add_security_headers(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; "
            "img-src 'self' data:; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.errorhandler(RequestValidationError)
    def handle_validation_error(exc: RequestValidationError):
        return _json_error(exc.message, exc.status_code, exc.field_errors)

    @app.errorhandler(413)
    def handle_too_large(_exc):
        return _json_error("Ukuran request melebihi batas aplikasi", 413)

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(exc: sqlite3.Error):
        app.logger.exception("Kesalahan database SQLite", exc_info=exc)
        return _json_error("Database sementara tidak dapat digunakan", 503)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        return _json_error(exc.description or "Request gagal", exc.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        app.logger.exception("Kesalahan aplikasi tidak terduga", exc_info=exc)
        return _json_error("Terjadi kesalahan internal saat memproses surat", 500)

    @app.get("/")
    def index():
        today_iso = _now().date().isoformat()
        registry = {
            key: _public_info(key, info, today_iso, combined=False)
            for key, info in JENIS_SURAT.items()
        }
        stats = {
            "guru": len(state["guru"]),
            "murid": len(state["murid"]),
            "template": len(JENIS_SURAT),
            "kode_arsip": len(state["kode_arsip"]),
        }
        return render_template(
            "index.html",
            jenis_surat=registry,
            stats=stats,
            auth_enabled=bool(app.config["AUTH_ENABLED"]),
            username=session.get("username", ""),
        )

    @app.get("/api/csrf")
    def api_csrf():
        return jsonify(
            {
                "csrf_token": _csrf_token(),
                "authenticated": bool(session.get("authenticated")),
                "auth_enabled": bool(app.config["AUTH_ENABLED"]),
            }
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not app.config["AUTH_ENABLED"]:
            return redirect(url_for("index")) if request.method == "GET" else _json_error(
                "Autentikasi tidak diaktifkan; aplikasi berjalan local-only", 400
            )
        if request.method == "GET":
            if session.get("authenticated"):
                return redirect(url_for("index"))
            return render_template("login.html", error=None, next_path=request.args.get("next", ""))

        data = request.get_json(silent=True) or request.form
        username = _normalize_text(data.get("username", ""))
        password = str(data.get("password", ""))
        if not hmac.compare_digest(username, str(app.config["AUTH_USERNAME"])) or not _password_matches(
            password
        ):
            if request.is_json:
                return _json_error("Username atau password salah", 401)
            return (
                render_template(
                    "login.html",
                    error="Username atau password salah.",
                    next_path=request.form.get("next", ""),
                ),
                401,
            )
        session.clear()
        session["authenticated"] = True
        session["username"] = username
        session["csrf_token"] = secrets.token_urlsafe(32)
        if request.is_json:
            return jsonify({"ok": True, "csrf_token": session["csrf_token"]})
        next_path = str(request.form.get("next", ""))
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = url_for("index")
        return redirect(next_path)

    @app.post("/logout")
    def logout():
        session.clear()
        if request.is_json:
            return jsonify({"ok": True})
        return redirect(url_for("login"))

    @app.get("/healthz")
    def healthz():
        problems: list[str] = []
        try:
            conn = _connect_db(Path(app.config["DATABASE"]))
            try:
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            problems.append("database")
        if len(app.extensions["template_hashes"]) != len(JENIS_SURAT):
            problems.append("templates")
        payload = {
            "status": "ok" if not problems else "degraded",
            "checks": {
                "database": "ok" if "database" not in problems else "error",
                "templates": "ok" if "templates" not in problems else "error",
                "guru_count": len(state["guru"]),
                "murid_count": len(state["murid"]),
                "kode_arsip_count": len(state["kode_arsip"]),
            },
        }
        return jsonify(payload), 200 if not problems else 503

    @app.get("/api/search")
    def api_search():
        kategori = _request_value(request.args, "kategori", "guru")
        if kategori not in {"guru", "murid"}:
            return _json_error("Kategori pencarian tidak valid", 400, {"kategori": "guru atau murid"})
        query = _request_value(request.args, "q").casefold()
        if len(query) < 2:
            return jsonify([])
        if len(query) > MAX_QUERY_LENGTH:
            return _json_error("Kueri pencarian terlalu panjang", 400, {"q": "maksimal 100 karakter"})
        source = state["guru"] if kategori == "guru" else state["murid"]
        results: list[dict[str, str]] = []
        for record in source:
            identifiers = record["nip"] if kategori == "guru" else f"{record['nis']} {record['nisn']}"
            haystack = f"{record['nama']} {identifiers}".casefold()
            if query in haystack:
                results.append(_public_person(record, kategori))
            if len(results) >= 15:
                break
        return jsonify(results)

    @app.get("/api/list/guru")
    def api_list_guru():
        query = _request_value(request.args, "q").casefold()
        if len(query) > MAX_QUERY_LENGTH:
            return _json_error("Kueri pencarian terlalu panjang", 400, {"q": "maksimal 100 karakter"})
        records = [
            _public_person(record, "guru", directory=True)
            for record in state["guru"]
            if not query or query in f"{record['nama']} {record['nip']} {record['jabatan']}".casefold()
        ]
        return jsonify(records[:100])

    @app.get("/api/list/murid")
    def api_list_murid():
        query = _request_value(request.args, "q").casefold()
        kelas = _request_value(request.args, "kelas").casefold()
        if len(query) > MAX_QUERY_LENGTH or len(kelas) > MAX_QUERY_LENGTH:
            return _json_error("Filter pencarian terlalu panjang", 400)
        results: list[dict[str, str]] = []
        for record in state["murid"]:
            haystack = f"{record['nama']} {record['nis']} {record['nisn']} {record['kelas']}".casefold()
            if query and query not in haystack:
                continue
            if kelas and kelas not in record["kelas"].casefold():
                continue
            results.append(_public_person(record, "murid", directory=True))
            if len(results) >= 100:
                break
        return jsonify(results)

    @app.get("/api/list/kode_arsip")
    def api_list_kode_arsip():
        query = _request_value(request.args, "q").casefold()
        if len(query) > MAX_QUERY_LENGTH:
            return _json_error("Kueri pencarian terlalu panjang", 400, {"q": "maksimal 100 karakter"})
        records = [
            {"kode": record["kode"], "keterangan": record["keterangan"]}
            for record in state["kode_arsip"]
            if not query or query in f"{record['kode']} {record['keterangan']}".casefold()
        ]
        return jsonify(records[:30])

    @app.get("/api/list/riwayat")
    def api_list_riwayat():
        conn = _connect_db(Path(app.config["DATABASE"]))
        try:
            rows = conn.execute(
                """
                SELECT id, created_at, updated_at, jenis_surat, jenis_key, nomor_surat,
                       nama_pemohon, id_pemohon, kategori, keperluan, status, request_id
                FROM riwayat_surat ORDER BY id DESC LIMIT 50
                """
            ).fetchall()
        finally:
            conn.close()
        return jsonify([dict(row) for row in rows])

    @app.get("/api/fields/<jenis>")
    def api_fields(jenis: str):
        info = JENIS_SURAT.get(jenis)
        if info is None:
            return _json_error("Jenis surat tidak ditemukan", 404, {"jenis_surat": "tidak terdaftar"})
        return jsonify(_public_info(jenis, info, _now().date().isoformat(), combined=True))

    @app.post("/api/preview_render")
    def api_preview_render():
        validated = _validate_request(request.form, preview=True)
        info = _public_info(
            validated["jenis"], validated["info"], validated["normalized"]["tanggal_surat"], combined=True
        )
        person = _public_person(validated["person"], validated["info"]["kategori"], directory=True)
        return jsonify(
            {
                "info": info,
                "context": validated["context"],
                "person": person,
                "signer": validated["signer"],
                "request_id": validated["normalized"]["request_id"],
                "preview_notice": "Ringkasan tervalidasi; nomor otomatis dialokasikan saat unduh.",
            }
        )

    @app.post("/generate")
    def generate():
        validated = _validate_request(request.form, preview=False)
        reservation = _reserve_letter(validated)
        validated["context"]["nomor_surat"] = reservation["number"]
        should_mark = reservation["action"] != "generated"
        try:
            buf = _render_letter(validated, reservation["number"])
        except Exception as exc:
            if should_mark:
                try:
                    _mark_letter_status(reservation["id"], "failed", str(exc))
                except sqlite3.Error:
                    app.logger.exception("Gagal mencatat status render failed")
            app.logger.exception("Gagal merender template %s", validated["jenis"])
            return _json_error("Dokumen gagal dirender; tidak ada surat sukses yang dicatat", 500)

        if should_mark:
            _mark_letter_status(reservation["id"], "generated")

        safe_name = secure_filename(validated["person"]["nama"]) or "personel"
        filename = f"{validated['jenis']}_{safe_name}.docx"[:180]
        response = send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response.headers["X-Letter-Number"] = reservation["number"]
        response.headers["X-Request-ID"] = reservation["request_id"]
        return response

    return app


def run(app_instance: Flask | None = None) -> None:
    """Jalankan server Waitress; ``app.py`` memasok instance WSGI produksi."""

    logging.basicConfig(level=logging.INFO)
    web_app = app_instance or create_app()
    web_app.extensions["ensure_database"]()
    from waitress import serve

    web_app.logger.info(
        "E-Surat berjalan di http://%s:%s (auth=%s)",
        web_app.config["BIND_HOST"],
        web_app.config["BIND_PORT"],
        "aktif" if web_app.config["AUTH_ENABLED"] else "local-only",
    )
    serve(
        web_app,
        host=str(web_app.config["BIND_HOST"]),
        port=int(web_app.config["BIND_PORT"]),
        threads=int(web_app.config["SERVER_THREADS"]),
        clear_untrusted_proxy_headers=True,
    )
