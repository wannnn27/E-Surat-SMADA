# Audit Kesiapan Produksi E-Surat SMADA

Tanggal audit: 23 Agustus 2026  
Ruang lingkup: source code, konfigurasi, data master, database riwayat, 25 dokumen bisnis + 1 master teknis DOCX, script import/build/backup/QA, dan alur operator pada working tree yang tersedia.

## Keputusan

**Belum layak untuk produksi penuh atau dibuka langsung ke LAN saat ini.** Aplikasi dapat masuk **pilot internal terbatas** hanya setelah seluruh gate P0 dan P1 di dokumen ini ditutup, bukti uji disimpan, dan pemilik layanan menandatangani penerimaan risiko.

Alasan utama:

1. Data pribadi masih terlacak pada history Git. Repository GitHub terverifikasi publik, deployment Vercel aktif, dan endpoint data merespons tanpa autentikasi. Ini adalah temuan P0, bukan lagi sekadar kemungkinan.
2. Hanya 7 dari 25 dokumen bisnis yang aktif otomatis. Delapan belas lainnya belum dimigrasikan; satu DOCX tambahan hanya master teknis.
3. Akses LAN memerlukan deployment autentikasi + HTTPS reverse proxy yang belum disediakan sebagai konfigurasi siap pasang di repositori.
4. Tersedia 15 automated tests, QA tujuh surat, satu putaran browser E2E desktop/mobile, dan render LibreOffice headless. Namun, belum ada CI atau pembandingan visual Microsoft Word otomatis; penerimaan Word/print tetap manual.
5. Backup tersedia, tetapi restore, RPO/RTO, retensi, dan rekonsiliasi nomor harus diuji serta disahkan secara operasional.

## Ringkasan inventaris terverifikasi

| Komponen | Kondisi audit |
| --- | --- |
| Runtime | Flask di atas Waitress, default satu proses pada `127.0.0.1:5000` |
| Data master | JSON di `data/master/`; sumber Excel resmi di `data/source/` |
| Riwayat/nomor | SQLite `data/runtime/surat_smada.db` |
| Template DOCX | 7 aktif di `templates_surat/active/`, 18 legacy, dan 1 master teknis |
| Template otomatis aktif | 7 |
| Template belum dimigrasikan | 18 |
| Import | Check-only sebagai default; `--write` untuk publikasi JSON; restart wajib |
| Rebuild template | Membangun ulang hanya tujuh template aktif; restart dan QA wajib |
| Backup | Snapshot SQLite konsisten + tiga JSON; Excel opsional; manifest SHA-256 |
| QA | `scripts/generate_qa_letters.py` membuat tujuh DOCX dengan database sementara |
| Automated test | 15 `unittest` memakai fixture sintetis dan database sementara; import package tidak membaca data produksi |
| CI/E2E/visual regression | Browser E2E desktop/mobile lulus sekali; CI dan visual regression Word belum tersedia |

### Hasil verifikasi snapshot audit

Verifikasi berikut dijalankan pada working tree tanggal 23 Agustus 2026. Hasil ini harus diulang setelah perubahan apa pun dan pada artefak rilis kandidat:

| Pemeriksaan | Hasil |
| --- | --- |
| `python -m compileall app.py esurat scripts tests` | Lulus |
| `python -m unittest discover -s tests -v` | 15 test lulus; mencakup auth, CSRF, tujuh generate, validasi, idempotency, nomor manual, render failure, concurrency, header keamanan, health, dan kontrak data |
| `python scripts/import_excel_data.py` | Check-only lulus: 50 guru/staf, 750 siswa, 146 kode, 21 rombel; tidak ada file ditulis |
| `python scripts/generate_qa_letters.py` | 7 DOCX dibuat, peran penandatangan sesuai, database produksi tidak berubah |
| `node --check static/app.js` | Lulus |
| Browser E2E desktop + viewport 390x844 | Search, pilih data, validasi, generate, unduh ulang idempoten, riwayat, dan login flow lulus tanpa error console |
| LibreOffice headless 26.2.5 | Ketujuh DOCX terbuka dan ter-render satu halaman A4 |

Pemeriksaan Microsoft Word, Print Preview, printer nyata, drill restore operasional, dan deployment HTTPS belum dapat dinyatakan lulus hanya dari hasil teknis di atas; semuanya tetap menjadi gate pilot.

