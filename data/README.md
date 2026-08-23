# Struktur data operasional

- `source/` berisi workbook Excel resmi sebagai sumber import.
- `master/` berisi JSON tervalidasi yang dibaca aplikasi saat startup.
- `runtime/` berisi SQLite riwayat dan counter nomor surat.

Ketiga folder mengandung data pribadi/operasional dan diabaikan untuk commit
baru. Provision, backup, dan pemindahannya harus melalui kanal privat. Menambah
aturan `.gitignore` tidak menghapus salinan yang sudah ada di riwayat Git.
