"""Unggah tiga JSON master privat ke PostgreSQL tanpa memasukkannya ke Git."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from esurat.config import DATA_DIR
from esurat.database import _connect_db, _table, init_db
from esurat.master_data import validate_master_data


def _read(name: str) -> list[dict[str, object]]:
    path = Path(DATA_DIR) / f"{name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path} harus berisi array JSON")
    return value


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("DATABASE_URL PostgreSQL wajib diatur")

    guru = _read("guru")
    murid = _read("murid")
    kode = _read("kode_arsip")
    validate_master_data(guru, murid, kode, os.getenv("ESURAT_KEPSEK_NIP", ""))
    init_db(database_url)

    conn = _connect_db(database_url)
    try:
        for kind, payload in (("guru", guru), ("murid", murid), ("kode_arsip", kode)):
            conn.execute(
                f"""
                INSERT INTO {_table('master_data', True)}(kind, payload, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (kind) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = CURRENT_TIMESTAMP
                """,
                (kind, Jsonb(payload)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Master PostgreSQL diperbarui: {len(guru)} guru, {len(murid)} murid, {len(kode)} kode")


if __name__ == "__main__":
    main()