### Tujuh template aktif

| Key | Berkas | Penandatangan |
| --- | --- | --- |
| `izin_guru` | `izin_guru.docx` | Pemohon |
| `cuti_guru` | `cuti_guru.docx` | Pemohon |
| `sakit_guru` | `sakit_guru.docx` | Pemohon |
| `surat_tugas_guru` | `3. Surat Tugas-smada.docx` | Kepala Sekolah |
| `surat_keterangan_guru` | `11. Surat Keterangan-smada.docx` | Kepala Sekolah |
| `izin_murid` | `izin_murid.docx` | Orang tua/wali |
| `dispensasi_murid` | `dispensasi_murid.docx` | Kepala Sekolah |

### Delapan belas DOCX belum dimigrasikan

- `1. Surat Keputusan-smada.docx`
- `2. Surat Perintah-smada.docx`
- `4. Surat Perjalanan Dinas-smada.docx`
- `5. Nota Dinas-smada.docx`
- `6. Memo-smada.docx`
- `8. Undangan-smada.docx`
- `9. Surat Kuasa-smada.docx`
- `10. Berita Acara-smada.docx`
- `12. Surat Pengantar-smada.docx`
- `13. Pengumuman-smada.docx`
- `14. Laporan-smada.docx`
- `15. Telaahan Staf-smada.docx`
- `16. Notula-smada.docx`
- `17. SPMT-smada.docx`
- `18. Surat Panggilan-smada.docx`
- `19. Surat Permohonan-smada.docx`
- `20. Ucapan Terima Kasih-smada.docx`
- `Lembar Disposisi SMADA new (1).docx`

Builder memakai salinan teknis `templates_surat/master/kop_smada.docx`; sumbernya byte-identik dengan legacy `13. Pengumuman-smada.docx`. Dokumen legacy tersebut tidak terdaftar sebagai jenis generate.

## Kontrol yang sudah tersedia

Audit source menemukan kontrol berikut. Kontrol ini mengurangi risiko, tetapi tidak menghapus kebutuhan deployment dan prosedur operasional yang benar.

| Area | Kontrol saat ini | Batasan |
| --- | --- | --- |
| Akses | Autentikasi berbasis session dapat diaktifkan; password hash didukung | Satu kredensial aplikasi; belum ada user individual, role, SSO, atau audit aktor |
| Local-only | Tanpa autentikasi, bind non-loopback ditolak dan request non-lokal diblok | Keamanan tetap bergantung pada akun/keamanan komputer lokal |
| Session/request | Secret stabil diwajibkan saat auth aktif, cookie aman dapat diaktifkan, CSRF digunakan | `ESURAT_HTTPS=1` dan secret harus benar-benar dipasang oleh admin |
| Input | Identitas dipilih dari master; format, panjang, tanggal, kode, dan field divalidasi | Akurasi substansi masih bergantung pada master/operator |
| Nomor | Nomor otomatis dialokasikan server; uniqueness dan request idempotency disimpan di SQLite | Koordinasi dengan register nomor eksternal dan kebijakan pembatalan belum otomatis |
| Template | Template aktif dan placeholder divalidasi saat startup/build | Validasi tidak menggantikan Word/print visual QA |
| Import | Semua dataset diperiksa sebelum penulisan; mode default tidak menulis | Restart manual wajib; tidak ada approval workflow/version data |
| Backup | SQLite online backup, JSON, manifest hash, Excel opsional | Belum terjadwal; tidak mencakup code/template/secret; restore belum otomatis |
| Server | Waitress, bukan Flask development server | Satu host/satu database SQLite; tidak dirancang multi-instance |
| UI | Ringkasan tervalidasi sebelum unduh dan Riwayat tersedia | Ringkasan bukan render DOCX final |
| Automated test | 15 test mencakup auth/CSRF, validation, tujuh generate, idempotency, numbering, concurrency, error path, security header, health, dan kontrak master | Belum dijalankan otomatis di CI; coverage formal belum diukur |
| QA DOCX | Satu dokumen untuk masing-masing tujuh jenis dibuat lewat route nyata dengan DB sementara | Artefak tetap wajib diperiksa manual di Word dan Print Preview |

## Register risiko dan gate rilis

