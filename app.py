"""
E-Surat SMADA - Elektronik Persuratan SMAN 2 Wonosari
=====================================================
Sistem Informasi Persuratan Resmi Siap Digunakan oleh Tata Usaha (TU) & Guru.

Cara jalankan:
    pip install -r requirements.txt
    python app.py
Lalu buka http://localhost:5000 di browser.
"""
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from docxtpl import DocxTemplate
from flask import Flask, render_template, request, send_file, jsonify

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "templates_surat"
DB_PATH = DATA_DIR / "surat_smada.db"

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Inisialisasi Database SQLite untuk Riwayat Surat Log TU
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS riwayat_surat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        jenis_surat TEXT,
        nomor_surat TEXT,
        nama_pemohon TEXT,
        id_pemohon TEXT,
        kategori TEXT,
        keperluan TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

def log_riwayat_surat(jenis_surat, nomor_surat, nama_pemohon, id_pemohon, kategori, keperluan):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now_str = datetime.now().strftime("%d-%m-%Y %H:%M")
        c.execute("""INSERT INTO riwayat_surat 
            (created_at, jenis_surat, nomor_surat, nama_pemohon, id_pemohon, kategori, keperluan)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now_str, jenis_surat, nomor_surat, nama_pemohon, id_pemohon, kategori, keperluan))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[WARN] Gagal mencatat riwayat surat:", e)

# ---------------------------------------------------------------------------
# Load Data Guru, Murid, dan Kode Klasifikasi Arsip
# ---------------------------------------------------------------------------
def load_json(name):
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))

GURU = load_json("guru.json")
MURID = load_json("murid.json")
KODE_ARSIP = load_json("kode_arsip.json")

GURU_BY_NIP = {g["nip"]: g for g in GURU}
MURID_BY_NIS = {m["nis"]: m for m in MURID}

BULAN_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

def format_tanggal_indo(iso_date: str) -> str:
    """'2026-08-22' -> '22 Agustus 2026'."""
    if not iso_date:
        return ""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return f"{d.day} {BULAN_ID[d.month]} {d.year}"
    except ValueError:
        return iso_date

# ---------------------------------------------------------------------------
# Master Mapping Jenis Surat SMAN 2 Wonosari (20 Master Template)
# ---------------------------------------------------------------------------
JENIS_SURAT = {
    "izin_guru": {
        "label": "Surat Permohonan Izin",
        "deskripsi": "Permohonan izin tidak masuk kerja bagi Guru / Staff SMADA.",
        "kategori": "guru",
        "icon": "fa-clipboard-user",
        "badge": "Izin Kerja",
        "template": "izin_guru.docx",
        "fields": [
            {"name": "tanggal_mulai", "label": "Tanggal Mulai Izin", "type": "date"},
            {"name": "tanggal_selesai", "label": "Tanggal Selesai Izin", "type": "date"},
            {"name": "keperluan", "label": "Keperluan", "type": "text"},
            {"name": "unit_kerja", "label": "Unit Kerja", "type": "text", "default": "SMA Negeri 2 Wonosari"},
        ],
    },
    "cuti_guru": {
        "label": "Surat Permohonan Cuti",
        "deskripsi": "Permohonan cuti tahunan, sakit, melahirkan, atau alasan penting.",
        "kategori": "guru",
        "icon": "fa-calendar-minus",
        "badge": "Cuti Resmi",
        "template": "cuti_guru.docx",
        "fields": [
            {"name": "jenis_cuti", "label": "Jenis Cuti", "type": "select",
             "options": ["Cuti Tahunan", "Cuti Sakit", "Cuti Melahirkan", "Cuti Besar", "Cuti Alasan Penting"]},
            {"name": "lama_cuti", "label": "Lama Cuti", "type": "text", "placeholder": "cth: 3 hari"},
            {"name": "tanggal_mulai", "label": "Terhitung Mulai Tanggal", "type": "date"},
            {"name": "tanggal_selesai", "label": "Sampai Dengan Tanggal", "type": "date"},
            {"name": "keperluan", "label": "Alasan Cuti", "type": "text"},
            {"name": "alamat_selama_cuti", "label": "Alamat Selama Cuti", "type": "text"},
        ],
    },
    "sakit_guru": {
        "label": "Surat Pemberitahuan Sakit",
        "deskripsi": "Pemberitahuan resmi izin tidak masuk kerja dikarenakan sakit.",
        "kategori": "guru",
        "icon": "fa-user-nurse",
        "badge": "Izin Sakit",
        "template": "sakit_guru.docx",
        "fields": [
            {"name": "tanggal_mulai", "label": "Tanggal Mulai Sakit", "type": "date"},
            {"name": "tanggal_selesai", "label": "Sampai Dengan Tanggal", "type": "date"},
            {"name": "keperluan", "label": "Keterangan Tambahan", "type": "text", "placeholder": "cth: demam tinggi"},
            {"name": "unit_kerja", "label": "Unit Kerja", "type": "text", "default": "SMA Negeri 2 Wonosari"},
        ],
    },
    "surat_tugas_guru": {
        "label": "Surat Tugas Penugasan",
        "deskripsi": "Surat tugas resmi Kepala Sekolah untuk perjalanan / tugas dinas.",
        "kategori": "guru",
        "icon": "fa-briefcase",
        "badge": "Dinas SMADA",
        "template": "3. Surat Tugas-smada.docx",
        "fields": [
            {"name": "tanggal_mulai", "label": "Tanggal Tugas", "type": "date"},
            {"name": "tanggal_selesai", "label": "Sampai Tanggal", "type": "date"},
            {"name": "keperluan", "label": "Uraian Tugas / Dasar", "type": "text"},
        ],
    },
    "surat_keterangan_guru": {
        "label": "Surat Keterangan Resmi",
        "deskripsi": "Surat keterangan aktif / penugasan resmi dari Kepala Sekolah.",
        "kategori": "guru",
        "icon": "fa-file-signature",
        "badge": "Keterangan",
        "template": "11. Surat Keterangan-smada.docx",
        "fields": [
            {"name": "tanggal_mulai", "label": "Tanggal Keterangan", "type": "date"},
            {"name": "keperluan", "label": "Menerangkan Bahwa", "type": "text"},
        ],
    },
    "izin_murid": {
        "label": "Surat Izin Tidak Masuk",
        "deskripsi": "Pemberitahuan izin tidak masuk sekolah dari orang tua / wali murid.",
        "kategori": "murid",
        "icon": "fa-user-graduate",
        "badge": "Izin Siswa",
        "template": "izin_murid.docx",
        "fields": [
            {"name": "nama_wali", "label": "Nama Orang Tua/Wali", "type": "text"},
            {"name": "tanggal_mulai", "label": "Tanggal Mulai Izin", "type": "date"},
            {"name": "tanggal_selesai", "label": "Tanggal Selesai Izin", "type": "date"},
            {"name": "keperluan", "label": "Keperluan/Alasan", "type": "text"},
        ],
    },
    "dispensasi_murid": {
        "label": "Surat Dispensasi Kegiatan",
        "deskripsi": "Izin dispensasi mengikuti kegiatan lomba, OSIS, atau dinas luar.",
        "kategori": "murid",
        "icon": "fa-award",
        "badge": "Dispensasi",
        "template": "dispensasi_murid.docx",
        "fields": [
            {"name": "nama_kegiatan", "label": "Nama Kegiatan", "type": "text"},
            {"name": "penyelenggara", "label": "Penyelenggara", "type": "text"},
            {"name": "tempat_kegiatan", "label": "Tempat Kegiatan", "type": "text"},
            {"name": "tanggal_mulai", "label": "Tanggal Mulai", "type": "date"},
            {"name": "tanggal_selesai", "label": "Tanggal Selesai", "type": "date"},
            {"name": "nama_kepsek", "label": "Nama Kepala Sekolah", "type": "text",
             "default": "ARIS BUDIANTO S.Pd., M.Pd."},
            {"name": "nip_kepsek", "label": "NIP Kepala Sekolah", "type": "text",
             "default": "197303242007011006"},
        ],
    },
}

# ---------------------------------------------------------------------------
# Routes & API Endpoints
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", jenis_surat=JENIS_SURAT)

@app.route("/api/search")
def api_search():
    """Pencarian orang (guru/murid) untuk autocomplete."""
    q = request.args.get("q", "").strip().lower()
    kategori = request.args.get("kategori", "guru")
    if len(q) < 2:
        return jsonify([])

    source = GURU if kategori == "guru" else MURID
    id_field = "nip" if kategori == "guru" else "nis"
    results = []
    for rec in source:
        haystack = f"{rec['nama']} {rec[id_field]}".lower()
        if q in haystack:
            results.append(rec)
        if len(results) >= 15:
            break
    return jsonify(results)

@app.route("/api/list/guru")
def api_list_guru():
    """Return all guru/staff data for directory modal."""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify(GURU)
    filtered = [g for g in GURU if q in f"{g['nama']} {g['nip']} {g['jabatan']}".lower()]
    return jsonify(filtered)

@app.route("/api/list/murid")
def api_list_murid():
    """Return murid data (limit 100 or search) for directory modal."""
    q = request.args.get("q", "").strip().lower()
    kelas = request.args.get("kelas", "").strip().lower()
    results = []
    for m in MURID:
        haystack = f"{m['nama']} {m['nis']} {m['nisn']} {m['kelas']}".lower()
        if q and q not in haystack:
            continue
        if kelas and kelas not in m['kelas'].lower():
            continue
        results.append(m)
        if len(results) >= 100:
            break
    return jsonify(results)

@app.route("/api/list/kode_arsip")
def api_list_kode_arsip():
    """Return list of official SMADA archive classification codes."""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify(KODE_ARSIP[:30])
    filtered = [k for k in KODE_ARSIP if q in f"{k['kode']} {k['keterangan']}".lower()]
    return jsonify(filtered[:30])

@app.route("/api/list/riwayat")
def api_list_riwayat():
    """Return riwayat surat log for Tata Usaha."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM riwayat_surat ORDER BY id DESC LIMIT 50")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify([])

