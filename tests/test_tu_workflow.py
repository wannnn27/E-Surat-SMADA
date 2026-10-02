"""Operational access and reporting regressions using synthetic school data."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

import esurat
from tests import test_app as fixtures


class TUWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="esurat-tu-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.database = root / "tu.sqlite3"
        users = root / "users.json"
        users.write_text(json.dumps([
            {"username": name, "password_hash": generate_password_hash("test-password"), "role": role}
            for name, role in (("admin-tu", "admin"), ("operator-satu", "operator"), ("operator-dua", "operator"))
        ]), encoding="utf-8")
        self.app = esurat.create_app({
            "TESTING": True, "DATA_DIR": fixtures.FIXTURE_DATA_DIR, "DATABASE": self.database,
            "SECRET_KEY": "tu-test-secret", "AUTH_USERS_FILE": str(users),
            "AUTH_USERNAME": "", "AUTH_PASSWORD": "", "AUTH_PASSWORD_HASH": "",
            "AUTH_ENABLED": True, "BIND_HOST": "127.0.0.1", "INIT_DB_ON_CREATE": True,
            "KEPSEK_NIP": fixtures.TEST_KEPSEK_NIP, "NOW_FUNC": lambda: fixtures.FIXED_NOW,
        })
        self.client = self.app.test_client()

    def login(self, username="operator-satu", client=None):
        client = client or self.client
        token = client.get("/api/csrf").get_json()["csrf_token"]
        response = client.post("/login", data={
            "csrf_token": token, "username": username, "password": "test-password",
        })
        self.assertEqual(response.status_code, 302)
        return client.get("/api/csrf").get_json()["csrf_token"]

    def form(self):
        helper = object.__new__(fixtures.BackendIntegrationTests)
        helper.state = self.app.extensions["esurat_data"]
        return helper.valid_form("surat_keterangan_guru", request_id=str(uuid.uuid4()))

    def generate(self, client=None, form=None, token=None):
        client = client or self.client
        token = token or client.get("/api/csrf").get_json()["csrf_token"]
        return client.post("/generate", data=form or self.form(), headers={"X-CSRFToken": token})

    def test_anonymous_cannot_read_personnel_or_allocate_numbers(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        login = self.client.get("/login").get_data(as_text=True)
        self.assertNotIn("Buat surat tanpa login", login)
        for path in ("/api/list/guru", "/api/list/murid", "/api/search?q=Guru", "/api/list/riwayat", "/api/fields/izin_guru"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.get_json()["code"], "auth_required")
        self.assertEqual(self.generate().status_code, 401)
        with closing(sqlite3.connect(self.database)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM riwayat_surat").fetchone()[0], 0)

    def test_operator_can_work_but_cannot_administer(self):
        token = self.login()
        for path in ("/", "/admin", "/admin/history", "/admin/master-data", "/admin/guide", "/api/list/riwayat", "/api/history/export.csv"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        dashboard = self.client.get("/admin").get_data(as_text=True)
        self.assertNotIn('href="/admin/templates"', dashboard)
        self.assertIn("Dashboard TU", dashboard)
        self.assertIn("operator-satu", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/templates").status_code, 403)
        for path in ("/admin/templates", "/admin/templates/example/delete", "/api/history/1/cancel", "/admin/history/1/cancel"):
            self.assertEqual(self.client.post(path, data={"csrf_token": token}).status_code, 403, path)
        form = self.form()
        generated = self.generate(form=form)
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(self.generate(form=form).headers["X-Letter-Number"], generated.headers["X-Letter-Number"])
        row = self.client.get("/api/list/riwayat").get_json()["items"][0]
        self.assertEqual((row["created_by"], row["created_by_role"]), ("operator-satu", "operator"))
        history_html = self.client.get("/admin/history").get_data(as_text=True)
        self.assertNotIn("Batalkan surat ini?", history_html)
        detail = self.client.get(f"/admin/history/{row['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(row["nomor_surat"], detail.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/history/999999").status_code, 404)
        form = self.form()
        form["nomor_surat_custom"] = "MANUAL/2026/TEST"
        self.assertEqual(self.generate(form=form).status_code, 422)

    def test_absolute_session_expiry_denies_api_and_preserves_relogin_path(self):
        self.login()
        with self.client.session_transaction() as session:
            session["login_started_at"] = time.time() - 8 * 3600 - 1
        response = self.client.get("/api/list/guru")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "auth_required")
        self.assertTrue(self.client.get("/admin/history?q=surat").headers["Location"].startswith("/login?next="))
        self.assertFalse(self.client.get("/api/csrf").get_json()["authenticated"])

    def test_changed_or_disabled_user_invalidates_session(self):
        self.login()
        self.app.extensions["auth_users"].pop("operator-satu")
        self.assertEqual(self.client.get("/api/list/murid").status_code, 401)

    def test_another_operator_cannot_reuse_request(self):
        self.login()
        form = self.form()
        first = self.generate(form=form)
        self.assertEqual(first.status_code, 200)
        second = self.app.test_client()
        token = self.login("operator-dua", second)
        denied = self.generate(second, form, token)
        self.assertEqual(denied.status_code, 403)
        self.assertIn("operator lain", denied.get_json()["error"])

    def test_template_change_cannot_silently_change_an_existing_number(self):
        self.login()
        form = self.form()
        first = self.generate(form=form)
        self.assertEqual(first.status_code, 200)
        self.app.extensions["builtin_template_hashes"][form["jenis_surat"]] = "new-template-hash"
        retry = self.generate(form=form)
        self.assertEqual(retry.status_code, 409)
        self.assertIn("Template surat telah berubah", retry.get_json()["error"])
        self.assertEqual(self.client.get("/api/list/riwayat").get_json()["total"], 1)

    def test_login_throttling_remains_a_browser_page(self):
        token = self.client.get("/api/csrf").get_json()["csrf_token"]
        for _ in range(5):
            self.assertEqual(self.client.post("/login", data={"csrf_token": token, "username": "missing", "password": "wrong"}).status_code, 401)
        blocked = self.client.post("/login", data={"csrf_token": token, "username": "missing", "password": "wrong"})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.mimetype, "text/html")
        self.assertIn("Terlalu banyak percobaan", blocked.get_data(as_text=True))

    def test_date_filters_include_whole_wib_day_and_match_csv(self):
        self.login()
        for _ in range(3):
            self.assertEqual(self.generate().status_code, 200)
        with closing(sqlite3.connect(self.database)) as conn:
            ids = [row[0] for row in conn.execute("SELECT id FROM riwayat_surat ORDER BY id")]
            for record_id, stamp in zip(ids, ("2026-08-22T16:59:59+00:00", "2026-08-22T17:00:00+00:00", "2026-08-23T23:59:59+07:00")):
                conn.execute("UPDATE riwayat_surat SET created_at = ? WHERE id = ?", (stamp, record_id))
            conn.commit()
        query = "?start=2026-08-23&end=2026-08-23&operator=operator-satu"
        response = self.client.get("/api/list/riwayat" + query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 2)
        records = list(csv.reader(io.StringIO(self.client.get("/api/history/export.csv" + query).data.decode("utf-8-sig"))))
        self.assertEqual(len(records), 3)
        html = self.client.get("/admin/history" + query).get_data(as_text=True)
        self.assertIn('name="start"', html)
        self.assertIn("start=2026-08-23", html)
        self.assertEqual(self.client.get("/api/list/riwayat?operator=operator-dua").get_json()["total"], 0)

    def test_invalid_filters_fail_before_export(self):
        self.login()
        for query in ("start=2026-02-30", "start=20260823", "start=2026-08-24&end=2026-08-23", "operator=%27%20OR%201=1", "end=9999-12-31"):
            for path in ("/api/list/riwayat", "/api/history/export.csv", "/admin/history"):
                response = self.client.get(path + "?" + query)
                self.assertEqual(response.status_code, 400, path + query)
                if path.startswith("/admin"):
                    self.assertEqual(response.mimetype, "text/html")
        self.assertEqual(self.client.get("/api/list/riwayat?q=%25").get_json()["total"], 0)

    def test_master_directory_searches_official_data_and_paginates(self):
        self.login()
        person = self.app.extensions["esurat_data"]["murid"][0]
        response = self.client.get("/admin/master-data", query_string={"kind": "murid", "q": person["nisn"]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(person["nama"], response.get_data(as_text=True))
        self.assertIn("1 data ditemukan", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/master-data?kind=invalid").status_code, 400)

    def test_login_rejects_external_and_backslash_redirects(self):
        for next_path in ("//evil.example", "/\\evil.example", "https://evil.example"):
            client = self.app.test_client()
            token = client.get("/api/csrf").get_json()["csrf_token"]
            response = client.post("/login", data={"csrf_token": token, "username": "operator-satu", "password": "test-password", "next": next_path})
            self.assertEqual(response.headers["Location"], "/admin")

    def test_admin_can_cancel_and_read_audit_detail(self):
        token = self.login("admin-tu")
        self.assertEqual(self.generate().status_code, 200)
        record_id = self.client.get("/api/list/riwayat").get_json()["items"][0]["id"]
        response = self.client.post(f"/admin/history/{record_id}/cancel", data={
            "csrf_token": token, "reason": "Koreksi isi atas permintaan TU", "confirm": "CANCEL",
            "start": "2026-08-23", "operator": "admin-tu",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("start=2026-08-23", response.headers["Location"])
        detail = self.client.get(f"/admin/history/{record_id}").get_data(as_text=True)
        self.assertIn("Koreksi isi atas permintaan TU", detail)
        self.assertIn("Dibatalkan oleh", detail)


if __name__ == "__main__":
    unittest.main()
