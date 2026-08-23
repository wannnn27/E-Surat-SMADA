"""Helper normalisasi teks dan tanggal."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any

from flask import current_app

from .config import BULAN_ID, DATE_RE, WIB


def _now() -> datetime:
    value = current_app.config["NOW_FUNC"]()
    if value.tzinfo is None:
        value = value.replace(tzinfo=WIB)
    return value.astimezone(WIB)


def format_tanggal_indo(iso_date: str) -> str:
    """Mengubah tanggal ISO tervalidasi menjadi format surat Indonesia."""

    parsed = _parse_iso_date(iso_date)
    return f"{parsed.day} {BULAN_ID[parsed.month]} {parsed.year}"


def _parse_iso_date(value: str) -> datetime:
    if not DATE_RE.fullmatch(value):
        raise ValueError("format tanggal harus YYYY-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d")


def _normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def _validate_safe_text(value: str, *, max_length: int, allow_empty: bool = False) -> str | None:
    if not value:
        return None if allow_empty else "wajib diisi"
    if len(value) > max_length:
        return f"maksimal {max_length} karakter"
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "mengandung karakter kontrol yang tidak diizinkan"
    if "<" in value or ">" in value:
        return "tidak boleh mengandung tag HTML/XML"
    return None
