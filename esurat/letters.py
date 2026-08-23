"""Validasi request surat dan penyusunan context template."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from flask import current_app, jsonify, request

from .config import (
    ARCHIVE_CODE_RE,
    AUTO_NUMBER_PREVIEW,
    CUSTOM_NUMBER_RE,
    MAX_ID_LENGTH,
    MAX_TEXT_LENGTH,
    REQUEST_ID_RE,
)
from .errors import RequestValidationError
from .registry import JENIS_SURAT
from .utils import _normalize_text, _now, _parse_iso_date, _validate_safe_text, format_tanggal_indo


def _public_person(person: Mapping[str, str], kategori: str, *, directory: bool = False) -> dict[str, str]:
    if kategori == "guru":
        fields = ["nip", "nama", "jabatan"]
        if directory:
            fields.extend(["golongan", "status_pegawai"])
    else:
        fields = ["nis", "nisn", "nama", "kelas"]
    return {field: person.get(field, "") for field in fields}


def _common_fields(info: Mapping[str, Any], today_iso: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "tanggal_surat",
            "label": "Tanggal Surat",
            "type": "date",
            "default": today_iso,
            "required": True,
        },
        {
            "name": "kode_arsip",
            "label": "Kode Klasifikasi Arsip",
            "type": "archive",
            "default": info["default_kode"],
            "required": True,
        },
        {
            "name": "nomor_surat_custom",
            "label": "Nomor Surat Manual (Opsional)",
            "type": "text",
            "default": "",
            "required": False,
            "max_length": 100,
        },
    ]


def _public_info(jenis: str, info: Mapping[str, Any], today_iso: str, *, combined: bool) -> dict[str, Any]:
    public = {
        key: info[key]
        for key in ("label", "deskripsi", "kategori", "icon", "badge")
        if key in info
    }
    specific = []
    for raw_field in info["fields"]:
        field = dict(raw_field, required=raw_field.get("required", True))
        if "max_length" in field:
            field["maxlength"] = field["max_length"]
        specific.append(field)
    public["fields"] = _common_fields(info, today_iso) + specific if combined else specific
    public["key"] = jenis
    return public


def _json_error(message: str, status: int, field_errors: Mapping[str, str] | None = None):
    payload: dict[str, Any] = {"error": message}
    if field_errors:
        payload["field_errors"] = dict(field_errors)
    return jsonify(payload), status


def _request_value(form_data: Mapping[str, Any], name: str, default: str = "") -> str:
    value = form_data.get(name, default)
    return _normalize_text(value) if value is not None else ""


def _validate_request(form_data: Mapping[str, Any], *, preview: bool) -> dict[str, Any]:
    state = current_app.extensions["esurat_data"]
    field_errors: dict[str, str] = {}

    jenis = _request_value(form_data, "jenis_surat")
    info = JENIS_SURAT.get(jenis)
    if info is None:
        raise RequestValidationError("Jenis surat tidak valid", {"jenis_surat": "pilih jenis yang tersedia"})

    posted_category = _request_value(form_data, "kategori")
    if posted_category and posted_category not in {"guru", "murid"}:
        field_errors["kategori"] = "kategori harus guru atau murid"
    elif posted_category and posted_category != info["kategori"]:
        field_errors["kategori"] = "kategori tidak sesuai jenis surat"

    id_value = _request_value(form_data, "id_value")
    if not id_value or len(id_value) > MAX_ID_LENGTH or not id_value.isdigit():
        field_errors["id_value"] = "identifier wajib berupa angka yang valid"
        person = None
    elif info["kategori"] == "guru":
        person = state["guru_by_nip"].get(id_value)
    else:
        person = state["murid_by_nis"].get(id_value) or state["murid_by_nisn"].get(id_value)
    if id_value and person is None and "id_value" not in field_errors:
        field_errors["id_value"] = "data personel tidak ditemukan"

    today_iso = _now().date().isoformat()
    tanggal_surat_iso = _request_value(form_data, "tanggal_surat", today_iso) or today_iso
    try:
        _parse_iso_date(tanggal_surat_iso)
    except ValueError:
        field_errors["tanggal_surat"] = "gunakan format tanggal YYYY-MM-DD yang valid"

    kode_arsip = _request_value(form_data, "kode_arsip", str(info["default_kode"])) or str(
        info["default_kode"]
    )
    if not ARCHIVE_CODE_RE.fullmatch(kode_arsip) or kode_arsip not in state["kode_by_value"]:
        field_errors["kode_arsip"] = "kode klasifikasi tidak terdaftar pada master arsip"

    custom_number = _request_value(form_data, "nomor_surat_custom")
    if custom_number and not CUSTOM_NUMBER_RE.fullmatch(custom_number):
        field_errors["nomor_surat_custom"] = (
            "gunakan 3-100 karakter berupa huruf, angka, spasi, titik, garis, atau slash"
        )

    for protected in ("nama_kepsek", "nip_kepsek"):
        if _request_value(form_data, protected):
            field_errors[protected] = "nilai penandatangan dikelola oleh sistem"

    normalized_fields: dict[str, str] = {}
    context_fields: dict[str, str] = {}
    date_values: dict[str, datetime] = {}
    for definition in info["fields"]:
        name = str(definition["name"])
        value = _request_value(form_data, name, str(definition.get("default", "")))
        required = bool(definition.get("required", True))
        if definition["type"] == "date":
            if not value and required:
                field_errors[name] = "tanggal wajib diisi"
                continue
            try:
                parsed = _parse_iso_date(value)
            except ValueError:
                field_errors[name] = "gunakan format tanggal YYYY-MM-DD yang valid"
                continue
            date_values[name] = parsed
            normalized_fields[name] = value
            context_fields[name] = format_tanggal_indo(value)
        elif definition["type"] == "select":
            if value not in definition.get("options", []):
                field_errors[name] = "pilihan tidak valid"
                continue
            normalized_fields[name] = value
            context_fields[name] = value
        else:
            error = _validate_safe_text(
                value,
                max_length=int(definition.get("max_length", MAX_TEXT_LENGTH)),
                allow_empty=not required,
            )
            if error:
                field_errors[name] = error
                continue
            normalized_fields[name] = value
            context_fields[name] = value

    if date_values.get("tanggal_mulai") and date_values.get("tanggal_selesai"):
        if date_values["tanggal_selesai"] < date_values["tanggal_mulai"]:
            field_errors["tanggal_selesai"] = "tidak boleh lebih awal dari tanggal mulai"

    request_id = _request_value(form_data, "request_id") or request.headers.get("X-Request-ID", "").strip()
    if request_id and not REQUEST_ID_RE.fullmatch(request_id):
        field_errors["request_id"] = "request_id harus 8-64 karakter aman"
    if not request_id and not preview:
        request_id = str(uuid.uuid4())

    if field_errors:
        raise RequestValidationError("Data surat belum valid", field_errors, 422)
    assert person is not None

    context = dict(person)
    # Menjamin template legacy tidak mendapat Undefined tanpa menyamarkan field form wajib.
    for legacy_key in (
        "nip",
        "nis",
        "nisn",
        "kelas",
        "jabatan",
        "golongan",
        "ttl",
        "jk",
        "agama",
        "keperluan",
        "nama_wali",
    ):
        context.setdefault(legacy_key, "")
    context.update(context_fields)
    context.update({str(key): str(value) for key, value in info.get("context_defaults", {}).items()})
    context["tanggal_surat"] = format_tanggal_indo(tanggal_surat_iso)
    context["tanggal_surat_iso"] = tanggal_surat_iso
    context["kode_arsip"] = kode_arsip
    context["nomor_surat_custom"] = custom_number
    context["nomor_surat"] = custom_number or AUTO_NUMBER_PREVIEW

    signer_kind = str(info["signer"])
    if signer_kind == "pemohon":
        signer = {
            "nama": person["nama"],
            "nip": person.get("nip", ""),
            "jabatan": person.get("jabatan", "Pemohon"),
            "peran": "Pemohon",
        }
    elif signer_kind == "wali":
        signer = {
            "nama": normalized_fields["nama_wali"],
            "nip": "",
            "jabatan": "Orang Tua / Wali",
            "peran": "Orang Tua / Wali",
        }
    else:
        kepsek = state["kepsek"]
        signer = {
            "nama": kepsek["nama"],
            "nip": kepsek["nip"],
            "jabatan": kepsek["jabatan"],
            "peran": "Kepala Sekolah",
        }
    context["penandatangan"] = signer
    context["nama_penandatangan"] = signer["nama"]
    context["nip_penandatangan"] = signer["nip"]
    context["jabatan_penandatangan"] = signer["jabatan"]
    context["peran_penandatangan"] = signer["peran"]
    context["penandatangan_nama"] = signer["nama"]
    context["penandatangan_jabatan"] = signer["peran"]
    context["penandatangan_id"] = signer["nip"]
    context["penandatangan_id_label"] = "NIP." if signer["nip"] else ""
    # Alias untuk template/frontend lama; nilainya tetap server-controlled.
    context["nama_kepsek"] = state["kepsek"]["nama"]
    context["nip_kepsek"] = state["kepsek"]["nip"]

    normalized = {
        "jenis_surat": jenis,
        "kategori": info["kategori"],
        "id_value": person.get("nip") or person.get("nis") or id_value,
        "tanggal_surat": tanggal_surat_iso,
        "kode_arsip": kode_arsip,
        "nomor_surat_custom": custom_number,
        "request_id": request_id,
        "fields": normalized_fields,
    }
    return {
        "jenis": jenis,
        "info": info,
        "person": person,
        "signer": signer,
        "context": context,
        "normalized": normalized,
    }


def get_surat_context(form_data: Mapping[str, Any]):
    """Compatibility wrapper untuk pemanggil lama; route baru memakai exception JSON."""

    try:
        validated = _validate_request(form_data, preview=True)
    except RequestValidationError as exc:
        return None, None, exc.message, exc.status_code
    return validated["info"], validated["context"], validated["person"], 200
