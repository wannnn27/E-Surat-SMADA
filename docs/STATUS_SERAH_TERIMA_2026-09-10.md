# Status Serah Terima E-Surat SMADA

Tanggal target: 10 September 2026

## Hasil teknis

- 42 automated test lulus.
- Seluruh 13 template bawaan berhasil menghasilkan DOCX sintetis; pengujian PDF
  juga tercakup dalam test suite.
- Surat Perintah mendukung banyak guru/staf tanpa batas maksimum aplikasi dan
  bagian `Dasar` dirender sebelum `Memberikan Perintah`.
- Admin dapat mengunggah, memakai, memperbarui, dan menghapus template tambahan;
  template aktif otomatis muncul pada sisi pengguna.
- Pyrefly kode runtime: 0 diagnostic.
- Audit dependensi: tidak ditemukan kerentanan yang dikenal.
- Deployment Vercel berstatus Ready; `/healthz` melaporkan database dan template
  `ok`.
- Header CSP, HSTS, anti-frame, nosniff, no-store serta cookie Secure, HttpOnly,
  dan SameSite=Strict terpasang.
- Login, logout POST ber-CSRF, session expiry, dan pemulihan token lama memiliki
  test regresi. Session memang berakhir setelah batas keamanan; browser diarahkan
  kembali ke login dengan pesan yang dapat dipahami, bukan JSON mentah.

## Wajib ditutup pemilik sebelum data nyata dipakai

1. Repository GitHub saat ini publik dan history lama pernah memuat data
   operasional. Ubah menjadi private, lakukan penanganan history/cache sesuai
   [Audit Produksi](AUDIT_PRODUKSI.md#p0-respons-data-pribadi), lalu rotasi secret
   yang berpotensi terpapar.
2. Domain produksi saat ini mengizinkan pengguna anonim melihat direktori
   guru/murid dan membuat surat bernomor. Pilih salah satu: wajib login untuk
   seluruh operator, atau lindungi deployment dengan jaringan/identity proxy
   sekolah. Jangan gunakan data nyata di internet sebelum keputusan ini
   diterapkan.
3. Owner Vercel/Supabase memverifikasi `DATABASE_URL` benar-benar memakai role
   `esurat_runtime` dan `sslmode=require`; nilai secret tidak dapat dibaca kembali
   melalui CLI Vercel.
4. Tata Usaha memeriksa hasil 13 surat di Microsoft Word dan printer nyata,
   termasuk kop, margin, tabel multi-orang, penomoran, dan tanda tangan.
5. Lakukan satu drill backup/restore dan rekonsiliasi nomor sebelum hari operasi.
6. Ganti password awal secara privat, tetapkan pemilik akun/platform, dan sahkan
   SOP pembatalan/koreksi surat.

Status: **siap untuk demo dan UAT terkontrol; belum aman untuk penggunaan data
nyata melalui internet sampai dua butir P0 pertama ditutup.**
