from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import esurat
from scripts.backup_data import create_backup
from scripts.verify_backup import BackupVerificationError, verify_backup


class BackupWorkflowTests(unittest.TestCase):
    def test_backup_and_verification_use_explicit_private_layout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="esurat-backup-tests-") as temp_dir:
            root = Path(temp_dir)
            private_root = root / "private"
            master_dir = private_root / "custom-master"
            master_dir.mkdir(parents=True)
            for name in ("guru.json", "murid.json", "kode_arsip.json"):
                (master_dir / name).write_text("[]\n", encoding="utf-8")

            database_path = private_root / "custom-runtime" / "history.sqlite3"
            database_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE sample(value TEXT)")
                connection.execute("INSERT INTO sample(value) VALUES ('aman')")
                connection.commit()
            finally:
                connection.close()

            destination = create_backup(
                root / "backups",
                data_dir=private_root,
                master_dir=master_dir,
                database_path=database_path,
                now=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc),
            )
            manifest = verify_backup(destination)
            self.assertEqual(len(manifest["files"]), 4)

            snapshot = sqlite3.connect(destination / "history.sqlite3")
            try:
                value = snapshot.execute("SELECT value FROM sample").fetchone()[0]
            finally:
                snapshot.close()
            self.assertEqual(value, "aman")

            (destination / "guru.json").write_text("diubah\n", encoding="utf-8")
            with self.assertRaisesRegex(BackupVerificationError, "Ukuran file berubah"):
                verify_backup(destination)


class DatabaseMigrationTests(unittest.TestCase):
    def test_legacy_history_is_backfilled_without_reusing_number(self) -> None:
        with tempfile.TemporaryDirectory(prefix="esurat-migration-tests-") as temp_dir:
            database = Path(temp_dir) / "legacy.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """
                    CREATE TABLE riwayat_surat (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT,
                        jenis_surat TEXT,
                        nomor_surat TEXT,
                        nama_pemohon TEXT,
                        id_pemohon TEXT,
                        kategori TEXT,
                        keperluan TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO riwayat_surat (
                        created_at, jenis_surat, nomor_surat, nama_pemohon,
                        id_pemohon, kategori, keperluan
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-08-20T08:00:00+07:00",
                        "Surat Lama",
                        "800/001/SMADA/2026",
                        "DATA LEGACY",
                        "123",
                        "guru",
                        "Migrasi",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            esurat.init_db(database)
            migrated = sqlite3.connect(database)
            migrated.row_factory = sqlite3.Row
            try:
                row = migrated.execute("SELECT * FROM riwayat_surat").fetchone()
                version = migrated.execute("PRAGMA user_version").fetchone()[0]
            finally:
                migrated.close()
            self.assertEqual(version, 3)
            self.assertEqual(row["nomor_surat"], "800/001/SMADA/2026")
            self.assertEqual(row["status"], "generated")
            self.assertEqual(row["created_by"], "legacy")
            self.assertEqual(row["created_by_role"], "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
