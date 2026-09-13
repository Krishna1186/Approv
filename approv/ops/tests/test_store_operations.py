from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

import pytest

from approv.ops.telemetry import Operation
from approv.receipts import migrations
from approv.receipts.backup import audit, backup, restore
from approv.receipts.chain import (
    SIGNATURE_VERSION, canonical_json, key_id_for, public_key_hex, record_hash, record_json, seal,
)
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore, _SCHEMA, _content_hash
from approv.surface.verification import VerificationRequest, verify_order


def legacy_store(path, deployment, body):
    key = KeyStore(deployment.base / "keys", password=b"secret-key-password").load_private()
    result = verify_order(VerificationRequest.model_validate(body), schemas=deployment.schemas)
    record = seal(result.record, key)
    public = public_key_hex(key)
    key_id = key_id_for(public)
    store_id = str(uuid.uuid4())
    checkpoint = {"format": "approv-receipt-checkpoint-v1", "store_id": store_id,
                  "count": 1, "head_hash": record.hash, "key_id": key_id,
                  "signature_version": SIGNATURE_VERSION}
    digest = record_hash(checkpoint, None)
    checkpoint.update(hash=digest, signature=key.sign(digest.encode()).hex())
    db = sqlite3.connect(path)
    db.executescript(_SCHEMA)
    # Recreate the shipped v1 schema, not a downgrade operation on a live ledger.
    for table in ("receipts", "checkpoints", "public_keys", "metadata"):
        for operation in ("UPDATE", "DELETE"):
            db.execute(f"""CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END""")
    db.execute("INSERT INTO metadata VALUES (1, ?)", (store_id,))
    db.execute("INSERT INTO public_keys VALUES (?, ?)", (key_id, public))
    raw = record_json(record)
    db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
               (1, record.correlation_id, record.hash, None, _content_hash(raw), canonical_json(raw)))
    db.execute("INSERT INTO checkpoints VALUES (1, ?)", (canonical_json(checkpoint),))
    db.execute("PRAGMA user_version=1")
    db.commit()
    db.close()
    return raw, checkpoint


def stranger(tmp_path, bundle, keys, checkpoint):
    isolated = tmp_path / "stranger"
    isolated.mkdir()
    verifier = Path(__file__).resolve().parents[3] / "scripts" / "verify_receipt.py"
    shutil.copyfile(verifier, isolated / "verify_receipt.py")
    for name, data in (("receipts.json", bundle), ("keys.json", {"format": "approv-public-keys-v1", "keys": keys}),
                       ("checkpoint.json", checkpoint)):
        (isolated / name).write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", "verify_receipt.py", "receipts.json", "--keys", "keys.json",
                             "--checkpoint", "checkpoint.json"], cwd=isolated, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_v1_migration_preserves_signed_bytes_and_is_forward_only(deployment, body, tmp_path):
    path = tmp_path / "v1.sqlite3"
    original, checkpoint = legacy_store(path, deployment, body)
    with pytest.raises(ValueError, match="migration required"):
        ReceiptStore(path, create=False, migrate=False)
    migrated = ReceiptStore(path)
    assert migrated.export()["records"] == [original]
    assert migrated.export()["checkpoint"] == checkpoint
    with migrated._connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert [r[0] for r in db.execute("SELECT version FROM schema_migrations")] == [1, 2]
    stranger(tmp_path, migrated.export(), deployment.public_keys, checkpoint)
    ReceiptStore(path)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=3")
    with pytest.raises(ValueError, match="newer"):
        ReceiptStore(path)


