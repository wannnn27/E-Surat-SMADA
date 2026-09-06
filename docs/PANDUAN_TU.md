# Panduan Operasional E-Surat SMADA

Panduan ini ditujukan kepada pengguna Tata Usaha dan administrator teknis SMAN 2 Wonosari. Versi kandidat: 5 September 2026.

## Batas penggunaan

E-Surat saat ini hanya mendukung tujuh jenis surat otomatis:

1. Permohonan izin guru/staf.
2. Permohonan cuti guru/staf.
3. Pemberitahuan sakit guru/staf.
4. Surat tugas guru/staf.
5. Surat keterangan guru/staf.
6. Izin tidak masuk siswa.
7. Dispensasi kegiatan untuk satu sampai tiga siswa dalam satu surat.

Administrator memantau ringkasan operasional dari dashboard `/admin` dan dapat
menambahkan template DOCX lain dari menu **Template Surat** (`/admin/templates`).

Folder `templates_surat/active/` berisi 7 template aktif, `legacy/` berisi **18 dokumen belum aktif**, dan `master/` berisi satu master teknis kop. Jangan mengaktifkan dokumen legacy dengan mengganti nama atau menyalin tag tanpa proses migrasi dan uji pada [Audit Produksi](AUDIT_PRODUKSI.md#backlog-migrasi-18-template).

Ringkasan di layar adalah ringkasan data tervalidasi, bukan tampilan halaman Word. DOCX hasil generate belum dianggap final sampai diperiksa dan disetujui sesuai prosedur sekolah.

## Peran dan tanggung jawab

| Peran | Tanggung jawab minimum |
| --- | --- |
| Pengguna (`user`, tanpa login) | Memilih orang yang benar, mengisi surat, memeriksa ringkasan dan DOCX, serta menyimpan hasil di lokasi arsip resmi; tidak dapat membuka riwayat, nomor manual, pembatalan, atau pengelolaan template |
| Administrator (`admin`, dengan login) | Menjaga service, akun, TLS, data master, template, backup/restore; dapat melihat riwayat, mengekspor, memakai nomor manual, membatalkan, dan menambah template |
| Pemilik data/pimpinan | Menetapkan hak akses, retensi, kebijakan nomor surat, penerimaan pilot, dan respons insiden data pribadi |

Gunakan akun admin individual agar tindakan pengelolaan dapat ditelusuri. Jangan berbagi akun atau meninggalkan session admin terbuka ketika meja ditinggalkan.

## Aturan keamanan data

- Gunakan aplikasi hanya dari perangkat sekolah yang disetujui dan terkunci.
- Jangan mengirim Excel master, JSON, SQLite, backup, atau DOCX melalui kanal pribadi yang tidak disetujui.
- Jangan menyimpan hasil surat permanen di folder `Downloads`; pindahkan ke sistem/folder arsip sekolah dengan hak akses terbatas.
- Jangan menaruh data produksi atau backup di Git, GitHub, cloud drive publik, atau folder sinkronisasi tanpa persetujuan dan enkripsi.
- Jangan membagikan kata sandi, hash kata sandi, atau `ESURAT_SECRET_KEY` di chat, tiket publik, screenshot, maupun commit.
- Kunci layar atau logout ketika meja ditinggalkan.
- Riwayat aplikasi menampilkan identitas dan nomor surat; aksesnya juga harus dibatasi.

Kandidat lokal telah mengeluarkan data operasional dari Git index, tetapi history/remote lama pernah memuat data pribadi. Administrator wajib menyelesaikan tindakan P0 pada [Audit Produksi](AUDIT_PRODUKSI.md#p0-respons-data-pribadi) sebelum rollout.

## Checklist mulai hari kerja

Administrator atau petugas yang ditunjuk:

- Pastikan aplikasi berjalan dari rilis yang disetujui, bukan dari working tree pengembangan.
- Pastikan backup terakhir berhasil dan tersedia pada media terpisah yang terenkripsi.
- Pastikan reverse proxy HTTPS dan sertifikat aktif bila layanan dipakai melalui LAN.
- Periksa health lokal:

  ```powershell
  Invoke-RestMethod http://127.0.0.1:5000/healthz
  ```

- Pastikan respons berstatus sehat dan pemeriksaan database/template lulus.
- Cocokkan jumlah/sampel master melalui pencarian dan laporan import yang disetujui; health sengaja tidak membuka jumlah data.
- Jika status tidak sehat atau master berubah tanpa jadwal, hentikan penerbitan surat dan hubungi administrator.

Pengguna:

- Buka alamat HTTPS resmi dari bookmark sekolah. Jangan mengabaikan peringatan sertifikat browser.
- Tidak perlu login; halaman utama langsung membuka alur pembuatan surat.
- Pastikan nama aplikasi, tanggal, dan koneksi sesuai; jangan lanjut melalui salinan situs atau alamat IP yang tidak diumumkan admin.

## Alur membuat surat

### 1. Pilih kategori dan jenis surat

Pilih kategori guru/staf atau siswa, lalu pilih salah satu dari tujuh jenis aktif. Pastikan tujuan surat sesuai dengan label dan penandatangan yang berlaku:

- Surat tugas, surat keterangan, dan dispensasi ditandatangani Kepala Sekolah.
- Permohonan izin, cuti, dan sakit guru/staf ditandatangani pemohon.
- Izin siswa ditandatangani orang tua/wali.

### 2. Pilih personel dari data master

Cari menggunakan nama, NIP, NIS, atau NISN. **Klik hasil pencarian yang benar**; mengetik teks saja belum berarti data telah dipilih.

Khusus surat dispensasi, pilih satu siswa lalu cari kembali untuk menambahkan
siswa kedua atau ketiga. Hapus pilihan yang keliru sebelum melanjutkan. Sistem
menolak siswa duplikat dan lebih dari tiga siswa.

Sebelum lanjut, cocokkan sekurang-kurangnya:

- nama lengkap;
- NIP untuk guru/staf, atau NIS/NISN dan kelas untuk siswa;
- unit/status lain yang relevan.

Jika ada dua nama mirip, gunakan nomor identitas sebagai pembeda. Bila orang tidak ditemukan atau datanya salah, jangan membuat identitas pengganti dan jangan edit JSON; minta administrator memperbarui Excel master, menjalankan import, lalu me-restart aplikasi.

### 3. Isi data surat

- Periksa tanggal surat serta rentang tanggal izin/tugas.
- Pilih kode klasifikasi arsip yang benar dari direktori resmi.
- Isi keperluan secara spesifik, singkat, dan tanpa data pribadi yang tidak diperlukan.
- Isi field khusus, misalnya jenis cuti, nama wali, kegiatan, penyelenggara, dan tempat.
- Secara normal, **kosongkan nomor surat manual** agar server mengalokasikan nomor unik ketika dokumen dibuat.
- Hanya role admin dapat memakai nomor manual setelah mendapat nomor dari pejabat pengelola. Pengguna umum tidak dapat melewati pembatasan ini.

### 4. Periksa Ringkasan Data

Buka Ringkasan Data dan cocokkan:

- jenis surat dan identitas subjek;
- tanggal;
- kode klasifikasi;
- keperluan dan seluruh field khusus;
- nama/peran penandatangan;
- nomor manual bila digunakan.

Nomor otomatis baru dialokasikan saat tombol unduh/generate dijalankan, sehingga ringkasan dapat menampilkan penanda nomor otomatis.

### 5. Generate dan unduh

- Klik unduh satu kali dan tunggu status selesai.
- Catat nomor surat yang dikembalikan aplikasi.
- Jika koneksi terputus setelah klik, periksa menu Riwayat sebelum mencoba lagi. Jangan mengulang berkali-kali atau membuat form baru karena dapat menghasilkan reservasi nomor berbeda.
- Aplikasi mencatat metadata riwayat, tetapi tidak menjadi penyimpanan permanen DOCX hasil pengguna. Simpan file yang terunduh ke lokasi arsip resmi.

### 6. Pemeriksaan DOCX wajib

Buka hasil di Microsoft Word atau aplikasi DOCX yang ditetapkan sekolah. Periksa:

- file terbuka tanpa pesan repair/corrupt;
- kop, logo, margin, spasi, tabel, pagination, dan area tanda tangan;
- nama dan nomor identitas subjek;
- nomor dan kode surat;
- semua tanggal, isi keperluan, dan ejaan;
- nama, jabatan, dan NIP penandatangan;
- tidak ada token seperti `{{ ... }}`, `{% ... %}`, teks contoh, atau field kosong yang seharusnya terisi;
- hasil Print Preview dan, untuk pilot, satu sampel cetak.

Gunakan pemeriksaan dua orang untuk masa pilot atau surat berisiko tinggi. Jika salah, jangan edit nomor/identitas secara diam-diam di DOCX. Koreksi sumber/form, generate sesuai kebijakan nomor, lalu dokumentasikan pembatalan atau penggantian nomor.

### 7. Terbitkan dan arsipkan

Setelah disetujui, simpan DOCX/PDF final sesuai tata nama, klasifikasi, retensi, dan lokasi arsip sekolah. Riwayat aplikasi bukan pengganti sistem kearsipan resmi.

### 8. Riwayat, ekspor, dan pembatalan

- Login sebagai admin; menu Riwayat tidak tersedia untuk pengguna umum.
- Gunakan pencarian serta filter status/jenis; navigasikan halaman bila hasil banyak.
- `Ekspor CSV` mengekspor hasil sesuai filter aktif. Simpan CSV sebagai PII di lokasi terbatas dan hapus dari Downloads setelah dipindahkan.
- Pembatalan hanya tersedia untuk admin dan wajib memiliki alasan minimal lima karakter.
- Pembatalan tidak menghapus record dan tidak membuat nomor dapat digunakan ulang.
- Untuk surat pengganti, batalkan sesuai SOP lalu buat surat baru. Catat hubungan nomor lama-baru pada register resmi karena kandidat belum memiliki relasi koreksi digital.

## Menangani kesalahan

| Gejala | Tindakan aman |
| --- | --- |
| Data personel tidak ditemukan/salah | Hentikan form; minta admin memperbarui Excel, validasi import, `--write`, lalu restart |
| Kode arsip ditolak | Pilih kode dari direktori; jangan mengarang kode |
| Kembali ke login admin | Login ulang; jika berulang, minta administrator lain memeriksa akun dan secret |
| HTTP 403 / CSRF atau akses admin | Browser mencoba mengambil token baru dan mengulang satu kali. Jika mengakses fungsi admin, login sebagai admin; selain itu minta admin memeriksa secret stabil dan durasi session |
| HTTP 409 / proses sedang berjalan / nomor konflik | Tunggu, cek Riwayat, lalu minta admin memeriksa status; jangan klik berulang |
| Aplikasi tanpa autentikasi menolak akses jaringan | Ini kontrol local-only; admin harus memasang autentikasi dan HTTPS, bukan mematikan kontrol |
| `/healthz` gagal atau status tidak sehat | Hentikan penerbitan; simpan bukti waktu/error dan eskalasi |
| DOCX rusak, layout berubah, penandatangan salah, atau token tersisa | Jangan terbitkan; simpan sampel, hentikan jenis terkait, pulihkan template yang diketahui baik, restart, dan uji semua jenis |
| Nomor tampak meloncat | Cek Riwayat untuk generate gagal/percobaan; jangan mengubah database langsung |
| Ikon/font tidak tampil pada jaringan tertutup | Fungsi inti mungkin tetap jalan; laporkan ke admin. Asset eksternal perlu dipindahkan lokal sebelum penggunaan air-gapped |

Catat insiden dengan waktu, pengguna, jenis surat, nomor/request ID bila ada, screenshot tanpa menyebarkan data berlebih, dan keputusan penyelesaian.

## Pemeliharaan administrator

### Environment dan akses

Aplikasi membaca environment proses dan **tidak otomatis membaca `.env`**. Simpan konfigurasi pada mekanisme secret/service manager yang hanya dapat dibaca admin. Contoh variabel ada di [../.env.example](../.env.example).

Untuk satu komputer lokal, biarkan `ESURAT_HOST=127.0.0.1` dan jangan aktifkan akses jarak jauh. Untuk LAN, pertahankan backend di `127.0.0.1:5000`, gunakan `ESURAT_USERS_FILE` dengan akun admin individual, secret stabil, `ESURAT_HTTPS=1`, dan reverse proxy HTTPS pada port 443. Firewall tidak boleh membuka port 5000. Batasi `/healthz` di proxy/firewall. Vercel hanya boleh dipakai dengan Supabase PostgreSQL persisten, akun admin, dan secret stabil; tanpa `DATABASE_URL` aplikasi wajib gagal startup. Pengguna umum tetap mengakses alur pembuatan surat tanpa login.

Letakkan root operasional di luar checkout Git dan set `ESURAT_DATA_ROOT`. Struktur yang direkomendasikan adalah `source/`, `master/`, `runtime/`, dan `config/users.json`. Lihat [README](../README.md#provision-data-secara-privat).

Jangan menjalankan lebih dari satu proses/instance aplikasi pada database SQLite yang sama. Deployment multi-instance hanya menggunakan PostgreSQL dan tetap harus lulus uji concurrency nomor surat.

### Import data master

Lakukan pada maintenance window:

1. Pastikan hanya file Excel resmi yang akan menjadi sumber.
2. Buat backup data saat ini:

   ```powershell
   python scripts/backup_data.py --include-excel
   ```

3. Jalankan pemeriksaan tanpa mengubah data:

   ```powershell
   python scripts/import_excel_data.py
   ```

4. Baca seluruh output. Script memeriksa struktur dan keunikan NIP, NIS/NISN, kode, serta ringkasan jumlah/kelas. Jika ada `[GAGAL]`, perbaiki Excel dan ulangi check-only.
5. Setelah laporan bersih dan jumlah disetujui, publikasikan:

   ```powershell
   python scripts/import_excel_data.py --write
   ```

6. Restart service/aplikasi. Data dimuat ke memori saat startup; tanpa restart proses lama masih memakai data lama.
7. Periksa `/healthz`, cocokkan laporan jumlah import, cari beberapa guru/siswa/kode, lalu generate satu surat UAT sesuai prosedur.

Lokasi Excel alternatif dapat diberikan dengan `--guru-file`, `--murid-file`, dan `--kode-file`. Ketiga dataset divalidasi sebelum penulisan pertama, dan setiap JSON diganti secara atomik; walau demikian backup tetap wajib.

### Rebuild template

`scripts/build_docx_templates.py` hanya membangun ulang tujuh template di `templates_surat/active/`. Ia memakai `templates_surat/master/kop_smada.docx` sebagai sumber teknis dan tidak mengaktifkan 18 template di `legacy/`.

Untuk template tambahan, login sebagai admin, buka **Template Surat**, lalu unggah
DOCX maksimal 4 MB. Template wajib memiliki placeholder `nomor_surat`,
`tanggal_surat`, dan `nama`; placeholder lain otomatis menjadi field formulir.
Template tambahan disimpan di database privat dan dapat dihapus dari halaman template
dengan konfirmasi. Template bawaan tidak dapat ditimpa atau dihapus dari panel.

1. Jadwalkan maintenance dan hentikan penerbitan surat.
2. Backup/versioning ketujuh DOCX aktif dan master kop di lokasi privat.
3. Jalankan:

   ```powershell
   python scripts/build_docx_templates.py
   ```

4. Pastikan semua hasil berstatus `[OK]`; bila ada kegagalan, jangan restart ke versi yang tidak lengkap.
5. Restart aplikasi agar validasi/hash template dimuat ulang.
6. Jalankan:

   ```powershell
   python -m unittest discover -s tests -v
   python scripts/generate_qa_letters.py
   ```

7. Pastikan seluruh automated test lulus. Buka ketujuh file sintetis di `qa/generated/` dan periksa Word serta Print Preview. QA otomatis tidak membaca data master produksi.
8. Catat siapa yang menyetujui template dan hash/rilisnya.

### Backup

Backup online yang konsisten untuk SQLite, JSON, dan manifest SHA-256:

```powershell
python scripts/backup_data.py
python scripts/backup_data.py --include-excel
python scripts/backup_data.py --output-dir D:\Backup-E-Surat
python scripts/verify_backup.py D:\Backup-E-Surat\surat-smada-YYYYMMDD-HHMMSS
```

Rekomendasi minimum:

- backup harian selama aplikasi dipakai;
- backup sebelum dan sesudah import, perubahan template, upgrade, atau restore;
- salinan terenkripsi pada media terpisah/offsite yang disetujui;
- akses hanya untuk petugas bernama;
- kebijakan retensi dan pemusnahan tertulis;
- uji restore berkala pada lingkungan terisolasi.

`manifest.json` mencatat `layout_version`, mapping tujuan restore, path, ukuran, dan SHA-256 setiap berkas. `verify_backup.py` juga menolak file hilang/tambahan dan menjalankan SQLite `quick_check`; jalankan sebelum serta sesudah memindahkan backup. Backup default tidak mencakup source code, konfigurasi secret, atau template DOCX; simpan rilis aplikasi dan template secara terpisah serta privat.

## Checklist restore/rollback

Restore adalah operasi admin dan memerlukan persetujuan pemilik layanan. Rollback database dapat membuat nomor surat yang sudah terbit hilang dari riwayat dan berisiko digunakan kembali. Jika masalah hanya pada kode/template, prioritaskan rollback rilis tanpa mengganti database.

1. Umumkan downtime dan hentikan service agar tidak ada generate baru.
2. Catat gejala, waktu, rilis, nomor terakhir, dan surat yang mungkin sudah diterbitkan.
3. Buat backup pra-restore dari keadaan saat ini; jangan menimpa bukti insiden.
4. Pilih backup terakhir yang diketahui baik dan verifikasi semua SHA-256 terhadap `manifest.json`.
5. Pulihkan hanya komponen yang diperlukan:
   - kode/template dari artefak rilis privat;
   - `guru.json`, `murid.json`, dan `kode_arsip.json` ke `$ESURAT_DATA_ROOT/master/` atau `ESURAT_DATA_DIR` bila master rusak;
   - `surat_smada.db` ke `$ESURAT_DATA_ROOT/runtime/` atau `ESURAT_DB_PATH` hanya bila database memang harus dipulihkan;
   - isi `source/` ke `$ESURAT_DATA_ROOT/source/` atau `ESURAT_SOURCE_DIR` bila workbook sumber juga harus dikembalikan.
6. Pastikan file berada pada folder yang benar dan hak akses tetap terbatas.
7. Start ulang satu instance aplikasi dengan environment produksi yang benar.
8. Periksa `/healthz`, laporan/sampel master, beberapa pencarian, login, dan Riwayat.
9. Jalankan automated test dan QA tujuh template, lalu buka DOCX hasilnya.
10. Rekonsiliasi nomor surat terhadap register/arsip nyata. Tandai nomor yang pernah terbit; jangan menghapus atau menggunakan ulang nomor hanya karena tidak ada di database hasil restore.
11. Minta pengguna TU/pemilik layanan menyetujui pembukaan kembali.
12. Dokumentasikan backup yang dipakai, hash, pelaksana, hasil uji, dan tindakan pencegahan.

## Checklist penutupan hari kerja

- Pastikan seluruh DOCX final telah dipindahkan dari Downloads ke arsip resmi.
- Cocokkan surat hari itu dengan menu Riwayat dan register resmi.
- Laporkan generate gagal, nomor tidak terpakai, atau koreksi surat.
- Logout dan tutup browser; kunci perangkat.
- Pastikan backup terjadwal berhasil dan tidak tersimpan pada media publik.

## Checklist penerimaan pilot

Sebelum pilot dimulai, pemilik layanan menandatangani bahwa:

- respons insiden PII/Git P0 telah selesai dan diverifikasi;
- rilis dijalankan dari lokasi privat dengan hak akses terbatas;
- LAN menggunakan autentikasi, secret stabil, HTTPS, firewall, dan sertifikat tepercaya;
- backup serta simulasi restore berhasil;
- data master dan Kepala Sekolah telah diverifikasi;
- automated test serta tujuh jenis aktif lulus QA data, Word, dan cetak;
- kebijakan nomor manual, pembatalan, retensi, serta eskalasi sudah tertulis;
- pengguna TU telah dilatih dan masa pilot memakai pemeriksaan dua orang;
- 18 template belum aktif dinyatakan di luar cakupan;
- pemilik teknis dan pengganti, jam dukungan, serta prosedur rollback sudah ditetapkan.
