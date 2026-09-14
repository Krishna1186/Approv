"""Reproducible offline storage benchmark. Synthetic comparisons, no provider calls.

The directory must be new. It retains databases, public keys, checkpoints and results;
no private key is written. This measures retention, not extraction or partner accuracy.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3
import statistics
import time

import cryptography

from approv.receipts.chain import canonical_json, generate_key, key_id_for, public_key_hex
from approv.receipts.store import ReceiptStore
from approv.surface.verification import VerificationRequest, verify_order
from approv.types.core import AttributeSpec, CategorySchema, Certainty, Criticality, Dimension, FieldProfile, Liability


def workload(count):
    """Actual deterministic surface output over synthetic, versioned catalogue rows."""
    schema = CategorySchema(
        category_id="storage-benchmark-apparel", version="storage-fixture-v1",
        attributes=tuple(AttributeSpec(name=name, dimension=Dimension.NOMINAL,
                                       criticality=Criticality.HARD) for name in ("size", "colour")),
        floor=frozenset({"size", "colour"}),
        field_profiles=tuple(FieldProfile(field_name=name, attributes=(name,), is_variant_axis=True,
                                          certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED)
                             for name in ("size", "colour")))
    schemas = {schema.category_id: schema}
    schema_json = json.loads(schema.model_dump_json())
    schema_json["floor"] = sorted(schema_json["floor"])
    manifest = {"format": "approv-storage-benchmark-v1", "schema": schema_json,
                "source": "synthetic; no partner data", "extractor": "none-structured"}
    rows = []
    for index in range(count):
        product = "product-%d" % (index % 20)
        request = VerificationRequest.model_validate({
            "merchant_id": "synthetic-merchant", "correlation_id": "fixture-import:%08d" % index,
            "category_id": schema.category_id,
            "order": {"order_id": "fixture-order-%08d" % index, "product_id": product,
                      "sku": product + "-M-blue", "quantity": 1,
                      "unit_price": {"kind": "money", "amount": "24.50", "currency": "USD"}},
            "product_snapshot": {"product_id": product, "size": "M", "colour": "blue",
                                 "description": "Synthetic catalogue description. " * 32},
            "artifact": {"shape": "structured", "protocol": "acp",
                         "fields": {"size": "M", "colour": "red" if index % 5 == 0 else "blue"}}})
        response = verify_order(request, schemas=schemas).model_dump(mode="json")
        request_hash = hashlib.sha256(canonical_json(request.model_dump(mode="json")).encode()).hexdigest()
        rows.append((response, request_hash))
    return rows, manifest


def measure(directory: Path, *, rows=20000, batch_size=1000, runs=3, strategy="reused"):
    if min(rows, batch_size, runs) < 1 or strategy not in ("reused", "stateless"):
        raise ValueError("positive counts and a supported strategy are required")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    submissions, manifest = workload(rows)
    trials = []
    for trial in range(runs):
        store = ReceiptStore(directory / ("trial-%d.sqlite3" % trial), namespace="sandbox")
        key = generate_key()
        public = public_key_hex(key)
        batches = []
        wall_start = time.perf_counter()
        with (store.batch_writer() if strategy == "reused" else nullcontext(store)) as writer:
            for start in range(0, rows, batch_size):
                chunk = submissions[start:start + batch_size]
                began = time.perf_counter()
                written = writer.commit_verifications(chunk, manifest, key)
                elapsed = time.perf_counter() - began
                assert len(written) == len(chunk)
                batches.append({"first_row": start + 1, "last_row": start + len(chunk),
                                "rows": len(chunk), "seconds": elapsed})
        wall_seconds = time.perf_counter() - wall_start
        audit_start = time.perf_counter()
        exported = store.export()
        audit_seconds = time.perf_counter() - audit_start
        assert len(exported["records"]) == len(exported["submissions"]) == rows
        (directory / ("trial-%d-public-keys.json" % trial)).write_text(canonical_json({
            "format": "approv-public-keys-v1", "keys": {key_id_for(public): public}}), encoding="utf-8")
        (directory / ("trial-%d-checkpoint.json" % trial)).write_text(
            canonical_json(exported["checkpoint"]), encoding="utf-8")
        trials.append({"trial": trial + 1, "rows": rows, "batches": batches,
                       "wall_seconds": wall_seconds, "records_per_second": rows / wall_seconds,
                       "final_full_audit_seconds": audit_seconds,
                       "database_bytes": store.path.stat().st_size})
        print(json.dumps({"trial_complete": trial + 1, "strategy": strategy,
                          "rows": rows, "seconds": wall_seconds}), flush=True)
    elapsed = [trial["wall_seconds"] for trial in trials]
    durations = sorted(batch["seconds"] for trial in trials for batch in trial["batches"])
    versions = submissions[0][0]["record"]
    result = {"format": "approv-store-benchmark-v1", "measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "dataset": "storage-fixture-v1: synthetic structured apparel comparisons",
              "strategy": strategy, "rows_per_trial": rows, "trials": trials,
              "runs": runs, "batch_size": batch_size, "total_measured_rows": runs * rows,
              "model_called": False, "model_version": versions["model_version"],
              "prompt_version": versions["prompt_version"], "evaluator_version": versions["evaluator_version"],
              "first_response_bytes": len(canonical_json(submissions[0][0]).encode()),
              "environment": {"python": platform.python_version(), "os": platform.platform(),
                              "sqlite": sqlite3.sqlite_version, "cryptography": cryptography.__version__,
                              "processor": platform.processor()},
              "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                                for name in ("receipts/store.py", "receipts/chain.py", "receipts/migrations.py",
                                             "ops/benchmark_store.py", "types/core.py", "surface/verification.py")},
              "storage": "local SQLite WAL, synchronous=FULL; two local Ed25519 signatures verified per new row",
              "timing": "writer connection, validation, history audits, signing, inserts and commits; "
                        "fixture construction, database creation and final export audit excluded",
              "median_records_per_second": rows / statistics.median(elapsed),
              "observed_total_seconds_range": [min(elapsed), max(elapsed)],
              "interval_kind": "observed min/max across runs, not a statistical confidence interval",
              "p50_batch_seconds": durations[math.ceil(.5 * len(durations)) - 1],
              "p95_batch_seconds": durations[math.ceil(.95 * len(durations)) - 1]}
    (directory / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--strategy", choices=("reused", "stateless"), default="reused")
    args = parser.parse_args()
    measure(args.directory, rows=args.rows, batch_size=args.batch_size, runs=args.runs, strategy=args.strategy)
    print(json.dumps({"results": str(args.directory / "results.json")}))


if __name__ == "__main__":
    main()