| Prioritas | Risiko | Dampak | Gate/tindakan wajib | Status audit |
| --- | --- | --- | --- | --- |
| P0 | Data pribadi terlacak Git dan terpapar melalui repository/deployment publik | Kebocoran NIP, NIS/NISN, biodata, workbook, serta riwayat surat | Tutup akses publik, jalankan respons insiden, dan bersihkan seluruh history/remote secara terkoordinasi | **Terbuka** |
| P1 | LAN tanpa arsitektur HTTPS yang disahkan | Kredensial dan PII dapat disadap; service dapat terekspos | Reverse proxy HTTPS, auth, secret stabil, firewall, sertifikat tepercaya, uji negatif | **Terbuka** |
| P1 | Restore dan rekonsiliasi nomor belum dibuktikan | Kehilangan riwayat, nomor ganda/pakai ulang, downtime | Drill restore terisolasi, verifikasi hash, rekonsiliasi nomor, bukti persetujuan | **Terbuka** |
| P1 | Belum ada hasil penerimaan Word/print untuk rilis kandidat | Surat salah format/penandatangan/data dapat terbit | Generate, buka, dan print-preview ketujuh jenis; dua pemeriksa menandatangani | **Terbuka** |
| P1 | Kebijakan nomor manual/pembatalan dan register eksternal belum formal | Konflik atau nomor tak dapat dipertanggungjawabkan | SOP nomor, kewenangan input manual, koreksi, pembatalan, dan rekonsiliasi | **Terbuka** |
| P1 | Akurasi/otorisasi data master belum ditandatangani | Surat dibuat dari identitas atau Kepala Sekolah yang salah | Data owner menyetujui hitungan/sampel dan `ESURAT_KEPSEK_NIP` | **Terbuka** |
| P2 | Hanya 7/25 template aktif | Harapan pengguna tidak terpenuhi; improvisasi manual | Nyatakan 18 di luar scope pilot dan migrasikan satu per satu | Diterima hanya bila scope disahkan |
| P2 | Asset UI menggunakan CDN eksternal | Ikon/font gagal pada jaringan tertutup; dependensi supply/network | Self-host asset dan uji air-gapped | Terbuka |
| P2 | `/healthz` tidak memerlukan login dan memberi status/jumlah | Informasi operasional bocor | Batasi dengan reverse proxy/firewall/monitor lokal | Terbuka |
| P2 | Satu akun dan riwayat tidak mengidentifikasi operator | Akuntabilitas lemah | Akun individual/RBAC atau kontrol register shift sementara | Terbuka |
| P2 | SQLite/satu proses | Scaling/multi-instance berisiko konflik atau perilaku tak didukung | Pertahankan satu instance; desain ulang DB sebelum scaling | Terbuka |
| P2 | Retensi backup, riwayat, DOCX, dan log belum otomatis | PII tersimpan terlalu lama atau pemulihan tidak memadai | Kebijakan retensi/pemusnahan, enkripsi, akses bernama, monitoring kapasitas | Terbuka |
| P2 | Backup tidak mencakup rilis/template/secret | Restore data saja tidak memulihkan layanan penuh | Arsip rilis/template privat dan prosedur reprovision secret terpisah | Terbuka |
| P2 | Automated test belum berjalan di CI; browser E2E/visual QA belum otomatis | Regression dapat lolos jika operator lupa menjalankan test atau layout berubah | Tambahkan CI data sintetis, otomatisasi browser, dan strategi visual Word | Terbuka |

Status "terbuka" berarti belum ada bukti operasional pada repositori, bukan selalu berarti kontrol kode tidak ada.

## P0: data pribadi di Git dan GitHub

### Temuan

Pada commit yang diaudit, `git ls-files` menunjukkan path lama berikut terlacak; working tree kini memindahkannya ke struktur baru dan mengabaikan seluruh `data/**`, tetapi commit/history lama belum bersih:

- `data/guru.json`
- `data/murid.json`
- `data/kode_arsip.json`
- `data/surat_smada.db`
- tiga workbook di `data/master_excel/`

Remote `origin` mengarah ke repository GitHub yang pada audit terverifikasi `public`. Deployment Vercel juga aktif; request anonim ke endpoint daftar murid dan raw data GitHub berhasil. Fork, clone/download, artifact, release, cache, dan audit akses tetap harus diinventarisasi karena tidak seluruh salinan dapat ditarik kembali.

