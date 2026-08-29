"""Migrasikan master dan riwayat SQLite ke PostgreSQL secara satu transaksi.

Script ini sengaja menolak target yang sudah berisi data agar migrasi ulang tidak
menimpa record produksi. Nilai ``DATABASE_URL`` harus disediakan sebagai secret
environment dan tidak pernah ditulis ke file atau output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from psycopg.types.json import Jsonb

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from esurat.config import DB_PATH, WIB
from esurat.database import _connect_db, _table, init_db
from esurat.master_data import validate_master_data


DEFAULT_MASTER_DIR = BASE_DIR / "data" / "master"
HISTORY_COLUMNS = (
    "id",
    "created_at",
    "jenis_surat",
    "nomor_surat",
    "nama_pemohon",
    "id_pemohon",
    "kategori",
    "keperluan",
    "request_id",
    "status",
    "jenis_key",
    "template",
    "hash",
    "payload_hash",
    "error",
    "updated_at",
    "created_by",
    "created_by_role",
    "cancelled_at",
    "cancelled_by",
    "cancel_reason",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=DB_PATH,
        help="Database SQLite sumber (default mengikuti ESURAT_DB_PATH)",
    )
    parser.add_argument(
        "--master-dir",
        type=Path,
        default=DEFAULT_MASTER_DIR,
        help="Folder guru.json, murid.json, dan kode_arsip.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validasi sumber dan tampilkan agregat tanpa menyentuh PostgreSQL",
    )
    return parser.parse_args(argv)


def _read_json_list(directory: Path, name: str) -> list[dict[str, Any]]:
    path = directory / f"{name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path} harus berupa array object JSON")
    return value


def _timestamp(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        parsed = None
        if text:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                for pattern in (
                    "%d-%m-%Y %H:%M:%S",
                    "%d-%m-%Y %H:%M",
                    "%d/%m/%Y %H:%M:%S",
                    "%d/%m/%Y %H:%M",
                ):
                    try:
                        parsed = datetime.strptime(text, pattern)
                        break
                    except ValueError:
                        continue
        if parsed is None:
            if fallback is None:
                raise ValueError(f"Timestamp legacy tidak dapat dibaca: {text!r}")
            parsed = fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=WIB)
    return parsed.astimezone(WIB)


def _load_history(database_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = database_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Database SQLite tidak ditemukan: {source}")
    conn = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "riwayat_surat" not in tables:
            raise ValueError("SQLite tidak memiliki tabel riwayat_surat")
        history = [dict(row) for row in conn.execute("SELECT * FROM riwayat_surat ORDER BY id")]
        counters = (
            [dict(row) for row in conn.execute("SELECT * FROM nomor_counter")]
            if "nomor_counter" in tables
            else []
        )
        return history, counters
    finally:
        conn.close()


def _normalize_history(row: dict[str, Any]) -> tuple[Any, ...]:
    created_at = _timestamp(row.get("created_at"))
    updated_at = _timestamp(row.get("updated_at"), created_at)
    cancelled_at = (
        _timestamp(row.get("cancelled_at"), updated_at)
        if row.get("cancelled_at")
        else None
    )
    values = {
        **row,
        "created_at": created_at,
        "updated_at": updated_at,
        "cancelled_at": cancelled_at,
        "status": str(row.get("status") or "generated"),
        "created_by": str(row.get("created_by") or "legacy"),
        "created_by_role": str(row.get("created_by_role") or "unknown"),
    }
    return tuple(values.get(column) for column in HISTORY_COLUMNS)


def _counter_seeds(
    history: Iterable[dict[str, Any]],
    stored_counters: Iterable[dict[str, Any]],
    suffix: str,
) -> dict[tuple[str, int], int]:
    seeds: dict[tuple[str, int], int] = {}
    pattern = re.compile(
        rf"^(?P<kode>.+)/(?P<seq>\d+)/{re.escape(suffix)}/(?P<tahun>\d{{4}})$"
    )
    for row in history:
        match = pattern.fullmatch(str(row.get("nomor_surat") or "").strip())
        if not match:
            continue
        key = (match.group("kode"), int(match.group("tahun")))
        seeds[key] = max(seeds.get(key, 0), int(match.group("seq")))
    for row in stored_counters:
        key = (str(row["kode"]), int(row["tahun"]))
        seeds[key] = max(seeds.get(key, 0), int(row["last_seq"]))
    return seeds


def migrate(
    database_url: str,
    *,
    master_dir: Path,
    sqlite_path: Path,
    dry_run: bool = False,
) -> dict[str, int]:
    guru = _read_json_list(master_dir, "guru")
    murid = _read_json_list(master_dir, "murid")
    kode = _read_json_list(master_dir, "kode_arsip")
    validate_master_data(guru, murid, kode, os.getenv("ESURAT_KEPSEK_NIP", ""))
    history, stored_counters = _load_history(sqlite_path)
    normalized_history = [_normalize_history(row) for row in history]
    seeds = _counter_seeds(
        history,
        stored_counters,
        os.getenv("ESURAT_NUMBER_SUFFIX", "SMADA"),
    )
    summary = {
        "guru": len(guru),
        "murid": len(murid),
        "kode_arsip": len(kode),
        "riwayat_surat": len(history),
        "nomor_counter": len(seeds),
    }
    if dry_run:
        return summary

    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL PostgreSQL wajib diatur")

    init_db(database_url)
    conn = _connect_db(database_url)
    master_table = _table("master_data", True)
    history_table = _table("riwayat_surat", True)
    counter_table = _table("nomor_counter", True)
    try:
        target_counts = {
            "master_data": conn.execute(f"SELECT COUNT(*) AS count FROM {master_table}").fetchone()[
                "count"
            ],
            "riwayat_surat": conn.execute(
                f"SELECT COUNT(*) AS count FROM {history_table}"
            ).fetchone()["count"],
            "nomor_counter": conn.execute(
                f"SELECT COUNT(*) AS count FROM {counter_table}"
            ).fetchone()["count"],
        }
        occupied = {name: count for name, count in target_counts.items() if count}
        if occupied:
            raise RuntimeError(
                "Target PostgreSQL tidak kosong; migrasi dibatalkan agar data tidak tertimpa: "
                + ", ".join(f"{name}={count}" for name, count in occupied.items())
            )

        with conn.cursor() as cursor:
            cursor.executemany(
                f"""
                INSERT INTO {master_table}(kind, payload, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                """,
                [
                    ("guru", Jsonb(guru)),
                    ("murid", Jsonb(murid)),
                    ("kode_arsip", Jsonb(kode)),
                ],
            )
            if normalized_history:
                placeholders = ", ".join(["%s"] * len(HISTORY_COLUMNS))
                cursor.executemany(
                    f"""
                    INSERT INTO {history_table} ({', '.join(HISTORY_COLUMNS)})
                    VALUES ({placeholders})
                    """,
                    normalized_history,
                )
            if seeds:
                cursor.executemany(
                    f"""
                    INSERT INTO {counter_table}(kode, tahun, last_seq, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    [(kode_value, tahun, sequence) for (kode_value, tahun), sequence in seeds.items()],
                )

        if normalized_history:
            max_id = max(int(row[0]) for row in normalized_history)
            conn.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)",
                (history_table, max_id),
            )

        actual = {
            "master_data": int(
                conn.execute(f"SELECT COUNT(*) AS count FROM {master_table}").fetchone()["count"]
            ),
            "riwayat_surat": int(
                conn.execute(f"SELECT COUNT(*) AS count FROM {history_table}").fetchone()["count"]
            ),
            "nomor_counter": int(
                conn.execute(f"SELECT COUNT(*) AS count FROM {counter_table}").fetchone()["count"]
            ),
        }
        if actual != {
            "master_data": 3,
            "riwayat_surat": summary["riwayat_surat"],
            "nomor_counter": summary["nomor_counter"],
        }:
            raise RuntimeError(f"Verifikasi jumlah target gagal: {actual}")
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.getenv("DATABASE_URL", "").strip()
    summary = migrate(
        database_url,
        master_dir=args.master_dir.expanduser().resolve(),
        sqlite_path=args.sqlite.expanduser().resolve(),
        dry_run=args.dry_run,
    )
    mode = "Dry-run valid" if args.dry_run else "Migrasi selesai"
    print(
        f"[OK] {mode}: {summary['guru']} guru, {summary['murid']} murid, "
        f"{summary['kode_arsip']} kode, {summary['riwayat_surat']} riwayat, "
        f"{summary['nomor_counter']} counter"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
