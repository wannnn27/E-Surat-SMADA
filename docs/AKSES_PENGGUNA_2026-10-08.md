# Alur pengguna dan admin — 8 Oktober 2026

Perubahan ini mengoreksi login wajib pada upgrade 2 Oktober sesuai kebutuhan
pemilik aplikasi. Pengguna membuat surat tanpa akun; login disediakan untuk
akses administrasi.

## Pengguna

1. Buka halaman utama.
2. Pilih jenis/template surat.
3. Cari NIP atau NIS dan pilih identitas resmi.
4. Isi detail dan periksa ringkasan.
5. Unduh Word/PDF. Kedua format menggunakan satu nomor untuk permintaan sama.

Pengguna tanpa akun dicatat sebagai `public/user`. CSRF, validasi identitas,
penomoran, dan perlindungan pengulangan permintaan tetap berlaku.

## Admin

Klik Login Admin atau buka `/login`. Panel, riwayat, ekspor, template, nomor
manual, dan pembatalan tetap memerlukan otorisasi. Akun operator lama tetap
didukung untuk kompatibilitas staf internal; pengguna umum tidak memerlukannya.

## Konfigurasi

Default kode, `.env.example`, dan provisioning baru memakai
`ESURAT_REQUIRE_LOGIN=0`. Instalasi/deployment yang sudah memiliki nilai `1`
harus menggantinya ke `0`, lalu restart/redeploy. Perubahan default kode tidak
menimpa konfigurasi eksplisit yang sudah dipasang.

Untuk terminal PowerShell yang sebelumnya dipakai menjalankan server:

```powershell
$env:ESURAT_REQUIRE_LOGIN = '0'
.\.venv\Scripts\python.exe app.py
```

Hentikan proses lama sebelum menjalankan ulang. Pertahankan konfigurasi akun
admin dan secret yang sudah dibuat. Berkas `.env.local` tidak otomatis dimuat
oleh `app.py`; environment perlu diberikan melalui terminal atau service.

Laporan audit 2 Oktober adalah catatan historis sebelum koreksi alur ini.
