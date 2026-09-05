"""Migrasi SQLite, reservasi nomor, idempotensi, dan riwayat surat."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - instalasi lokal lama tetap memberi pesan jelas saat dipakai
    psycopg = None
    dict_row = None

from flask import current_app

from .config import DB_PATH, WIB
from .errors import RequestValidationError
from .security import _current_actor
from .utils import _now, _parse_iso_date


POSTGRES_SCHEMA = "esurat"
POSTGRES_ERROR = psycopg.Error if psycopg is not None else None
DATABASE_ERRORS = (
    (sqlite3.Error, psycopg.Error) if psycopg is not None else (sqlite3.Error,)
)


def _is_postgres(database: Path | str) -> bool:
    return str(database).startswith(("postgresql://", "postgres://"))


def _table(name: str, postgres: bool) -> str:
    """Kembalikan nama tabel statis yang aman untuk backend aktif."""

    if name not in {"custom_templates", "master_data", "nomor_counter", "riwayat_surat"}:
        raise ValueError(f"Nama tabel tidak dikenal: {name}")
    return f"{POSTGRES_SCHEMA}.{name}" if postgres else name


def _connect_db(db_path: Path | str):
    if _is_postgres(db_path):
        if psycopg is None:
            raise RuntimeError("Driver PostgreSQL psycopg belum terpasang")
        # Supabase Transaction Pooler tidak mendukung named prepared statements.
        # Menonaktifkannya juga mencegah state statement bocor antar koneksi pool.
        return psycopg.connect(
            str(db_path),
            row_factory=dict_row,
            prepare_threshold=None,
            connect_timeout=10,
        )
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _begin_write(conn, postgres: bool) -> None:
    conn.execute("BEGIN" if postgres else "BEGIN IMMEDIATE")


def _sql(query: str, postgres: bool) -> str:
    return query.replace("?", "%s") if postgres else query


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Migrasi database secara additive; record lama tidak diubah atau dihapus."""

    if _is_postgres(db_path):
        _init_postgres(str(db_path))
        return

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect_db(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS riwayat_surat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                jenis_surat TEXT,
                nomor_surat TEXT,
                nama_pemohon TEXT,
                id_pemohon TEXT,
                kategori TEXT,
                keperluan TEXT,
                request_id TEXT,
                status TEXT,
                jenis_key TEXT,
                template TEXT,
                hash TEXT,
                payload_hash TEXT,
                error TEXT,
                updated_at TEXT,
                created_by TEXT,
                created_by_role TEXT,
                cancelled_at TEXT,
                cancelled_by TEXT,
                cancel_reason TEXT
            )
            """
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(riwayat_surat)")}
        additions = {
            "request_id": "TEXT",
            "status": "TEXT",
            "jenis_key": "TEXT",
            "template": "TEXT",
            "hash": "TEXT",
            "payload_hash": "TEXT",
            "error": "TEXT",
            "updated_at": "TEXT",
            "created_by": "TEXT",
            "created_by_role": "TEXT",
            "cancelled_at": "TEXT",
            "cancelled_by": "TEXT",
            "cancel_reason": "TEXT",
        }
        for column, column_type in additions.items():
            if column not in existing:
                conn.execute(f'ALTER TABLE riwayat_surat ADD COLUMN "{column}" {column_type}')

        # Record sebelum schema status/audit dianggap surat legacy yang telah
        # dibuat. Backfill ini membuat filter dan ekspor konsisten tanpa
        # menghapus atau mengalokasikan ulang nomor.
        conn.execute(
            "UPDATE riwayat_surat SET status = 'generated' WHERE status IS NULL OR status = ''"
        )
        conn.execute(
            "UPDATE riwayat_surat SET created_by = 'legacy' "
            "WHERE created_by IS NULL OR created_by = ''"
        )
        conn.execute(
            "UPDATE riwayat_surat SET created_by_role = 'unknown' "
            "WHERE created_by_role IS NULL OR created_by_role = ''"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nomor_counter (
                kode TEXT NOT NULL,
                tahun INTEGER NOT NULL,
                last_seq INTEGER NOT NULL CHECK(last_seq > 0),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (kode, tahun)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_templates (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('guru', 'murid')),
                default_code TEXT NOT NULL,
                signer TEXT NOT NULL CHECK (signer IN ('kepsek', 'pemohon', 'wali')),
                fields_json TEXT NOT NULL,
                filename TEXT NOT NULL,
                content BLOB NOT NULL,
                sha256 TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_request_id_new
            ON riwayat_surat(request_id)
            WHERE request_id IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_nomor_new
            ON riwayat_surat(nomor_surat)
            WHERE request_id IS NOT NULL AND nomor_surat IS NOT NULL
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_riwayat_status_updated ON riwayat_surat(status, updated_at)"
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_postgres(database_url: str) -> None:
    conn = _connect_db(database_url)
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_SCHEMA}")
        conn.execute(f"REVOKE ALL ON SCHEMA {POSTGRES_SCHEMA} FROM PUBLIC")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_table('riwayat_surat', True)} (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                jenis_surat TEXT,
                nomor_surat TEXT,
                nama_pemohon TEXT,
                id_pemohon TEXT,
                kategori TEXT,
                keperluan TEXT,
                request_id TEXT,
                status TEXT NOT NULL DEFAULT 'generated'
                    CHECK (status IN ('rendering', 'generated', 'failed', 'cancelled')),
                jenis_key TEXT,
                template TEXT,
                hash TEXT,
                payload_hash TEXT,
                error TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                created_by_role TEXT,
                cancelled_at TIMESTAMPTZ,
                cancelled_by TEXT,
                cancel_reason TEXT
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_table('nomor_counter', True)} (
                kode TEXT NOT NULL,
                tahun INTEGER NOT NULL CHECK (tahun BETWEEN 2000 AND 2200),
                last_seq INTEGER NOT NULL CHECK(last_seq > 0),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (kode, tahun)
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_table('master_data', True)} (
                kind TEXT PRIMARY KEY CHECK (kind IN ('guru', 'murid', 'kode_arsip')),
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_table('custom_templates', True)} (
                key TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{{2,49}}$'),
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('guru', 'murid')),
                default_code TEXT NOT NULL,
                signer TEXT NOT NULL CHECK (signer IN ('kepsek', 'pemohon', 'wali')),
                fields_json JSONB NOT NULL,
                filename TEXT NOT NULL,
                content BYTEA NOT NULL,
                sha256 TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_request_id_new "
            f"ON {_table('riwayat_surat', True)}(request_id) WHERE request_id IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_nomor_new "
            f"ON {_table('riwayat_surat', True)}(nomor_surat) "
            "WHERE request_id IS NOT NULL AND nomor_surat IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_riwayat_status_updated "
            f"ON {_table('riwayat_surat', True)}(status, updated_at DESC)"
        )
        for table_name in ("riwayat_surat", "nomor_counter", "master_data", "custom_templates"):
            table = _table(table_name, True)
            conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"REVOKE ALL ON TABLE {table} FROM anon, authenticated, service_role")
        conn.execute(
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {POSTGRES_SCHEMA} "
            "FROM anon, authenticated, service_role"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_postgres_runtime(database_url: str) -> None:
    """Pastikan schema runtime siap tanpa menjalankan DDL saat cold start."""

    if not _is_postgres(database_url):
        raise ValueError("Verifikasi runtime PostgreSQL memerlukan DATABASE_URL PostgreSQL")
    conn = _connect_db(database_url)
    try:
        # SELECT tanpa baris memverifikasi keberadaan tabel, kolom penting, schema
        # usage, dan privilege runtime. DDL tetap menjadi tanggung jawab migrasi.
        conn.execute(
            f"SELECT kind, payload FROM {_table('master_data', True)} LIMIT 0"
        ).fetchall()
        conn.execute(
            f"SELECT kode, tahun, last_seq FROM {_table('nomor_counter', True)} LIMIT 0"
        ).fetchall()
        conn.execute(
            f"SELECT id, request_id, nomor_surat, status "
            f"FROM {_table('riwayat_surat', True)} LIMIT 0"
        ).fetchall()
        conn.execute(
            f"SELECT key, fields_json, content FROM {_table('custom_templates', True)} LIMIT 0"
        ).fetchall()
    finally:
        conn.close()


def load_master_records(database_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    conn = _connect_db(database_url)
    try:
        rows = conn.execute(
            f"SELECT kind, payload FROM {_table('master_data', True)}"
        ).fetchall()
    finally:
        conn.close()
    values = {row["kind"]: row["payload"] for row in rows}
    missing = {"guru", "murid", "kode_arsip"} - set(values)
    if missing:
        raise RuntimeError(f"Data master PostgreSQL belum lengkap: {', '.join(sorted(missing))}")
    return values["guru"], values["murid"], values["kode_arsip"]


def load_custom_templates(database: Path | str) -> dict[str, dict[str, Any]]:
    postgres = _is_postgres(database)
    table = _table("custom_templates", postgres)
    conn = _connect_db(database)
    try:
        rows = conn.execute(
            f"SELECT key, label, description, category, default_code, signer, fields_json, "
            f"filename, content, sha256 FROM {table} WHERE active = " + ("TRUE" if postgres else "1")
        ).fetchall()
    finally:
        conn.close()
    templates: dict[str, dict[str, Any]] = {}
    for row in rows:
        fields = row["fields_json"]
        if isinstance(fields, str):
            fields = json.loads(fields)
        templates[str(row["key"])] = {
            "label": str(row["label"]),
            "deskripsi": str(row["description"]),
            "kategori": str(row["category"]),
            "icon": "fa-file-word",
            "badge": "Template Admin",
            "template": str(row["filename"]),
            "default_kode": str(row["default_code"]),
            "signer": str(row["signer"]),
            "fields": list(fields),
            "template_blob": bytes(row["content"]),
            "template_hash": str(row["sha256"]),
            "is_custom": True,
        }
    return templates


def save_custom_template(database: Path | str, template: Mapping[str, Any]) -> None:
    postgres = _is_postgres(database)
    table = _table("custom_templates", postgres)
    actor, actor_role = _current_actor()
    if actor_role != "admin":
        raise RequestValidationError("Akses admin diperlukan", {"role": "admin diperlukan"}, 403)
    now_iso = _now().isoformat(timespec="seconds")
    content = bytes(template["template_blob"])
    digest = hashlib.sha256(content).hexdigest()
    fields_json = json.dumps(template["fields"], ensure_ascii=False, separators=(",", ":"))
    values = (
        template["key"], template["label"], template["deskripsi"], template["kategori"],
        template["default_kode"], template["signer"], fields_json, template["template"],
        content, digest, now_iso, now_iso, actor,
    )
    placeholder = "?::jsonb" if postgres else "?"
    query = f"""
        INSERT INTO {table} (
            key, label, description, category, default_code, signer, fields_json,
            filename, content, sha256, active, created_at, updated_at, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, {placeholder}, ?, ?, ?, {'TRUE' if postgres else '1'}, ?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET
            label = EXCLUDED.label,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            default_code = EXCLUDED.default_code,
            signer = EXCLUDED.signer,
            fields_json = EXCLUDED.fields_json,
            filename = EXCLUDED.filename,
            content = EXCLUDED.content,
            sha256 = EXCLUDED.sha256,
            active = EXCLUDED.active,
            updated_at = EXCLUDED.updated_at,
            created_by = EXCLUDED.created_by
    """
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        conn.execute(_sql(query, postgres), values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_custom_template(database: Path | str, key: str) -> bool:
    actor_role = _current_actor()[1]
    if actor_role != "admin":
        raise RequestValidationError("Akses admin diperlukan", {"role": "admin diperlukan"}, 403)
    postgres = _is_postgres(database)
    table = _table("custom_templates", postgres)
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        cursor = conn.execute(_sql(f"DELETE FROM {table} WHERE key = ?", postgres), (key,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _payload_hash(normalized: Mapping[str, Any]) -> str:
    material = {key: value for key, value in normalized.items() if key != "request_id"}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reserve_letter(validated: Mapping[str, Any]) -> dict[str, Any]:
    db_path = current_app.config["DATABASE"]
    postgres = _is_postgres(db_path)
    history_table = _table("riwayat_surat", postgres)
    counter_table = _table("nomor_counter", postgres)
    normalized = validated["normalized"]
    info = validated["info"]
    person = validated["person"]
    people = validated.get("people") or [person]
    request_id = str(normalized["request_id"])
    payload_hash = _payload_hash(normalized)
    now_iso = _now().isoformat(timespec="seconds")
    custom_number = str(normalized["nomor_surat_custom"])
    kode = str(normalized["kode_arsip"])
    year = _parse_iso_date(str(normalized["tanggal_surat"])).year
    template_hash = current_app.extensions["template_hashes"][validated["jenis"]]
    actor, actor_role = _current_actor()

    conn = _connect_db(db_path)
    try:
        _begin_write(conn, postgres)
        existing = conn.execute(
            _sql(f"SELECT * FROM {history_table} WHERE request_id = ?", postgres),
            (request_id,),
        ).fetchone()
        if existing is not None:
            if existing["payload_hash"] != payload_hash:
                raise RequestValidationError(
                    "request_id sudah dipakai untuk payload berbeda",
                    {"request_id": "gunakan request_id baru setelah mengubah form"},
                    409,
                )
            status = existing["status"] or "legacy"
            if status == "rendering":
                updated_raw = existing["updated_at"] or existing["created_at"] or ""
                try:
                    updated_at = (
                        updated_raw
                        if isinstance(updated_raw, datetime)
                        else datetime.fromisoformat(str(updated_raw))
                    )
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=WIB)
                except (TypeError, ValueError):
                    updated_at = _now()
                if _now() - updated_at.astimezone(WIB) < timedelta(minutes=10):
                    raise RequestValidationError(
                        "Permintaan yang sama masih sedang diproses",
                        {"request_id": "sedang diproses"},
                        409,
                    )
                conn.execute(
                    _sql(
                        f"UPDATE {history_table} SET error = NULL, updated_at = ? WHERE id = ?",
                        postgres,
                    ),
                    (now_iso, existing["id"]),
                )
                action = "retry"
            elif status == "failed":
                conn.execute(
                    _sql(
                        f"UPDATE {history_table} SET status = 'rendering', "
                        "error = NULL, updated_at = ? WHERE id = ?",
                        postgres,
                    ),
                    (now_iso, existing["id"]),
                )
                action = "retry"
            elif status == "generated":
                action = "generated"
            else:
                raise RequestValidationError(
                    "Status idempotensi tidak dapat diproses", {"request_id": "status tidak valid"}, 409
                )
            conn.commit()
            return {
                "id": existing["id"],
                "number": existing["nomor_surat"],
                "request_id": request_id,
                "payload_hash": payload_hash,
                "action": action,
            }

        if custom_number:
            duplicate = conn.execute(
                _sql(
                    f"SELECT request_id FROM {history_table} WHERE nomor_surat = ? LIMIT 1",
                    postgres,
                ),
                (custom_number,),
            ).fetchone()
            if duplicate is not None:
                raise RequestValidationError(
                    "Nomor surat sudah digunakan",
                    {"nomor_surat_custom": "nomor harus unik"},
                    409,
                )
            number = custom_number
        else:
            number = ""
            for _ in range(100):
                if postgres:
                    counter = conn.execute(
                        f"""
                        INSERT INTO {counter_table} AS counter
                            (kode, tahun, last_seq, updated_at)
                        VALUES (%s, %s, 1, %s)
                        ON CONFLICT (kode, tahun) DO UPDATE
                        SET last_seq = counter.last_seq + 1,
                            updated_at = EXCLUDED.updated_at
                        RETURNING last_seq
                        """,
                        (kode, year, now_iso),
                    ).fetchone()
                    sequence = int(counter["last_seq"])
                else:
                    counter = conn.execute(
                        "SELECT last_seq FROM nomor_counter WHERE kode = ? AND tahun = ?",
                        (kode, year),
                    ).fetchone()
                    sequence = int(counter["last_seq"]) + 1 if counter else 1
                    if counter:
                        conn.execute(
                            "UPDATE nomor_counter SET last_seq = ?, updated_at = ? "
                            "WHERE kode = ? AND tahun = ?",
                            (sequence, now_iso, kode, year),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO nomor_counter(kode, tahun, last_seq, updated_at) "
                            "VALUES (?, ?, ?, ?)",
                            (kode, year, sequence, now_iso),
                        )
                candidate = (
                    f"{kode}/{sequence:03d}/{current_app.config['NUMBER_SUFFIX']}/{year}"
                )
                duplicate = conn.execute(
                    _sql(
                        f"SELECT 1 FROM {history_table} WHERE nomor_surat = ? LIMIT 1",
                        postgres,
                    ),
                    (candidate,),
                ).fetchone()
                if duplicate is None:
                    number = candidate
                    break
            if not number:
                raise RuntimeError("Tidak dapat mengalokasikan nomor surat unik")

        person_id = ", ".join(
            item.get("nip") or item.get("nis") or "" for item in people
        )
        person_name = ", ".join(item.get("nama", "") for item in people)
        insert_sql = f"""
            INSERT INTO {history_table} (
                created_at, updated_at, jenis_surat, jenis_key, template, hash,
                nomor_surat, nama_pemohon, id_pemohon, kategori, keperluan,
                request_id, status, payload_hash, error, created_by, created_by_role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rendering', ?, NULL, ?, ?)
            """ + (" RETURNING id" if postgres else "")
        cursor = conn.execute(
            _sql(insert_sql, postgres),
            (
                now_iso,
                now_iso,
                info["label"],
                validated["jenis"],
                info["template"],
                template_hash,
                number,
                person_name,
                person_id,
                info["kategori"],
                validated["context"].get("keperluan", "-"),
                request_id,
                payload_hash,
                actor,
                actor_role,
            ),
        )
        record_id = cursor.fetchone()["id"] if postgres else cursor.lastrowid
        conn.commit()
        return {
            "id": record_id,
            "number": number,
            "request_id": request_id,
            "payload_hash": payload_hash,
            "action": "new",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _mark_letter_status(record_id: int, status: str, error: str | None = None) -> None:
    if status not in {"generated", "failed"}:
        raise ValueError("status final tidak valid")
    database = current_app.config["DATABASE"]
    postgres = _is_postgres(database)
    history_table = _table("riwayat_surat", postgres)
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        conn.execute(
            _sql(
                f"UPDATE {history_table} SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                postgres,
            ),
            (status, error[:1000] if error else None, _now().isoformat(timespec="seconds"), record_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cancel_letter(record_id: int, reason: str) -> dict[str, Any]:
    actor, actor_role = _current_actor()
    if actor_role != "admin":
        raise RequestValidationError(
            "Hanya admin yang dapat membatalkan surat",
            {"role": "otorisasi tidak mencukupi"},
            403,
        )

    database = current_app.config["DATABASE"]
    postgres = _is_postgres(database)
    history_table = _table("riwayat_surat", postgres)
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        row = conn.execute(
            _sql(f"SELECT * FROM {history_table} WHERE id = ?", postgres),
            (record_id,),
        ).fetchone()
        if row is None:
            raise RequestValidationError(
                "Riwayat surat tidak ditemukan", {"id": "tidak ditemukan"}, 404
            )
        status = str(row["status"] or "legacy")
        if status == "cancelled":
            conn.commit()
            return dict(row)
        if status not in {"generated", "failed"}:
            raise RequestValidationError(
                "Surat dengan status ini tidak dapat dibatalkan",
                {"status": status},
                409,
            )
        cancelled_at = _now().isoformat(timespec="seconds")
        conn.execute(
            _sql(f"""
            UPDATE {history_table}
            SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?,
                cancel_reason = ?, updated_at = ?
            WHERE id = ?
            """, postgres),
            (cancelled_at, actor, reason, cancelled_at, record_id),
        )
        conn.commit()
        updated = conn.execute(
            _sql(f"SELECT * FROM {history_table} WHERE id = ?", postgres),
            (record_id,),
        ).fetchone()
        return dict(updated) if updated is not None else {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
