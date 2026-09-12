"""Cryptographic and persistence counterexamples, not product-accuracy evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from approv.receipts.chain import (
    SIGNATURE_VERSION, _UNSEALED, canonical_json, generate_key, key_id_for,
    public_key_hex, record_hash, record_json, seal, verify, verify_chain,
)
from approv.receipts.keys import KeyStore
from approv.receipts.store import ChainConflict, ReceiptStore, ReplayError
from approv.types.core import Attestation, ComparisonRecord, Decision, Money, OrderLine


def draft(correlation="request-1"):
    snapshot = {"sku": "shoe-9", "size": "9", "price": "24.50", "currency": "USD"}
    return ComparisonRecord(
        correlation_id=correlation, merchant_id="merchant-1", attestation=Attestation.NEITHER,
        category_id="fixture", category_version="1", locale="en-US", request_text="Size 9 shoes",
        product_id="shoe", product_snapshot=snapshot,
        snapshot_hash=hashlib.sha256(canonical_json(snapshot).encode()).hexdigest(),
        order=OrderLine(order_id=correlation, line_id="line-1", product_id="shoe", sku="shoe-9",
                        variant_id="9", quantity=1, unit_price=Money(amount="24.50", currency="USD")),
        findings=(), decision=Decision.CONFIRM, model_version="fixture", evaluator_version="fixture",
        prompt_version="fixture", timestamp=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )


def write_json(path, data):
    path.write_text(canonical_json(data), encoding="utf-8")
    return path


def stranger(tmp_path, payload, *, keys=None, key=None, checkpoint=None):
    """Only a copied standalone verifier, published keys and exported JSON, in -I mode."""
    directory = tmp_path / "stranger"
    directory.mkdir(exist_ok=True)
    verifier = directory / "verify_receipt.py"
    shutil.copyfile(Path("scripts/verify_receipt.py"), verifier)
    receipt = write_json(directory / "receipts.json", payload)
    command = [sys.executable, "-I", str(verifier), str(receipt)]
    if keys is not None:
        command += ["--keys", str(write_json(directory / "public-keys.json", keys))]
    else:
        command += ["--key", key]
    if checkpoint is not None:
        command += ["--checkpoint", str(write_json(directory / "retained-checkpoint.json", checkpoint))]
    return subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)


def test_a_stranger_verifies_before_and_after_rotation_from_the_reopened_store(tmp_path):
    keyring = KeyStore(tmp_path / "keys", password=b"fixture password")
    first_id = keyring.rotate()
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    first = ledger.append(draft("before-rotation"), keyring.load_private())
    original = record_json(first)
    keyring.rotate()
    current = keyring.load_private()
    second = ledger.append(draft("after-rotation"), current)
    published = json.loads(keyring.publish(tmp_path / "public-keys.json").read_text())
    assert first_id in published["keys"] and len(published["keys"]) == 2
    assert first.key_id != second.key_id and second.prev_hash == first.hash
    # A new process/instance needs only the database, never an in-memory head or receipt cache.
    exported = ReceiptStore(ledger.path).export()
    assert exported["records"][0] == original
    result = stranger(tmp_path, exported, keys=published, checkpoint=exported["checkpoint"])
    assert result.returncode == 0, result.stdout + result.stderr
    # Each receipt is also independently verifiable, even the non-genesis one.
    for receipt in exported["records"]:
        result = stranger(tmp_path, receipt, key=published["keys"][receipt["key_id"]])
        assert result.returncode == 0, result.stdout + result.stderr
    verify_chain(exported["records"], published["keys"])


def test_legacy_signed_json_remains_verifiable_after_schema_defaults_change(tmp_path):
    key = generate_key()
    legacy = record_json(draft())
    for name in ("key_id", "signature_version", "order"):
        legacy.pop(name)
    digest = record_hash(legacy, None)
    legacy.update(hash=digest, signature=key.sign(digest.encode()).hex())
    restored = ComparisonRecord.model_validate(legacy)
    verify(restored, public_key_hex(key))
    assert record_json(restored) == legacy
    result = stranger(tmp_path, legacy, key=public_key_hex(key))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("field,value", [("key_id", "substituted-key"), ("signature_version", "none")])
def test_signing_metadata_is_inside_the_digest(tmp_path, field, value):
    assert field not in _UNSEALED
    key = generate_key()
    original = seal(draft(), key)
    tampered = original.model_copy(update={field: value})
    assert record_hash(tampered, tampered.prev_hash) != original.hash
    with pytest.raises(ValueError, match="does not match its hash"):
        verify(tampered, public_key_hex(key))
    result = stranger(tmp_path, record_json(tampered), key=public_key_hex(key))
    assert result.returncode == 1 and "does not match its hash" in result.stdout


def test_unknown_version_is_rejected_even_with_an_authentic_signature(tmp_path):
    key = generate_key()
    payload = record_json(seal(draft(), key))
    payload["signature_version"] = "ed25519-sha256-v999"
    payload["hash"] = record_hash(payload, None)
    payload["signature"] = key.sign(payload["hash"].encode()).hex()
    with pytest.raises(ValueError, match="unsupported signature_version"):
        verify(payload, public_key_hex(key))
    result = stranger(tmp_path, payload, key=public_key_hex(key))
    assert result.returncode == 1 and "unsupported signature_version" in result.stdout
    with pytest.raises(ValueError, match="unsupported signature_version"):
        seal(draft().model_copy(update={"signature_version": "none"}), key)


def test_key_substitution_in_publication_is_rejected(tmp_path):
    key = generate_key()
    receipt = seal(draft(), key)
    wrong = {receipt.key_id: public_key_hex(generate_key())}
    with pytest.raises(ValueError, match="published key"):
        verify(receipt, wrong)
    result = stranger(tmp_path, record_json(receipt), keys={"format": "approv-public-keys-v1", "keys": wrong})
    assert result.returncode == 1 and "published key" in result.stdout
    with pytest.raises(ValueError, match="key_id"):
        seal(draft().model_copy(update={"key_id": "different"}), key)


def test_old_signatures_cannot_be_replaced_by_resealing():
    key = generate_key()
    with pytest.raises(ValueError, match="already sealed"):
        seal(seal(draft(), key), generate_key())


def test_keys_are_encrypted_and_rotation_preserves_publication(tmp_path):
    directory = tmp_path / "keyring"
    ring = KeyStore(directory, password=b"fixture password")
    with pytest.raises(ValueError, match="no active"):
        ring.load_private()
    old_id = ring.rotate()
    old_public = public_key_hex(ring.load_private())
    private = list((directory / "private").glob("*.pem"))[0]
    assert b"ENCRYPTED PRIVATE KEY" in private.read_bytes()
    wrong = KeyStore(directory, password=b"wrong password")
    with pytest.raises(ValueError):
        wrong.load_private()
    new_id = ring.rotate()
    restarted = KeyStore(directory, password=b"fixture password")
    assert restarted.active_id == new_id != old_id
    assert public_key_hex(restarted.load_private(old_id)) == old_public
    published = json.loads(restarted.publish(tmp_path / "public.json").read_text())
    assert published == {"format": "approv-public-keys-v1", "keys": restarted.public_keys()}
    assert all(key_id_for(v) == k for k, v in published["keys"].items())
    with pytest.raises(ValueError, match="outside"):
        restarted.publish(directory / "active.json")
    with pytest.raises(ValueError, match="key_id"):
        restarted.load_private("../../outside")


def test_retries_survive_rotation_restart_and_later_appends_without_rewriting(tmp_path):
    key = generate_key()
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    request = draft()
    original = ledger.append(request, key)
    rotated = generate_key()
    ledger.append(draft("second"), rotated)
    before = ledger.export()
    restarted = ReceiptStore(ledger.path)
    assert restarted.append(request, rotated) == original
    assert restarted.append(original, rotated) == original
    assert restarted.export() == before
    assert record_json(original)["timestamp"] == record_json(request)["timestamp"]


def test_conflicting_replay_and_stale_signed_head_are_rejected(tmp_path):
    key = generate_key()
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    ledger.append(draft(), key)
    with pytest.raises(ReplayError):
        ledger.append(draft().model_copy(update={"request_text": "changed intent"}), key)
    with pytest.raises(ChainConflict):
        ledger.append(seal(draft("new-id"), key), key)
    with pytest.raises(ChainConflict):
        ledger.append(draft("new-id").model_copy(update={"prev_hash": "stale"}), key)
    assert len(ledger.export()["records"]) == 1


def test_presealed_receipt_is_retained_exactly_and_must_be_authentic(tmp_path):
    key = generate_key()
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    signed = seal(draft(), key)
    assert ledger.append(signed, key) == signed
    with pytest.raises(ValueError, match="does not match its hash"):
        ledger.append(signed.model_copy(update={"request_text": "tampered"}), key)


@pytest.mark.parametrize("table", ["receipts", "checkpoints", "public_keys", "metadata"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "REPLACE"])
def test_append_only_is_enforced_for_sql_not_just_python_calls(tmp_path, table, operation):
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    ledger.append(draft(), generate_key())
    before = ledger.export()
    with sqlite3.connect(ledger.path) as db:
        # Deliberately do not enable recursive_triggers: REPLACE must still fail.
        column = db.execute(f"PRAGMA table_info({table})").fetchone()[1]
        sql = {"UPDATE": f"UPDATE {table} SET {column}={column}",
               "DELETE": f"DELETE FROM {table}",
               "REPLACE": f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}"}[operation]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    assert ledger.export() == before


def test_receipt_and_checkpoint_commit_atomically(tmp_path):
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    with sqlite3.connect(ledger.path) as db:
        db.execute("""CREATE TRIGGER simulate_disk_failure BEFORE INSERT ON checkpoints
                      BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated failure"):
        ledger.append(draft(), generate_key())
    assert ReceiptStore(ledger.path).export()["records"] == []
    assert ledger.public_keys()["keys"] == {}


