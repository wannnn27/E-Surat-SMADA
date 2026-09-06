from __future__ import annotations

import html
import io
import json
import os
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
from werkzeug.security import generate_password_hash
from werkzeug.datastructures import MultiDict


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
        if response.mimetype == "application/pdf":
            return f"PDF response ({len(response.data)} bytes)"
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
                    "created_by",
                    "created_by_role",
                    "cancelled_at",
                    "cancelled_by",
                    "cancel_reason",
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
                self.assertEqual(generated.headers["X-Document-Format"], "docx")
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
        self.assertEqual(missing.get_json()["code"], "csrf_invalid")

        wrong = self.post("/api/preview_render", form, token="token-yang-salah")
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(wrong.get_json()["code"], "csrf_invalid")
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

        pdf_form = dict(form)
        pdf_form["output_format"] = "pdf"
        pdf = self.post("/generate", pdf_form)
        self.assertEqual(pdf.status_code, 200, self.response_message(pdf))
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertEqual(pdf.headers["X-Document-Format"], "pdf")
        self.assertEqual(pdf.headers["X-Letter-Number"], first_number)
        self.assertIn(".pdf", pdf.headers["Content-Disposition"])
        self.assertTrue(pdf.data.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", pdf.data[-1024:])
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

        invalid_format = self.valid_form("izin_guru")
        invalid_format["output_format"] = "exe"
        invalid_response = self.post("/generate", invalid_format)
        self.assertEqual(invalid_response.status_code, 422)
        self.assertIn("output_format", invalid_response.get_json()["field_errors"])
        self.assertIsNone(self.history_for(invalid_format["request_id"]))

    def test_09_public_user_cannot_use_manual_number(self) -> None:
        manual = "800.1.11/900/SMADA/2026"
        first = self.valid_form("izin_guru", custom_number=manual)
        first_response = self.post("/generate", first)
        self.assertEqual(first_response.status_code, 422)
        self.assertIn("nomor_surat_custom", first_response.get_json()["field_errors"])

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

    def test_14_public_actor_history_and_cancellation_are_admin_only(self) -> None:
        form = self.valid_form("surat_keterangan_guru")
        generated = self.post("/generate", form)
        self.assertEqual(generated.status_code, 200, self.response_message(generated))
        row = self.history_for(form["request_id"])
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["created_by"], "public")
        self.assertEqual(row["created_by_role"], "user")

        cancelled = self.post(
            f"/api/history/{row['id']}/cancel",
            {"reason": "Dibatalkan pada pengujian terkontrol"},
        )
        self.assertEqual(cancelled.status_code, 403, self.response_message(cancelled))

        filtered = self.client.get(
            "/api/list/riwayat?status=cancelled&jenis=surat_keterangan_guru&page=1&per_page=10"
        )
        self.assertEqual(filtered.status_code, 403)

        exported = self.client.get(
            "/api/history/export.csv?status=cancelled&jenis=surat_keterangan_guru"
        )
        self.assertEqual(exported.status_code, 403)

    def test_15_dispensation_accepts_one_to_three_unique_students(self) -> None:
        students = self.state["murid"][:3]
        base_form = self.valid_form("dispensasi_murid")
        student_ids = [student["nis"] for student in students]
        form = MultiDict([*base_form.items(), *(("student_ids", value) for value in student_ids)])
        preview = self.post("/api/preview_render", form)
        self.assertEqual(preview.status_code, 200, self.response_message(preview))
        payload = preview.get_json()
        self.assertEqual([item["nis"] for item in payload["students"]], student_ids)
        self.assertEqual(len(payload["context"]["students"]), 3)

        generated = self.post("/generate", form)
        self.assertEqual(generated.status_code, 200, self.response_message(generated))
        text, xml = self.docx_text_and_xml(generated.data)
        self.assertNotRegex(xml, esurat.UNRESOLVED_TOKEN_RE)
        for student in students:
            self.assertIn(student["nama"], text)
            self.assertIn(student["nis"], text)
        row = self.history_for(form["request_id"])
        self.assertEqual(row["nama_pemohon"], ", ".join(item["nama"] for item in students))
        self.assertEqual(row["id_pemohon"], ", ".join(item["nis"] for item in students))

        pdf_form = MultiDict(form)
        pdf_form.setlist("student_ids", student_ids)
        pdf_form["output_format"] = "pdf"
        pdf = self.post("/generate", pdf_form)
        self.assertEqual(pdf.status_code, 200, self.response_message(pdf))
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertEqual(pdf.headers["X-Letter-Number"], generated.headers["X-Letter-Number"])
        self.assertIn("dan-2-siswa.pdf", pdf.headers["Content-Disposition"])

        duplicate_base = self.valid_form("dispensasi_murid")
        duplicate = MultiDict(
            [*duplicate_base.items(), ("student_ids", students[0]["nis"]), ("student_ids", students[0]["nis"])]
        )
        duplicate_response = self.post("/api/preview_render", duplicate)
        self.assertEqual(duplicate_response.status_code, 422)
        self.assertIn("student_ids", duplicate_response.get_json()["field_errors"])

        too_many_base = self.valid_form("dispensasi_murid")
        too_many = MultiDict(
            [*too_many_base.items(), *(("student_ids", item["nis"]) for item in self.state["murid"][:4])]
        )
        too_many_response = self.post("/api/preview_render", too_many)
        self.assertEqual(too_many_response.status_code, 422)
        self.assertIn("student_ids", too_many_response.get_json()["field_errors"])

    def test_16_all_seven_types_can_generate_pdf(self) -> None:
        for jenis in esurat.JENIS_SURAT:
            with self.subTest(jenis=jenis):
                form = self.valid_form(jenis)
                form["output_format"] = "pdf"
                generated = self.post("/generate", form)
                self.assertEqual(generated.status_code, 200, self.response_message(generated))
                self.assertEqual(generated.mimetype, "application/pdf")
                self.assertEqual(generated.headers["X-Document-Format"], "pdf")
                self.assertIn(".pdf", generated.headers["Content-Disposition"])
                self.assertTrue(generated.data.startswith(b"%PDF-"))
                self.assertIn(b"%%EOF", generated.data[-1024:])
                row = self.history_for(form["request_id"])
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "generated")


