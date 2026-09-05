"""Konversi hasil DOCX ke PDF tanpa program desktop eksternal.

Konverter bekerja dari DOCX yang sudah dirender. Template bawaan dan template
yang diunggah administrator menggunakan sumber isi serta nomor surat yang sama
untuk keluaran Word dan PDF.
"""

from __future__ import annotations

import io
from html import escape
from typing import Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DEFAULT_FONT_SIZE = 12.0
MAX_STORY_ITEMS = 5_000
MAX_TABLE_CELLS = 2_000


def _points(value, default: float = 0.0) -> float:
    """Ubah panjang python-docx (EMU) menjadi point dengan batas aman."""

    if value is None:
        return default
    try:
        return max(0.0, min(float(value) / 12_700.0, 2_000.0))
    except (TypeError, ValueError):
        return default


def _font_size(paragraph: DocxParagraph) -> float:
    for run in paragraph.runs:
        if run.font.size is not None:
            return max(6.0, min(float(run.font.size.pt), 36.0))
    try:
        if paragraph.style.font.size is not None:
            return max(6.0, min(float(paragraph.style.font.size.pt), 36.0))
    except (AttributeError, KeyError):
        pass
    return DEFAULT_FONT_SIZE


def _alignment(paragraph: DocxParagraph) -> int:
    return {
        WD_ALIGN_PARAGRAPH.CENTER: TA_CENTER,
        WD_ALIGN_PARAGRAPH.RIGHT: TA_RIGHT,
        WD_ALIGN_PARAGRAPH.JUSTIFY: TA_JUSTIFY,
        WD_ALIGN_PARAGRAPH.DISTRIBUTE: TA_JUSTIFY,
    }.get(paragraph.alignment, TA_LEFT)


def _run_markup(paragraph: DocxParagraph) -> str:
    parts: list[str] = []
    plain_from_runs: list[str] = []
    for run in paragraph.runs:
        text = run.text or ""
        plain_from_runs.append(text)
        if not text:
            continue
        rendered = escape(text).replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;").replace("\n", "<br/>")
        if run.bold:
            rendered = f"<b>{rendered}</b>"
        if run.italic:
            rendered = f"<i>{rendered}</i>"
        if run.underline:
            rendered = f"<u>{rendered}</u>"
        parts.append(rendered)

    # Teks di dalam hyperlink kadang tidak masuk paragraph.runs pada python-docx.
    if not parts and paragraph.text:
        return escape(paragraph.text).replace("\n", "<br/>")
    if "".join(plain_from_runs) != paragraph.text and paragraph.text:
        return escape(paragraph.text).replace("\n", "<br/>")
    return "".join(parts)


def _paragraph_style(paragraph: DocxParagraph) -> ParagraphStyle:
    size = _font_size(paragraph)
    paragraph_format = paragraph.paragraph_format
    leading = size * 1.15
    line_spacing = paragraph_format.line_spacing
    if isinstance(line_spacing, float):
        leading = size * max(0.8, min(line_spacing, 3.0))
    elif line_spacing is not None:
        leading = max(size, _points(line_spacing, leading))

    first_line_indent = paragraph_format.first_line_indent
    first_line = 0.0
    if first_line_indent is not None:
        try:
            first_line = max(-100.0, min(float(first_line_indent) / 12_700.0, 200.0))
        except (TypeError, ValueError):
            first_line = 0.0

    return ParagraphStyle(
        "DocxParagraph",
        fontName="Times-Roman",
        fontSize=size,
        leading=leading,
        textColor=colors.black,
        alignment=_alignment(paragraph),
        leftIndent=_points(paragraph_format.left_indent),
        rightIndent=_points(paragraph_format.right_indent),
        firstLineIndent=first_line,
        spaceBefore=_points(paragraph_format.space_before),
        spaceAfter=_points(paragraph_format.space_after),
        keepWithNext=bool(paragraph_format.keep_with_next),
        splitLongWords=True,
        allowWidows=0,
        allowOrphans=0,
    )


def _paragraph_images(paragraph: DocxParagraph, available_width: float) -> list[Image]:
    images: list[Image] = []
    for run in paragraph.runs:
        blips = run._element.xpath(".//a:blip")
        extents = run._element.xpath(".//wp:extent")
        for index, blip in enumerate(blips):
            relationship_id = blip.get(qn("r:embed"))
            related_part = paragraph.part.related_parts.get(relationship_id)
            if related_part is None:
                continue
            width = available_width
            height = available_width * 0.25
            if index < len(extents):
                width = _points(extents[index].get("cx"), available_width)
                height = _points(extents[index].get("cy"), height)
            if width <= 0 or height <= 0:
                continue
            scale = min(1.0, available_width / width)
            image = Image(io.BytesIO(related_part.blob), width=width * scale, height=height * scale)
            image.hAlign = {TA_CENTER: "CENTER", TA_RIGHT: "RIGHT"}.get(
                _alignment(paragraph), "LEFT"
            )
            images.append(image)
    return images