@app.route("/api/fields/<jenis>")
def api_fields(jenis):
    info = JENIS_SURAT.get(jenis)
    if not info:
        return jsonify({"error": "jenis surat tidak ditemukan"}), 404
    return jsonify(info)

def get_surat_context(form_data):
    jenis = form_data.get("jenis_surat")
    info = JENIS_SURAT.get(jenis)
    if not info:
        return None, None, "Jenis surat tidak valid", 400

    id_value = form_data.get("id_value", "").strip()
    kategori = info["kategori"]

    if kategori == "guru":
        person = GURU_BY_NIP.get(id_value)
    else:
        person = MURID_BY_NIS.get(id_value)

    if not person:
        return None, None, f"Data dengan ID '{id_value}' tidak ditemukan di database {kategori}.", 404

    # Konteks dasar dari data guru/murid
    context = dict(person)

    # Field tambahan dari form (tanggal, keperluan, dll)
    for f in info["fields"]:
        val = form_data.get(f["name"], "").strip()
        if f["type"] == "date":
            val = format_tanggal_indo(val)
        context[f["name"]] = val or f.get("default", "")

    # Nomor surat kustom atau otomatis
    today = datetime.now()
    custom_no = form_data.get("nomor_surat_custom", "").strip()
    if custom_no:
        context["nomor_surat"] = custom_no
    else:
        context["nomor_surat"] = f"00.1.2.3/{today.strftime('%m%d')}/SMADA/{today.year}"

    context["tanggal_surat"] = format_tanggal_indo(today.strftime("%Y-%m-%d"))
    return info, context, person, 200

@app.route("/api/preview_render", methods=["POST"])
def api_preview_render():
    info, context, person, code = get_surat_context(request.form)
    if code != 200:
        return jsonify({"error": person}), code

    return jsonify({
        "info": info,
        "context": context,
        "person": person
    })

@app.route("/generate", methods=["POST"])
def generate():
    info, context, person, code = get_surat_context(request.form)
    if code != 200:
        return person, code

    jenis = request.form.get("jenis_surat")
    
    # Log to SQLite DB
    id_field = person.get("nip") or person.get("nis") or ""
    log_riwayat_surat(
        jenis_surat=info["label"],
        nomor_surat=context["nomor_surat"],
        nama_pemohon=person["nama"],
        id_pemohon=id_field,
        kategori=info["kategori"],
        keperluan=context.get("keperluan", "-")
    )

    # Render docx
    template_path = TEMPLATE_DIR / info["template"]
    doc = DocxTemplate(str(template_path))
    doc.render(context)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    nama_file_aman = person["nama"].replace(" ", "_").replace("/", "-")
    filename = f"{jenis}_{nama_file_aman}.docx"

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