class DataContractTests(unittest.TestCase):
    def test_public_user_mode_is_supported_on_loopback(self) -> None:
        app = esurat.create_app(
            {
                "TESTING": True,
                "DATA_DIR": FIXTURE_DATA_DIR,
                "DATABASE": Path(tempfile.gettempdir()) / "public-user-mode.sqlite3",
                "AUTH_ENABLED": False,
                "BIND_HOST": "127.0.0.1",
                "KEPSEK_NIP": TEST_KEPSEK_NIP,
                "SECRET_KEY": "",
            }
        )
        self.assertFalse(app.config["AUTH_ENABLED"])

    def test_vercel_deployment_requires_persistent_postgres(self) -> None:
        with patch.dict(os.environ, {"VERCEL": "1"}):
            with self.assertRaisesRegex(esurat.DataValidationError, "DATABASE_URL PostgreSQL"):
                esurat.create_app(
                    {
                        "TESTING": False,
                        "DATA_DIR": FIXTURE_DATA_DIR,
                        "DATABASE": Path(tempfile.gettempdir()) / "temporary-vercel.sqlite3",
                    }
                )

    def test_vercel_runtime_verifies_schema_without_running_migration(self) -> None:
        state = {"guru": [], "murid": [], "kode_arsip": [], "kepsek": {}}
        with (
            patch.dict(os.environ, {"VERCEL": "1"}),
            patch.object(application_module, "_load_master_state", return_value=state),
            patch.object(application_module, "verify_postgres_runtime") as verify_runtime,
            patch.object(application_module, "init_db") as migrate_database,
            patch.object(application_module, "load_custom_templates", return_value={}),
        ):
            deployed_app = esurat.create_app(
                {
                    "TESTING": False,
                    "DATABASE": "postgresql://example.invalid/postgres?sslmode=require",
                    "AUTH_ENABLED": True,
                    "AUTH_USERNAME": "admin-tu",
                    "AUTH_PASSWORD": "",
                    "AUTH_PASSWORD_HASH": generate_password_hash("password-pengujian"),
                    "SECRET_KEY": "stable-production-test-secret",
                    "AUTO_MIGRATE_DATABASE": False,
                }
            )
            deployed_app.extensions["ensure_database"]()

        verify_runtime.assert_called_once_with(
            "postgresql://example.invalid/postgres?sslmode=require"
        )
        migrate_database.assert_not_called()

    def test_users_file_requires_an_active_account(self) -> None:
        with tempfile.TemporaryDirectory(prefix="esurat-inactive-users-") as temp_dir:
            users_file = Path(temp_dir) / "users.json"
            users_file.write_text(
                json.dumps(
                    [
                        {
                            "username": "operator-nonaktif",
                            "password_hash": generate_password_hash("password-pengujian"),
                            "role": "admin",
                            "active": False,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(esurat.DataValidationError, "satu akun aktif"):
                esurat.create_app(
                    {
                        "TESTING": True,
                        "DATA_DIR": FIXTURE_DATA_DIR,
                        "AUTH_USERS_FILE": str(users_file),
                        "AUTH_USERNAME": "",
                        "AUTH_PASSWORD": "",
                        "AUTH_PASSWORD_HASH": "",
                    }
                )

    def test_plaintext_password_is_rejected_outside_testing(self) -> None:
        with self.assertRaisesRegex(esurat.DataValidationError, "plaintext tidak didukung"):
            esurat.create_app(
                {
                    "TESTING": False,
                    "DATA_DIR": FIXTURE_DATA_DIR,
                    "AUTH_USERNAME": "operator-tu",
                    "AUTH_PASSWORD": "jangan-dipakai-di-produksi",
                    "AUTH_PASSWORD_HASH": "",
                    "SECRET_KEY": "test-only-secret",
                }
            )

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

    def test_public_user_admin_gate_and_form_login_logout(self) -> None:
        browser = self.client.get("/", follow_redirects=False)
        self.assertEqual(browser.status_code, 200)
        self.assertIn("Login Admin", browser.get_data(as_text=True))

        api = self.client.get("/api/list/guru")
        self.assertEqual(api.status_code, 200)
        self.assertGreater(len(api.get_json()), 0)

        for admin_path in ("/admin", "/admin/templates", "/admin/master-data"):
            admin_page = self.client.get(admin_path, follow_redirects=False)
            self.assertEqual(admin_page.status_code, 302)
            self.assertIn("/login?next=", admin_page.headers["Location"])
        self.assertEqual(self.client.get("/api/list/riwayat").status_code, 403)

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
        self.assertEqual(logged_in.headers["Location"], "/admin")
        self.assertEqual(self.client.get("/").status_code, 200)
        dashboard = self.client.get("/admin")
        self.assertEqual(dashboard.status_code, 200)
        dashboard_html = dashboard.get_data(as_text=True)
        self.assertIn("Dashboard Admin", dashboard_html)
        self.assertIn("Ringkasan operasional", dashboard_html)
        self.assertIn("Status sistem", dashboard_html)

        templates_page = self.client.get("/admin/templates")
        self.assertEqual(templates_page.status_code, 200)
        self.assertIn("Unggah template DOCX", templates_page.get_data(as_text=True))

        master_page = self.client.get("/admin/master-data")
        self.assertEqual(master_page.status_code, 200)
        master_html = master_page.get_data(as_text=True)
        self.assertIn("Data Master", master_html)
        self.assertIn("Guru &amp; staf", master_html)
        with self.client.session_transaction() as auth_session:
            self.assertEqual(auth_session["role"], "admin")
            self.assertTrue(auth_session.permanent)

        new_token = self.csrf()
        logged_out = self.client.post(
            "/logout", data={"csrf_token": new_token}, follow_redirects=False
        )
        self.assertEqual(logged_out.status_code, 302)
        self.assertEqual(logged_out.headers["Location"], "/")

    def test_login_rate_limit(self) -> None:
        token = self.csrf()
        for _ in range(5):
            response = self.client.post(
                "/login",
                data={"csrf_token": token, "username": "tidak-ada", "password": "salah"},
            )
            self.assertEqual(response.status_code, 401)
        blocked = self.client.post(
            "/login",
            data={"csrf_token": token, "username": "tidak-ada", "password": "salah"},
        )
        self.assertEqual(blocked.status_code, 429)

    def test_disabled_account_invalidates_existing_session(self) -> None:
        token = self.csrf()
        logged_in = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "operator-tu",
                "password": "password-pengujian",
            },
        )
        self.assertEqual(logged_in.status_code, 302)
        users = self.app.extensions["auth_users"]
        saved = users.pop("operator-tu")
        try:
            self.assertEqual(self.client.get("/api/list/guru").status_code, 200)
            denied = self.client.get("/api/list/riwayat")
            self.assertEqual(denied.status_code, 403)
            csrf_state = self.client.get("/api/csrf").get_json()
            self.assertFalse(csrf_state["authenticated"])
        finally:
            users["operator-tu"] = saved


class PublicAdminWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="esurat-public-admin-tests-")
        root = Path(cls.temp_dir.name)
        cls.database = root / "multi-user.sqlite3"
        cls.users_file = root / "users.json"
        cls.users_file.write_text(
            json.dumps(
                [
                    {
                        "username": "admin-satu",
                        "password_hash": generate_password_hash("password-admin"),
                        "role": "admin",
                    }
                ]
            ),
            encoding="utf-8",
        )
        cls.app = esurat.create_app(
            {
                "TESTING": True,
                "DATA_DIR": FIXTURE_DATA_DIR,
                "DATABASE": cls.database,
                "INIT_DB_ON_CREATE": True,
                "SECRET_KEY": "multi-user-test-secret",
                "AUTH_USERS_FILE": str(cls.users_file),
                "AUTH_USERNAME": "",
                "AUTH_PASSWORD": "",
                "AUTH_PASSWORD_HASH": "",
                "AUTH_ENABLED": True,
                "BIND_HOST": "127.0.0.1",
                "KEPSEK_NIP": TEST_KEPSEK_NIP,
                "NOW_FUNC": lambda: FIXED_NOW,
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def login(self, client, username: str, password: str) -> str:
        token = client.get("/api/csrf").get_json()["csrf_token"]
        response = client.post(
            "/login",
            data={"csrf_token": token, "username": username, "password": password},
        )
        self.assertEqual(response.status_code, 302)
        return client.get("/api/csrf").get_json()["csrf_token"]

    def test_public_generation_and_admin_management_boundaries(self) -> None:
        public = self.app.test_client()
        public_csrf = public.get("/api/csrf").get_json()["csrf_token"]
        person = self.app.extensions["esurat_data"]["guru"][0]
        form = {
            "jenis_surat": "surat_keterangan_guru",
            "kategori": "guru",
            "id_value": person["nip"],
            "tanggal_surat": "2026-08-23",
            "tanggal_mulai": "2026-08-24",
            "kode_arsip": "800.1.11",
            "nomor_surat_custom": "MANUAL/001/2026",
            "keperluan": "Pengujian akun individual",
            "request_id": str(uuid.uuid4()),
        }
        manual = public.post(
            "/generate", data=form, headers={"X-CSRFToken": public_csrf}
        )
        self.assertEqual(manual.status_code, 422)
        self.assertIn("nomor_surat_custom", manual.get_json()["field_errors"])

        form["nomor_surat_custom"] = ""
        form["request_id"] = str(uuid.uuid4())
        generated = public.post(
            "/generate", data=form, headers={"X-CSRFToken": public_csrf}
        )
        self.assertEqual(generated.status_code, 200)
        conn = sqlite3.connect(self.database)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM riwayat_surat WHERE request_id = ?", (form["request_id"],)
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["created_by"], "public")
        self.assertEqual(row["created_by_role"], "user")

        denied = public.post(
            f"/api/history/{row['id']}/cancel",
            data={"reason": "Pengguna mencoba membatalkan"},
            headers={"X-CSRFToken": public_csrf},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(public.get("/api/list/riwayat").status_code, 403)

        admin = self.app.test_client()
        admin_csrf = self.login(admin, "admin-satu", "password-admin")
        cancelled = admin.post(
            f"/api/history/{row['id']}/cancel",
            data={"reason": "Dibatalkan oleh admin pengujian"},
            headers={"X-CSRFToken": admin_csrf},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["cancelled_by"], "admin-satu")
        self.assertEqual(admin.get("/api/list/riwayat").status_code, 200)
        dashboard_html = admin.get("/admin").get_data(as_text=True)
        self.assertIn(person["nama"], dashboard_html)
        self.assertIn("Dibatalkan", dashboard_html)

        manual_number = "MANUAL/001/2026"
        form["nomor_surat_custom"] = manual_number
        form["request_id"] = str(uuid.uuid4())
        first_manual = admin.post(
            "/generate", data=form, headers={"X-CSRFToken": admin_csrf}
        )
        self.assertEqual(first_manual.status_code, 200)
        self.assertEqual(first_manual.headers["X-Letter-Number"], manual_number)
        form["request_id"] = str(uuid.uuid4())
        duplicate_manual = admin.post(
            "/generate", data=form, headers={"X-CSRFToken": admin_csrf}
        )
        self.assertEqual(duplicate_manual.status_code, 409)

    def test_admin_can_add_render_and_delete_custom_template(self) -> None:
        admin = self.app.test_client()
        admin_csrf = self.login(admin, "admin-satu", "password-admin")
        template_bytes = (esurat.TEMPLATE_DIR / "izin_murid.docx").read_bytes()
        uploaded = admin.post(
            "/admin/templates",
            data={
                "_csrf_token": admin_csrf,
                "key": "custom_izin_murid",
                "label": "Template Izin Murid Tambahan",
                "description": "Template tambahan yang dikelola administrator.",
                "category": "murid",
                "signer": "wali",
                "default_code": "400.3.8.9",
                "template_file": (io.BytesIO(template_bytes), "custom.docx"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(uploaded.status_code, 302, uploaded.get_data(as_text=True))
        self.assertIn("/admin/templates?success=", uploaded.headers["Location"])
        self.assertIn("custom_izin_murid", self.app.extensions["letter_registry"])

        student = self.app.extensions["esurat_data"]["murid"][0]
        form = {
            "jenis_surat": "custom_izin_murid",
            "kategori": "murid",
            "id_value": student["nis"],
            "tanggal_surat": "2026-08-23",
            "tanggal_mulai": "2026-08-24",
            "tanggal_selesai": "2026-08-25",
            "kode_arsip": "400.3.8.9",
            "nomor_surat_custom": "",
            "nama_wali": "Wali Template Tambahan",
            "keperluan": "Pengujian template tambahan",
            "request_id": str(uuid.uuid4()),
        }
        generated = admin.post("/generate", data=form, headers={"X-CSRFToken": admin_csrf})
        self.assertEqual(
            generated.status_code,
            200,
            BackendIntegrationTests.response_message(generated),
        )
        text, _xml = BackendIntegrationTests.docx_text_and_xml(generated.data)
        self.assertIn("Pengujian template tambahan", text)

        pdf_form = dict(form)
        pdf_form["output_format"] = "pdf"
        generated_pdf = admin.post(
            "/generate", data=pdf_form, headers={"X-CSRFToken": admin_csrf}
        )
        self.assertEqual(generated_pdf.status_code, 200)
        self.assertEqual(generated_pdf.mimetype, "application/pdf")
        self.assertEqual(
            generated_pdf.headers["X-Letter-Number"],
            generated.headers["X-Letter-Number"],
        )

        deleted = admin.post(
            "/admin/templates/custom_izin_murid/delete",
            data={"_csrf_token": admin_csrf, "confirm": "DELETE"},
            follow_redirects=False,
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertNotIn("custom_izin_murid", self.app.extensions["letter_registry"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
