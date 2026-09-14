#!/usr/bin/env python3
"""A week of shadow traffic, reported five times: once at each data tier.

    python scripts/demo_partner_report.py --out output/partner-report

Runs one synthetic week through the real path — surface, evaluator, receipts, ledger —
and then renders the weekly report over that one week five times, each time as though the
partner had sent a different amount of outcome data:

    tier-0-none.*          receipts only. A pilot's real first week.
    tier-1-returns-only.*  which orders came back, and nothing else
    tier-2-minimum.*       + ship date and return-window length, so a kept order exists
    tier-3-good.*          + the desk's own reason code
    tier-4-best.*          + dispute and chargeback events

Every one of these is built from real `types.core.OrderOutcome` events. The optional
fields the higher rungs need are on the wire type now, so the tiers are no longer a
statement about what Approv can receive - they are a statement about what a given partner
actually sends, which is the thing that will differ between design partners.

**The week underneath is identical in all five.** The same orders, the same decisions, the
same returns. What changes is only which fields the partner sent, so every difference
between two of these pages is a difference in what the data could support and never a
difference in what happened. Hold tier 1 and tier 3 side by side and that is the answer
to "what do I get for what I give".

**Every outcome number is invented.** No partner has sent returns data yet, so outcomes
come from the seeded generator below, which is described in full when this script runs. The report marks every
row it derives from them, and the generator is deliberately not tuned to flatter — it
returns items for reasons Approv cannot see as well as reasons it can.

What is real: the receipts. They come out of the same `verify_order` -> `ReceiptStore`
path as production, they are signed and chained, and `scripts/verify_receipt.py` checks
them with none of this code.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.receipts.chain import generate_key
from approv.receipts.store import ReceiptStore
from approv.report import FeedSource, render_html, render_text
from approv.report import tiers as t
from approv.report.outcomes import (
    BLOCKED_WITHOUT, REQUIRED_OF_A_FEED, empty_feed, from_order_outcomes,
    ingestion_status,
)
from approv.intake import FreeText, Reading, Search, Structured
from approv.surface.verification import VerificationRequest, verify_order
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, ComparisonRecord, Constraint,
    Criticality, Decision, Dimension, FieldProfile, Liability, Money, OrderLine,
    OrderOutcome, OutcomeKind, Term,
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
WINDOW_DAYS = 21

# How the fixture invents outcomes. Printed when this runs, because a number whose
# generative process is hidden is worse than no number.
GENERATOR = (
    "An order that did not match the request comes back 55% of the time, coded "
    "not-as-described.",
    "An order that did match comes back 4% of the time: wrong size on the bed, changed "
    "mind, damaged in transit. Approv sees none of those coming.",
    "The return window is %d days, and the report is generated once the last of them "
    "has closed. Generate it a week after the period instead and every rate is empty: a "
    "return resolves the day it happens, a keep resolves only at window close, so a "
    "young period holds every return and no keep." % WINDOW_DAYS,
    "Half of the returns carry the attribute the customer complained about; the rest are "
    "uncoded, which is what most desks actually record.",
    "One return in twelve becomes a dispute or a chargeback, and a dispute is never "
    "counted as a return: the customer who charges back may have kept the goods.",
)


@dataclass
class Fact:
    """What actually happened to one order, before any tier decides how much of it to send.

    The whole point of the tier demo: this is the truth, and each tier is a *projection*
    of it. Generating a different week per tier would make the five reports incomparable
    and would quietly turn "what your data buys" into "what this run happened to roll".
    """

    correlation_id: str
    shipped_at: datetime
    returned: bool
    returned_at: datetime | None
    reason_code: str | None
    attribute: str | None
    disputed: bool
    merchant_reason: str | None


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


def fact_for(record: ComparisonRecord, wrong: bool, rng) -> Fact:
    """Invent what happened next. Correlated with reality, not with our decision.

    Deliberately keyed on whether the *order* actually mismatched rather than on what
    Approv decided. A fixture built from our own decisions would make precision and
    recall come out at whatever the generator was told to produce, and the report would
    be measuring its own inputs.
    """
    shipped_at = record.timestamp + timedelta(days=1)
    returned = rng.random() < (0.55 if wrong else 0.04)
    if not returned:
        return Fact(record.correlation_id, shipped_at, False, None, None, None, False,
                    None)
    code = "not_as_described" if wrong else rng.choice(
        ["changed_mind", "damaged", "not_as_described"])
    coded = rng.random() < 0.5
    return Fact(
        correlation_id=record.correlation_id, shipped_at=shipped_at, returned=True,
        returned_at=shipped_at + timedelta(days=rng.randint(2, 16)),
        # Half the desk's returns carry no code at all, which is what most desks record.
        reason_code=code if coded else None,
        attribute="colour" if coded and code == "not_as_described" else None,
        disputed=rng.random() < 1 / 12,
        merchant_reason="customer says the colour is wrong" if code == "not_as_described"
        else "customer changed their mind")


def events_for(tier: t.Tier, facts: list[Fact]) -> list[OrderOutcome]:
    """One tier's projection of the truth, as real `OrderOutcome` events.

    Fields above the rung are simply not sent, which is what a partner at that rung looks
    like. The wire type carries all of them, so nothing here is a stand-in: the
    difference between two of these pages is only ever a difference in what was sent.

    One field the higher rungs would like is genuinely not on the wire type yet - which
    attribute the customer complained about - so even the top rung here attributes
    returns from the record as a whole rather than from the desk's own coding. The report
    prints how many it attributed each way, so that gap is visible on the page rather
    than only in this docstring.
    """
    events = []
    for fact in facts:
        ship = ({"ship_date": fact.shipped_at, "return_window_days": WINDOW_DAYS}
                if tier >= t.Tier.MINIMUM else {})
        events.append(OrderOutcome(correlation_id=fact.correlation_id,
                                   kind=OutcomeKind.SHIPPED,
                                   occurred_at=fact.shipped_at, **ship))
        if fact.returned:
            events.append(OrderOutcome(
                correlation_id=fact.correlation_id, kind=OutcomeKind.RETURNED,
                occurred_at=fact.returned_at, merchant_reason=fact.merchant_reason,
                reason_code=fact.reason_code if tier >= t.Tier.GOOD else None, **ship))
        if fact.disputed and tier >= t.Tier.BEST:
            events.append(OrderOutcome(
                correlation_id=fact.correlation_id, kind=OutcomeKind.DISPUTED,
                occurred_at=(fact.returned_at or fact.shipped_at) + timedelta(days=3),
                **ship))
    return events


FILENAMES = {
    t.Tier.NONE: "tier-0-none",
    t.Tier.RETURNS_ONLY: "tier-1-returns-only",
    t.Tier.MINIMUM: "tier-2-minimum",
    t.Tier.GOOD: "tier-3-good",
    t.Tier.BEST: "tier-4-best",
}

# What to read off each page, for the summary table at the end of the run.
WATCHED = (
    ("return rate, refused", lambda b: b.return_rates[Decision.REFUSE]),
    ("return rate, authorised", lambda b: b.return_rates[Decision.ALLOW]),
    ("precision", lambda b: b.precision),
    ("recall (strict)", lambda b: b.recall_strict),
    ("payout proxy", lambda b: b.payout_proxy),
    ("dispute rate, refused", lambda b: b.dispute_rates[Decision.REFUSE]),
)


def cell(measure) -> str:
    if measure.unavailable is not None:
        return "--"
    if not measure.denominator:
        return "n/a"
    return "%.0f%% (%d/%d)" % (100 * measure.rate, measure.numerator,
                               measure.denominator)


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

    records, facts = [], []
    for index in range(arguments.orders):
        record, wrong = one_order(index, rng, store, key)
        records.append(record)
        facts.append(fact_for(record, wrong, rng))

    period = "the week of %s" % min(r.timestamp for r in records).date().isoformat()
    partner = "Hearth & Loom"
    # **Five days after the last return window closes, not five days after the week.**
    # A weekly report can only rate orders whose windows have closed, because a return
    # resolves the day it happens and a keep resolves only at window close - so a page
    # generated a week after the period contains every return and no keep, and every rate
    # on it is 100% by construction. The outcome half of a weekly report is three weeks
    # behind its decision half, and this is that lag made explicit rather than hidden by
    # a fixture that quietly closed every window.
    as_of = max(r.timestamp for r in records) + timedelta(days=WINDOW_DAYS + 6)

    documents = {}
    for tier in t.Tier:
        if tier is t.Tier.NONE:
            feed = empty_feed("no outcome feed was supplied for this period")
        else:
            feed = from_order_outcomes(
                events_for(tier, facts), source=FeedSource.FIXTURE, as_of=as_of,
                description="seeded generator in scripts/demo_partner_report.py, seed "
                            "%d, sent at the %s tier. Not partner data."
                            % (arguments.seed, t.TIERS[tier].name))
        name = FILENAMES[tier]
        text = render_text(records, feed, partner=partner, period=period,
                           ledger=str(ledger), generated_at=as_of)
        (out / (name + ".txt")).write_text(text, encoding="utf-8")
        (out / (name + ".html")).write_text(
            render_html(records, feed, partner=partner, period=period,
                        ledger=str(ledger), generated_at=as_of), encoding="utf-8")
        documents[tier] = build_of(records, feed, partner, period, ledger, as_of)
        if tier is t.Tier.GOOD:
            print(text)

    print()
    print("=" * 88)
    print("HOW THE FIXTURE OUTCOMES WERE INVENTED")
    print("=" * 88)
    for line in GENERATOR:
        print("  - " + line)

    print()
    print("=" * 88)
    print("THE SAME WEEK AT EVERY TIER: WHAT THE PARTNER GETS FOR WHAT THEY SEND")
    print("=" * 88)
    print("Agent-stated orders only, so the columns are comparable. `--` is a row that")
    print("printed its reason instead of a number.")
    print()
    print("Generated %s, which is %d days after the last return window in the period"
          % (as_of.date().isoformat(), WINDOW_DAYS + 6))
    print("closes. Run it a week after the period instead and every rate below is empty:")
    print("a return resolves the day it happens and a keep resolves only at window")
    print("close, so a young period holds every return and no keep.")
    print()
    header = "%-26s" % "" + "".join("%-17s" % t.TIERS[tier].name[:16] for tier in t.Tier)
    print(header)
    print("-" * len(header))
    for label, pick in WATCHED:
        row = "%-26s" % label
        for tier in t.Tier:
            row += "%-17s" % cell(pick(documents[tier].populations[0]))
        print(row)

    print()
    print("WHAT A FEED HAS TO DELIVER FOR ANY OF THIS TO BE REAL")
    print("-" * 88)
    for line in REQUIRED_OF_A_FEED:
        print("  - " + line)
    print()
    print("Fields the fold looks for, and whether types.core.OrderOutcome carries them:")
    for name, why, present in ingestion_status(OrderOutcome):
        print("  [%s] %-26s %s" % ("x" if present else " ", name, why))
    print()
    print("Rows that print a reason instead of a number when a feed lacks one:")
    for missing, _ in BLOCKED_WITHOUT:
        print("  - missing: " + missing)
    print()
    print("written: %s" % ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


def build_of(records, feed, partner, period, ledger, as_of):
    from approv.report.document import build
    return build(records, feed, partner=partner, period=period, ledger=str(ledger),
                 generated_at=as_of)


if __name__ == "__main__":
    raise SystemExit(main())
