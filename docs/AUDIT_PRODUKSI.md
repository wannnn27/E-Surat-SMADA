# Audit Kesiapan Produksi E-Surat SMADA

Tanggal pembaruan: 9 September 2026

Ruang lingkup: source code, konfigurasi, Git index/history, data master, SQLite,
template DOCX, alur operator, autentikasi, backup, QA, dan deployment.

## Keputusan

**Belum layak diserahterimakan sebagai produksi sekolah.** Kode telah meningkat
menjadi **kandidat pilot internal terbatas**, tetapi blocker eksternal dan gate
operasional belum dapat diselesaikan hanya dengan perubahan source code.

Ringkasnya:

- core generate untuk 13 jenis bawaan bekerja dan memiliki automated test;
- masalah token CSRF akibat token lama sekarang dipulihkan satu kali secara
  otomatis, sedangkan session yang benar-benar habis meminta login ulang;
- akun individual, role, audit aktor, pembatalan, filter/pagination, dan ekspor
  riwayat sudah tersedia;
- data operasional tidak lagi berada dalam Git index kandidat ini dan CI akan
  menolak bila masuk kembali;
- Vercel tanpa PostgreSQL persisten ditolak; schema privat Supabase, migrasi data,
  serta policy role runtime berhak minimum telah diverifikasi; deployment
  produksi berstatus Ready dan health database/template lulus;
- **history/remote GitHub dan deployment lama yang pernah memaparkan PII masih
  merupakan insiden P0 terbuka** sampai ditangani pemilik;
- tersedia 13 jenis bawaan serta template tambahan yang dapat diunggah admin;
- direktori identitas dan generate saat ini dapat dipakai tanpa login pada domain
  publik; sekolah harus memilih pembatasan akses sebelum penggunaan data nyata;
- HTTPS, backup/restore, Word/print, data owner approval, SOP, dan pelatihan masih
  memerlukan bukti serta tanda tangan sekolah.

## Status pelaksanaan rekomendasi

| Area | Hasil implementasi kandidat | Status |
| --- | --- | --- |
| Data di commit baru | `data/**` diabaikan kecuali README; tiga JSON produksi dikeluarkan dari index | Selesai lokal; belum membersihkan history/remote |
| Guard kebocoran | `scripts/check_no_sensitive_tracking.py` dan gate CI | Selesai |
| Penyimpanan | `ESURAT_DATA_ROOT`/override privat; startup gagal bila data/DB tidak tersedia | Selesai |
| Serverless | Vercel tanpa PostgreSQL ditolak; fallback demo dihapus; Supabase memakai schema privat dan role runtime minimum | Deployment Ready; health database/template lulus; identitas role di secret perlu verifikasi owner |
| Autentikasi | Pengguna umum tanpa login; file akun privat khusus role admin; session 1–24 jam | Selesai |
| Brute force | Batas login per alamat+username dalam satu proses | Selesai untuk arsitektur satu instance |
| CSRF | Secret stabil diwajibkan saat auth; browser refresh token dan retry satu kali | Selesai |
| Audit aktor | Aktor `public/user` atau akun admin dicatat per nomor | Selesai untuk record baru |
| Nomor manual | Hanya admin | Selesai |
| Pembatalan | Admin; alasan, waktu, aktor; nomor tidak digunakan ulang | Selesai |
| Riwayat | Search, filter, pagination, status, aktor, CSV | Selesai |
| Health | Tidak lagi membuka hitungan data master | Selesai; endpoint tetap perlu dibatasi jaringan |
| QA sintetis | QA 13 DOCX memakai fixture, bukan master sekolah | Selesai |
| CI | Python 3.10/3.14, tests, type-check, QA, compile, JS syntax, data tracking guard | Workflow diperbaiki; run commit rilis harus hijau |
| Backup/import | Mengikuti lokasi data eksternal | Selesai di kode; drill restore belum dilakukan |

## Inventaris dan kesesuaian fitur TU

### Fitur siap diuji oleh TU

- cari guru/staf berdasarkan nama atau NIP;
- cari siswa berdasarkan nama, NIS, atau NISN;
- pilih kode arsip dari master;
- validasi tanggal, identitas, kategori, field wajib, dan panjang input;
- ringkasan data sebelum generate;
- generate DOCX dengan nomor otomatis unik dan idempotent;
- 13 jenis bawaan sesuai registry dan aturan penandatangan masing-masing;
- akun admin individual dan jejak aktor user/admin;
- riwayat, filter, pagination, ekspor CSV;
- pembatalan nomor tanpa menghapus/memakai ulang nomor;
- backup master/SQLite dan import Excel tervalidasi.

### Tiga belas jenis bawaan aktif

