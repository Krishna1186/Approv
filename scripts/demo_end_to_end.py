#!/usr/bin/env python3
"""The whole company, once, in one process: order event to a document a stranger checks.

    python scripts/demo_end_to_end.py --out output/end-to-end

    merchant order event
      -> approv.surface.verification   the stated request, the order line, the comparison
      -> approv.evaluator              the deterministic decision
      -> approv.receipts.store         sealed, chained, appended, checkpointed
      -> approv.artifact               the document a returns desk reads
      -> scripts/verify_receipt.py     checked with a published key and none of our code

Four orders, four outcomes a merchant actually sees: an authorised order, a refused one,
an order the merchant's own catalogue cannot settle, and one whose request we did not
finish reading. Two arrive as protocol calls and two as free text, because those produce
different records and the document has to say which.

No model call and no network. The extracted requirements are supplied directly, so what
this demonstrates is the *decision path* — deterministic, no model in it — rather than an
extractor, which is neither. Anything a model produced would sit in `request_constraints`
exactly as these do.

`scripts/demo_receipt.py` demonstrates the same engine against the frozen Shopify pack and
needs that pack on disk. This one needs no data at all and carries the ledger, the
document and the independent check that the older demo stops short of.

**The composition here is done by hand, because nothing in the repo does it yet.** The
order of the calls is load-bearing in one place — the store seals, so the surface must
not — and the seams between the four modules are pinned in `tests/test_end_to_end.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.artifact import build, render_html, render_text
from approv.intake import FreeText, Reading, Structured
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore
from approv.surface.verification import VerificationRequest, verify_order
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Dimension,
    FieldProfile, Liability, Money, OrderLine, Term,
)

VERIFIER = Path(__file__).resolve().parent / "verify_receipt.py"

# One merchant's catalogue, as it would arrive in a snapshot: the product record exactly
# as their own system holds it. Two lines of the same product one variant apart, which is
# the near miss that dominates first-party catalogues and needs no attacker.
CATALOGUE = {
    "duvet-tandem-frost": {
        "product_id": "duvet-tandem-frost", "title": "Tandem Stripe Duvet Cover",
        "variant": {"size": "King", "colour": "Frost"},
        "description": "Brushed cotton percale, woven in Portugal."},
    "duvet-tandem-stone": {
        "product_id": "duvet-tandem-stone", "title": "Tandem Stripe Duvet Cover",
        "variant": {"size": "King", "colour": "Stone"},
        "description": "Brushed cotton percale, woven in Portugal."},
    "duvet-halden": {
        "product_id": "duvet-halden", "title": "Halden Linen Duvet Cover",
        "variant": {"size": "King"},
        "description": "Washed linen."},
}

# The merchant's schema. Hand-authored, which is what a merchant has today:
# `approv.schema` derives one from a catalogue, but its field paths are not the ones the
# surface reads (seam 1 in tests/test_end_to_end.py), so onboarding is not wired in here.
SCHEMA = CategorySchema(
    category_id="bedding", version="demo-1",
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


def reading(*requirements, unread=()):
    """A stand-in extractor: the reading a model would have produced, supplied directly."""
    def extract(text, schema):
        return Reading(
            constraints=tuple(
                Constraint(attribute=attribute, value=Term(surface=value),
                           channel=Channel.AGENT_MESSAGE, raw_text=quote)
                for attribute, value, quote in requirements),
            unread=tuple(unread))
    return extract


CASES = [
    {"id": "ORD-4471", "product": "duvet-tandem-frost", "price": "118.00", "quantity": 2,
     "story": "a protocol call for exactly what is on the shelf",
     "artifact": Structured(protocol="acp", fields={"size": "King", "colour": "Frost"}),
     "extract": None},
    {"id": "ORD-4472", "product": "duvet-tandem-stone", "price": "118.00", "quantity": 1,
     "story": "free text, and the agent picked the wrong colourway of the right product",
     "artifact": FreeText(text="I need a king size duvet cover, it must be Frost, "
                               "nothing darker."),
     "extract": reading(("size", "King", "a king size duvet cover"),
                        ("colour", "Frost", "it must be Frost, nothing darker"))},
    {"id": "ORD-4473", "product": "duvet-halden", "price": "149.00", "quantity": 1,
     "story": "a colour this line does not publish, so the catalogue cannot settle it",
     "artifact": Structured(protocol="acp", fields={"size": "King", "colour": "Ash"}),
     "extract": None},
    {"id": "ORD-4474", "product": "duvet-tandem-frost", "price": "118.00", "quantity": 1,
     "story": "free text carrying a requirement we could not encode",
     "artifact": FreeText(text="a king duvet in Frost, hotel weight please"),
     "extract": reading(("size", "King", "a king duvet"),
                        ("colour", "Frost", "in Frost"),
                        unread=("Descriptive property, not a named value, left "
                                "unverified: hotel weight",))},
]


def place(case, store, signing_key):
    """One order through the whole path. The surface does not seal; the ledger does.

    Both can, and only the ledger knows the chain head — a record sealed at the surface
    carries `prev_hash=None` and is rejected from the second receipt onward.
    """
    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id=case["id"],
            category_id="bedding",
            order=OrderLine(order_id=case["id"], line_id="1",
                            product_id=case["product"],
                            sku=case["product"].upper(), variant_id="v-king",
                            quantity=case["quantity"],
                            unit_price=Money(amount=case["price"], currency="USD"),
                            availability="in_stock",
                            catalogue_version="2026-09-13T08:00Z"),
            artifact=case["artifact"],
            product_snapshot=dict(CATALOGUE[case["product"]])),
        schemas={"bedding": SCHEMA}, extract=case["extract"])
    return store.append(result.record, signing_key), result


def run_verifier(*arguments) -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(VERIFIER), *arguments],
                          capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="output/end-to-end")
    parser.add_argument("--password", default="demo-key-password",
                        help="encrypts the demo signing key on disk; never a real secret")
    arguments = parser.parse_args()

    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "receipts.sqlite"
    if ledger.exists():
        # The ledger is append-only by construction, so a rerun would replay correlation
        # ids into a chain that already has them. A demo starts from nothing.
        ledger.unlink()

    keys = KeyStore(out / "keys", password=arguments.password.encode("utf-8"))
    key_id = keys.rotate()
    signing_key = keys.load_private()
    public_hex = keys.public_keys()[key_id]
    store = ReceiptStore(ledger)

    print("APPROV, END TO END")
    print("=" * 78)
    print("merchant   hearth-and-loom, one category, three catalogue lines")
    print("signing    %s" % key_id)
    print()

    for case in CASES:
        record, result = place(case, store, signing_key)
        document = build(record)
        stem = case["id"]
        (out / (stem + ".json")).write_text(record.model_dump_json(indent=2),
                                            encoding="utf-8")
        (out / (stem + ".txt")).write_text(
            render_text(record, public_key=public_hex, record_file=stem + ".json"),
            encoding="utf-8")
        (out / (stem + ".html")).write_text(
            render_html(record, public_key=public_hex, record_file=stem + ".json"),
            encoding="utf-8")

        print("%s  %s" % (stem, case["story"]))
        print("   request     %s" % record.request_text[:64])
        print("   decision    %-8s %s" % (record.decision.value,
                                          ", ".join(record.decision_reasons) or "-"))
        print("   coverage    %s" % document.summary.split("Coverage: ")[-1].rstrip("."))
        if record.unread:
            print("   unread      %d requirement(s) Approv failed to read" % len(record.unread))
        print("   receipt     %s  prev %s" % (record.hash[:16],
                                              (record.prev_hash or "none")[:16]))
        print("   document    %s.txt, %s.html" % (stem, stem))
        print()

    export = store.export()
    export_path = out / "export.json"
    export_path.write_text(json.dumps(export, indent=2), encoding="utf-8")
    published = keys.publish(out / "public-keys.json")
    checkpoint_path = out / "checkpoint.json"
    checkpoint_path.write_text(json.dumps(export["checkpoint"], indent=2), encoding="utf-8")

    print("THE LEDGER")
    print("-" * 78)
    print("%d receipts, one chain, checkpoint at %s"
          % (export["checkpoint"]["count"], export["checkpoint"]["head_hash"][:16]))
    print("written    %s, %s, %s" % (export_path.name, published.name,
                                     checkpoint_path.name))
    print()

    print("AN INDEPENDENT CHECK, WITH NONE OF THIS CODE")
    print("-" * 78)
    genuine, output = run_verifier(str(export_path), "--keys", str(published),
                                   "--checkpoint", str(checkpoint_path))
    print("$ python scripts/verify_receipt.py %s --keys %s --checkpoint %s"
          % (export_path.name, published.name, checkpoint_path.name))
    print(output)
    print()

    # The same check against a record somebody has improved after the fact. This is the
    # threat the chain exists for: not a stranger forging a receipt, but the party holding
    # it turning a refusal into an authorisation once the outcome is known.
    tampered = json.loads(export_path.read_text(encoding="utf-8"))
    tampered["records"][1]["decision"] = "allow"
    tampered_path = out / "export-tampered.json"
    tampered_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    edited, output = run_verifier(str(tampered_path), "--keys", str(published))
    print("AND THE SAME EXPORT WITH ONE REFUSAL TURNED INTO AN AUTHORISATION")
    print("-" * 78)
    print(output.splitlines()[0])
    print()

    print("WHAT A RETURNS DESK OPENS")
    print("-" * 78)
    print("%s" % (out / "ORD-4472.html"))
    print("The refusal: what was asked for in the requester's own words, what was sold,")
    print("which of the merchant's own fields disagrees, and what Approv does and does")
    print("not stand behind. The page carries the signed record inside it.")
    # The demo is only a demonstration if both halves land: the genuine export verifies
    # and the edited one does not. Either way round, saying so beats printing success.
    if genuine == 0 and edited == 1:
        return 0
    print("DEMO FAILED: genuine export exited %d, edited export exited %d"
          % (genuine, edited))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
