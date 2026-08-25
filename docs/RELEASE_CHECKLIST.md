# Checklist Rilis dan Serah Terima E-Surat

Checklist ini memisahkan pekerjaan yang sudah diterapkan di kode dari tindakan
yang membutuhkan pemilik repository, administrator server, Tata Usaha, dan
pimpinan sekolah. Jangan menandai kotak tanpa bukti.

## A. Kandidat source code

- [x] Data operasional dikeluarkan dari Git index kandidat.
- [x] CI menolak data/database/workbook operasional yang terlacak.
- [x] Vercel/serverless ditolak dan konfigurasi Vercel dihapus.
- [x] Lokasi data eksternal dan fail-fast persistence tersedia.
- [x] Akun individual/role, audit aktor, login throttling, dan session stabil.
- [x] Pemulihan CSRF satu kali di browser.
- [x] Riwayat search/filter/pagination/CSV dan pembatalan bernomor.
- [x] QA menggunakan fixture sintetis.
- [x] Workflow CI Python 3.10/3.14 tersedia.
- [ ] Review diff oleh maintainer kedua.
- [ ] Tentukan owner dan lisensi source code.
- [ ] Buat versi/tag kandidat setelah seluruh review lulus.

## B. Insiden PII Git/hosting — owner repository

- [ ] Repository dibatasi/private dan deployment lama dihentikan.
- [ ] Branch, tag, PR, artifact, release, Pages, cache, fork, mirror, dan clone
  diinventarisasi.
- [ ] Pimpinan/petugas perlindungan data menerima laporan lingkup dan menentukan
  tindak lanjut.
- [ ] History seluruh ref disanitasi pada maintenance window yang disetujui.
- [ ] Hasil sanitasi direview sebelum force-push.
- [ ] Kolaborator menghapus clone lama dan re-clone repository bersih.
- [ ] Secret/credential yang mungkin terpapar telah dicabut dan diganti.
- [ ] Raw URL, commit lama, cache/platform, dan deployment diverifikasi tidak lagi
  dapat diakses sejauh berada dalam kendali sekolah.
- [ ] Seluruh DOCX aktif/legacy/master diperiksa untuk data contoh, identitas,
  komentar, tracked changes, dan metadata personal sebelum repository bersih
  dipublikasikan kepada pihak lain.
- [ ] Residual risk dan penutupan insiden ditandatangani.

## C. Provision server privat — administrator

- [ ] Satu server/PC dan satu proses aplikasi ditetapkan.
- [ ] `ESURAT_DATA_ROOT` berada di luar checkout Git dengan ACL minimum.
- [ ] Tiga workbook resmi diprovision melalui kanal privat.
- [ ] Import check-only lulus, hasil hitungan direview, lalu `--write` dijalankan.
- [ ] `users.json` privat berisi akun individual aktif; tidak ada akun bersama
  yang tidak dapat ditelusuri.
- [ ] Secret acak stabil dipasang; file konfigurasi tidak dapat dibaca pengguna
  biasa.
- [ ] Reverse proxy HTTPS, sertifikat tepercaya, HSTS, dan firewall diuji.
- [ ] Port backend 5000 tidak dapat dijangkau langsung dari LAN.
- [ ] `/healthz` hanya dapat dijangkau monitor/admin yang ditetapkan.
- [ ] Service otomatis start/restart memakai akun OS berprivilege minimum.
- [ ] Rotasi log, monitoring kapasitas disk, dan alert service/backup aktif.

## D. Verifikasi teknis kandidat

Catat tanggal, pelaksana, commit/tag, Python, dan output pada tiket/berita acara
privat.

```powershell
python scripts/check_no_sensitive_tracking.py
python -m pip check
python -m unittest discover -s tests -v
python scripts/generate_qa_letters.py
python scripts/verify_backup.py <direktori-backup-uji>
python -m compileall app.py esurat scripts tests
node --check static/app.js
```

- [ ] Semua perintah lulus pada artefak yang benar-benar akan dideploy.
- [ ] Run CI pada remote bersih lulus untuk Python 3.10 dan 3.14.
- [ ] Startup tanpa master/database persisten gagal dengan pesan yang benar.
- [ ] Startup Vercel/serverless gagal sesuai guard.
- [ ] Login salah/rate limit, logout, session expiry, dan retry CSRF diuji browser.
- [ ] Operator tidak dapat memakai nomor manual atau membatalkan.
- [ ] Admin dapat nomor manual; reviewer/admin dapat membatalkan dengan alasan.
- [ ] Filter, pagination, dan CSV cocok dengan SQLite/register.

## E. UAT Tata Usaha dan dokumen

- [ ] Data owner menyetujui guru/staf, siswa, kode arsip, dan Kepala Sekolah.
- [ ] TU menyetujui batas tujuh jenis aktif; 18 template lain dinyatakan di luar
  scope pilot.
- [ ] Setiap 7 jenis dibuat dengan skenario normal, teks panjang, dan karakter
  khusus yang sah.
- [ ] Dua pemeriksa membuka DOCX di Microsoft Word tanpa repair warning.
- [ ] Kop, logo, font, margin, tabel, pagination, identitas, nomor, tanggal,
  klasifikasi, isi, dan tanda tangan benar.
- [ ] Print Preview dan sampel printer nyata lulus.
- [ ] Desktop dan perangkat/browser operasional yang benar-benar dipakai lulus.
- [ ] Hasil surat dipindah ke arsip resmi; Downloads dan QA dibersihkan sesuai
  retensi.
- [ ] Berita acara UAT ditandatangani TU dan pemilik layanan.

## F. Backup, restore, dan penomoran

- [ ] RPO/RTO dan retensi disahkan.
- [ ] Backup harian terenkripsi dijadwalkan ke media terpisah.
- [ ] Manifest dan SHA-256 diverifikasi.
- [ ] Restore master + SQLite dilakukan di lingkungan terisolasi.
- [ ] Nomor setelah restore direkonsiliasi dengan register/surat yang telah
  terbit; tidak ada nomor terpakai ulang.
- [ ] SOP nomor manual, generate gagal, pembatalan, koreksi/pengganti, dan
  downtime disahkan.
- [ ] Rollback rilis tanpa rollback DB diuji sebagai jalur utama.

## G. Pelatihan dan pilot

- [ ] Operator, reviewer, admin, pemilik teknis, dan pengganti telah ditetapkan.
- [ ] Hak akses setiap akun disetujui dan password awal diganti privat.
- [ ] TU dilatih memilih identitas, memeriksa ringkasan/Word, mengecek riwayat,
  mengekspor, membatalkan, logout, dan melaporkan insiden.
- [ ] Pilot dibatasi pengguna, perangkat, periode, dan volume.
- [ ] Pemeriksaan dua orang serta review harian aktif selama pilot.
- [ ] Kriteria stop/rollback dan jalur eskalasi tersedia di meja operator.
- [ ] Setelah pilot, temuan ditinjau sebelum keputusan produksi penuh.

## Kriteria stop segera

Hentikan generate baru bila identitas/penandatangan/nomor salah, nomor ganda,
DOCX rusak, token template tertinggal, database/health bermasalah, HTTPS/auth
gagal, backup melewati RPO, atau ada dugaan akses tidak sah/PII bocor. Pertahankan
database dan bukti, buat backup pra-tindakan, lalu ikuti SOP insiden/rollback.
