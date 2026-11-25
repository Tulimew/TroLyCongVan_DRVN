"""Ed25519 signatures for release archives and a local, pinned trust key."""

import base64
import hashlib
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core import windows_credentials


PUBLIC_KEY_NAME = "update_public_key.pub"
_KEY_NAME = "release_signing_key"
_SIGNATURE_CONTEXT = b"TroLyCongVan_DRVN signed ZIP v1\0"


def parse_release_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}", value):
        raise ValueError("Phiên bản phải có dạng x.y.z.")
    return tuple(map(int, value.split(".")))


def _signed_message(archive):
    with open(archive, "rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return _SIGNATURE_CONTEXT + digest.digest()


def _pinned_public_key(app_dir):
    path = Path(app_dir) / PUBLIC_KEY_NAME
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except FileNotFoundError as error:
        raise ValueError("Chưa cài khóa công khai tin cậy cho bản cập nhật.") from error


def initialize_signing_key(app_dir):
    """Run once, on the Windows account responsible for signing releases."""
    path = Path(app_dir) / PUBLIC_KEY_NAME
    db_path = Path(app_dir) / "drvn_data.db"
    existing = windows_credentials.read(db_path, _KEY_NAME)
    if path.exists():
        _release_private_key(app_dir)
        return path
    if existing:
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(existing))
    else:
        key = Ed25519PrivateKey.generate()
        windows_credentials.write(db_path, _KEY_NAME, key.private_bytes_raw().hex())
    with path.open("x", encoding="ascii") as stream:
        stream.write(key.public_key().public_bytes_raw().hex() + "\n")
    return path


def _release_private_key(app_dir):
    db_path = Path(app_dir) / "drvn_data.db"
    secret = windows_credentials.read(db_path, _KEY_NAME)
    if not secret:
        raise ValueError("Máy ký chưa có khóa riêng. Chạy admin_update_tool.py --init-signing-key.")
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret))
    if key.public_key().public_bytes_raw() != _pinned_public_key(app_dir):
        raise ValueError("Khóa ký trong Windows Credential Manager không khớp khóa công khai đã cài.")
    return key


def sign_package(app_dir, archive):
    key = _release_private_key(app_dir)
    return base64.b64encode(key.sign(_signed_message(archive))).decode("ascii")


def verify_package(app_dir, archive, signature):
    if not isinstance(signature, str) or len(signature) != 88:
        raise ValueError("Thiếu chữ ký Ed25519 hợp lệ của gói cập nhật.")
    public_key = Ed25519PublicKey.from_public_bytes(_pinned_public_key(app_dir))
    try:
        public_key.verify(base64.b64decode(signature, validate=True), _signed_message(archive))
    except (InvalidSignature, ValueError) as error:
        raise ValueError("Chữ ký gói cập nhật không hợp lệ.") from error
