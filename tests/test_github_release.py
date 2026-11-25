import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core import windows_credentials
from core.github_release import GitHubRelease, REPOSITORY, prepare_draft
from core.update_signing import PUBLIC_KEY_NAME, verify_package


COMMIT = "a" * 40
VERSION = "1.1.4"
TAG = f"v{VERSION}"
ZIP = f"TroLyCongVan_DRVN_{TAG}.zip"
REVIEW_URL = f"https://github.com/{REPOSITORY}/releases/tag/{TAG}"


class Response:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def json(self):
        return self.data

    def iter_content(self, **kwargs):
        yield self.data


class FakeGitHub:
    def __init__(self):
        self.release = None
        self.fail_manifest = False
        self.uploaded = {}
        self.requests = []

    def get(self, url, **kwargs):
        assert url == f"https://codeload.github.com/{REPOSITORY}/zip/{COMMIT}"
        assert "headers" not in kwargs
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("source/main.py", "app = True\n")
            archive.writestr("source/version.json", json.dumps({"version": VERSION, "changelog": ["Mẫu"]}))
            archive.writestr("source/core/sample.py", "sample = 1\n")
            archive.writestr("source/.env", "TEST_PLACEHOLDER")
            archive.writestr("source/drvn_data.db", b"test-data")
        return Response(data=stream.getvalue())

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        assert kwargs["allow_redirects"] is False
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        if url.endswith("/commits/main"):
            return Response(data={"sha": COMMIT})
        if url.endswith(f"/git/ref/tags/{TAG}"):
            return Response(404)
        if url.endswith("/releases"):
            if method == "GET":
                return Response(data=[self.release] if self.release else [])
            assert method == "POST" and kwargs["json"]["draft"] is True
            self.release = {**kwargs["json"], "id": 42, "html_url": REVIEW_URL, "assets": []}
            return Response(201, self.release)
        if url.endswith("/releases/42"):
            return Response(data=self.release)
        if url.endswith("/releases/42/assets"):
            name = kwargs["params"]["name"]
            if name == "version.json" and self.fail_manifest:
                return Response(502)
            assert self.release["draft"] and name not in self.uploaded
            self.uploaded[name] = data = kwargs["data"].read()
            asset = {"name": name, "state": "uploaded", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
            self.release["assets"].append(asset)
            return Response(201, asset)
        raise AssertionError(url)


class GitHubReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / "out"
        key = Ed25519PrivateKey.generate()
        (self.directory / PUBLIC_KEY_NAME).write_text(key.public_key().public_bytes_raw().hex(), encoding="ascii")
        store = patch.object(windows_credentials, "read", return_value=key.private_bytes_raw().hex())
        store.start()
        self.addCleanup(store.stop)
        self.server = FakeGitHub()

    def create(self, version=VERSION):
        return prepare_draft(GitHubRelease(self.server, "test-token"), self.directory, self.output, "main",
                             version=version)

    def test_build_sign_and_verify_both_draft_assets(self):
        self.assertEqual(self.create(), REVIEW_URL)
        self.assertEqual(set(self.server.uploaded), {ZIP, "version.json"})
        self.assertTrue(self.server.release["draft"])
        self.assertEqual(self.server.release["target_commitish"], COMMIT)
        manifest = json.loads(self.server.uploaded["version.json"])
        self.assertEqual(manifest["source_commit"], COMMIT)
        self.assertEqual(manifest["download_url"], f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{ZIP}")
        verify_package(self.directory, self.output / TAG / COMMIT / ZIP, manifest["package_signature"])
        with zipfile.ZipFile(io.BytesIO(self.server.uploaded[ZIP])) as archive:
            self.assertEqual(set(archive.namelist()), {"main.py", "core/sample.py", "version.json"})
        self.assertEqual(self.create(), REVIEW_URL)
        self.assertEqual([method for method, _ in self.server.requests].count("POST"), 3)

    def test_retry_completed_zip_without_replacing_it(self):
        self.server.fail_manifest = True
        with self.assertRaisesRegex(ValueError, "HTTP 502"):
            self.create()
        self.assertEqual(set(self.server.uploaded), {ZIP})
        self.server.fail_manifest = False
        self.assertEqual(self.create(), REVIEW_URL)
        self.assertEqual(set(self.server.uploaded), {ZIP, "version.json"})

    def test_refuses_published_release_and_version_mismatch(self):
        with self.assertRaisesRegex(ValueError, "khác phiên bản"):
            self.create("1.9.9")
        self.assertFalse(any(method == "POST" for method, _ in self.server.requests))
        self.create()
        self.server.release["draft"] = False
        self.server.requests.clear()
        with self.assertRaisesRegex(ValueError, "không còn là bản nháp"):
            self.create()
        self.assertFalse(any(method == "POST" for method, _ in self.server.requests))

    def test_refuses_to_replace_different_existing_asset(self):
        self.create()
        self.server.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        self.server.requests.clear()
        with self.assertRaisesRegex(ValueError, "không khớp"):
            self.create()
        self.assertFalse(any(method == "POST" for method, _ in self.server.requests))