`.gitignore` kini mengabaikan seluruh `data/**` kecuali `data/README.md`. Kontrol ini hanya melindungi file yang belum terlacak pada commit mendatang; ia tidak:

- menghapus file dari index saat ini;
- menghapus isi commit lama atau reflog;
- menarik kembali clone/fork/download;
- menghapus cache, artifact, release, atau log platform;
- membatalkan akses yang sudah terjadi.

### Respons insiden wajib

Tindakan ini harus dipimpin pemilik repository bersama pimpinan/petugas perlindungan data sekolah. History rewrite dan force-push bersifat mengganggu serta tidak boleh dilakukan sepihak.

1. **Batasi paparan segera.** Ubah repository menjadi private atau nonaktifkan akses sesuai wewenang; hentikan publikasi/artifact yang memuat data; jangan melakukan clone baru.
2. **Pertahankan bukti minimum.** Catat URL, waktu, daftar file/ref/commit terdampak, visibility, anggota/kolaborator, fork, clone/download/audit log yang tersedia. Hindari menyalin PII lebih banyak dari yang diperlukan.
3. **Eskalasi resmi.** Beri tahu pimpinan dan fungsi perlindungan data/keamanan sekolah; tentukan kewajiban pemberitahuan berdasarkan kebijakan dan aturan yang berlaku.
4. **Inventaris semua salinan.** Periksa branches, tags, pull request, Actions/artifact, release, Pages, issue attachment, cache, fork, mirror, backup, dan clone pengguna.
5. **Putus tracking aktif.** Dalam perubahan terkoordinasi, keluarkan seluruh data produksi dari index Git sambil mempertahankan salinan kerja yang aman di luar artefak source. `.gitignore` tetap dipertahankan.
6. **Bersihkan history.** Gunakan alat seperti `git filter-repo` atau BFG pada mirror cadangan untuk menghapus path sensitif dari seluruh ref. Review hasil sebelum force-push. Minta GitHub membersihkan cache/ref yang tidak dapat dijangkau sendiri bila diperlukan.
7. **Koordinasikan force-push.** Bekukan merge, force-push history yang sudah dibersihkan hanya dengan persetujuan owner, lalu hapus branch/tag lama yang terdampak.
8. **Re-clone.** Semua kolaborator menghapus clone lama secara aman dan mengambil clone baru; jangan merge history lama kembali.
9. **Rotasi rahasia.** Jika pencarian history menemukan password, secret sesi, token, credential, atau konfigurasi lain, cabut dan ganti semuanya. Menghapus history tidak membuat secret lama aman.
10. **Provision data di luar Git.** Gunakan kanal privat, storage terenkripsi, hak akses bernama, dan audit akses untuk memasukkan Excel/JSON/database ke server produksi.
11. **Verifikasi.** Cari nama path, pola identitas, dan secret pada seluruh ref serta antarmuka GitHub; dokumentasikan keterbatasan untuk fork/clone yang tidak dikuasai.
12. **Tutup insiden secara formal.** Simpan keputusan, lingkup, penerima pemberitahuan, bukti sanitasi, residual risk, dan persetujuan pimpinan.

Jangan hanya menghapus file lokal atau menambahkan `.gitignore`; itu tidak menangani history. Jangan mengirim nilai PII sebagai bukti pada issue/tiket publik.

## Arsitektur deployment yang disetujui

### Profil A: satu komputer lokal

Untuk evaluasi/pilot satu komputer:

```text
Browser pada PC yang sama --> http://127.0.0.1:5000
```

- Pertahankan `ESURAT_HOST=127.0.0.1`.
- Mode tanpa auth diizinkan aplikasi hanya untuk loopback, tetapi akun Windows, disk, screen lock, dan folder arsip harus terlindungi.
- Untuk penggunaan berkelanjutan, autentikasi tetap direkomendasikan walaupun lokal.
- Jangan membuka port 5000 di firewall atau port-forwarding.

### Profil B: LAN sekolah

```text
Perangkat TU -- HTTPS 443 --> Reverse proxy pada server -- HTTP loopback --> 127.0.0.1:5000
```

Gate minimum:

