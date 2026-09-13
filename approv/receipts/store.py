"""SQLite receipt ledger: immutable rows, atomic chain appends, durable retry identity.

The database stores the signed JSON rather than reconstructing receipts from today's
model. A signed checkpoint accompanies every append. Keep an exported checkpoint
outside the database's trust boundary to detect restoration of an older valid file.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from approv.receipts.chain import (
    SIGNATURE_VERSION, canonical_json, key_id_for, public_key_hex, record_hash,
    record_json, seal, verify, verify_chain,
)
from approv.types.core import ComparisonRecord
from approv.receipts.migrations import check_schema, migrate as migrate_store


class ReplayError(ValueError):
    """The same correlation ID was reused for a different record."""


class ChainConflict(ValueError):
    """A pre-signed receipt does not extend the current head."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1), store_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public_keys (
    key_id TEXT PRIMARY KEY NOT NULL, public_hex TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
    sequence INTEGER PRIMARY KEY,
    correlation_id TEXT NOT NULL UNIQUE CHECK(length(correlation_id) > 0),
    hash TEXT NOT NULL UNIQUE, prev_hash TEXT, content_hash TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    sequence INTEGER PRIMARY KEY REFERENCES receipts(sequence), body TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS receipts_append BEFORE INSERT ON receipts BEGIN
    SELECT CASE WHEN NEW.sequence != COALESCE((SELECT MAX(sequence) FROM receipts), 0) + 1
        OR NEW.prev_hash IS NOT (SELECT hash FROM receipts ORDER BY sequence DESC LIMIT 1)
        OR EXISTS(SELECT 1 FROM receipts WHERE correlation_id = NEW.correlation_id OR hash = NEW.hash)
        THEN RAISE(ABORT, 'receipt must extend the chain without replay') END;
END;
CREATE TRIGGER IF NOT EXISTS checkpoints_append BEFORE INSERT ON checkpoints BEGIN
    SELECT CASE WHEN NEW.sequence != COALESCE((SELECT MAX(sequence) FROM checkpoints), 0) + 1
        OR NEW.sequence != (SELECT MAX(sequence) FROM receipts)
        THEN RAISE(ABORT, 'checkpoint must extend the manifest') END;
END;
CREATE TRIGGER IF NOT EXISTS keys_no_replace BEFORE INSERT ON public_keys
WHEN EXISTS(SELECT 1 FROM public_keys WHERE key_id = NEW.key_id) BEGIN
    SELECT RAISE(ABORT, 'published keys are immutable');
END;
CREATE TRIGGER IF NOT EXISTS metadata_no_replace BEFORE INSERT ON metadata
WHEN EXISTS(SELECT 1 FROM metadata) BEGIN
    SELECT RAISE(ABORT, 'store identity is immutable');
