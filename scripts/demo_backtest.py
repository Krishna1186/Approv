#!/usr/bin/env python3
"""The whole backtest path, at pilot scale, over an export that is deliberately a mess.

    python scripts/demo_backtest.py --rows 5000 --out output/backtest-demo

Generates a synthetic partner export with the problems a first export actually has - a
BOM, semicolon delimiters, their own column names, ambiguous dates, an exact duplicate,
cp1252 bytes in a customer's words, an outcome for an order that was never submitted -
then runs the two things a pilot does with it:

    1. the dry run, which reads the files, decides nothing, and says which rung of the
       data ladder this export lands on and what is missing to reach the next
    2. the run itself: batch verification, a signed sandbox ledger, the weekly report,
       and an independent verification of the chain with none of our code

**Every order and outcome here is invented.** No partner has sent an export. What is real
is the path: the same `verify_order`, the same `ReceiptStore.append_many`, the same
importer that will meet the first real file, and the same refusals.

The throughput printed at the end is end-to-end for this machine and this fixture. It is
not a guarantee and it is not the partner's number: extraction is off, the receipts are
small, and PILOT-RUNBOOK.md's measured storage table is the one to quote.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.receipts.chain import generate_key
from approv.receipts.store import ReceiptStore
from approv.report import backtest as bt
from approv.report.importing import Severity
from approv.report.render import to_html, to_text
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Criticality, Dimension, FieldProfile,
    Liability,
)

SCHEMA = CategorySchema(
    category_id="bedding", version="pilot-1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL,
                      criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL,
                      criticality=Criticality.HARD),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     is_variant_axis=True, certainty=Certainty.EXACT,
                     liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="description", attributes=("colour",),
                     certainty=Certainty.PARSED,
                     liability=Liability.MERCHANT_GUARANTEED),
    ))

SIZES = ["King", "Queen", "Double"]
COLOURS = ["Frost", "Stone", "Ash", "Clay"]
WINDOW_DAYS = 21

MESS = (
    "The orders file is semicolon-delimited with a UTF-8 byte order mark, which is what "
    "a European spreadsheet export looks like.",
    "Their columns are called `Order Ref.`, `Qty`, `Stock Status` and so on, and there is "
    "a `Warehouse` column Approv does not read.",
    "Dates are day-first and ambiguous (`03/04/2026`), so the run must be told the "
    "convention. Without --day-first every one of them is refused with its line number.",
    "One row in fifty is an exact duplicate: the export was run twice and concatenated.",
    "A customer's own words carry cp1252 smart quotes, so the requests file is not UTF-8.",
    "One outcome row in a hundred names an order that is not in the orders file. Those "
    "are kept: they are the share of their traffic that never reached Approv.",
    "The outcomes file has no window-length column, so the window is passed once for the "
    "whole export with --window-days.",
)


def write_export(directory: Path, rows: int, rng: random.Random) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)

    catalogue, orders, requests, outcomes, facts = {}, [], [], [], []
    orders.append("Order Ref.;Line;Product Type;Product;SKU;Variant;Qty;Unit Price;"
                  "Currency;Order Date;Stock Status;Warehouse")
    requests.append("order_ref,line,type,protocol,slots,search_query,facets,"
                    "declared_intent")
    outcomes.append("order_ref,line,event,date,reason,return_code,dispatched_at")

    for index in range(rows):
        wanted_size, wanted_colour = rng.choice(SIZES), rng.choice(COLOURS)
        mismatched = rng.random() < 0.22
        silent = rng.random() < 0.10
        got_colour = (rng.choice([c for c in COLOURS if c != wanted_colour])
                      if mismatched else wanted_colour)
        product = "duvet-%05d" % index
        snapshot = {"title": "Percale Duvet Cover",
                    "variant": {"size": wanted_size, "colour": got_colour},
                    "description": "Brushed cotton percale."}
        if silent:
            snapshot["variant"].pop("colour")
        catalogue[product] = snapshot

        ordered = start + timedelta(days=rng.randint(0, 11))
        order_ref = "SO-%06d" % index
        line = ("%s;1;bedding;%s;SKU-%06d;v-%06d;1;118.00;GBP;%s;in_stock;LEEDS"
                % (order_ref, product, index, index, ordered.strftime("%d/%m/%Y")))
        orders.append(line)
        if index % 50 == 0:                                    # the concatenated re-export
            orders.append(line)

        shape = rng.choices(["structured", "search", "free_text", "undeclared"],
                            weights=[52, 26, 15, 7])[0]
        if shape == "structured":
            slots = json.dumps({"size": wanted_size, "colour": wanted_colour})
            requests.append('%s,1,structured,acp,"%s",,,'
                            % (order_ref, slots.replace('"', '""')))
        elif shape == "search":
            requests.append('%s,1,search,,,"%s duvet %s","size=%s",'
                            % (order_ref, wanted_size.lower(), wanted_colour.lower(),
                               wanted_size))
        elif shape == "free_text":
            requests.append('%s,1,free_text,,,,,"a %s duvet cover in %s, “nothing too '
                            'dark”"' % (order_ref, wanted_size.lower(),
                                             wanted_colour.lower()))
        else:
            requests.append("%s,1,undeclared,,,,," % order_ref)

        shipped = ordered + timedelta(days=rng.randint(1, 3))
        outcomes.append("%s,1,dispatched,%s,,,%s"
                        % (order_ref, shipped.strftime("%d/%m/%Y"),
                           shipped.strftime("%d/%m/%Y")))
        wrong = mismatched or silent
        if rng.random() < (0.55 if wrong else 0.04):
            back = shipped + timedelta(days=rng.randint(2, 18))
            coded = rng.random() < 0.5
            code = ("not_as_described" if wrong else
                    rng.choice(["changed_mind", "damaged", "not_as_described"]))
            outcomes.append("%s,1,returned,%s,%s,%s,%s"
                            % (order_ref, back.strftime("%d/%m/%Y"),
                               "customer says the colour is wrong" if wrong
                               else "changed their mind", code if coded else "",
                               shipped.strftime("%d/%m/%Y")))
            if rng.random() < 1 / 12:
                outcomes.append("%s,1,chargeback,%s,,,%s"
                                % (order_ref,
                                   (back + timedelta(days=5)).strftime("%d/%m/%Y"),
                                   shipped.strftime("%d/%m/%Y")))
        if index % 100 == 0:                                   # never reached Approv
            outcomes.append("SO-NOTOURS-%04d,1,returned,%s,lost in transit,"
                            "not_as_described,%s"
                            % (index, (shipped + timedelta(days=6)).strftime("%d/%m/%Y"),
                               shipped.strftime("%d/%m/%Y")))
        facts.append(order_ref)

    (directory / "orders-2026-04.csv").write_bytes(
        b"\xef\xbb\xbf" + "\r\n".join(orders).encode("utf-8") + b"\r\n")
    (directory / "requests.csv").write_bytes("\n".join(requests).encode("cp1252"))
    (directory / "catalogue.json").write_text(json.dumps(catalogue), encoding="utf-8")
    (directory / "outcomes.csv").write_text("\n".join(outcomes), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--out", default="output/backtest-demo")
    parser.add_argument("--seed", type=int, default=20260914)
    parser.add_argument("--chunk", type=int, default=bt.CHUNK)
    arguments = parser.parse_args()

    out = Path(arguments.out)
    export_dir = out / "export"
    out.mkdir(parents=True, exist_ok=True)
    for stale in (out / "receipts.sqlite", out / "receipts.sqlite-wal",
                  out / "receipts.sqlite-shm"):
        if stale.exists():
            stale.unlink()

    write_export(export_dir, arguments.rows, random.Random(arguments.seed))
    print("Wrote a %d-row export to %s. What is wrong with it, on purpose:"
          % (arguments.rows, export_dir))
    for line in MESS:
        print("  - " + line)
    print()

    print("=" * 84)
    print("1. THE DRY RUN, WITHOUT DECLARING THE DATE CONVENTION")
    print("=" * 84)
    blind = bt.survey(export_dir, merchant_id="hearth-and-loom",
                      window_days=WINDOW_DAYS)
    fatal = [p for p in blind.problems if p.severity is Severity.FATAL]
    print("readable: %s, with %d fatal problem(s). The first three:"
          % (blind.readable, len(fatal)))
    for problem in fatal[:3]:
        print("  " + str(problem))
    print()
    print("Nothing was guessed at. Approv will not pick a reading of `03/04/2026`.")
    print()

    print("=" * 84)
    print("2. THE DRY RUN, WITH IT DECLARED")
    print("=" * 84)
    survey = bt.survey(export_dir, merchant_id="hearth-and-loom", day_first=True,
                       window_days=WINDOW_DAYS)
    page = bt.survey_text(survey)
    (out / "survey.txt").write_text(page, encoding="utf-8")
    print(page)

    print("=" * 84)
    print("3. THE RUN")
    print("=" * 84)
    export = bt.load(export_dir, merchant_id="hearth-and-loom", day_first=True,
                     window_days=WINDOW_DAYS)
    ledger = out / "receipts.sqlite"
    store = ReceiptStore(ledger, namespace="sandbox")
    key = generate_key()
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)
    result = bt.run(export, schemas={"bedding": SCHEMA}, store=store, signing_key=key,
                    chunk=arguments.chunk, as_of=as_of, partner="Hearth & Loom",
                    ledger=str(ledger))

    (out / "report.txt").write_text(to_text(result.document), encoding="utf-8")
    (out / "report.html").write_text(to_html(result.document), encoding="utf-8")
    (out / "receipts-export.json").write_text(
        json.dumps(store.export(), indent=2, default=str), encoding="utf-8")
    (out / "public-keys.json").write_text(
        json.dumps(store.public_keys(), indent=2, sort_keys=True), encoding="utf-8")

    print("  order lines verified              %d" % result.verified)
    print("  of which sealed into the ledger   %d" % len(result.records))
    if result.evidence_only:
        print("  cart-only, verified but unsealed  %d  (seam 7: the store accepts only"
              % len(result.evidence_only))
        print("                                        a ComparisonRecord)")
    print("  verifying                         %.2f s" % result.seconds_verifying)
    print("  storing, batched at %-5d         %.2f s"
          % (arguments.chunk, result.seconds_storing))
    print("  end to end                        %.0f records/second on this machine"
          % result.throughput)
    print("  ledger                            %s (sandbox namespace)" % ledger)
    unverified = [p for p in result.failed if p.code == "not_verified"]
    if unverified:
        print("  not verified                      %d, each with its line number"
              % len(unverified))
    print()
    print("  The rung this export reached: %s" % result.document.tier.name)
    print()

    print("=" * 84)
    print("4. VERIFIED WITH NONE OF OUR CODE")
    print("=" * 84)
    verifier = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("verify_receipt.py")),
         str(out / "receipts-export.json"), "--keys", str(out / "public-keys.json")],
        capture_output=True, text=True)
    tail = [line for line in verifier.stdout.splitlines() if line.strip()][-4:]
    print("  exit %d" % verifier.returncode)
    for line in tail:
        print("  " + line)
    print()
    print("written: %s" % ", ".join(sorted(p.name for p in out.iterdir())))
    return verifier.returncode


if __name__ == "__main__":
    raise SystemExit(main())