def test_concurrent_connections_cannot_fork_and_duplicates_only_append_once(tmp_path):
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    key = generate_key()
    requests = [draft("request-%d" % n) for n in range(10)]
    with ThreadPoolExecutor(max_workers=5) as workers:
        results = list(workers.map(lambda record: ledger.append(record, key), requests + requests))
    exported = ReceiptStore(ledger.path).export()
    assert len(exported["records"]) == 10
    assert exported["checkpoint"]["count"] == 10
    assert len({r.hash for r in results}) == 10
    verify_chain(exported["records"], ledger.public_keys()["keys"])


def test_retained_checkpoint_exposes_valid_prefix_rollback(tmp_path):
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    key = generate_key()
    ledger.append(draft("first"), key)
    old_export = ledger.export()
    ledger.append(draft("second"), key)
    current = ledger.export()
    # Both exports have real signatures. Only the independently retained head exposes rollback.
    result = stranger(tmp_path, old_export, keys=ledger.public_keys(), checkpoint=current["checkpoint"])
    assert result.returncode == 1 and "checkpoint count" in result.stdout
    current["records"].pop()
    result = stranger(tmp_path, current, keys=ledger.public_keys())
    assert result.returncode == 1 and "checkpoint count" in result.stdout


def test_export_keeps_the_order_and_source_snapshot_seen_at_signing(tmp_path):
    ledger = ReceiptStore(tmp_path / "receipts.sqlite")
    request = draft()
    receipt = ledger.append(request, generate_key())
    request.product_snapshot["size"] = "10"
    receipt.product_snapshot["size"] = "11"
    exported = ledger.export()["records"][0]
    assert exported["product_snapshot"]["size"] == "9"
    assert exported["order"]["sku"] == "shoe-9"
    assert exported["order"]["unit_price"] == {"kind": "money", "amount": "24.50", "currency": "USD"}
    assert exported["timestamp"] == "2026-09-12T00:00:00Z"


def test_standalone_rejects_duplicate_json_keys(tmp_path):
    key = generate_key()
    receipt = record_json(seal(draft(), key))
    result = stranger(tmp_path, receipt, key=public_key_hex(key))
    assert result.returncode == 0
    path = tmp_path / "stranger" / "receipts.json"
    path.write_text('{"decision":"allow",' + canonical_json(receipt)[1:], encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(path.parent / "verify_receipt.py"), str(path),
                             "--key", public_key_hex(key)], cwd=path.parent, capture_output=True, text=True)
    assert result.returncode == 1 and "duplicate JSON key" in result.stdout