| Key | Dokumen | Penandatangan |
| --- | --- | --- |
| `izin_guru` | Permohonan izin guru/staf | Pemohon |
| `cuti_guru` | Permohonan cuti guru/staf | Pemohon |
| `sakit_guru` | Pemberitahuan sakit guru/staf | Pemohon |
| `surat_tugas_guru` | Surat tugas | Kepala Sekolah |
| `surat_keterangan_guru` | Surat keterangan | Kepala Sekolah |
| `izin_murid` | Izin tidak masuk siswa | Orang tua/wali |
| `dispensasi_murid` | Dispensasi kegiatan 1–3 siswa | Kepala Sekolah |
| `surat_pengantar_umum` | Surat pengantar umum | Kepala Sekolah |
| `surat_pengantar_cuti_guru` | Surat pengantar cuti guru/staf | Kepala Sekolah |
| `permohonan_penceramah` | Permohonan penceramah | Kepala Sekolah |
| `surat_keterangan_kehilangan_murid` | Surat keterangan kehilangan siswa | Kepala Sekolah |
| `surat_rekomendasi_murid` | Surat rekomendasi satu/banyak siswa | Kepala Sekolah |
| `undangan_umum` | Surat undangan umum | Kepala Sekolah |

### Kekurangan fungsional yang perlu keputusan sekolah

1. **18 template legacy belum aktif.** Keputusan scope harus berdasarkan volume dan
   kebutuhan nyata TU, bukan sekadar jumlah file lama.
2. **Koreksi/pengganti belum menjadi workflow terhubung.** Kandidat mendukung
   pembatalan bernomor; nomor pengganti dibuat sebagai surat baru dan hubungan
   keduanya dicatat melalui SOP/register eksternal.
3. **Approval dua tahap belum digital.** Admin dapat membatalkan dan audit aktor
   tersedia, tetapi belum ada tombol approve sebelum terbit. Untuk pilot,
   pemeriksaan Word dua orang adalah kontrol prosedural.
4. **Arsip dokumen final tidak disimpan aplikasi.** Riwayat hanya metadata;
   DOCX/PDF final harus masuk sistem/folder arsip resmi sekolah.
5. **Tidak ada sinkronisasi Dapodik/e-office.** Data diperbarui melalui import
   Excel tervalidasi dan restart.
6. **Belum ada retensi/pemusnahan otomatis, monitoring/alert, dan backup
   terjadwal.** Ini tanggung jawab deployment/SOP sampai diotomatisasi.
7. **Aset font/ikon masih CDN.** Fungsi inti tetap ada, tetapi tampilan dapat
   turun pada jaringan tertutup; self-host menjadi backlog P2.

## Temuan keamanan dan operasional tersisa

| Prioritas | Risiko/gate | Kondisi kandidat | Tindakan penutup |
| --- | --- | --- | --- |
| P0 | PII pernah berada di GitHub/deployment publik | Index lokal dibersihkan; salinan lama tidak ditarik kembali | Private/nonaktifkan, inventaris, sanitasi history/ref/cache, re-clone, dokumentasi insiden |
| P0 | Direktori guru/murid dan generate dapat diakses anonim dari internet | Sesuai mode pengguna umum saat ini, tetapi terlalu terbuka untuk data sekolah | Wajibkan login seluruh operator atau batasi deployment ke jaringan/identity proxy sekolah |
| P1 | LAN belum dibuktikan HTTPS | Kode mendukung cookie secure dan bind loopback | Pasang proxy, sertifikat tepercaya, HSTS, firewall; uji dari perangkat TU |
| P1 | Restore/rekonsiliasi nomor belum diuji | Backup tersedia | Drill terisolasi, cocokkan register, tetapkan RPO/RTO |
| P1 | Akurasi master/kepala sekolah | Validasi struktur tersedia | Data owner menyetujui hitungan dan sampel resmi |
| P1 | Layout Word/print | Struktur DOCX dites otomatis | Dua pemeriksa menguji 13 jenis di Word, Print Preview, dan printer nyata |
| P1 | SOP nomor/koreksi/pembatalan | Kontrol aplikasi tersedia | Sahkan kewenangan admin dan prosedur register |
| P1 | Artefak rilis | Belum ada tag/release yang disetujui | Pilih versi, hash, owner/lisensi, simpan artefak privat |
| P2 | 18 template legacy | Tidak aktif | Prioritaskan berdasarkan kebutuhan dan migrasikan per jenis |
| P2 | CDN eksternal | Masih dipakai | Vendor/self-host aset berlisensi dan uji offline |
| P2 | Maintainability frontend | `static/app.js` besar/monolitik | Pecah per fitur setelah pilot stabil, dengan regression test |
| P2 | Observability | Log lokal dasar | Rotasi log, kapasitas disk, alert health/backup |

## P0: respons data pribadi

Audit sebelumnya memverifikasi remote GitHub publik dan akses anonim terhadap
data. Menghapus file dari commit berikutnya atau menambah `.gitignore` tidak
menghapus commit lama, fork, clone, cache, artifact, release, log, maupun salinan
deployment.

Tindakan wajib yang memerlukan wewenang owner/pimpinan:

