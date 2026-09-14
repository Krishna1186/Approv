"""SQLite receipt ledger: immutable rows, atomic chain appends, durable retry identity.

The database stores the signed JSON rather than reconstructing receipts from today's
model. A signed checkpoint accompanies every append. Keep an exported checkpoint
outside the database's trust boundary to detect restoration of an older valid file.
"""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from approv.receipts.chain import (
    SIGNATURE_VERSION, UnsealedRecord, canonical_json, key_id_for,
    load_receipt, public_key_hex, record_hash, record_json, require_unsealed, seal,
    verify, verify_chain,
)
from approv.types.core import ComparisonRecord
from approv.receipts.migrations import check_namespace, check_schema, migrate as migrate_store


class ReplayError(ValueError):
    """The same correlation ID was reused for a different record."""


class ChainConflict(ValueError):
    """Legacy exception name; append now rejects every pre-sealed input with ValueError."""


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
    # Historical index format. Do not change it: existing signed rows are immutable.
    content = {k: v for k, v in payload.items() if k not in ("prev_hash", "hash", "signature", "key_id")}
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def _retry_content(payload: dict) -> str:
    # Timestamp and namespace/identity are assigned by this store, not by the caller.
    # Everything describing the request, order, evidence, policy and verdict still counts.
    owned = {"timestamp", "prev_hash", "hash", "signature", "key_id", "store_namespace", "store_id"}
    return canonical_json({k: v for k, v in payload.items() if k not in owned})


