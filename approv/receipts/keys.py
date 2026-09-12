"""Encrypted local signing keys and an append-preserving public key publication.

Layout: private/<fingerprint>.pem, public/<fingerprint>.json, active.json.
Rotation changes only the active pointer. Old public keys are never retired from
verification. The password comes from the caller's secret manager, never this tree.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from approv.receipts.chain import canonical_json, generate_key, key_id_for, public_key_hex


def _write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace(path: Path, data: bytes) -> None:
    """Readers see the old complete pointer/publication or the new complete one."""
    descriptor, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _filename(key_id: str) -> str:
    # No colon in the filename: on Windows it denotes an alternate data stream.
    prefix, _, fingerprint = key_id.partition(":")
    if prefix != "ed25519" or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("invalid key_id")
    return fingerprint


class KeyStore:
    def __init__(self, directory: str | Path, *, password: bytes):
        if not isinstance(password, bytes) or not password:
            raise ValueError("a nonempty encryption password is required")
        self.directory = Path(directory).resolve()
        self._password = password
        for path in (self.directory, self.directory / "private", self.directory / "public"):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)

    def rotate(self) -> str:
        """Generate and publish a key before activating it; preserve all previous keys."""
        key = generate_key()
        public = public_key_hex(key)
        key_id = key_id_for(public)
        name = _filename(key_id)
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.BestAvailableEncryption(self._password))
        _write_new(self.directory / "private" / (name + ".pem"), private)
        _write_new(self.directory / "public" / (name + ".json"),
                   canonical_json({"key_id": key_id, "public_key": public}).encode("utf-8"))
        _replace(self.directory / "active.json", canonical_json({"key_id": key_id}).encode("utf-8"))
        return key_id

    @property
    def active_id(self) -> str:
        path = self.directory / "active.json"
        if not path.exists():
            raise ValueError("no active signing key; call rotate() to create the first key")
        key_id = json.loads(path.read_text(encoding="utf-8"))["key_id"]
        _filename(key_id)
        return key_id

    def load_private(self, key_id: str | None = None) -> Ed25519PrivateKey:
        key_id = key_id or self.active_id
        pem = (self.directory / "private" / (_filename(key_id) + ".pem")).read_bytes()
        key = serialization.load_pem_private_key(pem, password=self._password)
        if not isinstance(key, Ed25519PrivateKey) or key_id_for(public_key_hex(key)) != key_id:
            raise ValueError("private key does not match its key_id")
        return key

    def public_keys(self) -> dict[str, str]:
        keys = {}
        for path in sorted((self.directory / "public").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            key_id, public = record["key_id"], record["public_key"]
            if key_id_for(public) != key_id or path.stem != _filename(key_id):
                raise ValueError("published key does not match its key_id")
            keys[key_id] = public
        return keys

    def publish(self, destination: str | Path) -> Path:
        """Publish public material only, including keys used before every rotation."""
        destination = Path(destination).resolve()
        if destination == self.directory or self.directory in destination.parents:
            raise ValueError("publish outside the managed key directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        _replace(destination, canonical_json({"format": "approv-public-keys-v1",
                                              "keys": self.public_keys()}).encode("utf-8"))
        return destination