1. batasi/private repository dan hentikan deployment lama;
2. catat lingkup file, ref, waktu, visibility, fork, artifact, dan akses yang
   tersedia tanpa menyalin PII lebih banyak;
3. eskalasi ke pimpinan/petugas perlindungan data sekolah;
4. bekukan merge dan buat mirror bukti/backup yang aksesnya dibatasi;
5. sanitasi seluruh history dengan `git filter-repo`/alat setara, review, lalu
   force-push secara terkoordinasi;
6. minta kolaborator menghapus clone lama dan re-clone hasil bersih;
7. minta platform membersihkan cache/ref yang tidak terjangkau bila diperlukan;
8. rotasi setiap secret/credential yang ditemukan;
9. verifikasi ulang semua branch, tag, PR, artifact, release, fork, raw URL, dan
   deployment;
10. dokumentasikan residual risk serta keputusan penutupan insiden.

History rewrite sengaja tidak dieksekusi otomatis dalam perubahan ini karena
bersifat destruktif, memengaruhi seluruh kolaborator, dan memerlukan persetujuan
owner.

## Deployment yang disetujui

### Satu komputer

- bind `127.0.0.1`;
- local-only tanpa auth hanya untuk evaluasi, lebih baik tetap gunakan akun;
- disk, akun Windows, Downloads, dan folder arsip dibatasi;
- tidak ada firewall/port forwarding ke 5000.

### LAN sekolah

- backend tetap `127.0.0.1:5000` dan satu proses;
- reverse proxy HTTPS pada port 443 dengan sertifikat tepercaya dan HSTS;
- `ESURAT_USERS_FILE`, `ESURAT_SECRET_KEY`, `ESURAT_DATA_ROOT`, dan
  `ESURAT_HTTPS=1` terpasang pada service configuration;
- firewall hanya mengizinkan segmen/perangkat yang perlu;
- data, DB, users file, log, dan backup memiliki ACL minimum;
- `/healthz` dibatasi monitor/admin;
- backup terenkripsi dan terpisah.

Vercel/container ephemeral tanpa PostgreSQL persisten dan berbagi satu SQLite
melalui network share tidak disetujui. Deployment multi-instance dengan
PostgreSQL tetap memerlukan uji concurrency, autentikasi, backup, dan UAT.

## Over-engineering yang sebaiknya dihindari

- Jangan memigrasikan semua 18 template sebelum TU menyatakan prioritas dan
  aturan bisnisnya.
- Jangan mengganti SQLite dengan cluster database hanya untuk pilot satu server;
  itu baru relevan bila ada multi-instance, concurrency tinggi, atau integrasi.
- Jangan menambah SSO/approval engine kompleks sebelum akun individual + SOP
  diuji dan kebutuhan sekolah jelas.
- Jangan mengejar visual regression Word penuh sebagai pengganti review manusia;
  otomatisasi struktur + QA manual lebih proporsional untuk tahap ini.
- Jangan menyimpan DOCX final di database aplikasi tanpa keputusan sistem arsip,
  retensi, kapasitas, dan backup.

Refactor frontend modular, self-host asset, dan coverage script yang lebih luas
berguna, tetapi bukan alasan menunda penutupan P0/P1.

## Bukti teknis kandidat

Pada kandidat 9 September 2026 sebelum push final:

- 42 automated test lulus pada Python 3.14 lokal;
- test mencakup 13 generate DOCX/PDF, validasi, idempotency, concurrency, render failure,
  CSRF, auth, rate limit, role, aktor, pembatalan, filter/pagination/CSV, health,
  penolakan Vercel tanpa PostgreSQL, private schema/RLS, serta konfigurasi pooler;
- error log pada test render failure adalah kegagalan yang sengaja disimulasikan;
- pemeriksaan CI didefinisikan untuk Python 3.10 dan 3.14 dengan data sintetis
  dan type-check kode runtime tanpa diagnostic.

Pemeriksaan final lokal juga lulus untuk `pip check`, compile seluruh sumber,
syntax tiga berkas JavaScript, guard Git index, audit dependensi tanpa
kerentanan dikenal, dan QA 13 DOCX sintetis. Smoke test deployment produksi
berhasil untuk halaman publik/login, 13 schema field, header keamanan, cookie
aman, health database/template, dan pembatasan halaman admin bagi sesi anonim.

Hasil final untuk QA DOCX, compile, JavaScript, dependency check, dan tracking
data harus dicatat ulang pada [Checklist Rilis](RELEASE_CHECKLIST.md) setiap kali
membuat kandidat baru.

## Kesimpulan kelayakan

- **Untuk developer/testing sintetis:** layak.
- **Untuk demo local-only tanpa data nyata:** layak.
- **Untuk pilot TU dengan data nyata:** layak hanya setelah semua P0/P1 pada
  checklist ditutup dan ditandatangani.
- **Untuk serah terima produksi sekolah saat ini:** belum layak.

Gunakan [Checklist Rilis](RELEASE_CHECKLIST.md) sebagai urutan eksekusi tersisa.
