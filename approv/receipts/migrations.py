"""Ordered, transactional SQLite migrations. Receipt JSON is never rewritten."""
from __future__ import annotations

import sqlite3
import uuid

CURRENT_VERSION = 3
IMMUTABLE_TABLES = ("receipts", "checkpoints", "public_keys", "metadata",
                    "deployments", "submissions", "schema_migrations", "ledger_namespace")

V2 = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO schema_migrations(version) VALUES (1), (2);
CREATE TABLE deployments (hash TEXT PRIMARY KEY NOT NULL, body TEXT NOT NULL);
CREATE TABLE submissions (
    correlation_id TEXT PRIMARY KEY NOT NULL REFERENCES receipts(correlation_id),
    sequence INTEGER NOT NULL UNIQUE REFERENCES receipts(sequence),
    request_hash TEXT NOT NULL, deployment_hash TEXT NOT NULL REFERENCES deployments(hash),
    response_body TEXT NOT NULL
);
CREATE TABLE ops_write_probe (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value TEXT NOT NULL);
INSERT INTO ops_write_probe VALUES (1, 'initialized');
CREATE TRIGGER submissions_bind BEFORE INSERT ON submissions BEGIN
    SELECT CASE WHEN EXISTS(SELECT 1 FROM submissions WHERE sequence=NEW.sequence)
        OR NEW.correlation_id IS NOT (SELECT correlation_id FROM receipts WHERE sequence=NEW.sequence)
        THEN RAISE(ABORT, 'submission must bind one immutable receipt') END;
END;
"""


V3 = """
CREATE TABLE ledger_namespace (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    namespace TEXT NOT NULL CHECK(namespace IN ('production', 'sandbox'))
);
CREATE TRIGGER ledger_namespace_no_replace BEFORE INSERT ON ledger_namespace
WHEN EXISTS(SELECT 1 FROM ledger_namespace) BEGIN
    SELECT RAISE(ABORT, 'append-only ledger namespace');
END;
CREATE TRIGGER receipts_namespace BEFORE INSERT ON receipts BEGIN
    SELECT CASE WHEN (SELECT namespace FROM ledger_namespace) = 'sandbox'
        AND (json_extract(NEW.body, '$.store_namespace') IS NOT 'sandbox'
             OR json_extract(NEW.body, '$.store_id') IS NOT (SELECT store_id FROM metadata))
        OR (SELECT namespace FROM ledger_namespace) = 'production'
        AND (json_type(NEW.body, '$.store_namespace') IS NOT NULL
             OR json_type(NEW.body, '$.store_id') IS NOT NULL)
        THEN RAISE(ABORT, 'receipt belongs to a different namespace') END;
END;
CREATE TRIGGER checkpoints_namespace BEFORE INSERT ON checkpoints BEGIN
    SELECT CASE WHEN json_extract(NEW.body, '$.store_namespace') IS NOT (SELECT namespace FROM ledger_namespace)
        THEN RAISE(ABORT, 'checkpoint belongs to a different namespace') END;
END;
INSERT INTO schema_migrations(version) VALUES (3);
"""


def statements(script):
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise ValueError("incomplete migration statement")


def _immutable(db, tables):
    for table in tables:
        for operation in ("UPDATE", "DELETE"):
            db.execute(f"""CREATE TRIGGER {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'append-only ledger'); END""")
    for table, column in (("deployments", "hash"), ("submissions", "correlation_id"),
                          ("schema_migrations", "version")):
        if table in tables:
            db.execute(f"""CREATE TRIGGER {table}_no_replace BEFORE INSERT ON {table}
                WHEN EXISTS(SELECT 1 FROM {table} WHERE {column}=NEW.{column}) BEGIN
                SELECT RAISE(ABORT, 'append-only ledger'); END""")


def migrate(db, initial_schema, *, namespace="production", validate=None):
    """Hold the writer lock through version check, DDL and version advance.

    executescript is deliberately avoided: it commits an open transaction before DDL.
    Future migrations append a new numbered step; there is no down migration.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        original_version = version
        if version > CURRENT_VERSION:
            raise ValueError("receipt store is newer than this application")
        if version == 0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("unversioned nonempty store requires operator recovery")
            for statement in statements(initial_schema):
                db.execute(statement)
            _immutable(db, IMMUTABLE_TABLES[:4])
            db.execute("INSERT INTO metadata VALUES (1, ?)", (str(uuid.uuid4()),))
            version = 1
            db.execute("PRAGMA user_version=1")
        if version == 1:
            for statement in statements(V2):
                db.execute(statement)
            _immutable(db, IMMUTABLE_TABLES[4:7])
            db.execute("PRAGMA user_version=2")
            version = 2
        if version == 2:
            if namespace == "sandbox" and db.execute("SELECT 1 FROM receipts LIMIT 1").fetchone():
                raise ValueError("historical production receipts cannot become sandbox receipts")
            for statement in statements(V3):
                db.execute(statement)
            _immutable(db, ("ledger_namespace",))
            db.execute("INSERT INTO ledger_namespace VALUES (1, ?)", (namespace,))
            db.execute("PRAGMA user_version=3")
        check_schema(db)
        check_namespace(db, namespace)
        # The store verifies the original signed JSON and all retained bindings while
        # DDL is still reversible. Bad historical evidence must not advance the version.
        if validate is not None and original_version != CURRENT_VERSION:
            validate(db)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def check_schema(db):
    if db.execute("PRAGMA user_version").fetchone()[0] != CURRENT_VERSION:
        raise ValueError("receipt store migration required")
    versions = [r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")]
    if versions != list(range(1, CURRENT_VERSION + 1)):
        raise ValueError("receipt store migration history is incomplete")
    triggers = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    required = {f"{table}_no_{op}" for table in IMMUTABLE_TABLES for op in ("update", "delete")}
    required |= {"receipts_append", "checkpoints_append", "keys_no_replace", "metadata_no_replace",
                 "deployments_no_replace", "submissions_no_replace", "schema_migrations_no_replace", "submissions_bind",
                 "ledger_namespace_no_replace", "receipts_namespace", "checkpoints_namespace"}
    if not required <= triggers:
        raise ValueError("receipt store append-only guards are missing")


def check_namespace(db, expected):
    row = db.execute("SELECT namespace FROM ledger_namespace WHERE singleton=1").fetchone()
    if row is None or row[0] != expected:
        raise ValueError("receipt store namespace does not match the configured namespace")
