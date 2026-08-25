# E-Surat SMADA

E-Surat SMADA adalah aplikasi internal Tata Usaha untuk membuat DOCX surat dari
data master resmi. Aplikasi memvalidasi identitas, mengalokasikan nomor secara
transaksional, mencatat operator, dan menyediakan riwayat yang dapat dicari,
dibatalkan tanpa memakai ulang nomor, serta diekspor ke CSV.

> **Status rilis:** kode saat ini adalah kandidat **pilot internal terbatas**,
> belum rilis produksi. Data pribadi telah dikeluarkan dari Git index pada
> working tree ini, tetapi data masih pernah masuk history/remote GitHub. History,
> cache, fork, clone, deployment lama, dan respons insiden harus ditangani oleh
> pemilik repository sebelum aplikasi diberikan kepada sekolah. Lihat
> [Audit Produksi](docs/AUDIT_PRODUKSI.md) dan
> [Checklist Rilis](docs/RELEASE_CHECKLIST.md).

## Cakupan fitur

Tujuh dari 25 dokumen bisnis telah menjadi template dinamis:

| Kategori | Jenis surat | Penandatangan |
| --- | --- | --- |
| Guru/staf | Permohonan izin | Pemohon |
| Guru/staf | Permohonan cuti | Pemohon |
| Guru/staf | Pemberitahuan sakit | Pemohon |
| Guru/staf | Surat tugas | Kepala Sekolah |
| Guru/staf | Surat keterangan | Kepala Sekolah |
| Siswa | Izin tidak masuk | Orang tua/wali |
| Siswa | Dispensasi kegiatan | Kepala Sekolah |

Delapan belas DOCX di `templates_surat/legacy/` belum aktif dan tidak boleh
dianggap siap generate. Ringkasan layar juga bukan pratinjau visual Word; DOCX
tetap wajib diperiksa sebelum diterbitkan.

Kontrol yang tersedia pada kandidat ini:

- akun individual dari file privat dengan role `admin`, `operator`, dan
  `reviewer`;
- session 8 jam, login throttling, CSRF, cookie aman, dan retry token CSRF satu
  kali di browser;
- nomor otomatis unik/idempoten pada satu instance SQLite;
- nomor manual hanya untuk admin;
- audit operator, pencarian/filter/pagination riwayat, pembatalan bernomor, dan
  ekspor CSV;
- fail-fast bila data/template/database persisten tidak tersedia;
- CI dengan fixture sintetis dan pemeriksaan agar data operasional tidak masuk
  kembali ke Git.

## Arsitektur yang didukung

Aplikasi didesain untuk **satu proses aplikasi dan satu database SQLite pada disk
persisten**. Dua profil yang didukung:

```text
Satu PC: browser --> http://127.0.0.1:5000
LAN: browser TU --> HTTPS :443 --> Caddy/Nginx/IIS --> 127.0.0.1:5000
```

Vercel/serverless tidak didukung karena filesystem-nya tidak menjamin database
dan counter nomor persisten. Aplikasi sekarang menolak startup di Vercel agar
tidak kehilangan riwayat atau menerbitkan nomor yang salah. Backend port 5000
jangan dibuka langsung ke LAN/Internet.

## Instalasi pengembangan

Persyaratan: Python 3.10+, browser modern, serta Microsoft Word/aplikasi DOCX
yang ditetapkan sekolah untuk pemeriksaan hasil.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`import esurat` tidak membaca data produksi dan tidak membuat database. Aplikasi
baru memuat master dan menginisialisasi database ketika `create_app()`/`app.py`
dijalankan.

## Provision data secara privat

Direkomendasikan memakai root di luar repository:

