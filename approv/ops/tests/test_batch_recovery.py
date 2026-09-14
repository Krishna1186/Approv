"""Batch-scale crash recovery and invalidation of audited SQLite snapshots."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from approv.ops.benchmark_store import workload
from approv.receipts.chain import canonical_json, generate_key, key_id_for, load_receipt, public_key_hex
from approv.receipts.store import ReceiptStore, ReplayError

REPO = Path(__file__).resolve().parents[3]


def test_record_only_batches_share_one_audit_and_resume_without_resealing(tmp_path, monkeypatch):
    store = ReceiptStore(tmp_path / "records.sqlite3", namespace="sandbox")
    submissions, _ = workload(250)
    records = [load_receipt(response["record"]) for response, _ in submissions]
    audits = []
    read = store._read
    def counted(db):
        result = read(db)
        audits.append(len(result[0]))
        return result
    monkeypatch.setattr(store, "_read", counted)
    original = []
    with store.batch_writer() as writer:
        for start in range(0, 250, 50):
            original.extend(writer.append_many(records[start:start+50], generate_key()))
        assert writer.progress()["receipt_count"] == 250
        assert audits == [0]
    class NoKeyAvailable:
        def public_key(self):
            pytest.fail("unchanged record retry requested a private key")
    with store.batch_writer() as restarted:
        assert restarted.append_many(records, NoKeyAvailable()) == original
        assert restarted.progress()["receipt_count"] == 250
        assert audits == [0, 250]


def test_reused_writer_audits_once_but_reaudits_after_another_connection_commits(tmp_path, monkeypatch):
    store = ReceiptStore(tmp_path / "sandbox.sqlite3", namespace="sandbox")
    submissions, manifest = workload(6)
    key = generate_key()
    audits = []
    read = store._read
    def counted(db):
        result = read(db)
        audits.append(len(result[0]))
        return result
    monkeypatch.setattr(store, "_read", counted)
    with store.batch_writer() as writer:
        first = writer.commit_verifications(submissions[:2], manifest, key)
        writer.commit_verifications(submissions[2:4], manifest, key)
        assert writer.lookup_verifications([(first[0]["record"]["correlation_id"], submissions[0][1])]) == first[:1]
        assert writer.progress()["receipt_count"] == 4
        assert audits == [0]
        other = ReceiptStore(store.path, namespace="sandbox", create=False, migrate=False)
        other.commit_verifications(submissions[4:5], manifest, key)
        writer.commit_verifications(submissions[5:], manifest, key)
        assert writer.progress()["receipt_count"] == 6
        assert audits == [0, 5]
    with pytest.raises(ValueError, match="closed"):
        writer.progress()


def test_cached_writer_does_not_trust_history_corrupted_by_another_connection(tmp_path):
    store = ReceiptStore(tmp_path / "sandbox.sqlite3", namespace="sandbox")
    submissions, manifest = workload(2)
    with store.batch_writer() as writer:
        writer.commit_verifications(submissions[:1], manifest, generate_key())
        with sqlite3.connect(store.path) as db:
            guard = db.execute("SELECT sql FROM sqlite_master WHERE name='receipts_no_update'").fetchone()[0]
            db.execute("DROP TRIGGER receipts_no_update")
            db.execute("UPDATE receipts SET body=json_set(body, '$.request_text', 'tampered')")
            db.execute(guard)
        with pytest.raises(ValueError):
            writer.commit_verifications(submissions[1:], manifest, generate_key())
        with pytest.raises(ValueError):
            writer.progress()
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


def test_foreign_commit_between_our_commit_and_acknowledgement_is_not_cached_as_verified(tmp_path, monkeypatch):
    store = ReceiptStore(tmp_path / "sandbox.sqlite3", namespace="sandbox")
    submissions, manifest = workload(3)
    key = generate_key()
    other = ReceiptStore(store.path, namespace="sandbox", create=False, migrate=False)
    audits = []
    read = store._read
    def counted(db):
        result = read(db)
        audits.append(len(result[0]))
        return result
    monkeypatch.setattr(store, "_read", counted)
    with store.batch_writer() as writer:
        connection = writer._db
        class CommitRace:
            armed = True
            def __getattr__(self, name):
                return getattr(connection, name)
            def commit(self):
                connection.commit()
                if self.armed:
                    self.armed = False
                    other.commit_verifications(submissions[1:2], manifest, key)
        writer._db = CommitRace()
        writer.commit_verifications(submissions[:1], manifest, key)
        writer.commit_verifications(submissions[2:], manifest, key)
        assert audits == [0, 2]
        assert writer.progress()["receipt_count"] == 3


@pytest.mark.parametrize("failure", ["invalid_signature", "ignored_checkpoint", "conflicting_retry"])
def test_failed_batch_preserves_committed_progress_and_writer_can_resume(tmp_path, failure):
    store = ReceiptStore(tmp_path / "sandbox.sqlite3", namespace="sandbox")
    submissions, manifest = workload(5)
    key = generate_key()
    class BadSigner:
        def public_key(self):
            return key.public_key()
        def sign(self, message):
            return bytes(64)
    with store.batch_writer() as writer:
        original = writer.commit_verifications(submissions[:2], manifest, key)
        before = writer.progress()
        if failure == "ignored_checkpoint":
            with sqlite3.connect(store.path) as db:
                db.execute("""CREATE TRIGGER ignore_checkpoint BEFORE INSERT ON checkpoints
                              WHEN NEW.sequence=4 BEGIN SELECT RAISE(IGNORE); END""")
        attempted = submissions[2:]
        if failure == "conflicting_retry":
            attempted = attempted + [(submissions[0][0], "different-request")]
        with pytest.raises(ValueError):
            writer.commit_verifications(attempted, manifest, BadSigner() if failure == "invalid_signature" else key)
        assert writer.progress() == before
        if failure == "ignored_checkpoint":
            with sqlite3.connect(store.path) as db:
                db.execute("DROP TRIGGER ignore_checkpoint")
        finished = writer.commit_verifications(submissions, manifest, key)
        assert finished[:2] == original
        assert writer.progress()["receipt_count"] == 5
    assert store.progress()["submission_count"] == 5


CRASH_WRITER = r'''
import json, os, sys
from pathlib import Path
from approv.ops.benchmark_store import workload
from approv.receipts.chain import canonical_json, generate_key, key_id_for, public_key_hex
from approv.receipts.store import ReceiptStore
root, scenario = Path(sys.argv[1]), sys.argv[2]
submissions, manifest = workload(6000)
key = generate_key()
public = public_key_hex(key)
(root / 'old-public-keys.json').write_text(canonical_json({
    'format': 'approv-public-keys-v1', 'keys': {key_id_for(public): public}}), encoding='utf-8')
class CrashSigner:
    calls = 0
    def public_key(self):
        return key.public_key()
    def sign(self, message):
        self.calls += 1
        # The receipt at row 4,500 is inserted but its checkpoint is not: no finally,
        # connection close, Python exception handler or explicit rollback can run.
        if scenario == 'mid_batch' and self.calls == 9000:
            os._exit(73)
        return key.sign(message)
store = ReceiptStore(root / 'import.sqlite3', namespace='sandbox')
with store.batch_writer() as writer:
    signer = CrashSigner()
    for start in range(0, 6000, 1000):
        writer.commit_verifications(submissions[start:start+1000], manifest, signer)
        if start == 3000 and scenario == 'after_commit_before_ack':
            os._exit(74)
raise RuntimeError('the injected crash did not run')
'''


@pytest.mark.parametrize("scenario,exit_code", [("mid_batch", 73), ("after_commit_before_ack", 74)])
def test_restart_after_row_4000_resumes_6000_row_import_without_duplicates_or_forks(tmp_path, scenario, exit_code):
    failed = subprocess.run([sys.executable, "-c", CRASH_WRITER, str(tmp_path), scenario],
                            cwd=REPO, capture_output=True, text=True, timeout=180)
    assert failed.returncode == exit_code, failed.stdout + failed.stderr
    store = ReceiptStore(tmp_path / "import.sqlite3", namespace="sandbox", create=False, migrate=False)
    progress = store.progress()
    assert progress["receipt_count"] == progress["submission_count"] == 4000
    assert progress["last_correlation_id"] == "fixture-import:00003999"
    assert progress["checkpoint"]["count"] == 4000
    original = store.export()["records"]
    submissions, manifest = workload(6000)  # new draft timestamps, same request identities
    requests = [(response["record"]["correlation_id"], request_hash) for response, request_hash in submissions]
    found = store.lookup_verifications(requests)
    assert all(row is not None for row in found[:4000]) and found[4000:] == [None] * 2000
    key = generate_key()  # the original private key died with the first process
    class CountedSigner:
        calls = 0
        def public_key(self):
            return key.public_key()
        def sign(self, message):
            self.calls += 1
            return key.sign(message)
    signer = CountedSigner()
    with store.batch_writer() as writer:
        for start in range(0, 6000, 1000):
            retained = writer.commit_verifications(submissions[start:start+1000], manifest, signer)
            if start < 4000:
                assert retained == found[start:start+1000]
        assert writer.progress()["receipt_count"] == 6000
        with pytest.raises(ReplayError):
            writer.lookup_verifications([(requests[0][0], "changed-request")])
    assert signer.calls == 2 * 2000  # duplicates did not create replacement signatures
    exported = store.export()
    assert exported["records"][:4000] == original
    assert len(exported["records"]) == len(exported["submissions"]) == 6000
    assert len({row["correlation_id"] for row in exported["records"]}) == 6000
    assert exported["records"][4000]["prev_hash"] == original[-1]["hash"]
    # A third process has no Approv code or private keys, and verifies both sides of rotation.
    isolated = tmp_path / "stranger"
    isolated.mkdir()
    shutil.copyfile(REPO / "scripts/verify_receipt.py", isolated / "verify_receipt.py")
    publication = json.loads((tmp_path / "old-public-keys.json").read_text())
    public = public_key_hex(key)
    publication["keys"][key_id_for(public)] = public
    for name, payload in (("receipts.json", exported), ("keys.json", publication),
                          ("checkpoint.json", exported["checkpoint"])):
        (isolated / name).write_text(canonical_json(payload), encoding="utf-8")
    verified = subprocess.run([sys.executable, "-I", "verify_receipt.py", "receipts.json", "--keys", "keys.json",
                               "--checkpoint", "checkpoint.json"], cwd=isolated, capture_output=True, text=True, timeout=90)
    assert verified.returncode == 0, verified.stdout + verified.stderr