class ReceiptStore:
    def __init__(self, path: str | Path, *, namespace: str = "production",
                 create: bool = True, migrate: bool = True):
        if namespace not in ("production", "sandbox"):
            raise ValueError("namespace must be production or sandbox")
        self.path = Path(path).resolve()
        self._namespace = namespace
        if not create and not self.path.is_file():
            raise ValueError("receipt store is missing; initialize it explicitly")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(_create=create) as db:
            if migrate:
                migrate_store(db, _SCHEMA, namespace=namespace, validate=self._read)
                db.execute("PRAGMA journal_mode=WAL")
            else:
                check_schema(db)
                check_namespace(db, namespace)

    @property
    def namespace(self) -> str:
        """One immutable namespace per database; never selected from a request body."""
        return self._namespace

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
        """Retain a published key. Historical databases are restored, never re-appended."""
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            key_id = self._register(db, public_hex)
            db.commit()
            return key_id

    def _read(self, db) -> tuple[list[dict], dict | None]:
        check_namespace(db, self.namespace)
        store_id = db.execute("SELECT store_id FROM metadata").fetchone()[0]
        records = []
        for sequence, row in enumerate(db.execute("SELECT * FROM receipts ORDER BY sequence"), 1):
            payload = json.loads(row["body"])
            if (row["sequence"] != sequence or row["hash"] != payload.get("hash") or
                    row["prev_hash"] != payload.get("prev_hash") or
                    row["correlation_id"] != payload.get("correlation_id") or
                    row["content_hash"] != _content_hash(payload)):
                raise ValueError("receipt index does not match signed record")
            self._check_record_namespace(payload, store_id)
            records.append(payload)
        keys = dict(db.execute("SELECT key_id, public_hex FROM public_keys"))
        verify_chain(records, keys)
        rows = db.execute("SELECT sequence, body FROM checkpoints ORDER BY sequence").fetchall()
        if len(rows) != len(records):
            raise ValueError("receipt/checkpoint count mismatch")
        for sequence, row in enumerate(rows, 1):
            checkpoint = json.loads(row["body"])
            if (row["sequence"] != sequence or checkpoint.get("count") != sequence or
                    checkpoint.get("head_hash") != records[sequence - 1]["hash"] or
                    checkpoint.get("store_id") != store_id or
                    checkpoint.get("format") != "approv-receipt-checkpoint-v1"):
                raise ValueError("checkpoint does not match stored chain")
            if checkpoint.get("store_namespace", "production") != self.namespace:
                raise ValueError("checkpoint namespace does not match stored chain")
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

    def _check_record_namespace(self, payload: dict, store_id: str):
        if self.namespace == "sandbox":
            if payload.get("store_namespace") != "sandbox" or payload.get("store_id") != store_id:
                raise ValueError("sandbox receipt is missing its signed namespace or store identity")
        elif "store_namespace" in payload or "store_id" in payload:
            raise ValueError("sandbox receipt cannot enter the production chain")

    def append(self, record: UnsealedRecord, signing_key: Ed25519PrivateKey) -> ComparisonRecord:
        """Accept only an unsealed decision. Own its timestamp, chain link and signature.

        An identical decision retried with a different draft timestamp returns the
        original receipt. Changed decision content under that ID raises ReplayError.
        A signed receipt, including an exact retry, must be read with get(), not appended.
        """
        return self.append_many((record,), signing_key)[0]

    def append_many(self, records: Iterable[UnsealedRecord],
                    signing_key: Ed25519PrivateKey) -> list[ComparisonRecord]:
        """One writer transaction and one history audit for an entire offline batch.

        Materialize decisions before taking the lock: no extraction or other caller
        work runs inside it. All new rows commit together or none do. Retrying a
        committed batch returns its original receipts in input order, including duplicates.
        """
        with self.batch_writer() as writer:
            return writer.append_many(records, signing_key)

    @contextmanager
    def batch_writer(self):
        """Reuse one audited connection across independently committed offline batches.

        A foreign commit invalidates the audit; our own writes are verified before
        commit. Not thread-shareable. Exiting never rolls back earlier successful batches.
        """
        with self._connection() as db:
            writer = ReceiptBatchWriter(self, db)
            try:
                yield writer
            finally:
                writer._closed = True

    def _append(self, db, record, signing_key, submission=None) -> dict:
        payload = record_json(record)
        if not isinstance(record.correlation_id, str) or not record.correlation_id.strip():
            raise ValueError("record needs a nonempty correlation_id")
        store_id = db.execute("SELECT store_id FROM metadata").fetchone()[0]
        if "store_namespace" in payload or "store_id" in payload:
            self._check_record_namespace(payload, store_id)
        if submission is not None:
            existing = self._lookup(db, record.correlation_id, submission["request_hash"])
            if existing is not None:
                return existing["record"]
        existing = db.execute("SELECT body FROM receipts WHERE correlation_id=?",
                              (record.correlation_id,)).fetchone()
        if existing:
            if submission is not None:
                raise ReplayError("correlation id already belongs to a different receipt path")
            original = json.loads(existing["body"])
            if _retry_content(payload) != _retry_content(original):
                raise ReplayError("correlation id reused with a different receipt")
            return original
        head = db.execute("SELECT sequence, hash FROM receipts ORDER BY sequence DESC LIMIT 1").fetchone()
        sequence, previous = (head["sequence"] + 1, head["hash"]) if head else (1, None)
        public = public_key_hex(signing_key)
        key_id = self._register(db, public)
        payload["timestamp"] = datetime.now(timezone.utc)
        if self.namespace == "sandbox":
            payload.update(store_namespace="sandbox", store_id=store_id)
        stamped = load_receipt(payload)
        sealed = seal(stamped, signing_key, previous)
        body = record_json(sealed)
        verify(body, public)
        db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
                   (sequence, sealed.correlation_id, sealed.hash, sealed.prev_hash,
                    _content_hash(body), canonical_json(body)))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError("receipt insertion did not write exactly one row")
        checkpoint = {"format": "approv-receipt-checkpoint-v1", "store_id": store_id,
                      "store_namespace": self.namespace, "count": sequence,
                      "head_hash": sealed.hash, "key_id": key_id,
                      "signature_version": SIGNATURE_VERSION}
        if submission is not None:
            deployment = canonical_json(submission["deployment"])
            deployment_hash = hashlib.sha256(deployment.encode()).hexdigest()
            if not db.execute("SELECT 1 FROM deployments WHERE hash=?", (deployment_hash,)).fetchone():
                db.execute("INSERT INTO deployments VALUES (?, ?)", (deployment_hash, deployment))
            response = canonical_json({**submission["response"], "record": body})
            db.execute("INSERT INTO submissions VALUES (?, ?, ?, ?, ?)",
                       (sealed.correlation_id, sequence, submission["request_hash"], deployment_hash, response))
            checkpoint["context"] = {"request_hash": submission["request_hash"],
                                     "deployment_hash": deployment_hash,
                                     "response_hash": hashlib.sha256(response.encode()).hexdigest()}
        digest = record_hash(checkpoint, None)
        checkpoint.update(hash=digest, signature=signing_key.sign(digest.encode("utf-8")).hex())
        verify(checkpoint, public)
        db.execute("INSERT INTO checkpoints VALUES (?, ?)", (sequence, canonical_json(checkpoint)))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError("checkpoint insertion did not write exactly one row")
        return body

    def get(self, correlation_id: str) -> ComparisonRecord | None:
        """Return a verified retained receipt, with no signing key or new timestamp."""
        with self._connection() as db:
            db.execute("BEGIN")
            self._read(db)
            row = db.execute("SELECT body FROM receipts WHERE correlation_id=?", (correlation_id,)).fetchone()
            return load_receipt(json.loads(row["body"])) if row else None

    @staticmethod
    def _lookup(db, correlation_id: str, request_hash: str) -> dict | None:
        row = db.execute("SELECT * FROM submissions WHERE correlation_id=?", (correlation_id,)).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ReplayError("correlation id reused with a different verification request")
        return json.loads(row["response_body"])

    def lookup_verification(self, correlation_id: str, request_hash: str) -> dict | None:
        return self.lookup_verifications(((correlation_id, request_hash),))[0]

    def lookup_verifications(self, requests: Iterable[tuple[str, str]]) -> list[dict | None]:
        """Bulk retry lookup in input order, with one audit and no signing/extraction."""
        requests = list(requests)
        with self._connection() as db:
            db.execute("BEGIN")
            self._read(db)
            return [self._lookup(db, correlation_id, request_hash) for correlation_id, request_hash in requests]

    @staticmethod
    def _progress(db) -> dict:
        head = db.execute("SELECT sequence, correlation_id FROM receipts ORDER BY sequence DESC LIMIT 1").fetchone()
        checkpoint = db.execute("SELECT body FROM checkpoints ORDER BY sequence DESC LIMIT 1").fetchone()
        return {"format": "approv-store-progress-v1",
                "store_id": db.execute("SELECT store_id FROM metadata").fetchone()[0],
                "store_namespace": db.execute("SELECT namespace FROM ledger_namespace").fetchone()[0],
                "receipt_count": head["sequence"] if head else 0,
                "submission_count": db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0],
                "last_correlation_id": head["correlation_id"] if head else None,
                "checkpoint": json.loads(checkpoint["body"]) if checkpoint else None}

    def progress(self) -> dict:
        """Verified committed progress, never uncommitted attempts or an import row count."""
        with self._connection() as db:
            db.execute("BEGIN")
            self._read(db)
            return self._progress(db)

    def commit_verification(self, response: dict, request_hash: str,
                            deployment: dict, signing_key) -> dict:
        """Bind the API retry identity and deployment to the receipt in one commit."""
        return self.commit_verifications(((response, request_hash),), deployment, signing_key)[0]

    def commit_verifications(self, submissions: Iterable[tuple[dict, str]],
                             deployment: dict, signing_key) -> list[dict]:
        """Batch equivalent of commit_verification; retains full request/deployment bindings."""
        with self.batch_writer() as writer:
            return writer.commit_verifications(submissions, deployment, signing_key)

    def probe_writable(self) -> None:
        """A real committed write, in a separate operational table, never a fake receipt."""
        with self._connection(timeout=1) as db:
            check_schema(db)
            check_namespace(db, self.namespace)
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
            return {"format": "approv-receipt-export-v1", "store_namespace": self.namespace,
                    "records": records, "checkpoint": checkpoint,
                    "deployments": {r["hash"]: json.loads(r["body"]) for r in db.execute("SELECT * FROM deployments")},
                    "submissions": [dict(r) for r in db.execute("SELECT * FROM submissions ORDER BY sequence")]}

    def public_keys(self) -> dict:
        with self._connection() as db:
            return {"format": "approv-public-keys-v1",
                    "keys": dict(db.execute("SELECT key_id, public_hex FROM public_keys"))}


