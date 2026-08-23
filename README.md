# E-Surat SMADA

E-Surat SMADA adalah aplikasi web internal untuk membuat surat Tata Usaha dari data master guru/staf, siswa, kode arsip, dan template Microsoft Word. Operator memilih jenis surat, memilih orang berdasarkan identitas resminya, mengisi kebutuhan surat, lalu mengunduh DOCX untuk diperiksa sebelum dicetak atau diarsipkan.

> **Peringatan data pribadi:** JSON, Excel, SQLite, dan hasil QA dapat memuat NIP, NIS/NISN, biodata, serta riwayat surat. Audit menemukan repository GitHub publik, deployment Vercel aktif, dan endpoint data dapat diakses tanpa autentikasi. Anggap ini insiden paparan sampai repository, deployment, history, cache, fork, dan clone ditangani. Aturan `.gitignore` baru tidak membersihkan salinan lama. Jangan gunakan aplikasi untuk produksi sebelum prosedur [P0 pada Audit Produksi](docs/AUDIT_PRODUKSI.md#p0-data-pribadi-di-git-dan-github) selesai.

## Status dan cakupan

Aplikasi saat ini memiliki **7 template otomatis aktif dari 25 dokumen bisnis**. Terdapat satu DOCX tambahan sebagai master teknis kop, sehingga inventaris fisik berjumlah 26 DOCX. Hanya tujuh jenis berikut yang ditampilkan dan didukung alur generate:

| Kategori | Jenis surat | Berkas aktif |
| --- | --- | --- |
| Guru/staf | Permohonan izin | `izin_guru.docx` |
| Guru/staf | Permohonan cuti | `cuti_guru.docx` |
| Guru/staf | Pemberitahuan sakit | `sakit_guru.docx` |
| Guru/staf | Surat tugas | `3. Surat Tugas-smada.docx` |
| Guru/staf | Surat keterangan | `11. Surat Keterangan-smada.docx` |
| Siswa | Izin tidak masuk | `izin_murid.docx` |
| Siswa | Dispensasi kegiatan | `dispensasi_murid.docx` |

**Delapan belas DOCX lainnya belum dimigrasikan menjadi template dinamis dan tidak boleh dianggap siap generate.** Salinan sumber kop berada di `templates_surat/master/kop_smada.docx`; dokumen legacy `13. Pengumuman-smada.docx` bukan jenis surat aktif.

Kesiapan yang direkomendasikan saat ini adalah **pilot internal terbatas**, setelah seluruh blocker P0/P1 dalam [docs/AUDIT_PRODUKSI.md](docs/AUDIT_PRODUKSI.md) ditutup. Hasil "Ringkasan Data" di antarmuka bukan render visual DOCX; dokumen hasil tetap wajib dibuka dan diperiksa di Word sebelum diterbitkan.

## Struktur proyek

```text
surat-app/
|-- app.py                         # entry point WSGI/Waitress
|-- esurat/                        # package backend per tanggung jawab
|   |-- application.py             # factory dan route Flask
|   |-- config.py                  # path, batas, timezone, regex
|   |-- database.py                # migrasi, nomor, dan riwayat
|   |-- letters.py                 # validasi dan context surat
|   |-- master_data.py             # validasi JSON/template
|   |-- registry.py                # definisi tujuh jenis surat
|   |-- rendering.py               # render dan inspeksi DOCX
|   |-- security.py                # auth, CSRF, local-only
|   `-- utils.py                   # helper teks dan tanggal
|-- data/
|   |-- source/                    # Excel resmi; privat/ignored
|   |-- master/                    # JSON hasil import; privat/ignored
|   `-- runtime/                   # SQLite; privat/ignored
|-- templates_surat/
|   |-- active/                    # 7 template aktif
|   |-- legacy/                    # 18 referensi belum aktif
|   `-- master/kop_smada.docx      # sumber teknis builder
|-- templates/ dan static/         # UI Flask
|-- scripts/                       # import, build, backup, QA
|-- tests/fixtures/                # data uji sintetis tanpa PII
|-- docs/                          # audit dan panduan operator
`-- qa/ dan backups/               # artefak lokal, tidak di-Git
```

`import esurat` tidak membaca data produksi atau membuat database. Hanya `app.py` yang membuat instance aplikasi untuk deployment; test menyuntikkan fixture sintetis.

## Persyaratan

- Python 3.10 atau lebih baru.
- Microsoft Word atau aplikasi kompatibel DOCX untuk pemeriksaan akhir dan cetak.
- Browser modern.
- Untuk akses LAN: nama pengguna, hash kata sandi, secret sesi stabil, reverse proxy HTTPS, dan firewall.

## Instalasi dan uji lokal

Contoh PowerShell dari root proyek:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/import_excel_data.py
python app.py
```

Buka `http://127.0.0.1:5000`. Perintah import tanpa `--write` hanya memeriksa data dan tidak mengubah berkas.

Konfigurasi bawaan mengikat aplikasi ke loopback (`127.0.0.1`) tanpa autentikasi. Dalam mode ini permintaan non-lokal ditolak. Ini cocok untuk evaluasi di satu komputer, bukan untuk layanan LAN.

Untuk Linux/macOS, aktivasi virtual environment dengan `source .venv/bin/activate`, lalu gunakan perintah Python yang sama.

## Konfigurasi environment

Daftar variabel tersedia di [.env.example](.env.example). **Aplikasi tidak memuat `.env` secara otomatis**; atur environment pada shell, Windows Service, service manager, atau pemuat environment yang dikelola administrator. Jangan commit nilai rahasia.

| Variabel | Default | Keterangan |
| --- | --- | --- |
| `ESURAT_HOST` | `127.0.0.1` | Alamat bind aplikasi |
| `ESURAT_PORT` | `5000` | Port aplikasi |
| `ESURAT_THREADS` | `4` | Thread Waitress, valid 1-32 |
| `ESURAT_USERNAME` | kosong | Nama pengguna; bersama password mengaktifkan autentikasi |
| `ESURAT_PASSWORD_HASH` | kosong | Hash kata sandi yang direkomendasikan |
| `ESURAT_SECRET_KEY` | kosong | Wajib dan harus stabil saat autentikasi aktif |
| `ESURAT_HTTPS` | `0` | Set `1` bila pengguna mengakses melalui HTTPS |
| `ESURAT_KEPSEK_NIP` | kosong | Opsional bila tepat satu record berjabatan Kepala Sekolah; isi bila perlu memilih secara eksplisit |
| `ESURAT_NUMBER_SUFFIX` | `SMADA` | Sufiks nomor surat, 1-20 karakter |

Buat hash kata sandi dan secret di mesin admin:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash(input('Password TU: ')))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Contoh menjalankan backend untuk reverse proxy HTTPS pada mesin yang sama:

