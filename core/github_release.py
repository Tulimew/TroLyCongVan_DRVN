"""Build a signed update from a pinned GitHub commit and upload it to a draft."""

import hashlib
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests

from core import updater
from core.update_signing import parse_release_version
from update_transaction import MAX_PACKAGE_BYTES, is_managed_file


REPOSITORY = "Tulimew/TroLyCongVan_DRVN"
_API = f"https://api.github.com/repos/{REPOSITORY}"
_WEB = f"https://github.com/{REPOSITORY}"
_UPLOADS = f"https://uploads.github.com/repos/{REPOSITORY}"
_SHA = re.compile(r"[0-9a-f]{40}")


class GitHubRelease:
    def __init__(self, session, token):
        self.session = session
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def _request(self, method, url, expected, *, optional=False, content_type=None, **kwargs):
        headers = self.headers.copy()
        if content_type:
            headers["Content-Type"] = content_type
        with self.session.request(method, url, headers=headers, timeout=(10, 120),
                                  allow_redirects=False, **kwargs) as response:
            if optional and response.status_code == 404:
                return None
            if response.status_code != expected:
                raise ValueError(f"GitHub trả HTTP {response.status_code} ({method} {url}).")
            return response.json()

    def resolve_commit(self, ref):
        sha = self._request("GET", f"{_API}/commits/{quote(ref, safe='')}", 200)["sha"]
        if not _SHA.fullmatch(sha):
            raise ValueError("GitHub không trả mã commit hợp lệ.")
        return sha

    def source_archive(self, sha, destination):
        # The repository is public. Keep the GitHub credential out of this request.
        url = f"https://codeload.github.com/{REPOSITORY}/zip/{sha}"
        with self.session.get(url, stream=True, timeout=(10, 60), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError(f"Không lấy được mã nguồn đã chọn (HTTP {response.status_code}).")
            total = 0
            with destination.open("xb") as stream:
                for data in response.iter_content(chunk_size=65536):
                    total += len(data)
                    if total > MAX_PACKAGE_BYTES:
                        raise ValueError("Mã nguồn vượt giới hạn dung lượng.")
                    stream.write(data)

    def find_release(self, tag):
        page = 1
        while True:
            releases = self._request("GET", f"{_API}/releases", 200, params={"per_page": 100, "page": page})
            for release in releases:
                if release["tag_name"] == tag:
                    return release
            if len(releases) < 100:
                return None
            page += 1

    def create_draft(self, tag, commit, body):
        tag_ref = self._request("GET", f"{_API}/git/ref/tags/{tag}", 200, optional=True)
        if tag_ref and self.resolve_commit(f"tags/{tag}") != commit:
            raise ValueError(f"Tag {tag} đã trỏ đến một commit khác.")
        return self._request("POST", f"{_API}/releases", 201, json={
            "tag_name": tag, "target_commitish": commit, "name": f"Trợ lý Công văn DRVN {tag}",
            "body": body, "draft": True, "prerelease": False,
        })

    def read_release(self, release_id):
        return self._request("GET", f"{_API}/releases/{release_id}", 200)

    def upload_asset(self, release_id, path, content_type):
        with path.open("rb") as stream:
            return self._request("POST", f"{_UPLOADS}/releases/{release_id}/assets", 201,
                                 params={"name": path.name}, data=stream, content_type=content_type)


def _read_source(path):
    entries = {}
    total = 0
    with zipfile.ZipFile(path) as archive:
        roots = {info.filename.split("/", 1)[0] for info in archive.infolist()}
        if len(roots) != 1:
            raise ValueError("Cấu trúc ZIP mã nguồn không hợp lệ.")
        for info in archive.infolist():
            _, _, name = info.filename.partition("/")
            if not info.is_dir() and is_managed_file(name):
                key = name.casefold()
                if key in entries or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError(f"Tệp phát hành trùng hoặc không phải tệp thường: {name}")
                total += info.file_size
                if total > MAX_PACKAGE_BYTES:
                    raise ValueError("Các tệp phát hành vượt giới hạn dung lượng.")
                entries[key] = (name, archive.read(info))
    files = dict(entries.values())
    if not {"main.py", "version.json"} <= files.keys():
        raise ValueError("Commit thiếu main.py hoặc version.json.")
    return files


def _assert_draft(release, tag, commit):
    if release["tag_name"] != tag or release.get("draft") is not True:
        raise ValueError(f"{tag} không còn là bản nháp.")
    if release.get("target_commitish") != commit:
        raise ValueError(f"Bản nháp {tag} trỏ đến commit khác. Hãy kiểm tra trên GitHub.")


def _asset_matches(release, path):
    matches = [asset for asset in release["assets"] if asset["name"] == path.name]
    if not matches:
        return False
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if len(matches) != 1 or matches[0].get("state") != "uploaded" or matches[0].get("digest") != digest:
        raise ValueError(f"Tệp {path.name} đã có trên bản nháp nhưng không khớp gói cục bộ. Hãy kiểm tra trên GitHub.")
    return True


def prepare_draft(client, signing_dir, output_dir, ref, *, version=None, notes=None):
    commit = client.resolve_commit(ref)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.zip"
        client.source_archive(commit, source)
        files = _read_source(source)
    manifest = json.loads(files.pop("version.json"))
    source_version = manifest["version"]
    if parse_release_version(source_version) < parse_release_version(updater.APP_VERSION):
        raise ValueError(f"Commit đã chọn có phiên bản {source_version}, cũ hơn công cụ {updater.APP_VERSION}.")
    if version is not None and version != source_version:
        raise ValueError(f"Commit đã chọn khai báo phiên bản {source_version}, khác phiên bản yêu cầu {version}.")
    tag = f"v{source_version}"
    package_name = f"TroLyCongVan_DRVN_{tag}.zip"
    manifest["download_url"] = f"{_WEB}/releases/download/{tag}/{package_name}"
    manifest["source_commit"] = commit
    notes = notes if notes is not None else "\n".join(f"- {line}" for line in manifest.get("changelog", []))
    archive, version_file = updater.write_signed_release(
        signing_dir, Path(output_dir) / tag / commit / "version.json", manifest, files.items()
    )
    release = client.find_release(tag)
    if release is None:
        release = client.create_draft(tag, commit, notes)
    review_url = release["html_url"]
    if not review_url.startswith(f"{_WEB}/releases/"):
        raise ValueError("GitHub trả về đường dẫn duyệt bản nháp không đúng repository.")
    try:
        for path, content_type in ((archive, "application/zip"), (version_file, "application/json")):
            release = client.read_release(release["id"])
            _assert_draft(release, tag, commit)
            if not _asset_matches(release, path):
                client.upload_asset(release["id"], path, content_type)
        release = client.read_release(release["id"])
        _assert_draft(release, tag, commit)
        if not all(_asset_matches(release, path) for path in (archive, version_file)):
            raise ValueError("GitHub chưa xác nhận đủ hai tệp đã tải.")
    except (OSError, ValueError, requests.RequestException) as error:
        raise ValueError(f"{error}\nKiểm tra bản phát hành trên GitHub: {review_url}") from error
    return review_url
