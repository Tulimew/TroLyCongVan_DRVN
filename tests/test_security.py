import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import update_transaction
from core import db, updater, windows_credentials
from core.crawler import DRVNCrawler
from core.update_signing import PUBLIC_KEY_NAME, verify_package


class CredentialTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = str(Path(directory.name) / "drvn_data.db")
        db_path = patch.object(db, "DB_PATH", self.db_path)
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()

    def test_migrate_existing_secrets_and_keep_preferences(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executemany("INSERT INTO settings VALUES (?, ?)", [
                ("password", "sample-password"),
                ("session_cookies", '{"sample":"session"}'),
                ("interval_min", "5"),
            ])
        with patch.object(windows_credentials, "write") as write:
            db.init_db()
        write.assert_any_call(self.db_path, "password", "sample-password")
        write.assert_any_call(self.db_path, "session_cookies", '{"sample":"session"}')
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT * FROM settings").fetchall(), [("interval_min", "5")])

    def test_vault_failure_keeps_legacy_secret_for_next_attempt(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("INSERT INTO settings VALUES ('password', 'sample-password')")
        with patch.object(windows_credentials, "write", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                db.init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM settings").fetchone(), ("sample-password",))

    def test_new_secret_bypasses_sqlite(self):
        with patch.object(windows_credentials, "write") as write:
            db.set_setting("nhiemvu_token", "sample-token")
        write.assert_called_once_with(self.db_path, "nhiemvu_token", "sample-token")
        with patch.object(windows_credentials, "read", return_value="sample-token") as read:
            self.assertEqual(db.get_setting("nhiemvu_token"), "sample-token")
        read.assert_called_once_with(self.db_path, "nhiemvu_token", "")
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertIsNone(conn.execute("SELECT * FROM settings WHERE key = 'nhiemvu_token'").fetchone())

    def test_crawler_verifies_tls_and_rejects_http(self):
        with DRVNCrawler().session as session:
            self.assertIs(session.verify, True)
            with self.assertRaises(requests.exceptions.InvalidURL):
                session.get_adapter("http://example.invalid")

    @unittest.skipUnless(os.name == "nt", "Windows Credential Manager is required")
    def test_native_credential_manager_round_trip(self):
        key = "unittest_probe"
        try:
            windows_credentials.write(self.db_path, key, "Thông tin thử")
        except OSError as error:
            if error.winerror in (5, 1312):
                self.skipTest("The current Windows logon cannot access Credential Manager")
            raise
        self.addCleanup(windows_credentials.write, self.db_path, key, "")
        self.assertEqual(windows_credentials.read(self.db_path, key), "Thông tin thử")

    def test_application_starts_with_protected_settings(self):
        from PyQt6.QtWidgets import QApplication, QLabel
        from ui.main_window import MainWindow

        with (
            patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
            patch.object(windows_credentials, "read", side_effect=lambda path, key, default: default),
            patch.object(MainWindow, "start_background_scan"),
        ):
            application = QApplication.instance() or QApplication([])
            window = MainWindow()
            try:
                window.show()
                application.processEvents()
                self.assertTrue(window.isVisible())
                self.assertTrue(any(
                    f"(v{updater.APP_VERSION})" in label.text()
                    for label in window.findChildren(QLabel)
                ))
            finally:
                window.timer.stop()
                window.hide()
                window.deleteLater()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.app = self.root / "app"
        self.app.mkdir()
        (self.app / "main.py").write_text("old = True\n", encoding="utf-8")
        (self.app / "version.json").write_text('{"version": "1.1.1"}', encoding="utf-8")
        (self.app / "drvn_data.db").write_bytes(b"keep-data")
        self.key = Ed25519PrivateKey.generate()
        self.public_key = self.key.public_key().public_bytes_raw().hex()
        (self.app / PUBLIC_KEY_NAME).write_text(self.public_key, encoding="ascii")
        self.archive = self.root / "release.zip"
        with zipfile.ZipFile(self.archive, "w") as package:
            package.writestr("main.py", "new = True\n")
            package.writestr("core/new.py", "new_module = True\n")
            package.writestr("version.json", '{"version": "1.1.2"}')

    def test_release_manifest_signature_round_trip(self):
        manifest_path = self.root / "dist" / "version.json"
        with (
            patch.object(updater, "APP_DIR", str(self.app)),
            patch.object(updater, "release_manifest_path", return_value=manifest_path),
            patch.object(windows_credentials, "read", return_value=self.key.private_bytes_raw().hex()),
        ):
            result = updater.create_release_package("1.1.2")
        self.assertTrue(result["ok"], result)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        archive = Path(result["zip_path"])
        verify_package(self.app, archive, manifest["package_signature"])
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(set(package.namelist()), {"version.json", "main.py"})
        with archive.open("ab") as stream:
            stream.write(b"archive changed")
        with self.assertRaisesRegex(ValueError, "Chữ ký gói cập nhật"):
            verify_package(self.app, archive, manifest["package_signature"])
        self.assertEqual(json.loads((self.app / "version.json").read_text())["version"], "1.1.1")

    def test_unsigned_or_invalid_signature_leaves_installed_files_alone(self):
        with (
            patch.object(updater, "APP_DIR", str(self.app)),
            patch.object(updater, "APP_VERSION", "1.1.1"),
            patch.object(updater, "_download_archive", side_effect=lambda response, path, progress:
                              path.write_bytes(self.archive.read_bytes())),
            patch.object(updater, "_UpdateSession"),
            patch.object(updater, "_get_gdrive_confirm_token", return_value=None),
            patch.object(updater, "install_package") as install,
        ):
            url = "https://example.invalid/release.zip"
            for signature in ("", base64.b64encode(bytes(64)).decode("ascii")):
                with self.subTest(signature_present=bool(signature)):
                    ok, _ = updater.download_and_install_update(url, "1.1.2", signature)
                    self.assertFalse(ok)
        install.assert_not_called()
        self.assert_old_install()

    def test_verified_download_installs_new_version(self):
        message = b"TroLyCongVan_DRVN signed ZIP v1\0" + hashlib.sha256(self.archive.read_bytes()).digest()
        signature = base64.b64encode(self.key.sign(message)).decode("ascii")
        with (
            patch.object(updater, "APP_DIR", str(self.app)),
            patch.object(updater, "APP_VERSION", "1.1.1"),
            patch.object(updater, "_UpdateSession") as session,
            patch.object(updater, "_get_gdrive_confirm_token", return_value=None),
        ):
            response = session.return_value.__enter__.return_value.get.return_value.__enter__.return_value
            response.headers = {}
            response.iter_content.return_value = [self.archive.read_bytes()]
            ok, message = updater.download_and_install_update("https://example.invalid/release.zip", "1.1.2", signature)
        self.assertTrue(ok, message)
        self.assertEqual(json.loads((self.app / "version.json").read_text())["version"], "1.1.2")
        self.assert_local_data()

    def test_success_replaces_app_files_and_preserves_local_data(self):
        update_transaction.install_package(self.app, self.archive, "1.1.2")
        self.assertEqual((self.app / "main.py").read_text(), "new = True\n")
        self.assertEqual(json.loads((self.app / "version.json").read_text())["version"], "1.1.2")
        self.assert_local_data()

    def test_rollback_after_file_replacement_fails(self):
        replace = os.replace

        def fail_on_version(source, target):
            if target == self.app / "version.json":
                raise PermissionError("simulated locked file")
            return replace(source, target)

        with patch.object(update_transaction.os, "replace", side_effect=fail_on_version):
            with self.assertRaisesRegex(PermissionError, "simulated locked file"):
                update_transaction.install_package(self.app, self.archive, "1.1.2")
        self.assert_old_install()
        self.assertFalse((self.app / update_transaction.RECOVERY_DIR).exists())

    def test_recover_after_interrupted_process(self):
        replace = os.replace

        def interrupt_on_version(source, target):
            if target == self.app / "version.json":
                raise KeyboardInterrupt()
            return replace(source, target)

        with patch.object(update_transaction.os, "replace", side_effect=interrupt_on_version):
            with self.assertRaises(KeyboardInterrupt):
                update_transaction.install_package(self.app, self.archive, "1.1.2")
        self.assertEqual((self.app / "main.py").read_text(), "new = True\n")
        self.assertTrue(update_transaction.recover_interrupted_update(self.app))
        self.assert_old_install()

    def test_version_in_package_must_match_manifest(self):
        with self.assertRaisesRegex(ValueError, "không khớp"):
            update_transaction.install_package(self.app, self.archive, "1.1.3")
        self.assert_old_install()

    def assert_local_data(self):
        self.assertEqual((self.app / "drvn_data.db").read_bytes(), b"keep-data")
        self.assertEqual((self.app / PUBLIC_KEY_NAME).read_text(encoding="ascii"), self.public_key)

    def assert_old_install(self):
        self.assertEqual((self.app / "main.py").read_text(), "old = True\n")
        self.assertEqual(json.loads((self.app / "version.json").read_text())["version"], "1.1.1")
        self.assertFalse((self.app / "core" / "new.py").exists())
        self.assert_local_data()
