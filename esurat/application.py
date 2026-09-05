"""Factory, route, dan facade kompatibilitas E-Surat SMADA."""

from __future__ import annotations

import csv
import hmac
import io
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
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
    MAX_TEMPLATE_BYTES,
    PROJECT_ROOT,
    TEMPLATE_DIR,
    TEMPLATE_KEY_RE,
    TEMPLATE_ROOT,
    UNRESOLVED_TOKEN_RE,
    WIB,
    _env_bool,
)
from .database import (
    DATABASE_ERRORS,
    POSTGRES_ERROR,
    _cancel_letter,
    _connect_db,
    _is_postgres,
    _mark_letter_status,
    _reserve_letter,
    _sql,
    _table,
    delete_custom_template,
    init_db,
    load_custom_templates,
    save_custom_template,
    verify_postgres_runtime,
)
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
from .pdf_rendering import render_pdf_from_docx
from .registry import JENIS_SURAT
from .rendering import _check_rendered_docx, _render_letter
from .security import (
    _csrf_token,
    _is_loopback_address,
    _is_loopback_bind,
    _load_auth_users,
    _password_matches,
)
from .template_management import validate_custom_template
from .utils import _normalize_text, _now, _validate_safe_text, format_tanggal_indo


def _environment_integer(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise DataValidationError(f"{name} harus berupa bilangan bulat") from exc


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_mapping(
        DATA_DIR=DATA_DIR,
        TEMPLATE_DIR=TEMPLATE_DIR,
        DATABASE=os.getenv("DATABASE_URL", str(DB_PATH)),
        MAX_CONTENT_LENGTH=MAX_TEMPLATE_BYTES + 128 * 1024,
        NOW_FUNC=lambda: datetime.now(WIB),
        KEPSEK_NIP=os.getenv("ESURAT_KEPSEK_NIP", ""),
        AUTH_USERNAME=os.getenv("ESURAT_USERNAME", ""),
        AUTH_PASSWORD=os.getenv("ESURAT_PASSWORD", ""),
        AUTH_PASSWORD_HASH=os.getenv("ESURAT_PASSWORD_HASH", ""),
        AUTH_USERS_FILE=os.getenv("ESURAT_USERS_FILE", ""),
        AUTH_DEFAULT_ROLE=os.getenv("ESURAT_DEFAULT_ROLE", "admin"),
        AUTH_ENABLED=None,
        BIND_HOST=os.getenv("ESURAT_HOST", "127.0.0.1"),
        BIND_PORT=_environment_integer("ESURAT_PORT", 5000),
        SERVER_THREADS=_environment_integer("ESURAT_THREADS", 4),
        NUMBER_SUFFIX=os.getenv("ESURAT_NUMBER_SUFFIX", "SMADA"),
        SECRET_KEY=os.getenv("ESURAT_SECRET_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=_env_bool("ESURAT_HTTPS", False),
        PERMANENT_SESSION_LIFETIME=timedelta(
            hours=_environment_integer("ESURAT_SESSION_HOURS", 8)
        ),
        SESSION_REFRESH_EACH_REQUEST=True,
        LOGIN_MAX_ATTEMPTS=_environment_integer("ESURAT_LOGIN_MAX_ATTEMPTS", 5),
        LOGIN_WINDOW_SECONDS=_environment_integer("ESURAT_LOGIN_WINDOW_SECONDS", 900),
        AUTO_MIGRATE_DATABASE=_env_bool("ESURAT_AUTO_MIGRATE_DATABASE", False),
        INIT_DB_ON_CREATE=False,
    )
    if config:
        app.config.update(config)

    is_vercel = bool(os.getenv("VERCEL") and not app.config.get("TESTING"))
    app.config["VERCEL_DEMO"] = False
    if is_vercel and not _is_postgres(app.config["DATABASE"]):
        raise DataValidationError(
            "DATABASE_URL PostgreSQL wajib diatur pada Vercel; database demo sementara tidak didukung"
        )

    auth_users = _load_auth_users(app.config)
    if app.config.get("AUTH_ENABLED") is None:
        app.config["AUTH_ENABLED"] = bool(auth_users)
    if app.config["AUTH_ENABLED"] and not auth_users:
        raise DataValidationError("AUTH_ENABLED memerlukan setidaknya satu akun aktif")
    if is_vercel and not app.config["AUTH_ENABLED"]:
        raise DataValidationError("Akun admin wajib dikonfigurasi pada deployment Vercel")
    stable_secret_required = bool(app.config["AUTH_ENABLED"] or is_vercel)
    if stable_secret_required and not app.config.get("SECRET_KEY"):
        raise DataValidationError(
            "ESURAT_SECRET_KEY wajib diatur untuk autentikasi atau deployment publik/serverless"
        )
    if not app.config.get("SECRET_KEY"):
        # Aman untuk satu proses local-only; deployment publik/auth wajib memberi secret stabil.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    if (
        not app.config["AUTH_ENABLED"]
        and not _is_loopback_bind(str(app.config["BIND_HOST"]))
    ):
        raise DataValidationError("Aplikasi tanpa autentikasi hanya boleh bind ke loopback")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", str(app.config["NUMBER_SUFFIX"])):
        raise DataValidationError("ESURAT_NUMBER_SUFFIX harus 1-20 karakter huruf/angka/_/-")
    if not 1 <= int(app.config["SERVER_THREADS"]) <= 32:
        raise DataValidationError("ESURAT_THREADS harus berada pada rentang 1-32")
    if not 3600 <= app.permanent_session_lifetime.total_seconds() <= 24 * 3600:
        raise DataValidationError("ESURAT_SESSION_HOURS harus berada pada rentang 1-24")
    if not 1 <= int(app.config["LOGIN_MAX_ATTEMPTS"]) <= 20:
        raise DataValidationError("ESURAT_LOGIN_MAX_ATTEMPTS harus berada pada rentang 1-20")
    if not 60 <= int(app.config["LOGIN_WINDOW_SECONDS"]) <= 3600:
        raise DataValidationError("ESURAT_LOGIN_WINDOW_SECONDS harus 60-3600 detik")

    state = _load_master_state(app)
    app.extensions["esurat_data"] = state
    app.extensions["auth_users"] = auth_users
    builtin_template_hashes = _validate_templates(Path(app.config["TEMPLATE_DIR"]))
    app.extensions["builtin_template_hashes"] = builtin_template_hashes
    app.extensions["template_hashes"] = dict(builtin_template_hashes)
    app.extensions["letter_registry"] = dict(JENIS_SURAT)
    app.jinja_env.globals["csrf_token"] = _csrf_token
    database_lock = threading.Lock()
    login_attempts: dict[str, deque[float]] = defaultdict(deque)
    login_attempts_lock = threading.Lock()
    app.extensions["database_initialized"] = False

    def refresh_custom_templates() -> None:
        registry = dict(JENIS_SURAT)
        custom_templates = load_custom_templates(app.config["DATABASE"])
        registry.update(custom_templates)
        hashes = dict(app.extensions["builtin_template_hashes"])
        hashes.update(
            {key: str(info["template_hash"]) for key, info in custom_templates.items()}
        )
        app.extensions["letter_registry"] = registry
        app.extensions["template_hashes"] = hashes

    def letter_registry() -> dict[str, dict[str, Any]]:
        return app.extensions["letter_registry"]

    def ensure_database_initialized() -> None:
        if app.extensions["database_initialized"]:
            return
        with database_lock:
            if not app.extensions["database_initialized"]:
                database = app.config["DATABASE"]
                if _is_postgres(database) and not app.config["AUTO_MIGRATE_DATABASE"]:
                    verify_postgres_runtime(str(database))
                else:
                    init_db(database)
                refresh_custom_templates()
                app.extensions["database_initialized"] = True

    app.extensions["ensure_database"] = ensure_database_initialized
    if app.config["INIT_DB_ON_CREATE"]:
        ensure_database_initialized()

    @app.before_request
    def enforce_access_and_csrf():
        endpoint = request.endpoint or ""
        if app.config["AUTH_ENABLED"] and session.get("authenticated"):
            session_username = _normalize_text(session.get("username", ""))
            configured_user = auth_users.get(session_username.casefold())
            if (
                configured_user is None
                or session.get("role") != configured_user.get("role")
            ):
                session.clear()
        if not app.config["AUTH_ENABLED"]:
            if not _is_loopback_address(request.remote_addr):
                return _json_error("Akses tanpa autentikasi hanya diizinkan dari komputer lokal", 403)
        admin_endpoints = {
            "admin_dashboard",
            "admin_template_delete",
            "admin_template_upload",
            "api_cancel_history",
            "api_export_history",
            "api_list_riwayat",
        }
        if endpoint in admin_endpoints and session.get("role") != "admin":
            if request.method == "GET" and not request.path.startswith("/api/"):
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return _json_error("Akses admin diperlukan", 403, {"role": "admin diperlukan"})

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = (
                request.headers.get("X-CSRF-Token", "")
                or request.headers.get("X-CSRFToken", "")
                or request.form.get("_csrf_token")
                or request.form.get("csrf_token")
            )
            expected = session.get("csrf_token", "")
            if not supplied or not expected or not hmac.compare_digest(str(supplied), str(expected)):
                return jsonify(
                    {
                        "error": "Token CSRF tidak valid atau kedaluwarsa",
                        "code": "csrf_invalid",
                    }
                ), 403
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
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com"
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
    def handle_database_error(exc: Exception):
        app.logger.exception("Kesalahan database", exc_info=exc)
        return _json_error("Database tidak dapat digunakan sementara", 503)

    if POSTGRES_ERROR is not None:
        app.register_error_handler(POSTGRES_ERROR, handle_database_error)

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
            for key, info in letter_registry().items()
        }
        stats = {
            "guru": len(state["guru"]),
            "murid": len(state["murid"]),
            "template": len(registry),
            "kode_arsip": len(state["kode_arsip"]),
        }
        return render_template(
            "index.html",
            jenis_surat=registry,
            stats=stats,
            auth_enabled=bool(app.config["AUTH_ENABLED"]),
            username=session.get("username", ""),
            role=session.get("role", "user") if session.get("authenticated") else "user",
        )

    @app.get("/api/csrf")
    def api_csrf():
        return jsonify(
            {
                "csrf_token": _csrf_token(),
                "authenticated": bool(session.get("authenticated")),
                "auth_enabled": bool(app.config["AUTH_ENABLED"]),
                "role": session.get("role", "user") if session.get("authenticated") else "user",
            }
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not app.config["AUTH_ENABLED"]:
            return redirect(url_for("index")) if request.method == "GET" else _json_error(
                "Login admin belum dikonfigurasi; aplikasi berjalan local-only", 400
            )
        if request.method == "GET":
            if session.get("authenticated"):
                return redirect(url_for("admin_dashboard"))
            return render_template("login.html", error=None, next_path=request.args.get("next", ""))

        data = request.get_json(silent=True) or request.form
        username = _normalize_text(data.get("username", ""))
        password = str(data.get("password", ""))
        attempt_key = f"{request.remote_addr or 'unknown'}|{username[:80].casefold()}"
        now_monotonic = time.monotonic()
        with login_attempts_lock:
            if attempt_key not in login_attempts and len(login_attempts) >= 1024:
                global_cutoff = now_monotonic - int(app.config["LOGIN_WINDOW_SECONDS"])
                stale_keys = [
                    key
                    for key, values in login_attempts.items()
                    if not values or values[-1] < global_cutoff
                ]
                for key in stale_keys:
                    login_attempts.pop(key, None)
                while len(login_attempts) >= 1024:
                    login_attempts.pop(next(iter(login_attempts)))
            attempts = login_attempts[attempt_key]
            cutoff = now_monotonic - int(app.config["LOGIN_WINDOW_SECONDS"])
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            if len(attempts) >= int(app.config["LOGIN_MAX_ATTEMPTS"]):
                return _json_error(
                    "Terlalu banyak percobaan login. Tunggu sebelum mencoba kembali.", 429
                )

        user = (
            auth_users.get(username.casefold())
            if len(username) <= 80 and len(password) <= 512
            else None
        )
        if user is None or not _password_matches(user, password):
            with login_attempts_lock:
                login_attempts[attempt_key].append(now_monotonic)
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
        with login_attempts_lock:
            login_attempts.pop(attempt_key, None)
        session.clear()
        session.permanent = True
        session["authenticated"] = True
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        if request.is_json:
            return jsonify(
                {
                    "ok": True,
                    "csrf_token": session["csrf_token"],
                    "username": user["username"],
                    "role": user["role"],
                }
            )
        next_path = str(request.form.get("next", ""))
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = url_for("admin_dashboard")
        return redirect(next_path)

    @app.post("/logout")
    def logout():
        session.clear()
        if request.is_json:
            return jsonify({"ok": True})
        return redirect(url_for("index"))

    def render_admin_dashboard(*, error: str | None = None, field_errors=None, status: int = 200):
        custom = [
            dict(info, key=key)
            for key, info in letter_registry().items()
            if info.get("is_custom")
        ]
        return (
            render_template(
                "admin.html",
                custom_templates=custom,
                archive_codes=state["kode_arsip"],
                error=error,
                field_errors=field_errors or {},
                success=request.args.get("success", ""),
                username=session.get("username", "admin"),
            ),
            status,
        )

    @app.get("/admin")
    def admin_dashboard():
        return render_admin_dashboard()

    @app.post("/admin/templates")
    def admin_template_upload():
        upload = request.files.get("template_file")
        filename = secure_filename(upload.filename or "") if upload else ""
        content = upload.read(MAX_TEMPLATE_BYTES + 1) if upload else b""
        if filename and not filename.casefold().endswith(".docx"):
            return render_admin_dashboard(
                error="Template belum valid",
                field_errors={"template_file": "file harus berformat .docx"},
                status=422,
            )
        try:
            template = validate_custom_template(
                request.form,
                content,
                set(state["kode_by_value"]),
            )
            if template["key"] in JENIS_SURAT:
                raise RequestValidationError(
                    "Template belum valid",
                    {"key": "key tersebut dipakai template bawaan dan tidak dapat ditimpa"},
                    422,
                )
            save_custom_template(app.config["DATABASE"], template)
            refresh_custom_templates()
        except RequestValidationError as exc:
            return render_admin_dashboard(
                error=exc.message,
                field_errors=exc.field_errors,
                status=exc.status_code,
            )
        return redirect(url_for("admin_dashboard", success="Template berhasil disimpan"))

    @app.post("/admin/templates/<key>/delete")
    def admin_template_delete(key: str):
        if request.form.get("confirm") != "DELETE":
            return _json_error("Konfirmasi penghapusan diperlukan", 422)
        info = letter_registry().get(key)
        if info is None or not info.get("is_custom"):
            return _json_error("Template kustom tidak ditemukan", 404)
        delete_custom_template(app.config["DATABASE"], key)
        refresh_custom_templates()
        return redirect(url_for("admin_dashboard", success="Template berhasil dihapus"))

    @app.get("/healthz")
    def healthz():
        problems: list[str] = []
        try:
            conn = _connect_db(app.config["DATABASE"])
            try:
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
        except DATABASE_ERRORS:
            problems.append("database")
        if len(app.extensions["template_hashes"]) != len(letter_registry()):
            problems.append("templates")
        payload = {
            "status": "ok" if not problems else "degraded",
            "checks": {
                "database": "ok" if "database" not in problems else "error",
                "templates": "ok" if "templates" not in problems else "error",
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

    def history_filter_sql() -> tuple[str, list[Any]]:
        query = _request_value(request.args, "q").casefold()
        status = _request_value(request.args, "status").casefold()
        jenis = _request_value(request.args, "jenis")
        if len(query) > MAX_QUERY_LENGTH:
            raise RequestValidationError(
                "Kueri riwayat terlalu panjang", {"q": "maksimal 100 karakter"}
            )
        if status and status not in {"rendering", "generated", "failed", "cancelled"}:
            raise RequestValidationError(
                "Status riwayat tidak valid", {"status": "tidak dikenal"}
            )
        if jenis and not TEMPLATE_KEY_RE.fullmatch(jenis):
            raise RequestValidationError(
                "Jenis surat riwayat tidak valid", {"jenis": "tidak dikenal"}
            )

        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append(
                "(LOWER(nomor_surat) LIKE ? OR LOWER(nama_pemohon) LIKE ? "
                "OR LOWER(id_pemohon) LIKE ? OR LOWER(keperluan) LIKE ?)"
            )
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern, pattern])
        if status:
            clauses.append("status = ?")
            params.append(status)
        if jenis:
            clauses.append("jenis_key = ?")
            params.append(jenis)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where_sql, params

    @app.get("/api/list/riwayat")
    def api_list_riwayat():
        where_sql, params = history_filter_sql()
        try:
            page = int(request.args.get("page", "1"))
            per_page = int(request.args.get("per_page", "25"))
        except ValueError:
            return _json_error("Paginasi riwayat tidak valid", 400)
        if page < 1 or not 1 <= per_page <= 100:
            return _json_error("Paginasi riwayat di luar batas", 400)

        database = app.config["DATABASE"]
        postgres = _is_postgres(database)
        history_table = _table("riwayat_surat", postgres)
        conn = _connect_db(database)
        try:
            total = int(
                conn.execute(
                    _sql(f"SELECT COUNT(*) FROM {history_table}{where_sql}", postgres),
                    params,
                ).fetchone()[0]
            )
            rows = conn.execute(
                _sql(f"""
                SELECT id, created_at, updated_at, jenis_surat, jenis_key, nomor_surat,
                       nama_pemohon, id_pemohon, kategori, keperluan, status, request_id,
                       created_by, created_by_role, cancelled_at, cancelled_by, cancel_reason
                FROM {history_table}{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?
                """, postgres),
                [*params, per_page, (page - 1) * per_page],
            ).fetchall()
        finally:
            conn.close()
        return jsonify(
            {
                "items": [dict(row) for row in rows],
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            }
        )

    @app.get("/api/history/export.csv")
    def api_export_history():
        where_sql, params = history_filter_sql()
        database = app.config["DATABASE"]
        postgres = _is_postgres(database)
        history_table = _table("riwayat_surat", postgres)
        conn = _connect_db(database)
        try:
            rows = conn.execute(
                _sql(f"""
                SELECT created_at, nomor_surat, jenis_surat, status, nama_pemohon,
                       id_pemohon, kategori, keperluan, created_by, created_by_role,
                       cancelled_at, cancelled_by, cancel_reason
                FROM {history_table}{where_sql} ORDER BY id DESC
                """, postgres),
                params,
            ).fetchall()
        finally:
            conn.close()

        def safe_csv_cell(value: Any) -> str:
            text_value = "" if value is None else str(value)
            if text_value.startswith(("=", "+", "-", "@")):
                return "'" + text_value
            return text_value

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "Tanggal dibuat",
                "Nomor surat",
                "Jenis surat",
                "Status",
                "Nama pemohon",
                "ID pemohon",
                "Kategori",
                "Keperluan",
                "Operator",
                "Peran operator",
                "Tanggal pembatalan",
                "Dibatalkan oleh",
                "Alasan pembatalan",
            ]
        )
        writer.writerows([safe_csv_cell(value) for value in row] for row in rows)
        filename = f"riwayat-surat-{_now().date().isoformat()}.csv"
        return app.response_class(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/history/<int:record_id>/cancel")
    def api_cancel_history(record_id: int):
        data = request.get_json(silent=True) or request.form
        reason = _normalize_text(data.get("reason", ""))
        reason_error = _validate_safe_text(reason, max_length=300)
        if reason_error or len(reason) < 5:
            return _json_error(
                "Alasan pembatalan belum valid",
                422,
                {"reason": reason_error or "minimal 5 karakter"},
            )
        cancelled = _cancel_letter(record_id, reason)
        return jsonify(
            {
                "ok": True,
                "id": cancelled.get("id"),
                "status": cancelled.get("status"),
                "cancelled_at": cancelled.get("cancelled_at"),
                "cancelled_by": cancelled.get("cancelled_by"),
            }
        )

    @app.get("/api/fields/<jenis>")
    def api_fields(jenis: str):
        info = letter_registry().get(jenis)
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
        people = [
            _public_person(item, validated["info"]["kategori"], directory=True)
            for item in validated["people"]
        ]
        return jsonify(
            {
                "info": info,
                "context": validated["context"],
                "person": person,
                "students": people if int(validated["info"].get("max_people", 1)) > 1 else [],
                "signer": validated["signer"],
                "request_id": validated["normalized"]["request_id"],
                "preview_notice": "Ringkasan tervalidasi; nomor otomatis dialokasikan saat unduh.",
            }
        )

    @app.post("/generate")
    def generate():
        output_format = _normalize_text(request.form.get("output_format", "docx")).casefold()
        if output_format not in {"docx", "pdf"}:
            return _json_error(
                "Format dokumen tidak didukung",
                422,
                {"output_format": "pilih format docx atau pdf"},
            )
        validated = _validate_request(request.form, preview=False)
        reservation = _reserve_letter(validated)
        validated["context"]["nomor_surat"] = reservation["number"]
        should_mark = reservation["action"] != "generated"
        try:
            docx_buffer = _render_letter(validated, reservation["number"])
            if output_format == "pdf":
                buf = render_pdf_from_docx(docx_buffer)
            else:
                buf = docx_buffer
        except Exception as exc:
            if should_mark:
                try:
                    _mark_letter_status(reservation["id"], "failed", str(exc))
                except DATABASE_ERRORS:
                    app.logger.exception("Gagal mencatat status render failed")
            app.logger.exception("Gagal merender template %s", validated["jenis"])
            if output_format == "pdf":
                return _json_error("PDF gagal dibuat; silakan coba unduh format Word", 500)
            return _json_error("Dokumen gagal dirender; tidak ada surat sukses yang dicatat", 500)

        if should_mark:
            _mark_letter_status(reservation["id"], "generated")

        safe_name = secure_filename(validated["person"]["nama"]) or "personel"
        if len(validated["people"]) > 1:
            safe_name = f"{safe_name}-dan-{len(validated['people']) - 1}-siswa"
        extension = ".pdf" if output_format == "pdf" else ".docx"
        filename = f"{validated['jenis']}_{safe_name}"[: 180 - len(extension)] + extension
        mimetype = (
            "application/pdf"
            if output_format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response = send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype,
        )
        response.headers["X-Letter-Number"] = reservation["number"]
        response.headers["X-Request-ID"] = reservation["request_id"]
        response.headers["X-Document-Format"] = output_format
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
