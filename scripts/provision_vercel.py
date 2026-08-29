"""Konfigurasi Supabase/Vercel melalui prompt lokal tanpa mencetak secret."""

from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from esurat.database import verify_postgres_runtime

RUNTIME_ROLE = "esurat_runtime"


def _pooler_url(project_ref: str, region: str, username: str, password: str) -> str:
    encoded_user = quote(f"{username}.{project_ref}", safe="")
    encoded_password = quote(password, safe="")
    return (
        f"postgresql://{encoded_user}:{encoded_password}"
        f"@aws-0-{region}.pooler.supabase.com:6543/postgres?sslmode=require"
    )


def _set_vercel_env(name: str, value: str, *, sensitive: bool) -> None:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx tidak ditemukan; pasang Node.js/Vercel CLI terlebih dahulu")
    flag = "--sensitive" if sensitive else "--no-sensitive"
    completed = subprocess.run(
        [
            npx,
            "--yes",
            "vercel@latest",
            "env",
            "add",
            name,
            "production",
            "--force",
            "--yes",
            flag,
        ],
        cwd=BASE_DIR,
        input=f"{value}\n",
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Gagal menyimpan {name} ke Vercel")


def _prompt_confirmed_password(label: str) -> str:
    password = getpass(f"{label} (minimal 12 karakter): ")
    if len(password) < 12:
        raise ValueError(f"{label} harus minimal 12 karakter")
    if password != getpass(f"Ulangi {label.lower()}: "):
        raise ValueError(f"Konfirmasi {label.lower()} tidak sama")
    return password


def _activate_runtime_role(admin_url: str, runtime_password: str) -> None:
    with psycopg.connect(admin_url, prepare_threshold=None, connect_timeout=15) as conn:
        role_exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (RUNTIME_ROLE,)
        ).fetchone()
        if role_exists is None:
            raise RuntimeError(
                "Role esurat_runtime belum ada; jalankan migrasi runtime role terlebih dahulu"
            )
        conn.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(RUNTIME_ROLE), sql.Literal(runtime_password)
            )
        )


def _verify_runtime_write(runtime_url: str) -> None:
    verify_postgres_runtime(runtime_url)
    conn = psycopg.connect(runtime_url, prepare_threshold=None, connect_timeout=15)
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO esurat.nomor_counter(kode, tahun, last_seq, updated_at)
            VALUES ('999.999.999', 2200, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (kode, tahun) DO UPDATE
            SET last_seq = esurat.nomor_counter.last_seq + 1,
                updated_at = EXCLUDED.updated_at
            """
        )
        conn.rollback()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision role Supabase dan secret production Vercel E-Surat."
    )
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--username", default="admin-tu")
    args = parser.parse_args()

    print("Secret hanya dibaca dari prompt ini dan tidak disimpan ke file atau output.")
    database_password = getpass("Password database Supabase: ")
    if not database_password:
        raise ValueError("Password database Supabase wajib diisi")
    app_password = _prompt_confirmed_password("Password login admin E-Surat")

    admin_url = _pooler_url(args.project_ref, args.region, "postgres", database_password)
    runtime_password = secrets.token_urlsafe(48)
    runtime_url = _pooler_url(
        args.project_ref, args.region, RUNTIME_ROLE, runtime_password
    )

    print("Mengaktifkan role database runtime...")
    _activate_runtime_role(admin_url, runtime_password)
    _verify_runtime_write(runtime_url)

    print("Menyimpan konfigurasi production ke Vercel...")
    settings = {
        "DATABASE_URL": (runtime_url, True),
        "ESURAT_SECRET_KEY": (secrets.token_urlsafe(48), True),
        "ESURAT_USERNAME": (args.username, False),
        "ESURAT_PASSWORD_HASH": (generate_password_hash(app_password), True),
        "ESURAT_DEFAULT_ROLE": ("admin", False),
        "ESURAT_HTTPS": ("1", False),
        "ESURAT_NUMBER_SUFFIX": ("SMADA", False),
        "ESURAT_AUTO_MIGRATE_DATABASE": ("0", False),
    }
    for name, (value, sensitive) in settings.items():
        _set_vercel_env(name, value, sensitive=sensitive)

    print("\nBerhasil: role runtime dan environment production Vercel sudah siap.")
    print(f"Username login: {args.username}")
    print("Password login adalah password admin yang baru Anda masukkan.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, psycopg.Error) as exc:
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
