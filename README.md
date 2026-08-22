# 📄 E-Surat SMADA - Elektronik Persuratan SMAN 2 Wonosari

Aplikasi web modern berbasis **Flask** untuk mempermudah Tata Usaha (TU), Guru, dan Staf SMAN 2 Wonosari dalam meng-generate surat resmi sekolah (`.docx`) secara otomatis, cepat, dan presisi.

---

## 📁 Struktur Direktori Projek

```text
surat-app/
├── app.py                          # Application entry point (Server Flask)
├── requirements.txt                # Dependensi pustaka Python
├── README.md                       # Petunjuk penggunaan aplikasi
├── data/                           # Database & Master Excel
│   ├── master_excel/               # Tempat menyimpan file Excel mentah sekolah
│   │   ├── nomonatif guru peg sma2 2026.xlsx
│   │   ├── 2627=daftar_murid=v1.3.xlsx
│   │   └── KODE KLASIFIKASI ARSIP-SMAN 2 WONOSARI 2025.xlsx
│   ├── guru.json                   # Database JSON Guru & Staff (50 Orang)
│   ├── murid.json                  # Database JSON Siswa & Murid (750 Siswa)
│   └── kode_arsip.json             # Database JSON Kode Klasifikasi Arsip (146 Kode)
├── scripts/                        # Utility & Data Processing Scripts
│   ├── import_excel_data.py        # Script mengimpor data dari Excel ke JSON
│   └── build_docx_templates.py     # Script merekonstruksi template Word resmi SMADA
├── templates_surat/                # Template dokumen (.docx) resmi sekolah
│   ├── 1. Surat Keputusan-smada.docx
│   ├── 3. Surat Tugas-smada.docx
│   ├── 11. Surat Keterangan-smada.docx
│   ├── izin_guru.docx
│   ├── cuti_guru.docx
│   ├── sakit_guru.docx
│   ├── izin_murid.docx
│   └── dispensasi_murid.docx
├── static/                         # Assets Statis
│   ├── style.css                   # Responsive SAAS Design System (Light/Dark Theme)
│   └── logo_smada.jpg              # Logo Resmi SMAN 2 Wonosari
└── templates/                      # Template UI HTML
    └── index.html                  # Antarmuka Dashboard Utama
```

---

## 🚀 Cara Menjalankan Aplikasi

1. **Install Pustaka Dependensi**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Jalankan Aplikasi Flask**:
   ```bash
   python app.py
   ```

3. **Buka Aplikasi di Browser**:
   Buka URL: **`http://localhost:5000`**

---

## ⚙️ Script Pemeliharaan Data & Template

- **Mengimpor Data Excel Baru**:
  Jika ada perubahan data Guru, Murid, atau Kode Arsip pada file Excel di `data/master_excel/`, jalankan:
  ```bash
  python scripts/import_excel_data.py
  ```

- **Merekonstruksi Template Dokumen (.docx)**:
  Jika ingin memperbarui format Jinja tag pada template `.docx` di `templates_surat/`, jalankan:
  ```bash
  python scripts/build_docx_templates.py
  ```

---

## ✨ Fitur-Fitur Utama

1. **Dashboard SAAS Modern & Fully Responsive**: Tampilan elegan di PC/Laptop, Tablet, dan Ponsel dengan penyesuaian otomatis.
2. **Pencarian Autocomplete Instan**: Mencari NIP, Nama Guru, NIS, NISN, atau Nama Siswa secara *real-time*.
3. **Modal Direktori Interaktif**:
   - Direktori Data Guru & Staff (Lengkap dengan NIP, Golongan, Status Pegawai, TTL).
   - Direktori Data Siswa & Murid (Lengkap dengan NIS, NISN, Kelas, Gender, Agama).
   - Direktori Kode Klasifikasi Arsip (146 Kode Klasifikasi Resmi Surat SMADA 2025).
4. **Modal Pratinjau Surat Sebelum Unduh**: Pop-up pratinjau surat resmi dengan Kop Surat SMAN 2 Wonosari sebelum file `.docx` diunduh.
5. **Dukungan Mode Terang & Gelap (Light / Dark Theme)**.
