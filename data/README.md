# Struktur data operasional

Direktori ini hanya dokumentasi tata letak. Untuk pilot/produksi, letakkan data
di luar checkout Git dan set `ESURAT_DATA_ROOT`, misalnya
`D:\E-Surat-Private`:

```text
D:\E-Surat-Private\
|-- source\       # workbook Excel resmi untuk import
|-- master\       # guru.json, murid.json, kode_arsip.json
|-- runtime\      # surat_smada.db (riwayat dan counter nomor)
`-- config\       # users.json dan konfigurasi privat lain
```

`ESURAT_DATA_DIR`, `ESURAT_DB_PATH`, dan `ESURAT_SOURCE_DIR` dapat dipakai
sebagai override granular. Folder dan file tersebut mengandung data pribadi;
batasi ACL ke akun service/admin, enkripsi media/backup, serta kirim melalui
kanal privat.

Semua isi `data/**` selain README ini ditolak oleh pemeriksaan CI. Aturan ini
tidak membersihkan data yang sudah ada pada history Git; respons insiden dan
sanitasi remote tetap harus dilakukan oleh pemilik repository.
