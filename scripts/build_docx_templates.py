"""
Script Pembuatan & Pembaruan Template Dokumen (.docx) Resmi SMADA
===================================================================
Memastikan SELURUH TERTULIS dalam Font Times New Roman 12pt dengan Kop Surat Resmi SMAN 2 Wonosari utuh.
- Tanpa bullet points (titik) di samping kiri label.
- Menggunakan Tabel Tanpa Garis agar Tanda Titik Dua (:) SEJAJAR sempurna secara vertikal.

Cara jalankan:
    python scripts/build_docx_templates.py
"""
from pathlib import Path
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

BASE_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = BASE_DIR / "templates_surat"
MASTER_DOC = TEMPLATE_DIR / "11. Surat Keterangan-smada.docx"

def remove_cell_borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for border_name in ['top', 'left', 'bottom', 'right']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'none')
        tcBorders.append(border)
    tcPr.append(tcBorders)

def update_docx_body(target_filename: str, title: str, subtitle_no: str, opening_text: str, kv_pairs: list, closing_text: str):
    doc = docx.Document(MASTER_DOC)

    # Set default style to Times New Roman 12pt
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Times New Roman'
    style_normal.font.size = docx.shared.Pt(12)

    # Paragraph 4: Title
    p_title = doc.paragraphs[4]
    p_title.text = title
    p_title.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
    if p_title.runs:
        r = p_title.runs[0]
        r.bold = True
        r.font.size = docx.shared.Pt(14)
        r.font.name = "Times New Roman"

    # Paragraph 5: Nomor
    p_no = doc.paragraphs[5]
    p_no.text = subtitle_no
    p_no.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
    if p_no.runs:
        r = p_no.runs[0]
        r.font.size = docx.shared.Pt(12)
        r.font.name = "Times New Roman"

    # Delete old body paragraphs from index 6 onwards
    while len(doc.paragraphs) > 6:
        p_old = doc.paragraphs[6]
        p_element = p_old._element
        p_element.getparent().remove(p_element)

    # Opening Paragraph
    p_open = doc.add_paragraph()
    p_open.paragraph_format.space_before = docx.shared.Pt(8)
    p_open.paragraph_format.space_after = docx.shared.Pt(6)
    p_open.paragraph_format.line_spacing = 1.15
    r_open = p_open.add_run(opening_text)
    r_open.font.name = "Times New Roman"
    r_open.font.size = docx.shared.Pt(12)

    # Key-Value Pairs Table (Borderless, Perfectly Aligned Colons)
    table = doc.add_table(rows=len(kv_pairs), cols=3)
    table.alignment = docx.enum.table.WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [docx.shared.Cm(5.2), docx.shared.Cm(0.4), docx.shared.Cm(10.4)]

    for idx, (label, val) in enumerate(kv_pairs):
        row_cells = table.rows[idx].cells

        # Cell 0: Label
        p0 = row_cells[0].paragraphs[0]
        p0.paragraph_format.line_spacing = 1.15
        p0.paragraph_format.space_after = docx.shared.Pt(3)
        r0 = p0.add_run(label)
        r0.font.name = "Times New Roman"
        r0.font.size = docx.shared.Pt(12)

        # Cell 1: Colon :
        p1 = row_cells[1].paragraphs[0]
        p1.paragraph_format.line_spacing = 1.15
        p1.paragraph_format.space_after = docx.shared.Pt(3)
        r1 = p1.add_run(":")
        r1.font.name = "Times New Roman"
        r1.font.size = docx.shared.Pt(12)

        # Cell 2: Value
        p2 = row_cells[2].paragraphs[0]
        p2.paragraph_format.line_spacing = 1.15
        p2.paragraph_format.space_after = docx.shared.Pt(3)
        r2 = p2.add_run(val)
        r2.font.name = "Times New Roman"
        r2.font.size = docx.shared.Pt(12)
        if label in ["Nama", "Nama Siswa", "NIP", "NIS"]:
            r2.bold = True

        for c_idx, cell in enumerate(row_cells):
            cell.width = col_widths[c_idx]
            remove_cell_borders(cell)

    # Closing Paragraph
    p_close = doc.add_paragraph()
    p_close.paragraph_format.space_before = docx.shared.Pt(8)
    p_close.paragraph_format.space_after = docx.shared.Pt(12)
    p_close.paragraph_format.line_spacing = 1.15
    r_close = p_close.add_run(closing_text)
    r_close.font.name = "Times New Roman"
    r_close.font.size = docx.shared.Pt(12)

    # Tanda Tangan Footer
    p_ttd = doc.add_paragraph()
    p_ttd.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT
    
    r1 = p_ttd.add_run("Wonosari, {{ tanggal_surat }}\n")
    r1.font.name = "Times New Roman"
    r1.font.size = docx.shared.Pt(12)
    
    r2 = p_ttd.add_run("Hormat kami,\n\n\n\n")
    r2.font.name = "Times New Roman"
    r2.font.size = docx.shared.Pt(12)
    
    r3 = p_ttd.add_run("{{ nama }}\n")
    r3.font.name = "Times New Roman"
    r3.font.size = docx.shared.Pt(12)
    r3.bold = True
    
    r4 = p_ttd.add_run("NIP. {{ nip }}")
    r4.font.name = "Times New Roman"
    r4.font.size = docx.shared.Pt(12)

    # Force Times New Roman 12pt across ALL paragraphs
    for p in doc.paragraphs:
        for run in p.runs:
            run.font.name = "Times New Roman"

    target_path = TEMPLATE_DIR / target_filename
    doc.save(target_path)
    print(f"[OK] Template {target_filename} berhasil dibuat dengan tabel tanpa garis & tanda (:) sejajar.")