- `ESURAT_USERNAME` dan `ESURAT_PASSWORD_HASH` terisi;
- `ESURAT_SECRET_KEY` acak, stabil, dan disimpan secret manager/service configuration;
- `ESURAT_HTTPS=1`;
- backend tetap bind `127.0.0.1`, bukan diekspos pada LAN;
- Caddy/Nginx/IIS memakai sertifikat tepercaya dan menambahkan HSTS;
- firewall membuka 443 hanya dari segmen/perangkat yang diperlukan dan menutup 5000;
- `/healthz` hanya dapat dijangkau monitor/admin yang berwenang;
- service berjalan dengan akun OS berprivilege minimum dan akses folder terbatas;
- header proxy tidak diasumsikan dipercaya oleh aplikasi; jangan membuat keputusan akses berbasis forwarded IP tanpa konfigurasi kode yang diaudit;
- backup terenkripsi berada di lokasi terpisah.

Bind langsung `0.0.0.0` dengan HTTP tidak disetujui meskipun autentikasi aplikasi aktif.

## Rencana uji rilis kandidat

Semua hasil harus disimpan sebagai bukti rilis tanpa memasukkan PII ke Git.

### Pemeriksaan teknis

```powershell
python -m compileall app.py esurat scripts tests
python scripts/import_excel_data.py
python -m unittest discover -s tests -v
python scripts/generate_qa_letters.py
python app.py
```

Setelah start, cek `/healthz`. Bila Node tersedia, tambahkan `node --check static/app.js`.

Kriteria lulus:

- compile dan check-only import selesai tanpa error;
- startup menolak data/template invalid dan health melaporkan pemeriksaan sehat;
- QA menghasilkan tepat tujuh DOCX, tidak mengubah database produksi, tidak meninggalkan token template, dan menandatangani dengan peran yang benar;
- seluruh DOCX terbuka tanpa repair warning;
- semua data, tanggal, kode, nomor, kop, tabel, tanda tangan, pagination, dan Print Preview benar;
- sampel teks panjang serta karakter `&` tidak merusak XML/layout;
- salah password, request tanpa CSRF, kode tidak terdaftar, identitas tidak dipilih, tanggal invalid, dan nomor duplikat ditolak;
- double-click/retry dengan request yang sama tidak menerbitkan nomor berbeda;
- nomor otomatis unik untuk generate paralel yang wajar pada satu instance;
- Riwayat sesuai dengan hasil generate/gagal;
- browser dan printer yang benar-benar digunakan TU lulus;
- backup dibuat, hash diverifikasi, dan restore terisolasi berhasil.

Test suite saat ini mencakup banyak jalur backend penting, tetapi belum menjadi jaminan lengkap. Perluas coverage untuk script import/build/backup, route dan error path yang belum tercakup, serta browser end-to-end; jalankan di CI menggunakan data sintetis saja. Script QA DOCX tetap diperlukan dan hasil visualnya harus diperiksa manusia.

## Backup, RPO/RTO, dan pemulihan

`scripts/backup_data.py` membuat snapshot online SQLite yang konsisten, tiga JSON, dan `manifest.json`. `--include-excel` menambah workbook. Backup mengandung PII dan harus dienkripsi serta dibatasi.

Sebelum pilot, pemilik layanan harus menetapkan dan menandatangani RPO/RTO. Usulan awal untuk pilot adalah RPO maksimal satu hari kerja dan RTO empat jam, tetapi nilai itu **belum menjadi jaminan** sampai jadwal backup, monitoring, personel pengganti, dan drill restore membuktikannya.

Restore database memiliki risiko khusus: surat yang sudah terbit setelah waktu backup mungkin hilang dari SQLite dan nomornya dapat dialokasikan ulang. Karena itu:

- selalu backup keadaan pra-restore;
- prioritaskan rollback code/template tanpa rollback database bila memungkinkan;
- cocokkan nomor dengan register dan arsip fisik/digital sebelum layanan dibuka;
- tandai nomor yang pernah terbit/gagal sesuai SOP; jangan gunakan ulang secara otomatis;
- simpan bukti manifest/hash dan persetujuan restore.

