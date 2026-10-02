# Upgrade ruang kerja TU 2 Oktober 2026

Pemeriksaan lanjutan dan penyederhanaan fitur dicatat dalam
[Audit sistem 2 Oktober 2026](AUDIT_SISTEM_2026-10-02.html).

Upgrade ini menyiapkan alur kerja staf untuk penggunaan internet dan LAN.
Perubahan berada pada kode lokal; deployment lama belum dianggap menggunakan
perilaku baru sampai rilis ini diterapkan dan diperiksa.

## Perubahan operasional

- Akun yang dikonfigurasi kini mewajibkan login secara default sebelum direktori
  guru/siswa, ringkasan, atau pembuatan surat dapat diakses.
- Role `operator` membuat surat, membaca seluruh riwayat TU dan data master,
  serta mengekspor rekap. Role `admin` juga mengelola template, menggunakan nomor
  manual, dan membatalkan surat. Hak ini diterapkan pada server, bukan hanya menu.
- Nama akun dan role pembuat tersimpan pada setiap permintaan baru. Permintaan
  milik akun lain tidak dapat digunakan ulang. Ketika template berubah,
  pengulangan permintaan lama ditolak agar nomor yang sama tidak diam-diam
  menghasilkan dokumen dengan versi template berbeda.
- Sesi memiliki batas mutlak sejak login, sesuai `ESURAT_SESSION_HOURS`.
  Sesi lama dari versi sebelumnya harus login kembali. Formulir yang masih
  terbuka memberi tautan login di tab baru ketika API menolak sesi yang berakhir.
- Riwayat dapat difilter berdasarkan tanggal pembuatan mulai/sampai dalam WIB,
  username operator, jenis, status, dan kata kunci. Ekspor menggunakan filter
  yang sama dan mencakup semua halaman. Tanggal akhir mencakup seluruh hari.
- Nomor surat membuka detail identitas, keperluan, pembuat, waktu, dan pembatalan.
- Panel data master memiliki pencarian guru, siswa, dan kode arsip serta paginasi
  25 record. Pembaruan sumber data tetap melalui import terverifikasi.
- Panduan pekerjaan harian tersedia pada `/admin/guide`. Kesalahan halaman dan
  pembatasan login ditampilkan sebagai halaman browser yang dapat dipahami.
- Label dokumen dibuat dibedakan dari pengesahan dan penerbitan oleh sekolah.
  File hasil tetap harus diperiksa dan disimpan di arsip sekolah.

## Konfigurasi penerapan

Tetapkan `ESURAT_REQUIRE_LOGIN=1` untuk internet maupun LAN. Nilai ini sudah
menjadi default saat akun aktif. Mode `0` hanya untuk demo sintetis atau
lingkungan yang telah dilindungi identity proxy sekolah. Mode tanpa akun
tetap dibatasi pada loopback dan tidak memberikan ruang kerja TU.

Untuk akun individual, gunakan file JSON privat melalui `ESURAT_USERS_FILE`.
Setiap record memuat `username`, `password_hash`, `role` (`admin` atau
`operator`), dan `active`. Hash dibuat melalui `scripts/generate_password_hash.py`.
Jangan gunakan file akun bersamaan dengan kredensial tunggal environment.
Bootstrap environment tetap dapat dipakai oleh satu admin. Akun cloud tambahan
memerlukan provisioning file privat pada deployment; panel pengelolaan akun
belum tersedia pada versi ini.

Perubahan tidak membutuhkan migrasi schema database. Gunakan konfigurasi
SQLite persisten untuk satu proses LAN atau PostgreSQL persisten untuk cloud.
Pertahankan HTTPS dan cookie Secure pada operasional jaringan. Perubahan akun
file baru berlaku setelah restart atau redeploy; sesi diverifikasi terhadap akun
yang dimuat pada instance. Untuk penghentian akun di semua instance, terapkan
file yang diperbarui pada semua instance; rotasi secret bila seluruh sesi harus
segera dihentikan.

## Validasi rilis

Hasil pemeriksaan lokal: 54 pengujian lulus, Pyrefly tanpa diagnostik,
kompilasi Python dan sintaks JavaScript valid, dependensi Python konsisten,
serta pemeriksaan kandidat commit tidak menemukan data operasional.
Uji browser desktop dan ponsel lulus tanpa kesalahan JavaScript atau
overflow horizontal pada halaman yang diperiksa.

Jalankan suite `python -m unittest discover -s tests -v`, pemeriksaan Pyrefly,
kompilasi Python, pemeriksaan sintaks JavaScript, dan pemeriksaan kandidat Git
untuk data operasional. Test TU memakai data sintetis dan mencakup akses anonim,
hak operator/admin, masa berlaku sesi, kepemilikan permintaan, perubahan template,
tanggal WIB, ekspor, direktori, serta pembatalan.

Pengujian browser menggunakan server fixture lokal dan memeriksa login,
navigasi operator, filter, unduhan CSV, halaman detail, dan tampilan desktop serta
ponsel. Pengujian SQL aktual dijalankan pada SQLite; koneksi produksi PostgreSQL
dan deployment sekolah tetap perlu diperiksa setelah penerapan.

## Batas kesiapan sekolah

Riwayat adalah register administrasi, belum menyimpan file hasil untuk unduh
ulang dari halaman riwayat. Dokumen Word/PDF harus dipindahkan ke arsip sekolah
yang disetujui. Relasi surat pengganti, persetujuan berjenjang, dan tanda tangan
elektronik tersertifikasi belum tersedia.

Sebelum data nyata dipakai, pemilik tetap perlu menyelesaikan penanganan data
yang pernah masuk history Git, menyiapkan akun pribadi, memeriksa hasil surat
di Word/printer sekolah, serta menjalankan drill backup/restore. Upgrade ini
menutup akses anonim pada rilis baru dengan konfigurasi default, tetapi tidak
menghapus history lama atau mengubah deployment lama secara otomatis.