if __name__ == "__main__":
    # 1. Izin Guru
    update_docx_body(
        "izin_guru.docx",
        "SURAT PERMOHONAN IZIN PEGAWAI",
        "Nomor: {{ nomor_surat }}",
        "Yang bertanda tangan di bawah ini mengajukan permohonan izin tidak masuk kerja:",
        [
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Unit Kerja", "SMA Negeri 2 Wonosari"),
            ("Tanggal Mulai", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai", "{{ tanggal_selesai }}"),
            ("Keperluan / Alasan", "{{ keperluan }}"),
        ],
        "Demikian permohonan izin ini dibuat untuk dapat dipergunakan sebagaimana mestinya."
    )

    # 2. Cuti Guru
    update_docx_body(
        "cuti_guru.docx",
        "SURAT PERMOHONAN CUTI PEGAWAI",
        "Nomor: {{ nomor_surat }}",
        "Yang bertanda tangan di bawah ini mengajukan permohonan cuti pegawai:",
        [
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
        ],
        "Demikian permohonan cuti ini disampaikan untuk pertimbangan lebih lanjut."
    )

    # 3. Sakit Guru
    update_docx_body(
        "sakit_guru.docx",
        "SURAT PEMBERITAHUAN SAKIT",
        "Nomor: {{ nomor_surat }}",
        "Memberitahukan bahwa pegawai bersangkutan tidak dapat melaksanakan tugas karena sakit:",
        [
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Tanggal Mulai Sakit", "{{ tanggal_mulai }}"),
            ("Sampai Tanggal", "{{ tanggal_selesai }}"),
            ("Keterangan Sakit", "{{ keperluan }}"),
        ],
        "Demikian surat pemberitahuan sakit ini dibuat dengan sebenarnya."
    )

    # 4. Surat Tugas Guru
    update_docx_body(
        "3. Surat Tugas-smada.docx",
        "SURAT TUGAS PENUGASAN",
        "Nomor: {{ nomor_surat }}",
        "Kepala SMA Negeri 2 Wonosari dengan ini menugaskan kepada:",
        [
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Tanggal Tugas", "{{ tanggal_mulai }}"),
            ("Sampai Tanggal", "{{ tanggal_selesai }}"),
            ("Uraian / Keperluan Tugas", "{{ keperluan }}"),
        ],
        "Demikian surat tugas ini diberikan untuk dilaksanakan dengan penuh rasa tanggung jawab."
    )

    # 5. Surat Keterangan Guru
    update_docx_body(
        "11. Surat Keterangan-smada.docx",
        "SURAT KETERANGAN RESMI",
        "Nomor: {{ nomor_surat }}",
        "Kepala SMA Negeri 2 Wonosari dengan ini menerangkan bahwa:",
        [
            ("Nama", "{{ nama }}"),
            ("NIP", "{{ nip }}"),
            ("Pangkat / Golongan", "{{ golongan }}"),
            ("Jabatan", "{{ jabatan }}"),
            ("Terhitung Mulai Tgl", "{{ tanggal_mulai }}"),
            ("Menerangkan Bahwa", "{{ keperluan }}"),
        ],
        "Demikian surat keterangan ini dibuat dengan sebenarnya untuk dapat dipergunakan sebagaimana mestinya."
    )

    # 6. Izin Murid
    update_docx_body(
        "izin_murid.docx",
        "SURAT IZIN SISWA",
        "Nomor: {{ nomor_surat }}",
        "Memberitahukan bahwa siswa bersangkutan mengajukan izin tidak mengikuti KBM:",
        [
            ("Nama Siswa", "{{ nama }}"),
            ("NIS / NISN", "{{ nis }} / {{ nisn }}"),
            ("Kelas", "Kelas {{ kelas }}"),
            ("Tanggal Mulai Izin", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai Izin", "{{ tanggal_selesai }}"),
            ("Alasan Izin", "{{ keperluan }}"),
            ("Orang Tua / Wali", "{{ nama_wali }}"),
        ],
        "Demikian surat izin ini disampaikan agar menjadi maklum."
    )

    # 7. Dispensasi Murid
    update_docx_body(
        "dispensasi_murid.docx",
        "SURAT DISPENSASI SISWA",
        "Nomor: {{ nomor_surat }}",
        "Kepala SMA Negeri 2 Wonosari memberikan dispensasi kepada siswa:",
        [
            ("Nama Siswa", "{{ nama }}"),
            ("NIS / NISN", "{{ nis }} / {{ nisn }}"),
            ("Kelas", "Kelas {{ kelas }}"),
            ("Nama Kegiatan", "{{ nama_kegiatan }}"),
            ("Penyelenggara", "{{ penyelenggara }}"),
            ("Tempat Kegiatan", "{{ tempat_kegiatan }}"),
            ("Tanggal Mulai", "{{ tanggal_mulai }}"),
            ("Tanggal Selesai", "{{ tanggal_selesai }}"),
            ("Uraian / Keperluan", "{{ keperluan }}"),
        ],
        "Demikian surat dispensasi ini dibuat untuk dipergunakan sebagaimana mestinya."
    )
