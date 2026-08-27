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


def _is_postgres(database: Path | str) -> bool:
    return str(database).startswith(("postgresql://", "postgres://"))


def _connect_db(db_path: Path | str):
    if _is_postgres(db_path):
        if psycopg is None:
            raise RuntimeError("Driver PostgreSQL psycopg belum terpasang")
        return psycopg.connect(str(db_path), row_factory=dict_row)
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
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_postgres(database_url: str) -> None:
    conn = _connect_db(database_url)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS riwayat_surat (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
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
            CREATE TABLE IF NOT EXISTS master_data (
                kind TEXT PRIMARY KEY CHECK (kind IN ('guru', 'murid', 'kode_arsip')),
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_request_id_new "
            "ON riwayat_surat(request_id) WHERE request_id IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_riwayat_nomor_new "
            "ON riwayat_surat(nomor_surat) WHERE request_id IS NOT NULL AND nomor_surat IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_riwayat_status_updated "
            "ON riwayat_surat(status, updated_at)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_master_records(database_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    conn = _connect_db(database_url)
    try:
        rows = conn.execute("SELECT kind, payload FROM master_data").fetchall()
    finally:
        conn.close()
    values = {row["kind"]: row["payload"] for row in rows}
    missing = {"guru", "murid", "kode_arsip"} - set(values)
    if missing:
        raise RuntimeError(f"Data master PostgreSQL belum lengkap: {', '.join(sorted(missing))}")
    return values["guru"], values["murid"], values["kode_arsip"]


def _payload_hash(normalized: Mapping[str, Any]) -> str:
    material = {key: value for key, value in normalized.items() if key != "request_id"}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reserve_letter(validated: Mapping[str, Any]) -> dict[str, Any]:
    db_path = current_app.config["DATABASE"]
    postgres = _is_postgres(db_path)
    normalized = validated["normalized"]
    info = validated["info"]
    person = validated["person"]
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
            _sql("SELECT * FROM riwayat_surat WHERE request_id = ?", postgres), (request_id,)
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
                    updated_at = datetime.fromisoformat(updated_raw)
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
                    _sql("UPDATE riwayat_surat SET error = NULL, updated_at = ? WHERE id = ?", postgres),
                    (now_iso, existing["id"]),
                )
                action = "retry"
            elif status == "failed":
                conn.execute(
                    _sql("UPDATE riwayat_surat SET status = 'rendering', error = NULL, updated_at = ? WHERE id = ?", postgres),
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
                _sql("SELECT request_id FROM riwayat_surat WHERE nomor_surat = ? LIMIT 1", postgres), (custom_number,)
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
                counter = conn.execute(
                    _sql("SELECT last_seq FROM nomor_counter WHERE kode = ? AND tahun = ?" + (" FOR UPDATE" if postgres else ""), postgres), (kode, year)
                ).fetchone()
                sequence = int(counter["last_seq"]) + 1 if counter else 1
                if counter:
                    conn.execute(
                        _sql("UPDATE nomor_counter SET last_seq = ?, updated_at = ? WHERE kode = ? AND tahun = ?", postgres),
                        (sequence, now_iso, kode, year),
                    )
                else:
                    conn.execute(
                        _sql("INSERT INTO nomor_counter(kode, tahun, last_seq, updated_at) VALUES (?, ?, ?, ?)", postgres),
                        (kode, year, sequence, now_iso),
                    )
                candidate = (
                    f"{kode}/{sequence:03d}/{current_app.config['NUMBER_SUFFIX']}/{year}"
                )
                duplicate = conn.execute(
                    _sql("SELECT 1 FROM riwayat_surat WHERE nomor_surat = ? LIMIT 1", postgres), (candidate,)
                ).fetchone()
                if duplicate is None:
                    number = candidate
                    break
            if not number:
                raise RuntimeError("Tidak dapat mengalokasikan nomor surat unik")

        person_id = person.get("nip") or person.get("nis") or ""
        insert_sql = """
            INSERT INTO riwayat_surat (
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
                person["nama"],
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
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        conn.execute(
            _sql("UPDATE riwayat_surat SET status = ?, error = ?, updated_at = ? WHERE id = ?", postgres),
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
    if actor_role not in {"admin", "reviewer"}:
        raise RequestValidationError(
            "Hanya admin atau reviewer yang dapat membatalkan surat",
            {"role": "otorisasi tidak mencukupi"},
            403,
        )

    database = current_app.config["DATABASE"]
    postgres = _is_postgres(database)
    conn = _connect_db(database)
    try:
        _begin_write(conn, postgres)
        row = conn.execute(_sql("SELECT * FROM riwayat_surat WHERE id = ?", postgres), (record_id,)).fetchone()
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
            _sql("""
            UPDATE riwayat_surat
            SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?,
                cancel_reason = ?, updated_at = ?
            WHERE id = ?
            """, postgres),
            (cancelled_at, actor, reason, cancelled_at, record_id),
        )
        conn.commit()
        updated = conn.execute(_sql("SELECT * FROM riwayat_surat WHERE id = ?", postgres), (record_id,)).fetchone()
        return dict(updated) if updated is not None else {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
