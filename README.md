# E-Surat SMADA

E-Surat SMADA adalah aplikasi internal Tata Usaha untuk membuat surat Word (DOCX) dan PDF dari
data master resmi. Aplikasi memvalidasi identitas, mengalokasikan nomor secara
transaksional, mencatat aktor, dan menyediakan riwayat yang dapat dicari,
dibatalkan tanpa memakai ulang nomor, serta diekspor ke CSV.

> **Status rilis:** kode saat ini adalah kandidat **pilot internal terbatas**,
> belum rilis produksi. Data pribadi telah dikeluarkan dari Git index pada
> working tree ini, tetapi data masih pernah masuk history/remote GitHub. History,
> cache, fork, clone, deployment lama, dan respons insiden harus ditangani oleh
> pemilik repository sebelum aplikasi diberikan kepada sekolah. Lihat
> [Audit Produksi](docs/AUDIT_PRODUKSI.md) dan
> [Checklist Rilis](docs/RELEASE_CHECKLIST.md).

## Cakupan fitur

Tujuh template bawaan telah menjadi template dinamis; administrator juga mendapat
dashboard operasional di `/admin` dan dapat menambahkan template DOCX sendiri dari
halaman `/admin/templates`:

| Kategori | Jenis surat | Penandatangan |
| --- | --- | --- |
| Guru/staf | Permohonan izin | Pemohon |
| Guru/staf | Permohonan cuti | Pemohon |
| Guru/staf | Pemberitahuan sakit | Pemohon |
| Guru/staf | Surat tugas | Kepala Sekolah |
| Guru/staf | Surat keterangan | Kepala Sekolah |
| Siswa | Izin tidak masuk | Orang tua/wali |
| Siswa (1–3 siswa/surat) | Dispensasi kegiatan | Kepala Sekolah |

Delapan belas DOCX di `templates_surat/legacy/` belum aktif dan tidak boleh
dianggap siap generate. Ringkasan layar juga bukan pratinjau visual dokumen;
hasil Word atau PDF tetap wajib diperiksa sebelum diterbitkan.

Kontrol yang tersedia pada kandidat ini:

- role `user` tanpa login untuk membuat surat dan akun privat role `admin` untuk
  riwayat, pembatalan, nomor manual, serta pengelolaan template;
- session admin 8 jam, login throttling, CSRF, cookie aman, dan retry token CSRF
  satu kali di browser;
- nomor otomatis unik/idempoten pada satu instance SQLite atau PostgreSQL;
- nomor manual hanya untuk admin;
- audit aktor, pencarian/filter/pagination riwayat admin, pembatalan bernomor,
  ekspor CSV, dan template tambahan persisten di database privat;
- fail-fast bila data/template/database persisten tidak tersedia;
- unduhan Word dan PDF memakai template, nomor surat, serta entri riwayat yang sama;
- CI dengan fixture sintetis dan pemeriksaan agar data operasional tidak masuk
  kembali ke Git.

## Arsitektur yang didukung

Aplikasi mendukung dua profil penyimpanan:

```text
Lokal/LAN: browser --> HTTPS/reverse proxy --> satu proses Flask --> SQLite persisten
Cloud: browser --> HTTPS Vercel --> Flask Function --> Supabase PostgreSQL
```

SQLite tetap ditujukan untuk satu proses dan tidak boleh ditempatkan pada network
share. Vercel hanya didukung bila `DATABASE_URL` menunjuk PostgreSQL persisten dan
akun admin serta secret stabil aktif. Pengguna umum tetap tidak perlu login.
Tanpa PostgreSQL aplikasi menolak startup;
fallback database demo/sementara sudah dihapus.

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

## Migrasi ke Supabase PostgreSQL

Gunakan **Transaction Pooler** Supabase (port `6543`) untuk runtime Vercel. Simpan
connection string sebagai secret `DATABASE_URL`; jangan menaruh password database
di `.env`, Git, screenshot, atau chat. Driver menonaktifkan named prepared
statements agar kompatibel dengan transaction pooling. Tambahkan
`sslmode=require` pada URI dan pertahankan `ESURAT_AUTO_MIGRATE_DATABASE=0` di
runtime; cold start hanya memverifikasi schema dan tidak menjalankan DDL.