class ReceiptBatchWriter:
    """Use through ReceiptStore.batch_writer(); each method owns its transaction.

    data_version is meaningful only on this one connection. Read it after acquiring
    the writer lock; remember that value, not a post-COMMIT value that could include
    a racing foreign writer. No caller-owned SQL connection is exposed by this API.
    """

    def __init__(self, store, db):
        self._store, self._db = store, db
        self._verified_version = None
        self._closed = False
        self._active = False
        stat = store.path.stat()
        self._file_identity = stat.st_dev, stat.st_ino

    @contextmanager
    def _transaction(self):
        if self._closed:
            raise ValueError("batch writer is closed")
        if self._active:
            raise ValueError("batch writer is already in a transaction")
        stat = self._store.path.stat()
        if (stat.st_dev, stat.st_ino) != self._file_identity:
            raise ValueError("receipt database was replaced; close and reopen the writer")
        db = self._db
        self._active = True
        try:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA data_version").fetchone()[0]
            if version != self._verified_version:
                check_schema(db)
                self._store._read(db)
            yield db
            db.commit()
            self._verified_version = version
        except BaseException:
            self._verified_version = None
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            self._active = False

    def append_many(self, records: Iterable[UnsealedRecord], signing_key) -> list[ComparisonRecord]:
        prepared = [require_unsealed(record) for record in records]
        with self._transaction() as db:
            result = [load_receipt(self._store._append(db, record, signing_key)) for record in prepared]
        return result

    def commit_verifications(self, submissions: Iterable[tuple[dict, str]],
                             deployment: dict, signing_key) -> list[dict]:
        prepared = []
        manifest = json.loads(canonical_json(deployment))
        for response, request_hash in submissions:
            response = json.loads(canonical_json(response))
            record = require_unsealed(load_receipt(response["record"]))
            prepared.append((record, {"response": response, "request_hash": request_hash,
                                      "deployment": manifest}))
        with self._transaction() as db:
            result = []
            for record, submission in prepared:
                self._store._append(db, record, signing_key, submission)
                result.append(self._store._lookup(db, record.correlation_id, submission["request_hash"]))
        return result

    def lookup_verifications(self, requests: Iterable[tuple[str, str]]) -> list[dict | None]:
        requests = list(requests)
        with self._transaction() as db:
            return [self._store._lookup(db, correlation_id, request_hash) for correlation_id, request_hash in requests]

    def progress(self) -> dict:
        with self._transaction() as db:
            return self._store._progress(db)
