from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import esurat
from esurat import database as database_module
from scripts.backup_data import create_backup
from scripts.migrate_sqlite_to_postgres import _counter_seeds, _timestamp
from scripts.provision_vercel import _pooler_url
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
                connection.execute("PRAGMA journal_mode=WAL")
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
            self.assertEqual(verify_backup(destination), manifest)
            self.assertFalse((destination / "history.sqlite3-wal").exists())
            self.assertFalse((destination / "history.sqlite3-shm").exists())

            snapshot_path = (destination / "history.sqlite3").as_uri()
            snapshot = sqlite3.connect(
                f"{snapshot_path}?mode=ro&immutable=1",
                uri=True,
            )
            try:
                value = snapshot.execute("SELECT value FROM sample").fetchone()[0]
            finally:
                snapshot.close()
            self.assertEqual(value, "aman")

            (destination / "guru.json").write_text("diubah\n", encoding="utf-8")
            with self.assertRaisesRegex(BackupVerificationError, "Ukuran file berubah"):
                verify_backup(destination)


class DatabaseMigrationTests(unittest.TestCase):
    def test_pooler_url_encodes_credentials_and_requires_ssl(self) -> None:
        url = _pooler_url(
            "abcdefghijklmnopqrst",
            "ap-southeast-1",
            "esurat_runtime",
            "rahasia:/?& dengan-spasi",
        )
        self.assertEqual(
            url,
            "postgresql://esurat_runtime.abcdefghijklmnopqrst:"
            "rahasia%3A%2F%3F%26%20dengan-spasi@"
            "aws-0-ap-southeast-1.pooler.supabase.com:6543/"
            "postgres?sslmode=require",
        )

    def test_postgres_schema_is_private_and_rls_enabled(self) -> None:
        connection = MagicMock()
        with patch.object(database_module, "_connect_db", return_value=connection):
            database_module._init_postgres("postgresql://example.invalid/database")
        statements = "\n".join(
            str(call.args[0]) for call in connection.execute.call_args_list
        ).casefold()
        self.assertIn("create schema if not exists esurat", statements)
        self.assertIn("create table if not exists esurat.master_data", statements)
        self.assertIn("alter table esurat.riwayat_surat enable row level security", statements)
        self.assertIn("revoke all on table esurat.master_data", statements)
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_postgres_connection_disables_named_prepared_statements(self) -> None:
        sentinel = object()
        with patch.object(database_module.psycopg, "connect", return_value=sentinel) as connect:
            result = database_module._connect_db("postgresql://example.invalid/database")
        self.assertIs(result, sentinel)
        self.assertIsNone(connect.call_args.kwargs["prepare_threshold"])
        self.assertEqual(connect.call_args.kwargs["connect_timeout"], 10)

    def test_postgres_runtime_verification_is_read_only(self) -> None:
        connection = MagicMock()
        with patch.object(database_module, "_connect_db", return_value=connection):
            database_module.verify_postgres_runtime(
                "postgresql://example.invalid/database"
            )
        statements = [
            str(call.args[0]).strip().casefold()
            for call in connection.execute.call_args_list
        ]
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(statement.startswith("select ") for statement in statements))
        self.assertTrue(all("esurat." in statement for statement in statements))
        connection.commit.assert_not_called()
        connection.close.assert_called_once_with()

    def test_postgres_seed_preserves_highest_legacy_number(self) -> None:
        seeds = _counter_seeds(
            [
                {"nomor_surat": "800/045/SMADA/2026"},
                {"nomor_surat": "800/012/SMADA/2026"},
                {"nomor_surat": "00.1.2.3/0822/SMADA/2026"},
                {"nomor_surat": "format-manual"},
            ],
            [{"kode": "421", "tahun": 2026, "last_seq": 88}],
            "SMADA",
        )
        self.assertEqual(seeds[("800", 2026)], 45)
        self.assertEqual(seeds[("00.1.2.3", 2026)], 822)
        self.assertEqual(seeds[("421", 2026)], 88)

    def test_legacy_timestamp_is_converted_to_wib(self) -> None:
        parsed = _timestamp("22-08-2026 13:10")
        self.assertEqual(parsed.isoformat(), "2026-08-22T13:10:00+07:00")

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
