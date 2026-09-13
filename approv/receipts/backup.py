"""Online backups and verified restore to a new path; never overwrite a live ledger."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from approv.receipts.chain import canonical_json, verify
from approv.receipts.keys import _write_new
from approv.receipts.store import ReceiptStore


def audit(store: ReceiptStore, trusted_keys: dict[str, str], checkpoint: dict | None = None,
          *, exact: bool = False) -> dict:
    """Trust comes from independently published keys / checkpoint, never the backup."""
    with store._connection() as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite integrity check failed")
    publication = store.public_keys()["keys"]
    if any(trusted_keys.get(key) != value for key, value in publication.items()):
        raise ValueError("store contains an unpublished key")
    bundle = store.export()
    if checkpoint is not None:
        verify(checkpoint, trusted_keys)
        current = bundle["checkpoint"]
        count = checkpoint.get("count")
        if (checkpoint.get("format") != "approv-receipt-checkpoint-v1" or
                type(count) is not int or count < 1 or current is None or
                checkpoint.get("store_id") != current["store_id"] or count > len(bundle["records"]) or
                bundle["records"][count - 1]["hash"] != checkpoint.get("head_hash") or
                (exact and checkpoint != current)):
            raise ValueError("store does not match independently retained checkpoint")
    elif exact and bundle["records"]:
        raise ValueError("restore of a nonempty store requires a retained checkpoint")
    return bundle


def backup(store: ReceiptStore, destination: str | Path, trusted_keys: dict[str, str]) -> Path:
    """SQLite online backup includes committed WAL pages and works with a live writer.

    A new directory is reserved exclusively. COMPLETE.json is written last: partial
    backups are deliberately left for inspection but cannot be restored by this API.
    """
    destination = Path(destination).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    target = destination / "receipts.sqlite3"
    _write_new(target, b"")
    with store._connection() as source:
        db = sqlite3.connect(target)
        try:
            source.backup(db, pages=256, sleep=0.01)
        finally:
            db.close()
    copied = ReceiptStore(target, create=False, migrate=False)
    bundle = audit(copied, trusted_keys)
    for name, body in (("receipts.json", bundle), ("checkpoint.json", bundle["checkpoint"]),
                       ("public-keys.json", {"format": "approv-public-keys-v1", "keys": trusted_keys})):
        _write_new(destination / name, canonical_json(body).encode())
    _write_new(destination / "COMPLETE.json", canonical_json({
        "format": "approv-backup-v1", "count": len(bundle["records"]),
        "checkpoint": bundle["checkpoint"]}).encode())
    return destination


def restore(source: str | Path, destination: str | Path, trusted_keys: dict[str, str],
            checkpoint: dict | None) -> ReceiptStore:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    complete = json.loads((source / "COMPLETE.json").read_text(encoding="utf-8"))
    if complete.get("format") != "approv-backup-v1":
        raise ValueError("incomplete backup")
    candidate = ReceiptStore(source / "receipts.sqlite3", create=False, migrate=False)
    bundle = audit(candidate, trusted_keys, checkpoint, exact=True)
    if complete.get("checkpoint") != bundle["checkpoint"] or complete.get("count") != len(bundle["records"]):
        raise ValueError("backup completion marker does not match store")
    # Reserve a new target, including protection against stale SQLite sidecars.
    if any(Path(str(destination) + suffix).exists() for suffix in ("", "-wal", "-shm", "-journal")):
        raise ValueError("restore target or sidecar already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_new(destination, b"")
    with candidate._connection() as db:
        target = sqlite3.connect(destination)
        try:
            db.backup(target)
        finally:
            target.close()
    restored = ReceiptStore(destination, create=False, migrate=False)
    audit(restored, trusted_keys, checkpoint, exact=True)
    with destination.open("rb+") as handle:
        os.fsync(handle.fileno())
    return restored
