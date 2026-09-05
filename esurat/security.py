"""Helper autentikasi, CSRF, dan pembatasan akses lokal."""

from __future__ import annotations

import hmac
import ipaddress
import json
import re
import secrets
from pathlib import Path
from typing import Any, Mapping

from flask import session
from werkzeug.security import check_password_hash

from .errors import DataValidationError
from .utils import _normalize_text


AUTH_ROLES = {"admin"}
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")


def _is_loopback_address(address: str | None) -> bool:
    if not address:
        return False
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return address.casefold() == "localhost"
    if parsed.is_loopback:
        return True
    return bool(getattr(parsed, "ipv4_mapped", None) and parsed.ipv4_mapped.is_loopback)


def _is_loopback_bind(host: str) -> bool:
    return host.casefold() == "localhost" or _is_loopback_address(host)


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def _load_auth_users(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Muat akun bernama dari file privat, atau satu akun environment legacy."""

    users_file = str(config.get("AUTH_USERS_FILE") or "").strip()
    legacy_username = _normalize_text(config.get("AUTH_USERNAME", ""))
    legacy_password = str(config.get("AUTH_PASSWORD") or "")
    legacy_hash = str(config.get("AUTH_PASSWORD_HASH") or "")
    has_legacy_password = bool(legacy_password or legacy_hash)

    if bool(legacy_username) != has_legacy_password:
        raise DataValidationError("Konfigurasi autentikasi harus berisi username dan password/hash")
    if legacy_username and not USERNAME_RE.fullmatch(legacy_username):
        raise DataValidationError("Username environment harus 3-80 karakter aman")
    if legacy_password and not config.get("TESTING"):
        raise DataValidationError(
            "ESURAT_PASSWORD plaintext tidak didukung; gunakan ESURAT_PASSWORD_HASH"
        )
    if users_file and (legacy_username or has_legacy_password):
        raise DataValidationError(
            "Gunakan ESURAT_USERS_FILE atau kredensial tunggal environment, bukan keduanya"
        )

    users: dict[str, dict[str, str]] = {}
    if users_file:
        path = Path(users_file).expanduser()
        try:
            raw_users = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DataValidationError(f"File akun tidak ditemukan: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise DataValidationError(f"File akun tidak dapat dibaca: {path}") from exc
        if not isinstance(raw_users, list) or not raw_users:
            raise DataValidationError("File akun harus berupa array JSON yang tidak kosong")

        for position, raw in enumerate(raw_users, start=1):
            if not isinstance(raw, dict):
                raise DataValidationError(f"Akun record {position} harus berupa object JSON")
            username = _normalize_text(raw.get("username", ""))
            password_hash = str(raw.get("password_hash") or "").strip()
            role = _normalize_text(raw.get("role", "admin")).casefold()
            active = raw.get("active", True)
            if not USERNAME_RE.fullmatch(username):
                raise DataValidationError(
                    f"Akun record {position}: username harus 3-80 karakter aman"
                )
            if not password_hash:
                raise DataValidationError(f"Akun {username}: password_hash wajib diisi")
            if role not in AUTH_ROLES:
                raise DataValidationError(
                    f"Akun {username}: role harus admin"
                )
            if not isinstance(active, bool):
                raise DataValidationError(f"Akun {username}: active harus boolean")
            key = username.casefold()
            if key in users:
                raise DataValidationError(f"Username duplikat: {username}")
            if active:
                users[key] = {
                    "username": username,
                    "password_hash": password_hash,
                    "password": "",
                    "role": role,
                }
        if not users:
            raise DataValidationError("File akun harus memiliki setidaknya satu akun aktif")
    elif legacy_username:
        role = _normalize_text(config.get("AUTH_DEFAULT_ROLE", "admin")).casefold()
        if role not in AUTH_ROLES:
            raise DataValidationError("AUTH_DEFAULT_ROLE harus admin")
        users[legacy_username.casefold()] = {
            "username": legacy_username,
            "password_hash": legacy_hash,
            "password": legacy_password,
            "role": role,
        }
    return users


def _password_matches(user: Mapping[str, str], password: str) -> bool:
    password_hash = str(user.get("password_hash") or "")
    if password_hash:
        try:
            return check_password_hash(password_hash, password)
        except (ValueError, TypeError):
            return False
    configured = str(user.get("password") or "")
    return hmac.compare_digest(configured.encode("utf-8"), password.encode("utf-8"))


def _current_actor() -> tuple[str, str]:
    if session.get("authenticated") and session.get("role") == "admin":
        return str(session.get("username") or "admin"), "admin"
    return "public", "user"
