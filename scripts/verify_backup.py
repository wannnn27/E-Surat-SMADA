"""Verify an E-Surat backup manifest, file hashes, and SQLite integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class BackupVerificationError(RuntimeError):
    """Backup is incomplete, altered, unsafe, or internally inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    root = backup_dir.expanduser().resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise BackupVerificationError(f"Manifest tidak ditemukan: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupVerificationError(f"Manifest tidak dapat dibaca: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("layout_version") != 1:
        raise BackupVerificationError("Versi/layout manifest backup tidak didukung")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise BackupVerificationError("Manifest tidak memiliki daftar file")

    listed: set[str] = set()
    database_paths: list[Path] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise BackupVerificationError(f"Entry manifest #{position} bukan object")
        raw_path = str(entry.get("path") or "")
        relative = PurePosixPath(raw_path)
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            raise BackupVerificationError(f"Path manifest tidak aman: {raw_path!r}")
        normalized = relative.as_posix()
        if normalized in listed:
            raise BackupVerificationError(f"Path manifest duplikat: {normalized}")
        listed.add(normalized)
        path = (root / Path(*relative.parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise BackupVerificationError(f"Path keluar dari backup: {normalized}") from exc
        if not path.is_file():
            raise BackupVerificationError(f"File backup tidak ditemukan: {normalized}")
        if path.stat().st_size != entry.get("size"):
            raise BackupVerificationError(f"Ukuran file berubah: {normalized}")
        if sha256(path) != entry.get("sha256"):
            raise BackupVerificationError(f"SHA-256 tidak cocok: {normalized}")
        if path.suffix.casefold() in DATABASE_SUFFIXES:
            database_paths.append(path)

    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual != listed:
        missing = sorted(listed - actual)
        extra = sorted(actual - listed)
        raise BackupVerificationError(
            f"Daftar file tidak cocok; hilang={missing or '-'}, tambahan={extra or '-'}"
        )
    if not database_paths:
        raise BackupVerificationError("Backup tidak memiliki database SQLite")

    for database_path in database_paths:
        connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
        if not result or result[0] != "ok":
            raise BackupVerificationError(
                f"SQLite quick_check gagal untuk {database_path.name}: {result}"
            )
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir", type=Path, help="Direktori backup yang memiliki manifest.json")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = verify_backup(args.backup_dir)
    print(
        f"[OK] Backup valid: {len(manifest['files'])} file; "
        f"dibuat {manifest.get('created_at', '-')}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupVerificationError as exc:
        print(f"[GAGAL] {exc}")
        raise SystemExit(2)
