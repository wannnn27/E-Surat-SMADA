"""Buat hash password Werkzeug tanpa mengekspos plaintext di command history."""

from __future__ import annotations

from getpass import getpass

from werkzeug.security import generate_password_hash


def main() -> int:
    password = getpass("Password baru (minimal 12 karakter): ")
    if len(password) < 12:
        print("Password harus minimal 12 karakter.")
        return 1
    confirmation = getpass("Ulangi password: ")
    if password != confirmation:
        print("Konfirmasi password tidak sama.")
        return 1
    print("\nSalin nilai berikut ke ESURAT_PASSWORD_HASH:")
    print(generate_password_hash(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
