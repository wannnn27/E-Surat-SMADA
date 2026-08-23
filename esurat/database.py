"""Migrasi SQLite, reservasi nomor, idempotensi, dan riwayat surat."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from flask import current_app

from .config import DB_PATH, WIB
from .errors import RequestValidationError
from .utils import _now, _parse_iso_date


def _connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Migrasi SQLite secara additive; record lama tidak diubah atau dihapus."""

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
                updated_at TEXT
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
        }
        for column, column_type in additions.items():
            if column not in existing:
                conn.execute(f'ALTER TABLE riwayat_surat ADD COLUMN "{column}" {column_type}')

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
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
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
    db_path = Path(current_app.config["DATABASE"])
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

    conn = _connect_db(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM riwayat_surat WHERE request_id = ?", (request_id,)
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
                    "UPDATE riwayat_surat SET error = NULL, updated_at = ? WHERE id = ?",
                    (now_iso, existing["id"]),
                )
                action = "retry"
            elif status == "failed":
                conn.execute(
                    "UPDATE riwayat_surat SET status = 'rendering', error = NULL, updated_at = ? WHERE id = ?",
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
                "SELECT request_id FROM riwayat_surat WHERE nomor_surat = ? LIMIT 1", (custom_number,)
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
                    "SELECT last_seq FROM nomor_counter WHERE kode = ? AND tahun = ?", (kode, year)
                ).fetchone()
                sequence = int(counter["last_seq"]) + 1 if counter else 1
                if counter:
                    conn.execute(
                        "UPDATE nomor_counter SET last_seq = ?, updated_at = ? WHERE kode = ? AND tahun = ?",
                        (sequence, now_iso, kode, year),
                    )
                else:
                    conn.execute(
                        "INSERT INTO nomor_counter(kode, tahun, last_seq, updated_at) VALUES (?, ?, ?, ?)",
                        (kode, year, sequence, now_iso),
                    )
                candidate = (
                    f"{kode}/{sequence:03d}/{current_app.config['NUMBER_SUFFIX']}/{year}"
                )
                duplicate = conn.execute(
                    "SELECT 1 FROM riwayat_surat WHERE nomor_surat = ? LIMIT 1", (candidate,)
                ).fetchone()
                if duplicate is None:
                    number = candidate
                    break
            if not number:
                raise RuntimeError("Tidak dapat mengalokasikan nomor surat unik")

        person_id = person.get("nip") or person.get("nis") or ""
        cursor = conn.execute(
            """
            INSERT INTO riwayat_surat (
                created_at, updated_at, jenis_surat, jenis_key, template, hash,
                nomor_surat, nama_pemohon, id_pemohon, kategori, keperluan,
                request_id, status, payload_hash, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rendering', ?, NULL)
            """,
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
            ),
        )
        record_id = cursor.lastrowid
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
    conn = _connect_db(Path(current_app.config["DATABASE"]))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE riwayat_surat SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error[:1000] if error else None, _now().isoformat(timespec="seconds"), record_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
