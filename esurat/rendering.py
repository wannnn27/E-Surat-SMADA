"""Render DOCX dan pemeriksaan placeholder hasil."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Mapping

from docxtpl import DocxTemplate
from flask import current_app
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from .config import UNRESOLVED_TOKEN_RE


def _check_rendered_docx(buf: io.BytesIO) -> None:
    buf.seek(0)
    try:
        with zipfile.ZipFile(buf) as archive:
            broken_entry = archive.testzip()
            if broken_entry:
                raise RuntimeError(f"Arsip DOCX rusak pada {broken_entry}")
            for name in archive.namelist():
                if name.startswith("word/") and name.endswith(".xml"):
                    xml = archive.read(name).decode("utf-8", errors="replace")
                    if UNRESOLVED_TOKEN_RE.search(xml):
                        raise RuntimeError(f"Placeholder template belum terisi pada {name}")
    except zipfile.BadZipFile as exc:
        raise RuntimeError("Hasil render bukan DOCX yang valid") from exc
    finally:
        buf.seek(0)


def _render_letter(validated: Mapping[str, Any], number: str) -> io.BytesIO:
    info = validated["info"]
    template_path = Path(current_app.config["TEMPLATE_DIR"]) / str(info["template"])
    context = dict(validated["context"])
    context["nomor_surat"] = number
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=True)
    template_source = (
        io.BytesIO(info["template_blob"])
        if info.get("template_blob")
        else str(template_path)
    )
    document = DocxTemplate(template_source)
    document.render(context, jinja_env=environment, autoescape=True)
    buf = io.BytesIO()
    document.save(buf)
    _check_rendered_docx(buf)
    return buf
