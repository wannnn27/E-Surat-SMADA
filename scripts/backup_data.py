"""Buat backup konsisten data operasional E-Surat tanpa menghentikan aplikasi."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("ESURAT_DATA_ROOT", str(BASE_DIR / "data"))).expanduser()
MASTER_DATA_DIR = Path(os.getenv("ESURAT_DATA_DIR", str(DATA_ROOT / "master"))).expanduser()
DATABASE_PATH = Path(
    os.getenv("ESURAT_DB_PATH", str(DATA_ROOT / "runtime" / "surat_smada.db"))
).expanduser()
SOURCE_DIR = Path(os.getenv("ESURAT_SOURCE_DIR", str(DATA_ROOT / "source"))).expanduser()
WIB = timezone(timedelta(hours=7), name="Asia/Jakarta")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR / "backups",
        help="Folder induk backup (default: ./backups)",
    )
    parser.add_argument(
        "--include-excel",
        action="store_true",
        help="Sertakan workbook master; default hanya JSON dan SQLite",
    )
    return parser.parse_args(argv)


def _normalize_now(value: datetime | None) -> datetime:
    current = value or datetime.now(WIB)
    if current.tzinfo is None:
        return current.replace(tzinfo=WIB)
    return current.astimezone(WIB)


def create_backup(
    output_dir: Path,
    *,
    include_excel: bool = False,
    data_dir: Path = DATA_ROOT,
    master_dir: Path | None = None,
    database_path: Path | None = None,
    excel_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Buat snapshot konsisten dan kembalikan direktori backup final."""

    operational_root = data_dir.expanduser().resolve()
    database_source = (
        database_path or operational_root / "runtime" / "surat_smada.db"
    ).resolve()
    master_source = (master_dir or operational_root / "master").resolve()
    json_sources = tuple(
        master_source / name for name in ("guru.json", "murid.json", "kode_arsip.json")
    )
    excel_source = (excel_dir or operational_root / "source").resolve()

    missing = [path for path in (database_source, *json_sources) if not path.is_file()]
    if include_excel and not excel_source.is_dir():
        missing.append(excel_source)
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Sumber backup tidak ditemukan: {names}")

    created_at = _normalize_now(now)
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    destination = output_dir.expanduser().resolve() / f"surat-smada-{timestamp}"
    destination.mkdir(parents=True, exist_ok=False)

    database_target = destination / database_source.name
    source = sqlite3.connect(f"{database_source.as_uri()}?mode=ro", uri=True)
    target = sqlite3.connect(database_target)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    for source_path in json_sources:
        shutil.copy2(source_path, destination / source_path.name)

    if include_excel:
        shutil.copytree(excel_source, destination / "source")

    files = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = {
        "layout_version": 1,
        "created_at": created_at.isoformat(timespec="seconds"),
        "restore_mapping": {
            "surat_smada.db": "$ESURAT_DB_PATH atau $ESURAT_DATA_ROOT/runtime/surat_smada.db",
            "guru.json": "$ESURAT_DATA_DIR atau $ESURAT_DATA_ROOT/master",
            "murid.json": "$ESURAT_DATA_DIR atau $ESURAT_DATA_ROOT/master",
            "kode_arsip.json": "$ESURAT_DATA_DIR atau $ESURAT_DATA_ROOT/master",
            "source/": "$ESURAT_SOURCE_DIR atau $ESURAT_DATA_ROOT/source",
        },
        "files": [
            {
                "path": path.relative_to(destination).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = create_backup(
        args.output_dir,
        include_excel=args.include_excel,
        master_dir=MASTER_DATA_DIR,
        database_path=DATABASE_PATH,
        excel_dir=SOURCE_DIR,
    )
    print(f"[OK] Backup dibuat: {destination}")
    print("[PENTING] Simpan salinan terenkripsi di media terpisah dan uji pemulihan berkala.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
