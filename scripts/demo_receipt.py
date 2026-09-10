#!/usr/bin/env python3
"""End to end: a request, a real catalogue, a decision, a signed receipt.

    python scripts/demo_receipt.py --out output/demo

Runs three requests against variants from the frozen Shopify pack and walks each through
the whole path — extracted requirements, typed comparison, `evaluator.decide`, then a
sealed record linked into a hash chain. It writes `receipts.json` and `public_key.txt`
and prints the command that verifies them with none of this code.

There is no model call and no network here. The requirements are supplied directly so the
demo shows the *decision path*, which is deterministic, rather than an extractor, which is
not. Anything a model produced would sit in `request_constraints` exactly as these do.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.algebra.runner import check_constraints
from approv.harness.shopping import Inventory, digest
from approv.receipts.chain import generate_key, public_key_hex, seal
from approv.receipts.record import build_record
from approv.types.core import Channel, Constraint, Term

PACK = "data/cache/shopping-study/shopper.json"

# request text, then what the shopper asked for, as typed requirements.
CASES = [
    ("I need these in size 9, dark blue, and they have to be in stock.",
     {"size": "9", "color": "Dark blue", "availability": "in stock"}),
    ("Size 9 please, any colour is fine.",
     {"size": "9"}),
    ("Size 13 in dark blue, must be available.",
     {"size": "13", "color": "Dark blue", "availability": "in stock"}),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", default=PACK)
    parser.add_argument("--out", default="output/demo")
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    inventory = Inventory.model_validate(pack["inventory"])
    schema = inventory.category_schema
    # One real product per case, chosen so the three decisions differ. Picking a variant
    # is retrieval's job, not this script's; the demo is about what happens after.
    products = [p for p in inventory.products if p.evidence][:3]

    key = generate_key()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    records, previous = [], None
    for index, ((request_text, wanted), product) in enumerate(zip(CASES, products)):
        constraints = tuple(
            Constraint(attribute=a, value=Term(surface=v), channel=Channel.AGENT_MESSAGE,
                       raw_text=v)
            for a, v in wanted.items()
            if a in {s.name for s in schema.attributes})
        findings = check_constraints(constraints, product.evidence, schema)
        asked = {c.attribute for c in constraints} | schema.floor
        findings = tuple(f for f in findings if f.attribute in asked)

        snapshot = product.model_dump(mode="json", exclude={"raw"})
        built = build_record(
            correlation_id="demo-%04d" % index,
            request_text=request_text,
            constraints=constraints,
            findings=findings,
            schema=schema,
            product_id=product.id,
            product_snapshot=snapshot,
            snapshot_hash=digest(snapshot),
            model_version="none (requirements supplied directly)",
            prompt_version="demo-v1",
        )
        sealed = seal(built, key, prev_hash=previous)
        records.append(sealed)
        previous = sealed.hash

        print(f"[{index}] {request_text}")
        print(f"     product      {product.id}  {product.title}")
        print(f"     decision     {sealed.decision.value.upper()}"
              + (f"  ({', '.join(sealed.decision_reasons)})" if sealed.decision_reasons else ""))
        print(f"     silent on    {', '.join(sealed.completeness) or 'nothing'}")
        for f in findings:
            print(f"       {f.support.value:9s} {f.attribute:14s}"
                  f"{'  ' + ', '.join(r.value for r in f.reasons) if f.reasons else ''}")
        print(f"     hash         {sealed.hash[:32]}...")
        print()

    receipts = out / "receipts.json"
    receipts.write_text("[" + ",".join(r.model_dump_json() for r in records) + "]",
                        encoding="utf-8")
    key_file = out / "public_key.txt"
    key_file.write_text(public_key_hex(key), encoding="utf-8")

    print(f"{len(records)} receipts -> {receipts}")
    print(f"public key    -> {key_file}")
    print()
    print("Verify with none of this code:")
    print(f"  python scripts/verify_receipt.py {receipts} --key $(cat {key_file})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