END;
"""


def _content_hash(payload: dict) -> str:
    # Rotation must not turn a retry of the same unsigned decision into a new decision.
    content = {k: v for k, v in payload.items() if k not in ("prev_hash", "hash", "signature", "key_id")}
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


class ReceiptStore:
    def __init__(self, path: str | Path, *, create: bool = True, migrate: bool = True):
        self.path = Path(path).resolve()
        if not create and not self.path.is_file():
            raise ValueError("receipt store is missing; initialize it explicitly")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(_create=create) as db:
            if migrate:
                migrate_store(db, _SCHEMA)
                db.execute("PRAGMA journal_mode=WAL")
            else:
                check_schema(db)

    @contextmanager
    def _connection(self, *, timeout: float = 30, _create: bool = False):
        uri = self.path.as_uri() + ("?mode=rwc" if _create else "?mode=rw")
        db = sqlite3.connect(uri, uri=True, timeout=timeout, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA recursive_triggers=ON")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _register(db, public_hex: str) -> str:
        key_id = key_id_for(public_hex)
        row = db.execute("SELECT public_hex FROM public_keys WHERE key_id=?", (key_id,)).fetchone()
        if row and row[0] != public_hex:
            raise ValueError("published signing key changed")
        if not row:
            db.execute("INSERT INTO public_keys VALUES (?, ?)", (key_id, public_hex))
        return key_id

    def register_public_key(self, public_hex: str) -> str:
        """Trust a previously published key before importing a historical receipt."""
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            key_id = self._register(db, public_hex)
            db.commit()
            return key_id

    @staticmethod
    def _read(db) -> tuple[list[dict], dict | None]:
        records = []
        for sequence, row in enumerate(db.execute("SELECT * FROM receipts ORDER BY sequence"), 1):
            payload = json.loads(row["body"])
            if (row["sequence"] != sequence or row["hash"] != payload.get("hash") or
                    row["prev_hash"] != payload.get("prev_hash") or
                    row["correlation_id"] != payload.get("correlation_id") or
                    row["content_hash"] != _content_hash(payload)):
                raise ValueError("receipt index does not match signed record")
            records.append(payload)
        keys = dict(db.execute("SELECT key_id, public_hex FROM public_keys"))
        verify_chain(records, keys)
        rows = db.execute("SELECT sequence, body FROM checkpoints ORDER BY sequence").fetchall()
        if len(rows) != len(records):
            raise ValueError("receipt/checkpoint count mismatch")
        store_id = db.execute("SELECT store_id FROM metadata").fetchone()[0]
        for sequence, row in enumerate(rows, 1):
            checkpoint = json.loads(row["body"])
            if (row["sequence"] != sequence or checkpoint.get("count") != sequence or
                    checkpoint.get("head_hash") != records[sequence - 1]["hash"] or
                    checkpoint.get("store_id") != store_id or
                    checkpoint.get("format") != "approv-receipt-checkpoint-v1"):
                raise ValueError("checkpoint does not match stored chain")
            verify(checkpoint, keys)
        for row in db.execute("SELECT * FROM deployments"):
            if hashlib.sha256(row["body"].encode()).hexdigest() != row["hash"]:
                raise ValueError("deployment manifest digest mismatch")
        submissions = db.execute("SELECT * FROM submissions").fetchall()
        if {r["sequence"] for r in submissions} != {
                r["sequence"] for r in rows if "context" in json.loads(r["body"])}:
            raise ValueError("signed submission context is missing from store")
        for row in submissions:
            response = json.loads(row["response_body"])
            checkpoint = json.loads(rows[row["sequence"] - 1]["body"])
            if (response["record"] != records[row["sequence"] - 1] or
                    row["correlation_id"] != response["record"]["correlation_id"] or
                    not db.execute("SELECT 1 FROM deployments WHERE hash=?", (row["deployment_hash"],)).fetchone() or
                    checkpoint.get("context") != {
                        "request_hash": row["request_hash"], "deployment_hash": row["deployment_hash"],
                        "response_hash": hashlib.sha256(row["response_body"].encode()).hexdigest()}):
                raise ValueError("submission does not match signed checkpoint")
        return records, json.loads(rows[-1]["body"]) if rows else None

    def append(self, record: ComparisonRecord, signing_key: Ed25519PrivateKey, *,
               _submission: dict | None = None) -> ComparisonRecord:
        """Atomically sign/append, or return the identical existing receipt on retry.

        A pre-signed receipt is verified and retained verbatim, never re-signed. Its
        key must be registered. The supplied key signs the retained checkpoint, and
        also signs the receipt if it was unsigned. A changed correlation ID's payload
        or a stale pre-signed link fails rather than forking or rewriting history.
        """
        payload = record_json(record)
        if not isinstance(record.correlation_id, str) or not record.correlation_id.strip():
            raise ValueError("record needs a nonempty correlation_id")
        if bool(record.hash) != bool(record.signature):
            raise ValueError("record is partly sealed")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            records, _ = self._read(db)
            if _submission is not None:
                existing = self._lookup(db, record.correlation_id, _submission["request_hash"])
                if existing is not None:
                    db.commit()
                    return ComparisonRecord.model_validate(existing["record"])
            public = public_key_hex(signing_key)
            key_id = self._register(db, public)
            if record.signature:
                verify(record, dict(db.execute("SELECT key_id, public_hex FROM public_keys")))
            elif record.key_id not in (None, key_id):
                raise ValueError("key_id does not identify the signing key")
            existing = db.execute("SELECT body, content_hash FROM receipts WHERE correlation_id=?",
                                  (record.correlation_id,)).fetchone()
            if existing:
                if _submission is not None:
                    raise ReplayError("correlation id already belongs to a different receipt path")
                if ((record.signature and canonical_json(payload) != existing["body"]) or
                        (not record.signature and _content_hash(payload) != existing["content_hash"])):
                    raise ReplayError("correlation id reused with a different receipt")
                restored = ComparisonRecord.model_validate_json(existing["body"])
                db.commit()
                return restored
            previous = records[-1]["hash"] if records else None
            if record.signature:
                if record.prev_hash != previous:
                    raise ChainConflict("pre-signed receipt does not extend the current head")
                sealed = record
            else:
                if record.prev_hash not in (None, previous):
                    raise ChainConflict("unsigned receipt carries a stale predecessor")
                sealed = seal(record, signing_key, previous)
            body = record_json(sealed)
            sequence = len(records) + 1
            db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
                       (sequence, sealed.correlation_id, sealed.hash, sealed.prev_hash,
                        _content_hash(body), canonical_json(body)))
            store_id = db.execute("SELECT store_id FROM metadata").fetchone()[0]
            checkpoint = {"format": "approv-receipt-checkpoint-v1", "store_id": store_id,
                          "count": sequence, "head_hash": sealed.hash, "key_id": key_id,
                          "signature_version": SIGNATURE_VERSION}
            if _submission is not None:
                deployment = canonical_json(_submission["deployment"])
                deployment_hash = hashlib.sha256(deployment.encode()).hexdigest()
                if not db.execute("SELECT 1 FROM deployments WHERE hash=?", (deployment_hash,)).fetchone():
                    db.execute("INSERT INTO deployments VALUES (?, ?)", (deployment_hash, deployment))
                response = canonical_json({**_submission["response"], "record": body})
                db.execute("INSERT INTO submissions VALUES (?, ?, ?, ?, ?)",
                           (sealed.correlation_id, sequence, _submission["request_hash"], deployment_hash, response))
                checkpoint["context"] = {"request_hash": _submission["request_hash"],
                                         "deployment_hash": deployment_hash,
                                         "response_hash": hashlib.sha256(response.encode()).hexdigest()}
            digest = record_hash(checkpoint, None)
            checkpoint.update(hash=digest, signature=signing_key.sign(digest.encode("utf-8")).hex())
            db.execute("INSERT INTO checkpoints VALUES (?, ?)", (sequence, canonical_json(checkpoint)))
            db.commit()
            # Copy out of caller-owned nested dictionaries as well as the DB transaction.
            return ComparisonRecord.model_validate(body)

    @staticmethod
    def _lookup(db, correlation_id: str, request_hash: str) -> dict | None:
        row = db.execute("SELECT * FROM submissions WHERE correlation_id=?", (correlation_id,)).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ReplayError("correlation id reused with a different verification request")
        return json.loads(row["response_body"])

    def lookup_verification(self, correlation_id: str, request_hash: str) -> dict | None:
        with self._connection() as db:
            db.execute("BEGIN")
            self._read(db)
            return self._lookup(db, correlation_id, request_hash)

    def commit_verification(self, response: dict, request_hash: str,
                            deployment: dict, signing_key) -> dict:
        """Bind the API retry identity and deployment to the receipt in one commit."""
        record = ComparisonRecord.model_validate(response["record"])
        self.append(record, signing_key, _submission={"response": response,
                    "request_hash": request_hash, "deployment": deployment})
        return self.lookup_verification(record.correlation_id, request_hash)

    def probe_writable(self) -> None:
        """A real committed write, in a separate operational table, never a fake receipt."""
        with self._connection(timeout=1) as db:
            check_schema(db)
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE ops_write_probe SET value=? WHERE singleton=1", (str(uuid.uuid4()),))
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise ValueError("store write probe is missing")
            db.commit()

    def export(self) -> dict:
        """Self-contained chain and signed manifest; public keys are published separately."""
        with self._connection() as db:
            db.execute("BEGIN")
            records, checkpoint = self._read(db)
            return {"format": "approv-receipt-export-v1", "records": records, "checkpoint": checkpoint,
                    "deployments": {r["hash"]: json.loads(r["body"]) for r in db.execute("SELECT * FROM deployments")},
                    "submissions": [dict(r) for r in db.execute("SELECT * FROM submissions ORDER BY sequence")]}

    def public_keys(self) -> dict:
        with self._connection() as db:
            return {"format": "approv-public-keys-v1",
                    "keys": dict(db.execute("SELECT key_id, public_hex FROM public_keys"))}