```powershell
$env:ESURAT_HOST='127.0.0.1'
$env:ESURAT_PORT='5000'
$env:ESURAT_THREADS='4'
$env:ESURAT_USERNAME='tu'
$env:ESURAT_PASSWORD_HASH='<hasil-hash>'
$env:ESURAT_SECRET_KEY='<secret-acak-stabil>'
$env:ESURAT_HTTPS='1'
python app.py
```

Arsitektur LAN yang direkomendasikan:

```text
Browser TU --HTTPS:443--> Caddy/Nginx/IIS --HTTP lokal--> 127.0.0.1:5000
```

TLS harus diterminasi oleh reverse proxy dengan sertifikat yang dipercaya. Firewall hanya membuka port 443; jangan paparkan port 5000. Batasi endpoint `/healthz` di reverse proxy/firewall karena endpoint tersebut tidak memerlukan login dan menampilkan status serta jumlah data. Konfigurasikan HSTS di reverse proxy. Bind langsung ke `0.0.0.0` tanpa autentikasi akan ditolak aplikasi; bind langsung dengan autentikasi tetapi HTTP tetap tidak layak produksi karena kredensial dan data tidak terenkripsi.

## Pemeliharaan

### Perbarui data master

```powershell
# 1. Validasi saja; tidak mengubah JSON
python scripts/import_excel_data.py

# 2. Setelah laporan bersih dan backup dibuat
python scripts/import_excel_data.py --write

# 3. Restart aplikasi agar data baru dimuat
```

Gunakan `--guru-file`, `--murid-file`, atau `--kode-file` bila lokasi Excel berbeda. Jangan edit JSON hasil import secara manual.

### Rebuild tujuh template aktif

```powershell
python scripts/build_docx_templates.py
```

Jalankan dalam maintenance window setelah backup/versioning DOCX, lalu restart aplikasi dan periksa hasil ketujuh surat di Word. Skrip ini **tidak** mengaktifkan 18 DOCX lainnya.

### Backup data

```powershell
# JSON dan snapshot SQLite yang konsisten
python scripts/backup_data.py

# Termasuk workbook Excel master
python scripts/backup_data.py --include-excel
```

Backup dibuat di `backups/surat-smada-YYYYMMDD-HHMMSS/` dengan versi layout, mapping restore, dan SHA-256 di `manifest.json`. Folder tersebut mengandung data pribadi: enkripsi, batasi akses, salin ke media terpisah, tetapkan retensi, dan uji restore berkala. Backup ini tidak mencakup source code atau template DOCX.

## Pemeriksaan sebelum pilot

```powershell
python -m compileall app.py esurat scripts tests
python scripts/import_excel_data.py
python -m unittest discover -s tests -v
python scripts/generate_qa_letters.py
python app.py
```

Saat aplikasi hidup, cek `http://127.0.0.1:5000/healthz`. Pada audit 23 Agustus 2026, 15 automated tests dengan data sintetis lulus. Alur browser desktop/mobile juga lulus tanpa error console, dan tujuh hasil QA berhasil dirender satu halaman A4 melalui LibreOffice headless. Microsoft Word, Print Preview, dan sampel cetak oleh petugas tetap menjadi gate karena belum ada CI atau visual regression Word otomatis.

## Dokumentasi

- [Panduan TU](docs/PANDUAN_TU.md): alur operator, pemeliharaan admin, backup, troubleshooting, dan restore.
- [Audit Produksi](docs/AUDIT_PRODUKSI.md): keputusan kesiapan, risiko, kontrol, checklist pilot, dan rencana migrasi template.
