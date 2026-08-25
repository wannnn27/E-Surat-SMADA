"""Konfigurasi, batas input, dan lokasi berkas E-Surat."""

from __future__ import annotations

import os
import re
from datetime import timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = PROJECT_ROOT  # Alias kompatibilitas untuk script/test lama.
_env_root = os.getenv("ESURAT_DATA_ROOT")
DATA_ROOT = Path(_env_root).expanduser() if _env_root else PROJECT_ROOT / "data"
_env_data = os.getenv("ESURAT_DATA_DIR")
DATA_DIR = Path(_env_data).expanduser() if _env_data else DATA_ROOT / "master"
_env_db = os.getenv("ESURAT_DB_PATH")
if _env_db:
    DB_PATH = Path(_env_db).expanduser()
else:
    DB_PATH = DATA_ROOT / "runtime" / "surat_smada.db"
TEMPLATE_ROOT = PROJECT_ROOT / "templates_surat"
TEMPLATE_DIR = TEMPLATE_ROOT / "active"
WIB = timezone(timedelta(hours=7), name="Asia/Jakarta")

MAX_QUERY_LENGTH = 100
MAX_ID_LENGTH = 24
MAX_TEXT_LENGTH = 500
AUTO_NUMBER_PREVIEW = "Otomatis saat unduh"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$")
ARCHIVE_CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")
CUSTOM_NUMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./ _-]{2,99}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNRESOLVED_TOKEN_RE = re.compile(r"(?:\{\{|\{%|\{#|\$\{)")

BULAN_ID = [
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
