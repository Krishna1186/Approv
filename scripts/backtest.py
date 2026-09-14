#!/usr/bin/env python3
"""Run a partner's historical export offline: files in, receipts and a report out.

    # what does this export buy? Reads their files, decides nothing, runs no engine.
    python scripts/backtest.py --export exports/hearth --merchant hearth-and-loom \
        --schema schemas/bedding.json --dry-run

    # the run itself
    python scripts/backtest.py --export exports/hearth --merchant hearth-and-loom \
        --schema schemas/bedding.json --window-days 21 --day-first \
        --store backtest/hearth.sqlite --out output/hearth

The dry run is the one to send first. It is the artifact that comes back after the first
data conversation: which rung of the data ladder this export lands on, what is missing to
reach the next, and every problem with a line number. It costs the partner nothing to ask
for and it does not run the engine at all.

**The schema is supplied, never derived here.** `approv.schema.propose_schema` can build
one from a catalogue and a human confirms it; doing that inside a backtest would mean the
schema and the comparison came out of the same run over the same data, and the matrix
would come back looking good having measured nothing (CLAUDE.md §6). So this takes a
confirmed schema file and refuses without one.

**The store is a sandbox database.** A backtest re-evaluates historical sales and must
never share a ledger with production receipts; the namespace is enforced by the store and
passed here so that it is a decision somebody made rather than a default they inherited.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.receipts.chain import generate_key
from approv.receipts.store import ReceiptStore
from approv.report import backtest as bt
from approv.report import render_html, render_text
from approv.report.importing import ExportRejected, Severity
from approv.report.render import to_html, to_text
from approv.types.core import CategorySchema


def load_schemas(paths: list[str]) -> dict[str, CategorySchema]:
    """A confirmed schema per category, read from disk.

    Accepts either a bare `CategorySchema` or the `ConfirmedSchema` envelope a review
    produces, because the second is what the schema pipeline actually emits and asking an
    operator to unwrap it by hand is asking for the wrong file to be passed.
    """
    schemas = {}
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("status") == "confirmed":
            payload = payload["category_schema"]
        elif payload.get("status") == "proposed":
            raise SystemExit(
                "%s is a *proposed* schema. A proposal has not been reviewed, and running "
                "a backtest against one would publish numbers derived from a schema "
                "nobody signed off. Confirm it first." % path)
        schema = CategorySchema.model_validate(payload)
        schemas[schema.category_id] = schema
    return schemas


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, help="directory of the partner's files")
    parser.add_argument("--merchant", required=True, help="merchant id for the records")
    parser.add_argument("--schema", action="append", default=[],
                        help="a confirmed category schema, repeatable")
    parser.add_argument("--out", default="output/backtest")
    parser.add_argument("--store", help="sandbox SQLite ledger. Default: <out>/receipts.sqlite")
    parser.add_argument("--window-days", type=int,
                        help="return window length, when the export does not carry one "
                             "per row. Without it or a ship date, no rate can be computed")
    parser.add_argument("--day-first", action="store_true",
                        help="the export writes dates day-first (03/04 is 3 April). "
                             "Approv refuses ambiguous dates rather than guessing")
    parser.add_argument("--month-first", action="store_true",
                        help="the export writes dates month-first (03/04 is 4 March)")
    parser.add_argument("--chunk", type=int, default=bt.CHUNK)
    parser.add_argument("--dry-run", action="store_true",
                        help="read the export and report what it would buy. Verifies "
                             "nothing, decides nothing, writes no receipts")
    arguments = parser.parse_args()

    if arguments.day_first and arguments.month_first:
        raise SystemExit("--day-first and --month-first are contradictory")
    day_first = True if arguments.day_first else (False if arguments.month_first else None)

    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)

    if arguments.dry_run:
        result = bt.survey(arguments.export, merchant_id=arguments.merchant,
                           day_first=day_first, window_days=arguments.window_days)
        page = bt.survey_text(result)
        (out / "survey.txt").write_text(page, encoding="utf-8")
        print(page)
        print("written: %s" % (out / "survey.txt"))
        return 0 if result.readable else 1

    if not arguments.schema:
        raise SystemExit(
            "--schema is required for a run. A backtest compares a stated request against "
            "your published catalogue using a reviewed category schema; deriving one here "
            "from the same catalogue would measure nothing. Use --dry-run to survey an "
            "export without one.")
    schemas = load_schemas(arguments.schema)

    try:
        export = bt.load(arguments.export, merchant_id=arguments.merchant,
                         day_first=day_first, window_days=arguments.window_days)
    except ExportRejected as rejected:
        print("This export cannot be run. %d problem(s):" % len(rejected.problems))
        for problem in rejected.problems:
            print("  " + str(problem))
        print("\nRun with --dry-run for the full survey, including what the readable part "
              "of this export would buy.")
        return 1

    ledger = Path(arguments.store) if arguments.store else out / "receipts.sqlite"
    store = ReceiptStore(ledger, namespace="sandbox")
    key = generate_key()

    result = bt.run(export, schemas=schemas, store=store, signing_key=key,
                    chunk=arguments.chunk, as_of=datetime.now(timezone.utc),
                    ledger=str(ledger))

    (out / "report.txt").write_text(to_text(result.document), encoding="utf-8")
    (out / "report.html").write_text(to_html(result.document), encoding="utf-8")
    (out / "receipts-export.json").write_text(
        json.dumps(store.export(), indent=2, default=str), encoding="utf-8")
    # The published key, beside the ledger. Without it the partner cannot check anything,
    # and "verify it yourself with none of our code" is a claim rather than an
    # instruction. The registry is written whole: a chain signed across a key rotation
    # needs every key it was signed under, not the current one.
    (out / "public-keys.json").write_text(
        json.dumps(store.public_keys(), indent=2, sort_keys=True), encoding="utf-8")

    print(to_text(result.document))
    print()
    print("=" * 84)
    print("THE RUN")
    print("=" * 84)
    print("  verified                 %d of %d order line(s)"
          % (result.verified, len(export.orders)))
    print("  sealed into the ledger   %d" % len(result.records))
    if result.evidence_only:
        print("  cart-only, not sealed    %d (order-evidence receipts; the store accepts"
              % len(result.evidence_only))
        print("                             only a ComparisonRecord today)")
    print("  verifying                %.2f s" % result.seconds_verifying)
    print("  storing (batched, %-5d) %.2f s" % (arguments.chunk, result.seconds_storing))
    print("  throughput               %.0f records/second end to end"
          % result.throughput)
    print("  ledger                   %s (namespace: sandbox)" % ledger)
    print()
    for note in result.notes:
        print("  - " + note)
    if result.failed:
        print()
        print("  %d problem(s) during the run:" % len(result.failed))
        for problem in result.failed[:20]:
            print("    " + str(problem))
    notes = [p for p in export.problems if p.severity is Severity.NOTE]
    if notes:
        print()
        print("  read, with a note:")
        for problem in notes:
            print("    " + str(problem))
    print()
    print("Verify the ledger with none of our code:")
    print("  python scripts/verify_receipt.py %s --keys %s"
          % (out / "receipts-export.json", out / "public-keys.json"))
    print("written: %s" % ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
