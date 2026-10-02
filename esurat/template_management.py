"""Validasi template DOCX yang diunggah administrator."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Mapping

from docxtpl import DocxTemplate
from defusedxml import ElementTree  # type: ignore[untyped-import]

from .config import MAX_TEMPLATE_BYTES, TEMPLATE_KEY_RE
from .errors import RequestValidationError
from .utils import _normalize_text, _validate_safe_text


SYSTEM_CONTEXT_VARIABLES = {
    "agama",
    "golongan",
    "jabatan",
    "jabatan_penandatangan",
    "jk",
    "kelas",
    "kode_arsip",
    "nama",
    "nama_kepsek",
    "nama_penandatangan",
    "nip",
    "nip_kepsek",
    "nip_penandatangan",
    "nis",
    "nisn",
    "nomor_surat",
    "nomor_surat_custom",
    "penandatangan",
    "penandatangan_id",
    "penandatangan_id_label",
    "penandatangan_jabatan",
    "penandatangan_nama",
    "people",
    "peran_penandatangan",
    "tanggal_surat",
    "tanggal_surat_iso",
    "ttl",
}


def _field_label(name: str) -> str:
    abbreviations = {"nip": "NIP", "nis": "NIS", "nisn": "NISN"}
    return " ".join(abbreviations.get(part, part.capitalize()) for part in name.split("_"))


def validate_custom_template(
    metadata: Mapping[str, Any],
    content: bytes,
    archive_codes: set[str],
) -> dict[str, Any]:
    """Kembalikan metadata registry setelah DOCX dan field-nya tervalidasi."""

    field_errors: dict[str, str] = {}
    key = _normalize_text(metadata.get("key", "")).casefold()
    label = _normalize_text(metadata.get("label", ""))
    description = _normalize_text(metadata.get("description", ""))
    category = _normalize_text(metadata.get("category", "")).casefold()
    person_mode = _normalize_text(metadata.get("person_mode", "single")).casefold()
    max_people_raw = _normalize_text(metadata.get("max_people", ""))
    default_code = _normalize_text(metadata.get("default_code", ""))
    signer = _normalize_text(metadata.get("signer", "kepsek")).casefold()

    if not TEMPLATE_KEY_RE.fullmatch(key):
        field_errors["key"] = "gunakan 3-50 karakter huruf kecil, angka, atau underscore"
    if _validate_safe_text(label, max_length=120):
        field_errors["label"] = "nama template wajib dan maksimal 120 karakter"
    if _validate_safe_text(description, max_length=300):
        field_errors["description"] = "deskripsi wajib dan maksimal 300 karakter"
    if category not in {"guru", "murid", "umum"}:
        field_errors["category"] = "kategori harus guru, murid, atau umum"
    if person_mode not in {"none", "single", "multiple"}:
        field_errors["person_mode"] = "mode personel tidak valid"
    elif category == "umum" and person_mode != "none":
        field_errors["person_mode"] = "kategori umum harus memakai mode tanpa personel"
    elif category in {"guru", "murid"} and person_mode == "none":
        field_errors["person_mode"] = "kategori guru atau murid harus memilih personel"
    max_people: int | None = None
    if max_people_raw:
        try:
            max_people = int(max_people_raw)
        except ValueError:
            field_errors["max_people"] = "batas personel harus berupa angka"
        else:
            if person_mode != "multiple":
                field_errors["max_people"] = "batas hanya berlaku untuk mode banyak personel"
            elif max_people < 2:
                field_errors["max_people"] = "batas minimal untuk mode banyak personel adalah 2"
    if default_code not in archive_codes:
        field_errors["default_code"] = "kode klasifikasi tidak terdaftar"
    if signer not in {"kepsek", "pemohon", "wali"}:
        field_errors["signer"] = "penandatangan tidak valid"
    elif signer == "wali" and category != "murid":
        field_errors["signer"] = "orang tua/wali hanya berlaku untuk template murid"
    elif signer == "pemohon" and person_mode == "none":
        field_errors["signer"] = "penandatangan pemohon memerlukan pilihan personel"
    if not content:
        field_errors["template_file"] = "file DOCX wajib dipilih"
    elif len(content) > MAX_TEMPLATE_BYTES:
        field_errors["template_file"] = "ukuran template maksimal 4 MB"
    if field_errors:
        raise RequestValidationError("Template belum valid", field_errors, 422)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) > 1000 or sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024:
                raise ValueError("isi DOCX terlalu besar")
            if "word/document.xml" not in names or len(names) != len(set(names)):
                raise ValueError("struktur DOCX tidak lengkap atau entry duplikat")
            if any(item.flag_bits & 1 for item in archive.infolist()):
                raise ValueError("DOCX terenkripsi tidak didukung")
            if any("vbaproject" in name.casefold() or name.casefold().startswith(("word/embeddings/", "word/activex/")) for name in names):
                raise ValueError("macro atau objek aktif tidak diizinkan")
            if archive.testzip() is not None:
                raise ValueError("arsip DOCX rusak")
            for name in names:
                if name.endswith(".rels"):
                    relationships = ElementTree.fromstring(archive.read(name))
                    if any(item.get("TargetMode", "").casefold() == "external" for item in relationships):
                        raise ValueError("tautan eksternal tidak diizinkan")
        template = DocxTemplate(io.BytesIO(content))
        variables = set(template.get_undeclared_template_variables())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise RequestValidationError(
            "Template belum valid", {"template_file": f"file DOCX tidak valid: {exc}"}, 422
        ) from exc
    except Exception as exc:
        raise RequestValidationError(
            "Template belum valid", {"template_file": "placeholder DOCX tidak dapat dibaca"}, 422
        ) from exc

    required = {"nomor_surat", "tanggal_surat"}
    if person_mode == "single":
        required.add("nama")
    elif person_mode == "multiple":
        required.add("people")
    missing = sorted(required - variables)
    if missing:
        raise RequestValidationError(
            "Template belum valid",
            {"template_file": f"placeholder wajib belum ada: {', '.join(missing)}"},
            422,
        )
    if "students" in variables:
        raise RequestValidationError(
            "Template belum valid",
            {"template_file": "template multi-siswa khusus memakai jenis dispensasi bawaan"},
            422,
        )

    custom_names = sorted(variables - SYSTEM_CONTEXT_VARIABLES)
    if len(custom_names) > 30 or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", name) for name in custom_names):
        raise RequestValidationError("Template belum valid", {"template_file": "maksimal 30 field tambahan dengan nama huruf kecil, angka, dan underscore (maksimal 50 karakter)"}, 422)
    if signer == "wali" and "nama_wali" not in custom_names:
        raise RequestValidationError(
            "Template belum valid",
            {"template_file": "penandatangan wali memerlukan placeholder {{ nama_wali }}"},
            422,
        )
    fields = [
        {
            "name": name,
            "label": _field_label(name),
            "type": "date" if name.startswith("tanggal_") else "text",
            "max_length": 500,
        }
        for name in custom_names
    ]
    return {
        "key": key,
        "label": label,
        "deskripsi": description,
        "kategori": category,
        "icon": "fa-file-word",
        "badge": "Template Admin",
        "template": f"{key}.docx",
        "default_kode": default_code,
        "signer": signer,
        "person_mode": person_mode,
        "max_people": max_people,
        "fields": fields,
        "template_blob": content,
        "is_custom": True,
    }
