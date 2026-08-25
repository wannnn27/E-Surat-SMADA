"""Pembacaan dan validasi data master serta template aktif."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping

from docxtpl import DocxTemplate
from flask import Flask

from .config import ARCHIVE_CODE_RE
from .errors import DataValidationError
from .registry import JENIS_SURAT
from .utils import _normalize_text, _validate_safe_text


def _read_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DataValidationError(f"Data master {label} tidak ditemukan: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataValidationError(f"Data master {label} tidak dapat dibaca: {exc}") from exc
    if not isinstance(value, list) or not value:
        raise DataValidationError(f"Data master {label} harus berupa daftar yang tidak kosong")
    if not all(isinstance(record, dict) for record in value):
        raise DataValidationError(f"Setiap record data master {label} harus berupa objek")
    return value


def _clean_record(record: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): _normalize_text(value) if value is not None else "" for key, value in record.items()}


def _ensure_unique(index: dict[str, dict[str, str]], key: str, record: dict[str, str], label: str) -> None:
    value = record[key]
    if value in index:
        raise DataValidationError(f"{label} duplikat pada data master: {value}")
    index[value] = record


def validate_master_data(
    guru_records: list[dict[str, Any]],
    murid_records: list[dict[str, Any]],
    kode_records: list[dict[str, Any]],
    kepsek_nip: str = "",
) -> dict[str, Any]:
    """Validasi seluruh data dahulu, baru membangun indeks identifier unik."""

    guru: list[dict[str, str]] = []
    guru_by_nip: dict[str, dict[str, str]] = {}
    for position, raw in enumerate(guru_records, start=1):
        record = _clean_record(raw)
        for field in ("nip", "nama", "jabatan"):
            if not record.get(field):
                raise DataValidationError(f"guru record {position}: field {field} wajib diisi")
        if not re.fullmatch(r"\d{18}", record["nip"]):
            raise DataValidationError(f"guru record {position}: NIP harus tepat 18 digit")
        for field in ("nama", "jabatan", "ttl", "golongan", "status_pegawai"):
            value = record.get(field, "")
            if value and _validate_safe_text(value, max_length=300):
                raise DataValidationError(f"guru record {position}: field {field} tidak aman")
        for optional in ("ttl", "golongan", "tmt_golongan", "status_pegawai", "kedudukan"):
            record.setdefault(optional, "")
        _ensure_unique(guru_by_nip, "nip", record, "NIP")
        guru.append(record)

    murid: list[dict[str, str]] = []
    murid_by_nis: dict[str, dict[str, str]] = {}
    murid_by_nisn: dict[str, dict[str, str]] = {}
    for position, raw in enumerate(murid_records, start=1):
        record = _clean_record(raw)
        for field in ("nis", "nisn", "nama", "kelas"):
            if not record.get(field):
                raise DataValidationError(f"murid record {position}: field {field} wajib diisi")
        if not record["nis"].isdigit():
            raise DataValidationError(f"murid record {position}: NIS harus numerik")
        if not re.fullmatch(r"\d{10}", record["nisn"]):
            raise DataValidationError(f"murid record {position}: NISN harus tepat 10 digit")
        for field in ("nama", "kelas", "jk", "agama"):
            value = record.get(field, "")
            if value and _validate_safe_text(value, max_length=300):
                raise DataValidationError(f"murid record {position}: field {field} tidak aman")
        record.setdefault("jk", "")
        record.setdefault("agama", "")
        _ensure_unique(murid_by_nis, "nis", record, "NIS")
        _ensure_unique(murid_by_nisn, "nisn", record, "NISN")
        murid.append(record)

    kode_arsip: list[dict[str, str]] = []
    kode_by_value: dict[str, dict[str, str]] = {}
    for position, raw in enumerate(kode_records, start=1):
        record = _clean_record(raw)
        kode = record.get("kode", "")
        keterangan = record.get("keterangan", "")
        if not ARCHIVE_CODE_RE.fullmatch(kode):
            raise DataValidationError(f"kode arsip record {position}: format kode tidak valid")
        if _validate_safe_text(keterangan, max_length=500):
            raise DataValidationError(f"kode arsip record {position}: keterangan tidak valid")
        _ensure_unique(kode_by_value, "kode", record, "Kode arsip")
        kode_arsip.append(record)

    configured_kepsek = _normalize_text(kepsek_nip)
    kepsek = guru_by_nip.get(configured_kepsek) if configured_kepsek else None
    if kepsek is None:
        candidates = [g for g in guru if "kepala sekolah" in g["jabatan"].casefold()]
        if len(candidates) != 1:
            raise DataValidationError(
                "Data Kepala Sekolah tidak dapat ditentukan secara unik; set ESURAT_KEPSEK_NIP"
            )
        kepsek = candidates[0]

    missing_codes = sorted(
        {str(info["default_kode"]) for info in JENIS_SURAT.values()} - set(kode_by_value)
    )
    if missing_codes:
        raise DataValidationError(f"Kode arsip default tidak ada di master: {', '.join(missing_codes)}")

    return {
        "guru": guru,
        "murid": murid,
        "kode_arsip": kode_arsip,
        "guru_by_nip": guru_by_nip,
        "murid_by_nis": murid_by_nis,
        "murid_by_nisn": murid_by_nisn,
        "kode_by_value": kode_by_value,
        "kepsek": kepsek,
    }


def _load_master_state(app: Flask) -> dict[str, Any]:
    data_dir = Path(app.config["DATA_DIR"])
    guru_records = app.config.get("GURU_RECORDS")
    murid_records = app.config.get("MURID_RECORDS")
    kode_records = app.config.get("KODE_ARSIP_RECORDS")
    if guru_records is None:
        guru_file = data_dir / "guru.json"
        guru_records = _read_json_list(guru_file, "guru")
    if murid_records is None:
        murid_file = data_dir / "murid.json"
        murid_records = _read_json_list(murid_file, "murid")
    if kode_records is None:
        kode_file = data_dir / "kode_arsip.json"
        kode_records = _read_json_list(kode_file, "kode arsip")
    return validate_master_data(
        guru_records,
        murid_records,
        kode_records,
        str(app.config.get("KEPSEK_NIP", "")),
    )


def _validate_templates(template_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for jenis, info in JENIS_SURAT.items():
        path = (template_dir / str(info["template"])).resolve()
        try:
            path.relative_to(template_dir.resolve())
        except ValueError as exc:
            raise DataValidationError(f"Path template keluar dari direktori untuk {jenis}") from exc
        if not path.is_file():
            raise DataValidationError(f"Template untuk {jenis} tidak ditemukan: {path.name}")
        try:
            with zipfile.ZipFile(path) as archive:
                if "word/document.xml" not in archive.namelist() or archive.testzip() is not None:
                    raise DataValidationError(f"Template DOCX tidak valid: {path.name}")
            template = DocxTemplate(str(path))
            actual_variables = set(template.get_undeclared_template_variables())
            person_variables = (
                {"nama", "nip", "jabatan", "golongan"}
                if info["kategori"] == "guru"
                else {"nama", "nis", "nisn", "kelas"}
            )
            expected_variables = {
                "nomor_surat",
                "tanggal_surat",
                "penandatangan_jabatan",
                "penandatangan_nama",
                "penandatangan_id_label",
                "penandatangan_id",
            }
            expected_variables.update(person_variables)
            expected_variables.update(str(field["name"]) for field in info["fields"])
            expected_variables.update(str(key) for key in info.get("context_defaults", {}))
            if actual_variables != expected_variables:
                missing = sorted(expected_variables - actual_variables)
                unexpected = sorted(actual_variables - expected_variables)
                details = []
                if missing:
                    details.append(f"placeholder kurang: {', '.join(missing)}")
                if unexpected:
                    details.append(f"placeholder tidak dikenal: {', '.join(unexpected)}")
                raise DataValidationError(f"Kontrak template {path.name} tidak cocok ({'; '.join(details)})")
            hashes[jenis] = hashlib.sha256(path.read_bytes()).hexdigest()
        except DataValidationError:
            raise
        except Exception as exc:
            raise DataValidationError(f"Template DOCX tidak dapat dibaca: {path.name}") from exc
    return hashes
