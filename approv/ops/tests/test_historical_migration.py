"""Migration against frozen output of the real v2 writer, not today's model defaults."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from approv.receipts.store import ReceiptStore

FIXTURES = Path(__file__).with_name("fixtures")
REPO = Path(__file__).resolve().parents[3]
TABLES = ("metadata", "public_keys", "receipts", "checkpoints", "deployments", "submissions")


def historical_database(path):
    with sqlite3.connect(path) as db:
        db.executescript((FIXTURES / "v2-receipts.sql").read_text(encoding="utf-8"))
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    return path


def contents(path):
    with sqlite3.connect(path) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in TABLES}


def verify_alone(directory, payload, *, chain=False):
    directory.mkdir(exist_ok=True)
    shutil.copyfile(REPO / "scripts/verify_receipt.py", directory / "verify_receipt.py")
    shutil.copyfile(FIXTURES / "v2-public-keys.json", directory / "keys.json")
    shutil.copyfile(FIXTURES / "v2-checkpoint.json", directory / "checkpoint.json")
    (directory / "receipt.json").write_text(json.dumps(payload), encoding="utf-8")
    command = [sys.executable, "-I", "verify_receipt.py", "receipt.json", "--keys", "keys.json"]
    if chain:
        command += ["--checkpoint", "checkpoint.json"]
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_v2_cli_migration_preserves_every_historical_receipt_without_any_private_key(tmp_path):
    path = historical_database(tmp_path / "historical.sqlite3")
    before = contents(path)
    with sqlite3.connect(path) as db:
        records = [json.loads(row[0]) for row in db.execute("SELECT body FROM receipts ORDER BY sequence")]
    assert len(records) == 24 and len({row["key_id"] for row in records}) == 3
    assert {row["decision"] for row in records} == {"allow", "confirm", "refuse"}
    assert all("mode" not in row and "store_namespace" not in row for row in records)
    checkpoint = json.loads((FIXTURES / "v2-checkpoint.json").read_text())
    verify_alone(tmp_path / "before", {"format": "approv-receipt-export-v1",
                                        "records": records, "checkpoint": checkpoint}, chain=True)
    result = subprocess.run([sys.executable, "-m", "approv.ops", "migrate", "--store", str(path)],
                            cwd=REPO, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    progress = json.loads(result.stdout)
    assert progress["receipt_count"] == progress["submission_count"] == 24
    assert progress["last_correlation_id"] == "v2-order-23"
    assert progress["checkpoint"] == checkpoint
    assert contents(path) == before  # exact stored JSON strings, not reserialization
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,)]
        assert db.execute("SELECT namespace FROM ledger_namespace").fetchone()[0] == "production"
    migrated = ReceiptStore(path, create=False, migrate=False)
    exported = migrated.export()
    assert exported["records"] == records and exported["checkpoint"] == checkpoint
    verify_alone(tmp_path / "after", exported, chain=True)
    for record in records:
        verify_alone(tmp_path / "individual", record)
    ReceiptStore(path)  # repeat migration is a no-op, not another signing event
    assert contents(path) == before


def test_corrupt_historical_signature_rolls_back_the_entire_v3_migration(tmp_path):
    path = historical_database(tmp_path / "corrupt-v2.sqlite3")
    with sqlite3.connect(path) as db:
        guard = db.execute("SELECT sql FROM sqlite_master WHERE name='receipts_no_update'").fetchone()[0]
        db.execute("DROP TRIGGER receipts_no_update")
        payload = json.loads(db.execute("SELECT body FROM receipts WHERE sequence=12").fetchone()[0])
        payload["signature"] = "00" * 64
        db.execute("UPDATE receipts SET body=? WHERE sequence=12", (json.dumps(payload),))
        db.execute(guard)
    before = contents(path)
    with pytest.raises(ValueError, match="signature"):
        ReceiptStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='ledger_namespace'").fetchone()
        assert db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,)]
    assert contents(path) == before
