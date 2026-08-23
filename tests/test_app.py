from __future__ import annotations

import html
import io
import json
import re
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import esurat
from esurat import application as application_module


FIXED_NOW = datetime(2026, 8, 23, 10, 30, tzinfo=esurat.WIB)
FIXTURE_DATA_DIR = Path(__file__).parent / "fixtures" / "master"
TEST_KEPSEK_NIP = "190000000000000001"


def load_fixture(name: str) -> list[dict[str, str]]:
    return json.loads((FIXTURE_DATA_DIR / name).read_text(encoding="utf-8"))


class BackendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="esurat-tests-")
        cls.database = Path(cls.temp_dir.name) / "test.sqlite3"
        cls.app = esurat.create_app(
            {
                "TESTING": True,
                "DATA_DIR": FIXTURE_DATA_DIR,
                "DATABASE": cls.database,
                "INIT_DB_ON_CREATE": True,
                "SECRET_KEY": "backend-test-secret",
                "AUTH_ENABLED": False,
                "BIND_HOST": "127.0.0.1",
                "KEPSEK_NIP": TEST_KEPSEK_NIP,
                "NOW_FUNC": lambda: FIXED_NOW,
            }
        )
        cls.state = cls.app.extensions["esurat_data"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        self.client = self.app.test_client()
        csrf_response = self.client.get("/api/csrf")
        self.assertEqual(csrf_response.status_code, 200)
        self.csrf = csrf_response.get_json()["csrf_token"]

    def post(self, path: str, data: dict[str, str], *, token: str | None = None):
        headers = {"X-CSRFToken": self.csrf if token is None else token}
        return self.client.post(path, data=data, headers=headers)

    @staticmethod
    def response_message(response) -> str:
        if response.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return f"DOCX response ({len(response.data)} bytes)"
        return response.get_data(as_text=True)

    def person_for(self, jenis: str) -> dict[str, str]:
        kategori = esurat.JENIS_SURAT[jenis]["kategori"]
        return self.state["guru"][0] if kategori == "guru" else self.state["murid"][0]

    def valid_form(
        self,
        jenis: str,
        *,
        request_id: str | None = None,
        custom_number: str = "",
        use_nisn: bool = False,
    ) -> dict[str, str]:
        info = esurat.JENIS_SURAT[jenis]
        person = self.person_for(jenis)
        if info["kategori"] == "guru":
            identifier = person["nip"]
        else:
            identifier = person["nisn"] if use_nisn else person["nis"]
        form: dict[str, str] = {
            "jenis_surat": jenis,
            "kategori": info["kategori"],
            "id_value": identifier,
            "tanggal_surat": "2026-08-23",
            "kode_arsip": info["default_kode"],
            "nomor_surat_custom": custom_number,
            "request_id": request_id or str(uuid.uuid4()),
        }
        text_values = {
            "keperluan": "Keterangan & Verifikasi Tata Usaha",
            "unit_kerja": "SMA Negeri 2 Wonosari",
            "lama_cuti": "2 hari",
            "alamat_selama_cuti": "Jalan Pengujian Nomor 1",
            "nama_wali": "Wali Penguji",
            "nama_kegiatan": "Kegiatan Pengujian",
            "penyelenggara": "Panitia Pengujian",
            "tempat_kegiatan": "Aula Sekolah",
        }
        for field in info["fields"]:
            name = field["name"]
            if field["type"] == "date":
                form[name] = "2026-08-24" if name == "tanggal_mulai" else "2026-08-25"
            elif field["type"] == "select":
                form[name] = field["options"][0]
            else:
                form[name] = text_values.get(name, str(field.get("default") or "Nilai Pengujian"))
        return form

    @staticmethod
    def docx_text_and_xml(blob: bytes) -> tuple[str, str]:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            xml_parts = [
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.startswith("word/") and name.endswith(".xml")
            ]
        xml = "".join(xml_parts)
        text = html.unescape(re.sub(r"<[^>]+>", "", xml))
        return text, xml

    def history_for(self, request_id: str) -> sqlite3.Row | None:
        conn = sqlite3.connect(self.database)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM riwayat_surat WHERE request_id = ?", (request_id,)
            ).fetchone()
        finally:
            conn.close()

    def test_01_factory_does_not_initialize_database_by_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="esurat-lazy-db-") as temp_dir:
            database = Path(temp_dir) / "lazy.sqlite3"
            lazy_app = esurat.create_app(
                {
                    "TESTING": True,
                    "DATA_DIR": FIXTURE_DATA_DIR,
                    "DATABASE": database,
                    "TEMPLATE_DIR": esurat.TEMPLATE_DIR,
                    "AUTH_ENABLED": False,
                    "BIND_HOST": "127.0.0.1",
                    "KEPSEK_NIP": TEST_KEPSEK_NIP,
                }
            )
            self.assertFalse(lazy_app.extensions["database_initialized"])
            self.assertFalse(database.exists())

    def test_02_migration_contains_additive_audit_columns_and_partial_indexes(self) -> None:
        conn = sqlite3.connect(self.database)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(riwayat_surat)")}
            self.assertTrue(
                {
                    "request_id",
                    "status",
                    "jenis_key",
                    "template",
                    "hash",
                    "payload_hash",
                    "error",
                    "updated_at",
                }.issubset(columns)
            )
            counter = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='nomor_counter'"
            ).fetchone()
            self.assertIsNotNone(counter)
            indexes = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='riwayat_surat'"
                )
            }
            self.assertIn("WHERE request_id IS NOT NULL", indexes["uq_riwayat_request_id_new"])
            self.assertIn("WHERE request_id IS NOT NULL", indexes["uq_riwayat_nomor_new"])
        finally:
            conn.close()

    def test_03_fields_schema_has_common_fields_for_all_letter_types(self) -> None:
        for jenis, info in esurat.JENIS_SURAT.items():
            with self.subTest(jenis=jenis):
                response = self.client.get(f"/api/fields/{jenis}")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                names = [field["name"] for field in payload["fields"]]
                self.assertEqual(
                    names[:3], ["tanggal_surat", "kode_arsip", "nomor_surat_custom"]
                )
                self.assertEqual(payload["fields"][0]["default"], "2026-08-23")
                self.assertEqual(payload["fields"][1]["default"], info["default_kode"])
                self.assertFalse(payload["fields"][2]["required"])

    def test_04_all_seven_types_preview_generate_signer_and_no_jinja_tokens(self) -> None:
        generated_numbers: list[str] = []
        for jenis, info in esurat.JENIS_SURAT.items():
            with self.subTest(jenis=jenis):
                form = self.valid_form(jenis)
                preview = self.post("/api/preview_render", form)
                self.assertEqual(preview.status_code, 200, self.response_message(preview))
                summary = preview.get_json()
                self.assertEqual(summary["context"]["nomor_surat"], esurat.AUTO_NUMBER_PREVIEW)

                person = self.person_for(jenis)
                signer_kind = info["signer"]
                if signer_kind == "pemohon":
                    expected_name = person["nama"]
                    expected_id = person["nip"]
                elif signer_kind == "wali":
                    expected_name = form["nama_wali"]
                    expected_id = ""
                else:
                    expected_name = self.state["kepsek"]["nama"]
                    expected_id = self.state["kepsek"]["nip"]
                self.assertEqual(summary["signer"]["nama"], expected_name)
                self.assertEqual(summary["signer"]["nip"], expected_id)
                self.assertEqual(summary["context"]["penandatangan_nama"], expected_name)
                self.assertEqual(summary["context"]["penandatangan_id"], expected_id)

                generated = self.post("/generate", form)
                self.assertEqual(generated.status_code, 200, self.response_message(generated))
                self.assertEqual(
                    generated.mimetype,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                number = generated.headers.get("X-Letter-Number", "")
                self.assertRegex(
                    number,
                    rf"^{re.escape(info['default_kode'])}/\d{{3}}/SMADA/2026$",
                )
                generated_numbers.append(number)
                text, xml = self.docx_text_and_xml(generated.data)
                self.assertNotRegex(xml, esurat.UNRESOLVED_TOKEN_RE)
                self.assertIn(person["nama"], text)
                self.assertIn(expected_name, text)
                if expected_id:
                    self.assertIn(expected_id, text)
                self.assertIn("Keterangan & Verifikasi Tata Usaha", text)

                row = self.history_for(form["request_id"])
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "generated")
                self.assertEqual(row["nomor_surat"], number)
                self.assertEqual(len(row["hash"]), 64)
                self.assertEqual(len(row["payload_hash"]), 64)
                self.assertIsNone(row["error"])
        self.assertEqual(len(generated_numbers), 7)
        self.assertEqual(len(set(generated_numbers)), 7)

    def test_05_nisn_search_and_identifier_resolution(self) -> None:
        murid = self.state["murid"][0]
        response = self.client.get(
            "/api/search", query_string={"kategori": "murid", "q": murid["nisn"]}
        )
        self.assertEqual(response.status_code, 200)
        results = response.get_json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["nisn"], murid["nisn"])
        self.assertEqual(
            set(results[0]), {"nis", "nisn", "nama", "kelas"}, "API harus meminimalkan PII"
        )

        form = self.valid_form("izin_murid", use_nisn=True)
        preview = self.post("/api/preview_render", form)
        self.assertEqual(preview.status_code, 200, self.response_message(preview))
        self.assertEqual(preview.get_json()["person"]["nis"], murid["nis"])

    def test_06_csrf_is_required(self) -> None:
        form = self.valid_form("izin_guru")
        no_token_client = self.app.test_client()
        missing = no_token_client.post("/api/preview_render", data=form)
        self.assertEqual(missing.status_code, 403)
        self.assertIn("error", missing.get_json())

        wrong = self.post("/api/preview_render", form, token="token-yang-salah")
        self.assertEqual(wrong.status_code, 403)
        valid = self.post("/api/preview_render", form)
        self.assertEqual(valid.status_code, 200)

    def test_07_date_identifier_category_archive_and_html_validation(self) -> None:
        cases: list[tuple[str, str, str]] = []

        alpha_id = self.valid_form("izin_guru")
        alpha_id["id_value"] = "bukan-nip"
        cases.append(("identifier alpha", "id_value", alpha_id))

        unknown_id = self.valid_form("izin_guru")
        unknown_id["id_value"] = "999999999999999999"
        cases.append(("identifier unknown", "id_value", unknown_id))

        reversed_dates = self.valid_form("izin_guru")
        reversed_dates["tanggal_mulai"] = "2026-08-26"
        reversed_dates["tanggal_selesai"] = "2026-08-25"
        cases.append(("date range", "tanggal_selesai", reversed_dates))

        invalid_category = self.valid_form("izin_guru")
        invalid_category["kategori"] = "murid"
        cases.append(("category", "kategori", invalid_category))

        invalid_archive = self.valid_form("izin_guru")
        invalid_archive["kode_arsip"] = "999.999"
        cases.append(("archive", "kode_arsip", invalid_archive))

        html_payload = self.valid_form("izin_guru")
        html_payload["keperluan"] = "<img src=x onerror=alert(1)>"
        cases.append(("html", "keperluan", html_payload))

        invalid_select = self.valid_form("cuti_guru")
        invalid_select["jenis_cuti"] = "Cuti Buatan Penyerang"
        cases.append(("select", "jenis_cuti", invalid_select))

        for label, expected_field, form in cases:
            with self.subTest(case=label):
                response = self.post("/api/preview_render", form)
                self.assertEqual(response.status_code, 422, self.response_message(response))
                payload = response.get_json()
                self.assertIn("error", payload)
                self.assertIn(expected_field, payload["field_errors"])

    def test_08_idempotent_request_reuses_number_and_rejects_changed_payload(self) -> None:
        request_id = str(uuid.uuid4())
        form = self.valid_form("izin_guru", request_id=request_id)
        first = self.post("/generate", form)
        self.assertEqual(first.status_code, 200, self.response_message(first))
        first_number = first.headers["X-Letter-Number"]

        second = self.post("/generate", form)
        self.assertEqual(second.status_code, 200, self.response_message(second))
        self.assertEqual(second.headers["X-Letter-Number"], first_number)
        conn = sqlite3.connect(self.database)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM riwayat_surat WHERE request_id = ?", (request_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

        changed = dict(form)
        changed["keperluan"] = "Payload yang sudah berubah"
        conflict = self.post("/generate", changed)
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("request_id", conflict.get_json()["field_errors"])

    def test_09_duplicate_manual_number_is_rejected(self) -> None:
        manual = "800.1.11/900/SMADA/2026"
        first = self.valid_form("izin_guru", custom_number=manual)
        first_response = self.post("/generate", first)
        self.assertEqual(first_response.status_code, 200, self.response_message(first_response))
        self.assertEqual(first_response.headers["X-Letter-Number"], manual)

        second = self.valid_form("izin_guru", custom_number=manual)
        second_response = self.post("/generate", second)
        self.assertEqual(second_response.status_code, 409)
        self.assertIn("nomor_surat_custom", second_response.get_json()["field_errors"])

    def test_10_render_failure_is_failed_and_retry_reuses_reserved_number(self) -> None:
        form = self.valid_form("izin_guru")
        with patch.object(
            application_module,
            "_render_letter",
            side_effect=RuntimeError("render test gagal"),
        ):
            failed = self.post("/generate", form)
        self.assertEqual(failed.status_code, 500)
        failed_row = self.history_for(form["request_id"])
        self.assertEqual(failed_row["status"], "failed")
        self.assertIn("render test gagal", failed_row["error"])

        retried = self.post("/generate", form)
        self.assertEqual(retried.status_code, 200, self.response_message(retried))
        self.assertEqual(retried.headers["X-Letter-Number"], failed_row["nomor_surat"])
        self.assertEqual(self.history_for(form["request_id"])["status"], "generated")

    def test_11_concurrent_generation_allocates_unique_numbers(self) -> None:
        request_ids = [str(uuid.uuid4()) for _ in range(6)]

        def generate_one(request_id: str) -> tuple[int, str, str]:
            with self.app.test_client() as client:
                csrf = client.get("/api/csrf").get_json()["csrf_token"]
                form = self.valid_form("izin_guru", request_id=request_id)
                response = client.post(
                    "/generate", data=form, headers={"X-CSRFToken": csrf}
                )
                return (
                    response.status_code,
                    response.headers.get("X-Letter-Number", ""),
                    self.response_message(response),
                )

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(generate_one, request_ids))
        failures = [(status, body) for status, _number, body in results if status != 200]
        self.assertEqual(failures, [])
        numbers = [number for _status, number, _body in results]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertTrue(all(re.fullmatch(r"800\.1\.11/\d{3}/SMADA/2026", number) for number in numbers))

    def test_12_security_headers_and_health(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

        secure = self.client.get("/healthz", environ_overrides={"wsgi.url_scheme": "https"})
        self.assertEqual(secure.status_code, 200)
        self.assertIn("max-age=31536000", secure.headers["Strict-Transport-Security"])
        self.assertEqual(secure.get_json()["status"], "ok")

    def test_13_unresolved_jinja_token_is_rejected(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<w:document>{{ belum_diisi }}</w:document>")
        with self.assertRaisesRegex(RuntimeError, "Placeholder template belum terisi"):
            esurat._check_rendered_docx(buffer)


class DataContractTests(unittest.TestCase):
    def test_duplicate_nip_and_nisn_fail_fast(self) -> None:
        guru = load_fixture("guru.json")
        murid = load_fixture("murid.json")
        kode = load_fixture("kode_arsip.json")
        with self.assertRaisesRegex(esurat.DataValidationError, "NIP duplikat"):
            esurat.validate_master_data(guru + [dict(guru[0])], murid, kode, TEST_KEPSEK_NIP)
        with self.assertRaisesRegex(esurat.DataValidationError, "NISN duplikat"):
            esurat.validate_master_data(
                guru,
                murid + [dict(murid[0], nis="999999")],
                kode,
                TEST_KEPSEK_NIP,
            )


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="esurat-auth-tests-")
        cls.app = esurat.create_app(
            {
                "TESTING": True,
                "DATA_DIR": FIXTURE_DATA_DIR,
                "DATABASE": Path(cls.temp_dir.name) / "auth.sqlite3",
                "INIT_DB_ON_CREATE": True,
                "SECRET_KEY": "auth-test-secret",
                "AUTH_ENABLED": True,
                "AUTH_USERNAME": "operator-tu",
                "AUTH_PASSWORD": "password-pengujian",
                "AUTH_PASSWORD_HASH": "",
                "BIND_HOST": "127.0.0.1",
                "KEPSEK_NIP": TEST_KEPSEK_NIP,
                "NOW_FUNC": lambda: FIXED_NOW,
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        self.client = self.app.test_client()

    def csrf(self) -> str:
        return self.client.get("/api/csrf").get_json()["csrf_token"]

    def test_browser_redirect_api_401_and_form_login_logout(self) -> None:
        browser = self.client.get("/", follow_redirects=False)
        self.assertEqual(browser.status_code, 302)
        self.assertIn("/login?next=/", browser.headers["Location"])

        api = self.client.get("/api/list/guru")
        self.assertEqual(api.status_code, 401)
        self.assertIn("error", api.get_json())

        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("csrf_token", login_page.get_data(as_text=True))

        missing_csrf = self.client.post(
            "/login", data={"username": "operator-tu", "password": "password-pengujian"}
        )
        self.assertEqual(missing_csrf.status_code, 403)

        token = self.csrf()
        wrong = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "operator-tu",
                "password": "salah",
            },
        )
        self.assertEqual(wrong.status_code, 401)

        token = self.csrf()
        logged_in = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "operator-tu",
                "password": "password-pengujian",
                "next": "//evil.example/path",
            },
            follow_redirects=False,
        )
        self.assertEqual(logged_in.status_code, 302)
        self.assertEqual(logged_in.headers["Location"], "/")
        self.assertEqual(self.client.get("/").status_code, 200)

        new_token = self.csrf()
        logged_out = self.client.post(
            "/logout", data={"csrf_token": new_token}, follow_redirects=False
        )
        self.assertEqual(logged_out.status_code, 302)
        self.assertIn("/login", logged_out.headers["Location"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
