# Struktur template surat

- `active/`: tujuh template dinamis yang boleh dirender aplikasi.
- `legacy/`: delapan belas dokumen referensi yang belum dimigrasikan.
- `master/kop_smada.docx`: master teknis immutable untuk builder template aktif.

Keberadaan DOCX di `legacy/` tidak mengaktifkannya di aplikasi. Jalankan
`python scripts/build_docx_templates.py` untuk membangun ulang seluruh isi
`active/`, lalu ulangi test dan pemeriksaan visual.

Template dispensasi memakai daftar `students` dan mendukung 1–3 siswa. Template
tambahan yang diunggah melalui `/admin` disimpan di database privat, bukan di
folder ini.
