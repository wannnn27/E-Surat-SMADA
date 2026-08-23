"""Helper autentikasi, CSRF, dan pembatasan akses lokal."""

from __future__ import annotations

import hmac
import ipaddress
import secrets

from flask import current_app, session
from werkzeug.security import check_password_hash


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


def _password_matches(password: str) -> bool:
    password_hash = str(current_app.config.get("AUTH_PASSWORD_HASH") or "")
    if password_hash:
        try:
            return check_password_hash(password_hash, password)
        except (ValueError, TypeError):
            return False
    configured = str(current_app.config.get("AUTH_PASSWORD") or "")
    return hmac.compare_digest(configured.encode("utf-8"), password.encode("utf-8"))