Checklist teknis lengkap ada di [Panduan TU](PANDUAN_TU.md#checklist-restorerollback).

## Backlog migrasi 18 template

Setiap template harus diperlakukan sebagai fitur baru, bukan sekadar memindahkan DOCX ke folder:

1. Pemilik proses menyetujui format resmi, tujuan, klasifikasi, penandatangan, dan siapa subjeknya.
2. Buat key, label, kategori, kode default, field, opsi, panjang maksimum, dan aturan tanggal.
3. Bersihkan data contoh/PII dari DOCX dan pasang placeholder yang aman untuk `docxtpl`.
4. Tambahkan registrasi aplikasi dan dukungan builder/spec bila format dibangun otomatis.
5. Tambahkan validasi input serta error message untuk seluruh field.
6. Buat kasus QA positif, negatif, teks panjang, karakter khusus, dan data kosong yang sah.
7. Uji Word, Print Preview, printer nyata, kop, margin, page break, dan blok tanda tangan.
8. Lakukan review dua orang dari TU/pemilik surat dan administrator; simpan hash versi yang disetujui.
9. Tambahkan regression test, dokumentasi operator, dan rencana rollback sebelum mengaktifkan pada UI.

Urutan migrasi harus ditentukan oleh volume dan risiko surat. Master teknis sudah dipisah ke `templates_surat/master/kop_smada.docx`, tetapi isinya masih identik dengan legacy `13. Pengumuman-smada.docx`; sanitasi menjadi kop-only dan review metadata tetap diperlukan.

## Checklist gate pilot

Pilot boleh dimulai hanya bila semua kotak P0/P1 berikut ditandatangani:

- [ ] Insiden data Git/GitHub ditangani, history disanitasi, akses diverifikasi, dan data diprovision ulang secara privat.
- [ ] Rilis kandidat dibekukan, diberi versi/hash, dan dideploy dari working tree bersih/artefak privat.
- [ ] Data owner menyetujui master guru, siswa, kode arsip, dan Kepala Sekolah.
- [ ] Profil local-only atau LAN HTTPS dipilih dan diuji; port 5000 tidak terekspos.
- [ ] Auth, password hash, secret stabil, cookie HTTPS, firewall, sertifikat, serta pembatasan health diperiksa.
- [ ] Backup terenkripsi berhasil dan satu drill restore terisolasi lulus termasuk rekonsiliasi nomor.
- [ ] Ketujuh surat lulus script QA, pemeriksaan Word, Print Preview, dan sampel cetak oleh dua pemeriksa.
- [ ] Uji negatif, retry/idempotency, nomor unik, Riwayat, serta browser operasional lulus.
- [ ] SOP nomor manual, pembatalan, koreksi, filing, retensi, insiden, dan rollback disahkan.
- [ ] Operator dilatih; pemilik teknis, pengganti, serta jalur eskalasi ditetapkan.
- [ ] Batas tujuh template aktif dan 18 di luar scope disetujui tertulis.
- [ ] Pilot dibatasi pengguna, perangkat, periode, dan volume; review harian dijadwalkan.

## Kriteria berhenti dan rollback pilot

Hentikan generate baru bila terjadi salah satu kondisi berikut:

- identitas, penandatangan, nomor, atau kode arsip salah pada dokumen terbit;
- nomor ganda/pakai ulang atau Riwayat tidak dapat direkonsiliasi;
- template rusak, token tertinggal, atau Word meminta repair;
- `/healthz` tidak sehat atau data count berubah tidak terencana;
- autentikasi/TLS/firewall gagal;
- dugaan akses tidak sah atau kebocoran PII;
- backup gagal melewati batas RPO yang disetujui.

Saat rollback, pertahankan bukti dan database terkini, hentikan service, buat backup pra-rollback, pulihkan rilis/template terakhir yang diketahui baik, dan hanya pulihkan database bila benar-benar perlu. Sesudahnya lakukan health check, QA tujuh surat, serta rekonsiliasi nomor sebelum membuka layanan.

## Residual risk setelah pilot

Bahkan setelah gate pilot ditutup, risiko berikut tetap perlu backlog produksi penuh:

- akun individual/RBAC dan audit aktor;
- perluasan test suite, CI data sintetis, browser E2E, dan strategi visual regression;
- self-host asset UI;
- monitoring, alerting, dan rotasi log;
- job backup terjadwal serta uji restore berkala;
- retensi/pemusnahan otomatis;
- packaging service dan konfigurasi reverse proxy yang direview;
- migrasi bertahap 18 template;
- evaluasi database/server bila volume atau multi-instance diperlukan.
