#!/usr/bin/env python3
"""A week of shadow traffic, and the report a design partner would receive.

    python scripts/demo_partner_report.py --out output/partner-report

Runs a synthetic week through the real path — surface, evaluator, receipts, ledger — and
renders the weekly report over the resulting chain. Two reports are produced:

    week-1.*   no outcome data at all, which is a pilot's real first week
    week-2.*   a FIXTURE outcome feed carrying everything the report needs, so the
               outcome-derived rows can be seen working
    week-3.*   the same week through `types.core.OrderOutcome`, the ingestion path that
               actually exists. Most outcome rows print NOT COMPUTED with the reason, and
               the gap between this and week two is the specification for what ingestion
               still has to carry

**Every number in the second report is invented.** The returns data does not exist: the
ingestion path is claude1's and is not built, so the outcomes here come from the seeded
generator below, which is described in full when this script runs. The report marks every
row it derives from them, and the fixture is deliberately not tuned to flatter — the
generator returns items for reasons Approv cannot see as well as reasons it can.

What is real: the receipts. They come out of the same `verify_order` -> `ReceiptStore`
path as production, they are signed and chained, and `scripts/verify_receipt.py` checks
them with none of this code.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.receipts.chain import generate_key
from approv.receipts.store import ReceiptStore
from approv.report import FeedSource, from_rows, render_html, render_text
from approv.report.outcomes import MISSING_FROM_INGESTION, REQUIRED_OF_INGESTION
from approv.intake import FreeText, Reading, Search, Structured
from approv.surface.verification import VerificationRequest, verify_order
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, ComparisonRecord, Constraint,
    Criticality, Decision, Dimension, FieldProfile, Liability, Money, OrderLine, Term,
)

SCHEMA = CategorySchema(
    category_id="bedding", version="pilot-1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="material", dimension=Dimension.NOMINAL,
                      criticality=Criticality.SOFT),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     is_variant_axis=True, certainty=Certainty.EXACT,
                     liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="description", attributes=("material",),
                     certainty=Certainty.PARSED, liability=Liability.MERCHANT_GUARANTEED),
    ),
)

SIZES = ["King", "Queen", "Double"]
COLOURS = ["Frost", "Stone", "Ash", "Clay"]

# How the fixture invents outcomes. Printed when this runs, because a number whose
# generative process is hidden is worse than no number.
GENERATOR = (
    "An order that did not match the request comes back 55% of the time, coded "
    "not-as-described.",
    "An order that did match comes back 4% of the time: wrong size on the bed, changed "
    "mind, damaged in transit. Approv sees none of those coming.",
    "A quarter of the week's orders are still inside their return window and are `open`, "
    "which excludes them from every rate.",
    "Half of the returns carry the attribute the customer complained about; the rest are "
    "uncoded, which is what most desks actually record.",
)


def product(product_id, size, colour, material="Brushed cotton percale."):
    return {"product_id": product_id, "title": "%s Duvet Cover" % product_id.title(),
            "variant": {"size": size, "colour": colour}, "description": material}


def reading_for(size, colour):
    def extract(text, schema):
        return Reading(constraints=(
            Constraint(attribute="size", value=Term(surface=size),
                       channel=Channel.AGENT_MESSAGE, raw_text="a %s duvet cover" % size),
            Constraint(attribute="colour", value=Term(surface=colour),
                       channel=Channel.AGENT_MESSAGE, raw_text="in %s" % colour)))
    return extract


def one_order(index, rng, store, key):
    """One shadow order event: an agent asks, the merchant ships, Approv watches."""
    wanted_size, wanted_colour = rng.choice(SIZES), rng.choice(COLOURS)
    # The near miss: the agent picks the right product one variant along. This is the
    # failure the product exists for and it needs no attacker.
    mismatched = rng.random() < 0.22
    got_colour = rng.choice([c for c in COLOURS if c != wanted_colour]) if mismatched \
        else wanted_colour
    # Some lines publish no colour at all, which is what makes a confirm rather than a
    # refusal: the merchant's own catalogue cannot settle it.
    silent = rng.random() < 0.12
    snapshot = product("duvet-%03d" % index, wanted_size, got_colour)
    if silent:
        snapshot["variant"].pop("colour")

    origin = rng.choices(["protocol", "declared", "search", "none"],
                         weights=[45, 20, 28, 7])[0]
    extract = None
    if origin == "protocol":
        artifact = Structured(protocol="acp", fields={"size": wanted_size,
                                                      "colour": wanted_colour})
    elif origin == "declared":
        artifact = FreeText(text="a %s duvet cover in %s" % (wanted_size, wanted_colour))
        extract = reading_for(wanted_size, wanted_colour)
    elif origin == "search":
        artifact = Search(query="%s duvet %s" % (wanted_size, wanted_colour),
                          filters={"size": wanted_size})
        extract = reading_for(wanted_size, wanted_colour)
    else:
        artifact = Structured(protocol="acp", fields={})

    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id="corr-%04d" % index,
            category_id="bedding",
            order=OrderLine(order_id="ORD-%04d" % index, line_id="1",
                            product_id=snapshot["product_id"],
                            sku="SKU-%04d" % index, variant_id="v-%d" % index,
                            quantity=1,
                            unit_price=Money(amount="118.00", currency="USD"),
                            availability="in_stock"),
            artifact=artifact, product_snapshot=snapshot),
        schemas={"bedding": SCHEMA}, extract=extract)
    return store.append(result.record, key), mismatched or silent


def outcome_for(record: ComparisonRecord, wrong: bool, rng) -> dict:
    """Invent what happened next. Correlated with reality, not with our decision.

    Deliberately keyed on whether the *order* actually mismatched rather than on what
    Approv decided. A fixture built from our own decisions would make precision and
    recall come out at whatever the generator was told to produce, and the report would
    be measuring its own inputs.
    """
    if rng.random() < 0.25:
        return {"order_id": record.order.order_id, "line_id": record.order.line_id,
                "correlation_id": record.correlation_id, "status": "open",
                "window_closes_at": (record.timestamp + timedelta(days=21)).isoformat()}
    returned = rng.random() < (0.55 if wrong else 0.04)
    if not returned:
        return {"order_id": record.order.order_id, "line_id": record.order.line_id,
                "correlation_id": record.correlation_id, "status": "kept",
                "resolved_at": (record.timestamp + timedelta(days=21)).isoformat()}
    code = "not_as_described" if wrong else rng.choice(
        ["changed_mind", "damaged", "not_as_described"])
    row = {"order_id": record.order.order_id, "line_id": record.order.line_id,
           "correlation_id": record.correlation_id, "status": "returned",
           "reason_code": code,
           "resolved_at": (record.timestamp + timedelta(days=9)).isoformat()}
    if code == "not_as_described" and rng.random() < 0.5:
        row["attribute"] = "colour"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="output/partner-report")
    parser.add_argument("--orders", type=int, default=90)
    parser.add_argument("--seed", type=int, default=20260913)
    arguments = parser.parse_args()

    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "shadow.sqlite"
    if ledger.exists():
        ledger.unlink()

    rng = random.Random(arguments.seed)
    store = ReceiptStore(ledger)
    key = generate_key()

    records, wrongness = [], {}
    for index in range(arguments.orders):
        record, wrong = one_order(index, rng, store, key)
        records.append(record)
        wrongness[record.correlation_id] = wrong

    period = "7-13 September 2026"
    partner = "Hearth & Loom"

    # Week one: the receipts exist, the outcome feed does not. This is the real first
    # report of a pilot and the one most likely to be sent.
    first = render_text(records, None, partner=partner, period=period,
                        ledger=str(ledger))
    (out / "week-1.txt").write_text(first, encoding="utf-8")
    (out / "week-1.html").write_text(
        render_html(records, None, partner=partner, period=period, ledger=str(ledger)),
        encoding="utf-8")

    feed = from_rows((outcome_for(r, wrongness[r.correlation_id], rng) for r in records),
                     source=FeedSource.FIXTURE,
                     description="seeded generator in scripts/demo_partner_report.py, "
                                 "seed %d. Not partner data." % arguments.seed)
    (out / "outcomes-fixture.json").write_text(feed.model_dump_json(indent=2),
                                               encoding="utf-8")
    second = render_text(records, feed, partner=partner, period=period, ledger=str(ledger))
    (out / "week-2.txt").write_text(second, encoding="utf-8")
    (out / "week-2.html").write_text(
        render_html(records, feed, partner=partner, period=period, ledger=str(ledger)),
        encoding="utf-8")

    # Week three: the same week, through the ingestion path that actually exists. This is
    # the honest version of what a partner would receive today, and the gap between it and
    # week two is the specification for what ingestion still has to carry.
    from approv.types.core import OrderOutcome, OutcomeKind
    from approv.report.outcomes import from_order_outcomes
    events = []
    for r in records:
        events.append(OrderOutcome(correlation_id=r.correlation_id,
                                   kind=OutcomeKind.SHIPPED, occurred_at=r.timestamp))
        if wrongness[r.correlation_id] and rng.random() < 0.55:
            events.append(OrderOutcome(
                correlation_id=r.correlation_id, kind=OutcomeKind.RETURNED,
                occurred_at=r.timestamp + timedelta(days=9),
                merchant_reason="customer says the colour is wrong"))
    real = from_order_outcomes(events, source=FeedSource.PARTNER,
                               description="OrderOutcome events, ingestion run")
    (out / "week-3.txt").write_text(
        render_text(records, real, partner=partner, period=period, ledger=str(ledger)),
        encoding="utf-8")
    (out / "week-3.html").write_text(
        render_html(records, real, partner=partner, period=period, ledger=str(ledger)),
        encoding="utf-8")

    print(second)
    print()
    print("=" * 88)
    print("HOW THE FIXTURE OUTCOMES WERE INVENTED")
    print("=" * 88)
    for line in GENERATOR:
        print("  - " + line)
    print()
    print("WHAT THE INGESTION PATH HAS TO DELIVER FOR ANY OF THIS TO BE REAL")
    print("-" * 88)
    for line in REQUIRED_OF_INGESTION:
        print("  - " + line)
    print()
    print("week-3.txt is the same week through the real OrderOutcome shape. Rows it")
    print("cannot support print the reason instead of a number:")
    for missing, _ in MISSING_FROM_INGESTION:
        print("  - missing: " + missing)
    print()
    print("written: %s" % ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
