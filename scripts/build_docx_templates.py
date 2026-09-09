"""
Bangun ulang seluruh template DOCX aktif E-Surat SMADA.

Builder ini sengaja memakai master immutable yang tidak pernah menjadi target
output. Tiga elemen awal body master dipertahankan sebagai blok kop; seluruh
elemen sesudahnya (paragraf maupun tabel) dibuang sebelum isi surat dibuat.
Dengan demikian, menjalankan script berulang kali tidak menggandakan isi.

Cara menjalankan:
    python scripts/build_docx_templates.py
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import docx
from docxtpl import DocxTemplate
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = BASE_DIR / "templates_surat"
ACTIVE_TEMPLATE_DIR = TEMPLATE_ROOT / "active"

# Master ini hanya sumber kop. Jangan pernah masukkan namanya ke TEMPLATE_SPECS.
MASTER_DOC = TEMPLATE_ROOT / "master" / "kop_smada.docx"
KOP_BODY_ELEMENT_COUNT = 3

FONT_NAME = "Times New Roman"
BODY_FONT_SIZE_PT = 12
TITLE_FONT_SIZE_PT = 14

# A4 21 cm, margin kiri 3 cm dan kanan 2 cm menghasilkan lebar isi 16 cm.
TABLE_COLUMN_WIDTHS_DXA = (2948, 227, 5896)
TABLE_WIDTH_DXA = sum(TABLE_COLUMN_WIDTHS_DXA)
CELL_MARGIN_DXA = {"top": 80, "left": 100, "bottom": 80, "right": 100}


@dataclass(frozen=True)
class TemplateSpec:
    filename: str
    title: str
    opening: str
    rows: tuple[tuple[str, str], ...]
    closing: str
    layout: str = "standard"
    multi_people: bool = False
    field_names: tuple[str, ...] = ()
    extra_variables: tuple[str, ...] = ()
    expected_table_rows: tuple[int, ...] = ()


TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        filename="izin_guru.docx",
        title="SURAT PERMOHONAN IZIN PEGAWAI",
        opening="Yang bertanda tangan di bawah ini mengajukan permohonan izin tidak masuk kerja:",
        rows=(
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Unit Kerja", "{{ unit_kerja }}"),
            ("Tanggal Mulai", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai", "{{ tanggal_selesai }}"),
            ("Keperluan / Alasan", "{{ keperluan }}"),
        ),
        closing="Demikian permohonan izin ini dibuat untuk dapat dipergunakan sebagaimana mestinya.",
    ),
    TemplateSpec(
        filename="cuti_guru.docx",
        title="SURAT PERMOHONAN CUTI PEGAWAI",
        opening="Yang bertanda tangan di bawah ini mengajukan permohonan cuti pegawai:",
        rows=(
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Jenis Cuti", "{{ jenis_cuti }}"),
            ("Lama Cuti", "{{ lama_cuti }}"),
            ("Terhitung Mulai Tgl", "{{ tanggal_mulai }}"),
            ("Sampai Dengan Tgl", "{{ tanggal_selesai }}"),
            ("Alasan Cuti", "{{ keperluan }}"),
            ("Alamat Selama Cuti", "{{ alamat_selama_cuti }}"),
        ),
        closing="Demikian permohonan cuti ini disampaikan untuk pertimbangan lebih lanjut.",
    ),
    TemplateSpec(
        filename="sakit_guru.docx",
        title="SURAT PEMBERITAHUAN SAKIT",
        opening="Memberitahukan bahwa pegawai bersangkutan tidak dapat melaksanakan tugas karena sakit:",
        rows=(
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Unit Kerja", "{{ unit_kerja }}"),
            ("Tanggal Mulai Sakit", "{{ tanggal_mulai }}"),
            ("Sampai Tanggal", "{{ tanggal_selesai }}"),
            ("Keterangan Sakit", "{{ keperluan }}"),
        ),
        closing="Demikian surat pemberitahuan sakit ini dibuat dengan sebenarnya.",
    ),
    TemplateSpec(
        filename="3. Surat Tugas-smada.docx",
        title="SURAT TUGAS",
        opening="",
        rows=(),
        closing="Demikian surat tugas ini diberikan untuk dilaksanakan dengan penuh rasa tanggung jawab.",
        layout="surat_tugas",
        multi_people=True,
        field_names=("dasar", "tanggal_mulai", "tanggal_selesai", "waktu", "tempat_kegiatan", "keperluan"),
        expected_table_rows=(1, 4, 5),
    ),
    TemplateSpec(
        filename="11. Surat Keterangan-smada.docx",
        title="SURAT KETERANGAN",
        opening="Kepala SMA Negeri 2 Wonosari dengan ini menerangkan bahwa:",
        rows=(
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Terhitung Mulai Tgl", "{{ tanggal_mulai }}"),
            ("Menerangkan Bahwa", "{{ keperluan }}"),
        ),
        closing="Demikian surat keterangan ini dibuat dengan sebenarnya untuk dapat dipergunakan sebagaimana mestinya.",
    ),
    TemplateSpec(
        filename="izin_murid.docx",
        title="SURAT IZIN SISWA",
        opening="Memberitahukan bahwa siswa bersangkutan mengajukan izin tidak mengikuti kegiatan belajar mengajar:",
        rows=(
            ("Nama Siswa", "{{ nama }}"),
            ("NIS / NISN", "{{ nis }} / {{ nisn }}"),
            ("Kelas", "Kelas {{ kelas }}"),
            ("Tanggal Mulai Izin", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai Izin", "{{ tanggal_selesai }}"),
            ("Alasan Izin", "{{ keperluan }}"),
            ("Orang Tua / Wali", "{{ nama_wali }}"),
        ),
        closing="Demikian surat izin ini disampaikan agar menjadi maklum.",
    ),
    TemplateSpec(
        filename="dispensasi_murid.docx",
        title="SURAT DISPENSASI SISWA",
        opening="Kepala SMA Negeri 2 Wonosari memberikan dispensasi kepada siswa:",
        rows=(
            ("Nama Kegiatan", "{{ nama_kegiatan }}"),
            ("Penyelenggara", "{{ penyelenggara }}"),
            ("Tempat Kegiatan", "{{ tempat_kegiatan }}"),
            ("Tanggal Mulai", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai", "{{ tanggal_selesai }}"),
            ("Uraian / Keperluan", "{{ keperluan }}"),
        ),
        closing="Demikian surat dispensasi ini dibuat untuk dipergunakan sebagaimana mestinya.",
        multi_people=True,
    ),
    TemplateSpec(
        filename="surat_pengantar_umum.docx",
        title="SURAT PENGANTAR",
        opening="",
        rows=(),
        closing="",
        layout="pengantar_umum",
        field_names=("tujuan", "alamat_tujuan", "jenis_barang", "jumlah_barang", "keterangan_pengantar"),
        expected_table_rows=(2,),
    ),
    TemplateSpec(
        filename="surat_pengantar_cuti_guru.docx",
        title="SURAT PENGANTAR",
        opening="",
        rows=(),
        closing="",
        layout="pengantar_cuti",
        field_names=("tujuan", "alamat_tujuan", "jenis_cuti", "jumlah_barang", "keterangan_pengantar"),
        extra_variables=("nama", "nip", "jabatan", "golongan"),
        expected_table_rows=(2,),
    ),
    TemplateSpec(
        filename="permohonan_penceramah.docx",
        title="PERMOHONAN PENCERAMAH",
        opening="",
        rows=(),
        closing="Demikian surat permohonan ini kami sampaikan. Atas perhatian dan kesediaannya, kami ucapkan terima kasih.",
        layout="permohonan_penceramah",
        field_names=(
            "sifat", "lampiran", "perihal", "penerima", "alamat_penerima", "latar_kegiatan",
            "hari", "tanggal_kegiatan", "waktu", "tempat_kegiatan",
        ),
        expected_table_rows=(4, 4),
    ),
    TemplateSpec(
        filename="surat_keterangan_kehilangan_murid.docx",
        title="SURAT KETERANGAN KEHILANGAN",
        opening="Yang bertanda tangan di bawah ini:",
        rows=(),
        closing="Demikian surat keterangan ini dibuat untuk dipergunakan sebagaimana mestinya.",
        layout="keterangan_kehilangan",
        field_names=(
            "barang_hilang", "tempat_tanggal_lahir", "jenis_kelamin_lengkap", "nomor_rekening",
            "nama_ibu_kandung", "keperluan",
        ),
        extra_variables=("nama", "nis", "nisn", "kelas"),
        expected_table_rows=(3, 8),
    ),
    TemplateSpec(
        filename="surat_rekomendasi_murid.docx",
        title="SURAT REKOMENDASI",
        opening="Yang bertanda tangan di bawah ini:",
        rows=(),
        closing="Demikian surat rekomendasi ini dibuat untuk dipergunakan sebagaimana mestinya.",
        layout="rekomendasi_murid",
        multi_people=True,
        field_names=(
            "nama_kegiatan", "guru_pendamping", "nip_guru_pendamping", "email_guru_pendamping",
            "telepon_guru_pendamping", "kontak_peserta", "keperluan",
        ),
        expected_table_rows=(3, 4, 4),
    ),
    TemplateSpec(
        filename="undangan_umum.docx",
        title="SURAT UNDANGAN",
        opening="Kami mengharap kehadiran Bapak/Ibu dalam kegiatan yang akan diselenggarakan pada:",
        rows=(),
        closing="Atas perhatian dan kehadiran Bapak/Ibu, kami sampaikan terima kasih.",
        layout="undangan",
        field_names=(
            "sifat", "lampiran", "perihal", "penerima", "alamat_penerima", "hari",
            "tanggal_kegiatan", "waktu", "tempat_kegiatan", "acara",
        ),
        expected_table_rows=(4, 5),
    ),
)


def _get_or_add(parent, tag: str, *, first: bool = False):
    child = parent.find(qn(tag))
    if child is None:
        child = OxmlElement(tag)
        if first:
            parent.insert(0, child)
        else:
            parent.append(child)
    return child


def _set_dxa(element, value: int) -> None:
    element.set(qn("w:w"), str(value))
    element.set(qn("w:type"), "dxa")


def _set_font_properties(r_pr, size_pt: int) -> None:
    r_fonts = _get_or_add(r_pr, "w:rFonts", first=True)
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        r_fonts.set(qn(f"w:{attribute}"), FONT_NAME)

    half_points = str(size_pt * 2)
    _get_or_add(r_pr, "w:sz").set(qn("w:val"), half_points)
    _get_or_add(r_pr, "w:szCs").set(qn("w:val"), half_points)


def set_run_font(run, *, size_pt: int = BODY_FONT_SIZE_PT, bold=None, underline=None) -> None:
    run.font.name = FONT_NAME
    run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if underline is not None:
        run.underline = underline
    _set_font_properties(run._element.get_or_add_rPr(), size_pt)


def configure_default_font(doc: docx.Document) -> None:
    normal = next((style for style in doc.styles if style.style_id == "Normal"), None)
    if normal is None:
        raise RuntimeError("Style Normal tidak ditemukan pada master template.")
    normal.font.name = FONT_NAME
    normal.font.size = Pt(BODY_FONT_SIZE_PT)
    normal_r_pr = normal.element.get_or_add_rPr()
    _set_font_properties(normal_r_pr, BODY_FONT_SIZE_PT)

    styles = doc.styles.element
    doc_defaults = styles.find(qn("w:docDefaults"))
    if doc_defaults is None:
        doc_defaults = OxmlElement("w:docDefaults")
        styles.insert(0, doc_defaults)
    r_pr_default = _get_or_add(doc_defaults, "w:rPrDefault", first=True)
    default_r_pr = _get_or_add(r_pr_default, "w:rPr")
    _set_font_properties(default_r_pr, BODY_FONT_SIZE_PT)


def configure_page(doc: docx.Document) -> None:
    for section in doc.sections:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.top_margin = Cm(1.5)
        section.right_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(3.0)
        section.header_distance = Cm(0.5)
        section.footer_distance = Cm(1.0)


def retain_kop_only(doc: docx.Document) -> None:
    body = doc._element.body
    content = [child for child in body if child.tag != qn("w:sectPr")]
    if len(content) < KOP_BODY_ELEMENT_COUNT:
        raise RuntimeError("Master tidak memiliki blok kop yang diharapkan.")

    kop = content[:KOP_BODY_ELEMENT_COUNT]
    drawing_count = sum(1 for element in kop for node in element.iter() if node.tag == qn("w:drawing"))
    if drawing_count != 1:
        raise RuntimeError(f"Blok kop master harus memuat tepat satu drawing; ditemukan {drawing_count}.")

    for element in content[KOP_BODY_ELEMENT_COUNT:]:
        body.remove(element)


def add_text_paragraph(
    doc: docx.Document,
    text: str,
    *,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
    size_pt: int = BODY_FONT_SIZE_PT,
    bold: bool = False,
    underline: bool = False,
    space_before_pt: int = 0,
    space_after_pt: int = 0,
    line_spacing: float = 1.15,
    keep_with_next: bool = False,
    left_indent_cm: float | None = None,
):
    paragraph = doc.add_paragraph()
    paragraph.alignment = alignment
    paragraph.paragraph_format.space_before = Pt(space_before_pt)
    paragraph.paragraph_format.space_after = Pt(space_after_pt)
    paragraph.paragraph_format.line_spacing = line_spacing
    paragraph.paragraph_format.keep_with_next = keep_with_next
    if left_indent_cm is not None:
        paragraph.paragraph_format.left_indent = Cm(left_indent_cm)
    run = paragraph.add_run(text)
    set_run_font(run, size_pt=size_pt, bold=bold, underline=underline)
    return paragraph


def remove_cell_borders(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = _get_or_add(borders, f"w:{border_name}")
        border.set(qn("w:val"), "nil")


def configure_cell(cell, width_dxa: int, *, borderless: bool = True) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    tc_pr = cell._tc.get_or_add_tcPr()
    _set_dxa(_get_or_add(tc_pr, "w:tcW"), width_dxa)

    tc_mar = _get_or_add(tc_pr, "w:tcMar")
    for side, value in CELL_MARGIN_DXA.items():
        _set_dxa(_get_or_add(tc_mar, f"w:{side}"), value)
    if borderless:
        remove_cell_borders(cell)


def configure_table_geometry(
    table,
    widths: Sequence[int] = TABLE_COLUMN_WIDTHS_DXA,
    *,
    bordered: bool = False,
) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False

    tbl_pr = table._tbl.tblPr
    _set_dxa(_get_or_add(tbl_pr, "w:tblW"), sum(widths))

    tbl_ind = _get_or_add(tbl_pr, "w:tblInd")
    _set_dxa(tbl_ind, 0)

    layout = _get_or_add(tbl_pr, "w:tblLayout")
    layout.set(qn("w:type"), "fixed")

    justification = _get_or_add(tbl_pr, "w:jc")
    justification.set(qn("w:val"), "left")

    tbl_borders = _get_or_add(tbl_pr, "w:tblBorders")
    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = _get_or_add(tbl_borders, f"w:{border_name}")
        border.set(qn("w:val"), "single" if bordered else "nil")
        if bordered:
            border.set(qn("w:sz"), "4")
            border.set(qn("w:color"), "808080")

    tbl_grid = table._tbl.tblGrid
    for grid_col in list(tbl_grid):
        tbl_grid.remove(grid_col)
    for width in widths:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        tbl_grid.append(grid_col)


def add_key_value_table(doc: docx.Document, rows: Sequence[tuple[str, str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=3)
    configure_table_geometry(table)

    emphasized_labels = {"Nama", "Nama Siswa", "NIP", "NIS / NISN"}
    for row, (label, value) in zip(table.rows, rows):
        for cell, width in zip(row.cells, TABLE_COLUMN_WIDTHS_DXA):
            configure_cell(cell, width)

        values = (label, ":", value)
        alignments = (WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT)
        for index, (cell, text, alignment) in enumerate(zip(row.cells, values, alignments)):
            paragraph = cell.paragraphs[0]
            paragraph.alignment = alignment
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.15
            run = paragraph.add_run(text)
            set_run_font(run, bold=(index == 2 and label in emphasized_labels))


def _repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    marker = _get_or_add(tr_pr, "w:tblHeader")
    marker.set(qn("w:val"), "true")


def _set_cell_lines(cell, lines: Sequence[str], *, bold: bool = False, centered: bool = False) -> None:
    for index, text in enumerate(lines):
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.05
        set_run_font(paragraph.add_run(text), bold=bold)


def add_people_table(doc: docx.Document, *, category: str, compact_identity: bool = False) -> None:
    if category == "guru" and compact_identity:
        widths = (650, 5000, 3421)
        headers = (("No.",), ("Nama",), ("Jabatan",))
        body = (
            ("{{ loop.index }}",),
            ("{{ person.nama }}", "NIP. {{ person.nip }}"),
            ("{{ person.jabatan }}",),
        )
    else:
        widths = (650, 3700, 2721, 2000)
        headers = (("No.",), ("Nama Siswa",), ("NIS / NISN",), ("Kelas",))
        body = (
            ("{{ loop.index }}",),
            ("{{ person.nama }}",),
            ("{{ person.nis }} / {{ person.nisn }}",),
            ("{{ person.kelas }}",),
        )

    table = doc.add_table(rows=4, cols=len(widths))
    configure_table_geometry(table, widths, bordered=True)
    _repeat_table_header(table.rows[0])
    for cell, width, lines in zip(table.rows[0].cells, widths, headers):
        configure_cell(cell, width, borderless=False)
        _set_cell_lines(cell, lines, bold=True, centered=True)

    for control_row, tag in ((table.rows[1], "{%tr for person in people %}"), (table.rows[3], "{%tr endfor %}")):
        for cell, width in zip(control_row.cells, widths):
            configure_cell(cell, width, borderless=False)
        _set_cell_lines(control_row.cells[0], (tag,))

    for index, (cell, width, lines) in enumerate(zip(table.rows[2].cells, widths, body)):
        configure_cell(cell, width, borderless=False)
        _set_cell_lines(cell, lines, centered=(index == 0))


def add_bordered_table(
    doc: docx.Document,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    widths: Sequence[int],
) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    configure_table_geometry(table, widths, bordered=True)
    _repeat_table_header(table.rows[0])
    for cell, width, value in zip(table.rows[0].cells, widths, headers):
        configure_cell(cell, width, borderless=False)
        _set_cell_lines(cell, (value,), bold=True, centered=True)
    for row, values in zip(table.rows[1:], rows):
        for index, (cell, width, value) in enumerate(zip(row.cells, widths, values)):
            configure_cell(cell, width, borderless=False)
            _set_cell_lines(cell, (value,), centered=(index == 0))


def add_letter_title(doc: docx.Document, title: str) -> None:
    add_text_paragraph(
        doc,
        title,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        size_pt=TITLE_FONT_SIZE_PT,
        bold=True,
        underline=True,
        space_before_pt=10,
        keep_with_next=True,
    )
    add_text_paragraph(
        doc,
        "Nomor: {{ nomor_surat }}",
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_after_pt=8,
        keep_with_next=True,
    )


def add_recipient(doc: docx.Document, name: str, address: str) -> None:
    add_text_paragraph(doc, "Yth. " + name, space_before_pt=6, keep_with_next=True)
    add_text_paragraph(doc, address, space_after_pt=8, keep_with_next=True)


def add_correspondence_metadata(doc: docx.Document) -> None:
    add_text_paragraph(
        doc,
        "Wonosari, {{ tanggal_surat }}",
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
        keep_with_next=True,
    )
    add_key_value_table(
        doc,
        (
            ("Nomor", "{{ nomor_surat }}"),
            ("Sifat", "{{ sifat }}"),
            ("Lampiran", "{{ lampiran }}"),
            ("Perihal", "{{ perihal }}"),
        ),
    )


def build_special_layout(doc: docx.Document, spec: TemplateSpec) -> None:
    if spec.layout == "surat_tugas":
        add_letter_title(doc, "SURAT PERINTAH / SURAT TUGAS")
        add_key_value_table(doc, (("Dasar", "{{ dasar }}"),))
        add_text_paragraph(
            doc,
            "MEMERINTAHKAN:",
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            bold=True,
            space_before_pt=8,
            space_after_pt=4,
            keep_with_next=True,
        )
        add_text_paragraph(doc, "Kepada:", bold=True, keep_with_next=True)
        add_people_table(doc, category="guru", compact_identity=True)
        add_text_paragraph(doc, "Untuk:", bold=True, space_before_pt=6, keep_with_next=True)
        add_key_value_table(
            doc,
            (
                ("Uraian Perintah", "{{ keperluan }}"),
                ("Tanggal Mulai", "{{ tanggal_mulai }}"),
                ("Tanggal Selesai", "{{ tanggal_selesai }}"),
                ("Waktu", "{{ waktu }}"),
                ("Tempat", "{{ tempat_kegiatan }}"),
            ),
        )
        add_text_paragraph(doc, spec.closing, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before_pt=8)
        add_signature(doc)
        return

    if spec.layout in {"pengantar_umum", "pengantar_cuti"}:
        add_text_paragraph(doc, "Wonosari, {{ tanggal_surat }}", alignment=WD_ALIGN_PARAGRAPH.RIGHT)
        add_recipient(doc, "{{ tujuan }}", "{{ alamat_tujuan }}")
        add_letter_title(doc, spec.title)
        item = "{{ jenis_barang }}"
        if spec.layout == "pengantar_cuti":
            item = (
                "Usulan {{ jenis_cuti }} atas nama {{ nama }}\n"
                "NIP. {{ nip }}\nJabatan: {{ jabatan }}\nGolongan: {{ golongan }}"
            )
        add_bordered_table(
            doc,
            ("No.", "Jenis Dokumen / Barang", "Jumlah", "Keterangan"),
            (("1", item, "{{ jumlah_barang }}", "{{ keterangan_pengantar }}"),),
            (650, 4171, 1250, 3000),
        )
        add_text_paragraph(doc, "Diterima tanggal: ................................", space_before_pt=8)
        add_signature(doc)
        return

    if spec.layout == "permohonan_penceramah":
        add_correspondence_metadata(doc)
        add_recipient(doc, "{{ penerima }}", "{{ alamat_penerima }}")
        add_text_paragraph(doc, "Dengan hormat,", keep_with_next=True)
        add_text_paragraph(doc, "{{ latar_kegiatan }}", alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
        add_text_paragraph(
            doc,
            "Sehubungan dengan itu, kami mengharapkan kesediaan Bapak/Ibu untuk menjadi penceramah pada kegiatan yang akan dilaksanakan pada:",
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            keep_with_next=True,
        )
        add_key_value_table(
            doc,
            (
                ("Hari", "{{ hari }}"),
                ("Tanggal", "{{ tanggal_kegiatan }}"),
                ("Waktu", "{{ waktu }}"),
                ("Tempat", "{{ tempat_kegiatan }}"),
            ),
        )
        add_text_paragraph(doc, spec.closing, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before_pt=6)
        add_signature(doc)
        return

    if spec.layout == "keterangan_kehilangan":
        add_letter_title(doc, spec.title)
        add_text_paragraph(doc, spec.opening, keep_with_next=True)
        add_key_value_table(
            doc,
            (
                ("Nama", "{{ penandatangan_nama }}"),
                ("Jabatan", "{{ penandatangan_jabatan }}"),
                ("Nama Sekolah", "SMA Negeri 2 Wonosari"),
            ),
        )
        add_text_paragraph(
            doc,
            "Dengan ini menerangkan bahwa siswa di bawah ini benar terdaftar di SMA Negeri 2 Wonosari dan melaporkan kehilangan {{ barang_hilang }}:",
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_before_pt=6,
            keep_with_next=True,
        )
        add_key_value_table(
            doc,
            (
                ("Nama", "{{ nama }}"),
                ("NIS / NISN", "{{ nis }} / {{ nisn }}"),
                ("Kelas", "{{ kelas }}"),
                ("Tempat, Tanggal Lahir", "{{ tempat_tanggal_lahir }}"),
                ("Jenis Kelamin", "{{ jenis_kelamin_lengkap }}"),
                ("Nomor Rekening", "{{ nomor_rekening }}"),
                ("Nama Ibu Kandung", "{{ nama_ibu_kandung }}"),
                ("Keperluan", "{{ keperluan }}"),
            ),
        )
        add_text_paragraph(doc, spec.closing, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before_pt=6)
        add_signature(doc)
        return

    if spec.layout == "rekomendasi_murid":
        add_letter_title(doc, spec.title)
        add_text_paragraph(doc, spec.opening, keep_with_next=True)
        add_key_value_table(
            doc,
            (
                ("Nama", "{{ penandatangan_nama }}"),
                ("NIP", "{{ penandatangan_id }}"),
                ("Jabatan", "{{ penandatangan_jabatan }}"),
            ),
        )
        add_text_paragraph(
            doc,
            "Merekomendasikan siswa tersebut di bawah ini untuk mengikuti {{ nama_kegiatan }}:",
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_before_pt=6,
            keep_with_next=True,
        )
        add_people_table(doc, category="murid")
        add_text_paragraph(doc, "Kontak peserta (bila dipersyaratkan): {{ kontak_peserta }}", space_before_pt=6)
        add_text_paragraph(doc, "Guru pendamping yang ditugaskan adalah:", keep_with_next=True)
        add_key_value_table(
            doc,
            (
                ("Nama Guru", "{{ guru_pendamping }}"),
                ("NIP", "{{ nip_guru_pendamping }}"),
                ("Email", "{{ email_guru_pendamping }}"),
                ("Nomor HP", "{{ telepon_guru_pendamping }}"),
            ),
        )
        add_text_paragraph(doc, "{{ keperluan }}", alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before_pt=6)
        add_text_paragraph(doc, spec.closing, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
        add_signature(doc)
        return

    if spec.layout == "undangan":
        add_correspondence_metadata(doc)
        add_recipient(doc, "{{ penerima }}", "{{ alamat_penerima }}")
        add_text_paragraph(doc, spec.opening, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, keep_with_next=True)
        add_key_value_table(
            doc,
            (
                ("Hari", "{{ hari }}"),
                ("Tanggal", "{{ tanggal_kegiatan }}"),
                ("Waktu", "{{ waktu }}"),
                ("Tempat", "{{ tempat_kegiatan }}"),
                ("Acara", "{{ acara }}"),
            ),
        )
        add_text_paragraph(doc, spec.closing, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before_pt=6)
        add_signature(doc)
        return

    raise RuntimeError(f"Layout template tidak dikenal: {spec.layout}")


def add_signature(doc: docx.Document) -> None:
    signature_indent_cm = 9.0
    add_text_paragraph(
        doc,
        "Wonosari, {{ tanggal_surat }}",
        space_before_pt=8,
        keep_with_next=True,
        left_indent_cm=signature_indent_cm,
    )
    add_text_paragraph(
        doc,
        "{{ penandatangan_jabatan }}",
        keep_with_next=True,
        left_indent_cm=signature_indent_cm,
    )
    add_text_paragraph(
        doc,
        "\n\n",
        keep_with_next=True,
        left_indent_cm=signature_indent_cm,
    )
    add_text_paragraph(
        doc,
        "{{ penandatangan_nama }}",
        bold=True,
        underline=True,
        keep_with_next=True,
        left_indent_cm=signature_indent_cm,
    )

    # Tag {%p ... %} menghapus paragraf kontrolnya saat docxtpl merender.
    add_text_paragraph(
        doc,
        "{%p if penandatangan_id %}",
        left_indent_cm=signature_indent_cm,
    )
    add_text_paragraph(
        doc,
        "{{ penandatangan_id_label }} {{ penandatangan_id }}",
        left_indent_cm=signature_indent_cm,
    )
    add_text_paragraph(
        doc,
        "{%p endif %}",
        left_indent_cm=signature_indent_cm,
    )


def build_template(spec: TemplateSpec) -> Path:
    target = ACTIVE_TEMPLATE_DIR / spec.filename
    if target.resolve() == MASTER_DOC.resolve():
        raise RuntimeError("Master immutable tidak boleh menjadi target output.")

    doc = docx.Document(MASTER_DOC)
    retain_kop_only(doc)
    configure_default_font(doc)
    configure_page(doc)

    if spec.layout != "standard":
        build_special_layout(doc, spec)
    else:
        add_letter_title(doc, spec.title)
        add_text_paragraph(
            doc,
            spec.opening,
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_after_pt=6,
            keep_with_next=True,
        )
        if spec.multi_people:
            add_people_table(doc, category="murid")
            add_text_paragraph(doc, "Rincian kegiatan:", space_before_pt=6, keep_with_next=True)
        add_key_value_table(doc, spec.rows)
        add_text_paragraph(
            doc,
            spec.closing,
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_before_pt=8,
            space_after_pt=4,
        )
        add_signature(doc)

    doc.core_properties.author = "SMAN 2 Wonosari"
    doc.core_properties.last_modified_by = "E-Surat SMADA"
    doc.save(target)
    return target


def _variables_in(values: Iterable[str]) -> set[str]:
    variables: set[str] = set()
    for value in values:
        variables.update(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)", value))
    return variables


def expected_variables(spec: TemplateSpec) -> set[str]:
    source_values = [spec.title, spec.opening, spec.closing, "{{ nomor_surat }}"]
    source_values.extend(value for _, value in spec.rows)
    variables = _variables_in(source_values)
    variables.update(spec.field_names)
    variables.update(spec.extra_variables)
    if spec.multi_people:
        variables.add("people")
    variables.update(
        {
            "tanggal_surat",
            "penandatangan_jabatan",
            "penandatangan_nama",
            "penandatangan_id_label",
            "penandatangan_id",
        }
    )
    return variables


def audit_template(path: Path, spec: TemplateSpec) -> None:
    doc = docx.Document(path)
    expected_rows = spec.expected_table_rows or (
        (4, len(spec.rows)) if spec.multi_people else (len(spec.rows),)
    )
    actual_rows = tuple(len(table.rows) for table in doc.tables)
    if actual_rows != expected_rows:
        raise RuntimeError(
            f"{path.name}: baris tabel {actual_rows}, seharusnya {expected_rows}."
        )

    with zipfile.ZipFile(path) as package:
        document_xml = package.read("word/document.xml").decode("utf-8")

    actual_variables = set(DocxTemplate(str(path)).get_undeclared_template_variables())
    if actual_variables != expected_variables(spec):
        missing = sorted(expected_variables(spec) - actual_variables)
        unexpected = sorted(actual_variables - expected_variables(spec))
        raise RuntimeError(f"{path.name}: variabel hilang={missing}, tak dikenal={unexpected}.")

    drawing_count = document_xml.count("<w:drawing")
    if drawing_count != 1:
        raise RuntimeError(f"{path.name}: kop harus memiliki satu drawing; ditemukan {drawing_count}.")

    for table_index, table in enumerate(doc.tables, start=1):
        table_xml = table._tbl.xml
        tbl_width = re.search(r'<w:tblW\b[^>]*\bw:w="(\d+)"', table_xml)
        grid_widths = tuple(
            int(value) for value in re.findall(r'<w:gridCol w:w="(\d+)"', table_xml)
        )
        first_row = re.search(r"<w:tr(?:\s[^>]*)?>.*?</w:tr>", table_xml, re.DOTALL)
        cell_widths = ()
        if first_row:
            cell_widths = tuple(
                int(value)
                for value in re.findall(r'<w:tcW\b[^>]*\bw:w="(\d+)"', first_row.group(0))
            )
        if not tbl_width or int(tbl_width.group(1)) != sum(grid_widths):
            raise RuntimeError(f"{path.name}: tblW tabel {table_index} tidak konsisten.")
        if not grid_widths or cell_widths != grid_widths:
            raise RuntimeError(
                f"{path.name}: geometri tabel {table_index} grid={grid_widths}, cell={cell_widths}."
            )
    if "<w:trHeight" in document_xml:
        raise RuntimeError(f"{path.name}: ditemukan fixed row height.")


def package_content_hash(path: Path) -> str:
    """Hash isi entry ZIP; timestamp container ZIP sengaja diabaikan."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as package:
        for name in sorted(package.namelist()):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(package.read(name))
            digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    if not MASTER_DOC.exists():
        raise FileNotFoundError(f"Master template tidak ditemukan: {MASTER_DOC}")
    if MASTER_DOC.name in {spec.filename for spec in TEMPLATE_SPECS}:
        raise RuntimeError("Master immutable tercantum sebagai output.")

    master_hash = package_content_hash(MASTER_DOC)
    for spec in TEMPLATE_SPECS:
        target = build_template(spec)
        audit_template(target, spec)
        print(f"[OK] {target.name}: struktur, geometri, dan placeholder valid.")

    if package_content_hash(MASTER_DOC) != master_hash:
        raise RuntimeError("Master immutable berubah selama build.")
    print("[OK] Master immutable tidak berubah.")


if __name__ == "__main__":
    main()