def _paragraph_flowables(paragraph: DocxParagraph, available_width: float) -> list:
    flowables: list = list(_paragraph_images(paragraph, available_width))
    markup = _run_markup(paragraph)
    if markup:
        flowables.append(Paragraph(markup, _paragraph_style(paragraph)))
    elif paragraph.text.count("\n"):
        flowables.append(Spacer(1, _font_size(paragraph) * paragraph.text.count("\n")))
    elif flowables:
        after = _points(paragraph.paragraph_format.space_after, 2.0)
        if after:
            flowables.append(Spacer(1, after))
    return flowables


def _cell_markup(cell) -> str:
    paragraphs = [_run_markup(paragraph) for paragraph in cell.paragraphs]
    return "<br/>".join(part for part in paragraphs if part) or "&#160;"


def _table_has_borders(table: DocxTable) -> bool:
    borders = table._tbl.tblPr.find(qn("w:tblBorders"))
    if borders is None:
        return False
    return any(
        border.get(qn("w:val"), "nil") not in {"nil", "none"}
        for border in borders
    )


def _table_widths(table: DocxTable, available_width: float) -> list[float]:
    columns = max(1, len(table.columns))
    grid_columns = table._tbl.tblGrid.findall(qn("w:gridCol"))
    widths = []
    for column in grid_columns[:columns]:
        try:
            widths.append(max(1.0, float(column.get(qn("w:w"))) / 20.0))
        except (TypeError, ValueError):
            widths = []
            break
    if len(widths) != columns:
        return [available_width / columns] * columns
    total = sum(widths)
    scale = available_width / total if total > available_width else 1.0
    return [width * scale for width in widths]


def _table_flowable(table: DocxTable, available_width: float) -> Table:
    cell_count = len(table.rows) * max(1, len(table.columns))
    if cell_count > MAX_TABLE_CELLS:
        raise RuntimeError("Tabel DOCX terlalu besar untuk dibuat sebagai PDF")

    bordered = _table_has_borders(table)
    cell_style = ParagraphStyle(
        "DocxTableCell",
        fontName="Times-Roman",
        fontSize=11.5,
        leading=13.25,
        textColor=colors.black,
        splitLongWords=True,
    )
    data = [
        [Paragraph(_cell_markup(cell), cell_style) for cell in row.cells]
        for row in table.rows
    ]
    pdf_table = Table(
        data,
        colWidths=_table_widths(table, available_width),
        repeatRows=1 if bordered and len(data) > 1 else 0,
        hAlign="LEFT",
        spaceBefore=3,
        spaceAfter=6,
        splitByRow=1,
    )
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 if bordered else 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 if bordered else 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3 if bordered else 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if bordered else 1.5),
    ]
    if bordered:
        commands.extend(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#808080")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]
        )
    pdf_table.setStyle(TableStyle(commands))
    return pdf_table


def _story(document: DocxDocument, available_width: float) -> list:
    story: list = []
    blocks: Iterable[DocxParagraph | DocxTable] = document.iter_inner_content()
    for block in blocks:
        if isinstance(block, DocxParagraph):
            story.extend(_paragraph_flowables(block, available_width))
        elif isinstance(block, DocxTable):
            story.append(_table_flowable(block, available_width))
        if len(story) > MAX_STORY_ITEMS:
            raise RuntimeError("Isi DOCX terlalu panjang untuk dibuat sebagai PDF")
    if not story:
        raise RuntimeError("DOCX tidak memiliki isi yang dapat dibuat sebagai PDF")
    return story


def _check_rendered_pdf(buffer: io.BytesIO) -> None:
    data = buffer.getvalue()
    if len(data) < 1_000 or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1_024:]:
        raise RuntimeError("Hasil render bukan PDF yang valid")
    buffer.seek(0)


def render_pdf_from_docx(docx_buffer: io.BytesIO) -> io.BytesIO:
    """Konversi DOCX ter-render menjadi PDF A4 yang siap diunduh."""

    docx_buffer.seek(0)
    document = Document(docx_buffer)
    section = document.sections[0] if document.sections else None
    page_width = _points(section.page_width, A4[0]) if section else A4[0]
    page_height = _points(section.page_height, A4[1]) if section else A4[1]
    left_margin = _points(section.left_margin, 3 * cm) if section else 3 * cm
    right_margin = _points(section.right_margin, 2 * cm) if section else 2 * cm
    top_margin = _points(section.top_margin, 1.5 * cm) if section else 1.5 * cm
    bottom_margin = _points(section.bottom_margin, 2 * cm) if section else 2 * cm
    available_width = page_width - left_margin - right_margin
    if available_width < 5 * cm:
        raise RuntimeError("Margin DOCX tidak menyisakan area PDF yang layak")

    output = io.BytesIO()
    pdf = SimpleDocTemplate(
        output,
        pagesize=(page_width, page_height),
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title="Surat E-Surat SMADA",
        author="SMA Negeri 2 Wonosari",
        subject="Dokumen surat resmi",
        pageCompression=1,
    )

    def set_metadata(canvas, _doc) -> None:
        canvas.setTitle("Surat E-Surat SMADA")
        canvas.setAuthor("SMA Negeri 2 Wonosari")
        canvas.setSubject("Dokumen surat resmi")

    pdf.build(_story(document, available_width), onFirstPage=set_metadata, onLaterPages=set_metadata)
    _check_rendered_pdf(output)
    return output
