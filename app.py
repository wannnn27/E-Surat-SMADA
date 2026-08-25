"""Entry point WSGI dan ``python app.py``."""

from esurat import *  # noqa: F401,F403 - facade kompatibilitas publik


app = create_app()
GURU = app.extensions["esurat_data"]["guru"]
MURID = app.extensions["esurat_data"]["murid"]
KODE_ARSIP = app.extensions["esurat_data"]["kode_arsip"]
GURU_BY_NIP = app.extensions["esurat_data"]["guru_by_nip"]
MURID_BY_NIS = app.extensions["esurat_data"]["murid_by_nis"]
MURID_BY_NISN = app.extensions["esurat_data"]["murid_by_nisn"]


if __name__ == "__main__":
    run(app)