```text
D:\E-Surat-Private\
|-- source\       # tiga workbook sumber resmi
|-- master\       # tiga JSON hasil import
|-- runtime\      # surat_smada.db
`-- config\       # users.json
```

Atur environment pada konfigurasi service/secret manager:

```powershell
$env:ESURAT_DATA_ROOT='D:\E-Surat-Private'
python scripts/import_excel_data.py          # validasi/check-only
python scripts/import_excel_data.py --write  # publikasi JSON setelah disetujui
```

Nama file workbook default dijelaskan oleh output skrip import. Gunakan
`--guru-file`, `--murid-file`, dan `--kode-file` bila namanya berbeda. Override
`ESURAT_SOURCE_DIR`, `ESURAT_DATA_DIR`, dan `ESURAT_DB_PATH` tersedia untuk tata
letak nonstandar.

## Akun dan secret

Buat hash untuk setiap pengguna pada mesin admin:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash(input('Password: ')))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Simpan akun di `D:\E-Surat-Private\config\users.json`, bukan di Git:

```json
[
  {
    "username": "operator-tu-1",
    "password_hash": "<hash-yang-dihasilkan>",
    "role": "operator",
    "active": true
  },
  {
    "username": "pemeriksa-tu-1",
    "password_hash": "<hash-yang-dihasilkan>",
    "role": "reviewer",
    "active": true
  },
  {
    "username": "admin-esurat",
    "password_hash": "<hash-yang-dihasilkan>",
    "role": "admin",
    "active": true
  }
]
```

Konfigurasi minimum LAN:

```powershell
$env:ESURAT_HOST='127.0.0.1'
$env:ESURAT_PORT='5000'
$env:ESURAT_DATA_ROOT='D:\E-Surat-Private'
$env:ESURAT_USERS_FILE='D:\E-Surat-Private\config\users.json'
$env:ESURAT_SECRET_KEY='<secret-acak-stabil>'
$env:ESURAT_HTTPS='1'
python app.py
```

Jangan mengubah `ESURAT_SECRET_KEY` pada restart biasa. Perubahan secret memang
mengakhiri semua session/token CSRF. Browser menangani token CSRF kedaluwarsa
dengan meminta token baru dan mengulangi satu request; jika session login sudah
berakhir, pengguna tetap harus login ulang. Lihat seluruh variabel di
[.env.example](.env.example).

## Menjalankan dan memeriksa

Untuk evaluasi satu PC, `ESURAT_HOST=127.0.0.1` tanpa autentikasi masih didukung.
Request dari alamat non-loopback akan ditolak.

```powershell
python app.py
```

Buka `http://127.0.0.1:5000` dan cek health lokal di `/healthz`. Endpoint health
tidak menampilkan jumlah guru/siswa dan tetap harus dibatasi pada reverse proxy.

Pemeriksaan kandidat rilis:

```powershell
python scripts/check_no_sensitive_tracking.py
python -m pip check
python -m unittest discover -s tests -v
python scripts/generate_qa_letters.py
python -m compileall app.py esurat scripts tests
node --check static/app.js
```

QA DOCX selalu memakai data sintetis dari `tests/fixtures/`, bukan master
produksi. Workflow CI menjalankan pemeriksaan yang sama pada Python 3.10 dan
3.14. Pemeriksaan Word, Print Preview, printer nyata, HTTPS, backup/restore, dan
rekonsiliasi nomor tetap gate manual sekolah.

## Backup dan pemeliharaan

```powershell
python scripts/backup_data.py
python scripts/backup_data.py --include-excel
python scripts/backup_data.py --output-dir D:\Backup-E-Surat
python scripts/verify_backup.py D:\Backup-E-Surat\surat-smada-YYYYMMDD-HHMMSS
```

Skrip mengikuti `ESURAT_DATA_ROOT` beserta override granular. Verifikator
memeriksa daftar file, ukuran, SHA-256, file tambahan/hilang, dan SQLite
`quick_check`. Backup mengandung
PII: enkripsi, batasi akses, simpan di media terpisah, tetapkan retensi, dan uji
restore. Jangan edit SQLite atau JSON hasil import secara manual.

Untuk rebuild tujuh template aktif:

```powershell
python scripts/build_docx_templates.py
```

Jalankan dalam maintenance window, kemudian ulangi test, QA DOCX, pemeriksaan
Word, dan persetujuan dua orang.

## Dokumentasi

- [Panduan TU](docs/PANDUAN_TU.md) — operasi harian, role, pembatalan, backup,
  restore, dan troubleshooting.
- [Audit Produksi](docs/AUDIT_PRODUKSI.md) — keputusan kesiapan, risiko tersisa,
  dan scope template.
- [Checklist Rilis](docs/RELEASE_CHECKLIST.md) — langkah teknis dan persetujuan
  yang harus selesai sebelum serah terima.