def test_failed_migration_rolls_back_ddl_and_version(deployment, body, tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    original, _ = legacy_store(path, deployment, body)
    monkeypatch.setattr(migrations, "V2", migrations.V2 + "\nCREATE TABLE receipts (bad TEXT);\n")
    with pytest.raises(sqlite3.OperationalError):
        ReceiptStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        assert json.loads(db.execute("SELECT body FROM receipts").fetchone()[0]) == original


def test_backup_restore_after_rotation_is_verifiable_without_approv(runtime, body, tmp_path):
    assert runtime.verify(json.dumps(body).encode(), Operation())[0] == 200
    key_store = KeyStore(runtime.deployment.base / "keys", password=b"secret-key-password")
    key_store.rotate()
    result = verify_order(VerificationRequest.model_validate({**body, "correlation_id": "after-rotation"}),
                          schemas=runtime.deployment.schemas)
    runtime.store.append(result.record, key_store.load_private())
    keys = key_store.public_keys()
    saved = backup(runtime.store, tmp_path / "backup", keys)
    anchor = json.loads((saved / "checkpoint.json").read_text())
    restored = restore(saved, tmp_path / "restored.sqlite3", keys, anchor)
    assert restored.export() == runtime.store.export()
    stranger(tmp_path, restored.export(), keys, anchor)
    with pytest.raises(ValueError, match="exists"):
        restore(saved, restored.path, keys, anchor)


def test_restore_requires_an_independent_checkpoint_and_trusted_keys(runtime, body, tmp_path):
    runtime.verify(json.dumps(body).encode(), Operation())
    keys = runtime.deployment.public_keys
    saved = backup(runtime.store, tmp_path / "backup", keys)
    anchor = runtime.store.export()["checkpoint"]
    with pytest.raises(ValueError, match="checkpoint"):
        restore(saved, tmp_path / "missing-anchor.sqlite3", keys, None)
    runtime.verify(json.dumps({**body, "correlation_id": "newer"}).encode(), Operation())
    newer = runtime.store.export()["checkpoint"]
    with pytest.raises(ValueError, match="checkpoint"):
        restore(saved, tmp_path / "stale.sqlite3", keys, newer)
    with pytest.raises(ValueError, match="unpublished"):
        restore(saved, tmp_path / "untrusted.sqlite3", {}, anchor)
    assert not (tmp_path / "stale.sqlite3").exists()
    assert not (tmp_path / "untrusted.sqlite3").exists()


def test_online_backup_with_wal_writer_is_a_coherent_prefix(runtime, body, tmp_path):
    runtime.verify(json.dumps(body).encode(), Operation())
    def write():
        for i in range(10):
            assert runtime.verify(json.dumps({**body, "correlation_id": str(i)}).encode(), Operation())[0] == 200
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(write)
        saved = backup(runtime.store, tmp_path / "online", runtime.deployment.public_keys)
        writer.result()
    copied = ReceiptStore(saved / "receipts.sqlite3", create=False, migrate=False)
    bundle = audit(copied, runtime.deployment.public_keys)
    current = runtime.store.export()
    assert bundle["records"] == current["records"][:len(bundle["records"])]
    assert 1 <= len(bundle["records"]) <= 11


@pytest.mark.parametrize("table", ["deployments", "submissions", "schema_migrations"])
def test_new_audit_tables_cannot_be_rewritten_by_sql(runtime, body, table):
    runtime.verify(json.dumps(body).encode(), Operation())
    with runtime.store._connection() as db:
        db.execute("PRAGMA recursive_triggers=OFF")
        for sql in (f"DELETE FROM {table}", f"UPDATE {table} SET rowid=rowid",
                    f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(sql)
    assert len(runtime.store.export()["records"]) == 1


def test_checkpoint_failure_rolls_back_receipt_submission_and_manifest(runtime, body, monkeypatch):
    real_load = runtime.signers.load
    class FailsSecondSignature:
        calls = 0
        def public_key(self):
            return real_load().public_key()
        def sign(self, message):
            self.calls += 1
            if self.calls == 2:
                raise TimeoutError("KMS checkpoint signing timeout")
            return real_load().sign(message)
    monkeypatch.setattr(runtime.signers, "load", lambda: FailsSecondSignature())
    assert runtime.verify(json.dumps(body).encode(), Operation())[0] == 503
    bundle = runtime.store.export()
    assert bundle["records"] == [] and bundle["submissions"] == [] and bundle["deployments"] == {}


def test_corrupt_manifest_and_missing_submission_are_detected(runtime, body):
    runtime.verify(json.dumps(body).encode(), Operation())
    # Simulate an administrator bypassing SQL guards. Audit must still detect it.
    with runtime.store._connection() as db:
        db.execute("DROP TRIGGER submissions_no_delete")
        db.execute("DELETE FROM submissions")
    with pytest.raises(ValueError, match="context"):
        runtime.store.export()
