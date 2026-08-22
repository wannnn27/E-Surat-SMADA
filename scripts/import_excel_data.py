"""
Script Impor Data Master Excel ke Database JSON
================================================
Membaca file Excel di data/master_excel/ dan memperbarui file JSON di data/.

Cara jalankan:
    python scripts/import_excel_data.py
"""
import json
from pathlib import Path
import openpyxl

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
EXCEL_DIR = DATA_DIR / "master_excel"

def import_guru():
    file_guru = EXCEL_DIR / "nomonatif guru peg sma2 2026.xlsx"
    if not file_guru.exists():
        print(f"[SKIP] File {file_guru.name} tidak ditemukan.")
        return 0

    wb = openpyxl.load_workbook(file_guru)
    sh = wb.active
    guru_list = []
    for row in list(sh.iter_rows(values_only=True))[1:]:
        if not row[1] or not str(row[1]).strip().isdigit():
            continue
        nip = str(row[1]).strip()
        nama = str(row[2]).strip() if row[2] else ""
        ttl = str(row[3]).strip() if row[3] else ""
        golongan = str(row[5]).strip() if row[5] else ""
        tmt_gol = str(row[6]).strip() if row[6] else ""
        jabatan = str(row[7]).strip() if row[7] else ""
        status_peg = str(row[8]).strip() if row[8] else ""
        kedudukan = str(row[9]).strip() if row[9] else "Aktif"

        guru_list.append({
            "nip": nip,
            "nama": nama,
            "ttl": ttl,
            "golongan": golongan,
            "tmt_golongan": tmt_gol,
            "jabatan": jabatan,
            "status_pegawai": status_peg,
            "kedudukan": kedudukan
        })

    (DATA_DIR / "guru.json").write_text(json.dumps(guru_list, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(guru_list)

def import_murid():
    file_murid = EXCEL_DIR / "2627=daftar_murid=v1.3.xlsx"
    if not file_murid.exists():
        print(f"[SKIP] File {file_murid.name} tidak ditemukan.")
        return 0

    wb = openpyxl.load_workbook(file_murid)
    murid_list = []
    for sname in ["10", "11", "12"]:
        if sname not in wb.sheetnames:
            continue
        sh = wb[sname]
        current_kelas = ""
        for row in sh.iter_rows(values_only=True):
            if row[0] and "Kelas :" in str(row[0]):
                current_kelas = str(row[0]).replace("Kelas :", "").strip()
            elif row[0] and isinstance(row[0], int) and row[1] and row[3]:
                nis = str(row[1]).strip()
                nisn = str(row[2]).strip() if row[2] else ""
                nama = str(row[3]).strip()
                jk = str(row[4]).strip() if len(row) > 4 and row[4] else ""
                agama = str(row[5]).strip() if len(row) > 5 and row[5] else ""

                murid_list.append({
                    "nis": nis,
                    "nisn": nisn,
                    "nama": nama,
                    "jk": jk,
                    "agama": agama,
                    "kelas": current_kelas
                })

    (DATA_DIR / "murid.json").write_text(json.dumps(murid_list, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(murid_list)

def import_kode_arsip():
    file_arsip = EXCEL_DIR / "KODE KLASIFIKASI ARSIP-SMAN 2 WONOSARI 2025.xlsx"
    if not file_arsip.exists():
        print(f"[SKIP] File {file_arsip.name} tidak ditemukan.")
        return 0

    wb = openpyxl.load_workbook(file_arsip)
    sh = wb.active
    kode_list = []
    for row in list(sh.iter_rows(values_only=True))[2:]:
        if row[1] and row[2]:
            kode = str(row[1]).strip()
            ket = str(row[2]).strip()
            kode_list.append({"kode": kode, "keterangan": ket})

    (DATA_DIR / "kode_arsip.json").write_text(json.dumps(kode_list, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(kode_list)

if __name__ == "__main__":
    count_g = import_guru()
    count_m = import_murid()
    count_a = import_kode_arsip()
    print(f"[OK] Data Guru berhasil diimpor: {count_g} orang.")
    print(f"[OK] Data Murid berhasil diimpor: {count_m} siswa.")
    print(f"[OK] Kode Klasifikasi Arsip berhasil diimpor: {count_a} kode.")
