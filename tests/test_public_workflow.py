"""Users generate without login; administrative actions stay protected."""

from __future__ import annotations

import os
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import esurat
from tests import test_tu_workflow as fixtures


class PublicWorkflowTests(unittest.TestCase):
    login = fixtures.TUWorkflowTests.login
    form = fixtures.TUWorkflowTests.form
    generate = fixtures.TUWorkflowTests.generate

    def setUp(self):
        fixtures.TUWorkflowTests.setUp(self)
        config = dict(self.app.config)
        config.pop("REQUIRE_LOGIN", None)
        with patch.dict(os.environ):
            os.environ.pop("ESURAT_REQUIRE_LOGIN", None)
            self.app = esurat.create_app(config)
        self.client = self.app.test_client()

    def test_user_can_preview_and_download_without_login(self):
        self.assertFalse(self.app.config["REQUIRE_LOGIN"])
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("Login Admin", self.client.get("/").get_data(as_text=True))
        for path in ("/api/fields/surat_keterangan_guru", "/api/search?q=GURU&kategori=guru", "/api/list/guru", "/api/list/murid", "/api/list/kode_arsip"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        state = self.client.get("/api/csrf").get_json()
        self.assertFalse(state["authenticated"])
        self.assertFalse(state["login_required"])
        form = self.form()
        preview = self.client.post("/api/preview_render", data=form, headers={"X-CSRFToken": state["csrf_token"]})
        self.assertEqual(preview.status_code, 200)
        word = self.generate(form=form)
        self.assertEqual(word.status_code, 200)
        pdf = self.generate(form={**form, "output_format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(word.headers["X-Letter-Number"], pdf.headers["X-Letter-Number"])
        with closing(sqlite3.connect(self.database)) as conn:
            rows = conn.execute("SELECT created_by, created_by_role FROM riwayat_surat").fetchall()
        self.assertEqual(rows, [("public", "user")])

    def test_anonymous_user_cannot_access_admin_actions(self):
        for path in ("/admin", "/admin/history", "/admin/history/1", "/admin/master-data", "/admin/templates"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.headers["Location"])
        for path in ("/api/list/riwayat", "/api/history/export.csv"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        token = self.client.get("/api/csrf").get_json()["csrf_token"]
        for path in ("/admin/templates", "/api/history/1/cancel", "/admin/templates/sample/delete"):
            self.assertEqual(self.client.post(path, data={"csrf_token": token}).status_code, 403, path)
        form = self.form()
        form["nomor_surat_custom"] = "MANUAL/TEST/2026"
        self.assertEqual(self.generate(form=form).status_code, 422)
        self.assertEqual(self.generate(token="incorrect-token").status_code, 403)

    def test_admin_can_login_and_manage_while_public_access_stays_open(self):
        self.login("admin-tu")
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/admin/templates").status_code, 200)
        self.assertEqual(self.client.get("/api/list/riwayat").status_code, 200)
        self.assertEqual(self.app.test_client().get("/").status_code, 200)