Sebelum migrasi, buat dan verifikasi backup lokal. Script migrasi hanya menerima
target kosong dan menulis master, riwayat, serta seed counter dalam satu transaksi:

```powershell
python scripts/backup_data.py --include-excel
python scripts/verify_backup.py <folder-backup>
python scripts/migrate_sqlite_to_postgres.py --dry-run
$env:DATABASE_URL='<transaction-pooler-secret>'
python scripts/migrate_sqlite_to_postgres.py
Remove-Item Env:DATABASE_URL
```

Tabel berada di schema privat `esurat`, RLS aktif, dan akses Data API untuk
`anon`, `authenticated`, serta `service_role` dicabut. Aplikasi tidak memakai
REST/GraphQL Supabase; Data API sebaiknya dinonaktifkan pada project ini.

Migrasi remote awal ke project **E-Surat-SMADA** selesai diverifikasi pada
29 Agustus 2026: 50 guru, 750 murid, 146 kode arsip, 9 riwayat, dan 3 seed
counter. Uji rollback memastikan counter atomik dan indeks nomor baru bekerja;
data legacy yang sudah terduplikasi tetap dipertahankan sebagai arsip.

Environment minimum Vercel selain `DATABASE_URL`:

```text
ESURAT_SECRET_KEY=<acak-panjang-dan-stabil>
ESURAT_USERNAME=<akun-bootstrap>
ESURAT_PASSWORD_HASH=<hash-werkzeug>
ESURAT_DEFAULT_ROLE=admin
ESURAT_HTTPS=1
ESURAT_NUMBER_SUFFIX=SMADA
ESURAT_AUTO_MIGRATE_DATABASE=0
```

Kredensial bootstrap tunggal dapat dipakai sebagai akun admin. Tidak ada akun
untuk pengguna umum karena role `user` diberikan otomatis tanpa login.

Untuk provisioning awal tanpa menyalin secret ke chat atau command history,
hubungkan folder ke project Vercel lalu jalankan prompt lokal berikut. Script
mengaktifkan role `esurat_runtime` berhak minimum, menguji read/write dengan
rollback, dan menyimpan seluruh environment hanya untuk Production:

```powershell
python scripts/provision_vercel.py --project-ref <project-ref> --region <region>
```

Jalankan seluruh migrasi di `supabase/migrations/` secara berurutan, termasuk
migrasi role runtime dan tabel `custom_templates`, sebelum provisioning. Password
database Supabase hanya dipakai selama proses dan tidak disimpan; password login
admin dipilih oleh administrator pada prompt lokal.

## Akun dan secret

Buat hash untuk setiap administrator pada mesin admin. Script memakai input password
tersembunyi dan konfirmasi sehingga plaintext tidak masuk command history:

```powershell
python scripts/generate_password_hash.py
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Simpan akun di `D:\E-Surat-Private\config\users.json`, bukan di Git:

```json
[
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
berakhir, administrator harus login ulang. Pengguna umum tetap dapat memakai
fitur pembuatan surat. Lihat seluruh variabel di
[.env.example](.env.example).

## Menjalankan dan memeriksa

Untuk evaluasi satu PC, `ESURAT_HOST=127.0.0.1` tanpa akun admin masih didukung.
Mode tersebut tidak menyediakan dashboard admin dan request dari alamat
non-loopback akan ditolak.

```powershell
python app.py
```

Buka `http://127.0.0.1:5000` dan cek health lokal di `/healthz`. Endpoint health
tidak menampilkan jumlah guru/siswa dan tetap harus dibatasi pada reverse proxy.
Pengguna membuat surat langsung dari `/`; administrator memilih **Login Admin**
untuk membuka dashboard `/admin`. Dashboard menampilkan metrik dan aktivitas
surat, status sistem, akses riwayat, ringkasan data master, serta halaman khusus
pengelolaan template di `/admin/templates`.

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
