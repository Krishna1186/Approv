#!/usr/bin/env python3
"""Score the extractor against the generator's spec. No model call at evaluation time.

    python scripts/score_extraction.py --pack PACK --constraints WORK/constraints.json

Every gate number is conditional on this and it has never been measured. The gate compares
recorded requirements against published fields; if a requirement was never recorded the
gate is not wrong, it is blind, and the two are indistinguishable from inside the engine.
The one false allow in the first gate scoring was exactly that.

This is not the model grading itself. The request text was generated *from* the spec by
code; the extractor then reads the text back with a model and has to recover the spec.
Two independent paths, one of which cannot see the other, which is what makes the
comparison meaningful — the same reason the answer key is admissible under section 4.

Three things are counted separately, because they have different costs:

  recall     the spec said it and the extractor recorded it. A miss makes the gate blind
             on that attribute, and blind reads as `allow`.
  fidelity   recorded with the value the spec actually stated, under the same identity key
             the operators use. A wrong value is worse than a miss: it is checkable and
             checks the wrong thing.
  invention  recorded an attribute the spec never stated. Per DR 0005 an agent-fabricated
             constraint is its own failure mode, and here it would refuse a good product.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.algebra.term import normalize_term
from approv.harness.coverage import wilson

# The spec is the generator's vocabulary; constraints are the schema's. `kind` is the
# shopper's word for the thing and lands in product_type; `price_lte` is a bound whose
# attribute is simply price.
SPEC_TO_ATTRIBUTE = {"kind": "product_type", "price_lte": "price"}


def spec_of(task):
    spec = dict(task["gold"].get("spec") or {})
    if task["gold"].get("kind"):
        spec["kind"] = task["gold"]["kind"]
    return {SPEC_TO_ATTRIBUTE.get(k, k): v for k, v in spec.items()}


def recorded_value(constraint):
    """The surface an operator would compare, or None for a bound.

    A bound is an inequality and its fidelity is not a string comparison, so it is scored
    on recall only rather than pretended to be checked.
    """
    value = constraint.get("value") or {}
    return value.get("surface") if value.get("kind") == "term" else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--constraints", required=True)
    parser.add_argument("--split", default="heldout")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    tasks = {t["case"]["id"]: t for t in pack["tasks"] if t["split"] == args.split}
    extracted = json.loads(Path(args.constraints).read_text(encoding="utf-8"))

    per_attribute: dict[str, Counter] = {}
    invented, rows = Counter(), []
    cases = 0

    for cid, record in sorted(extracted.items()):
        task = tasks.get(cid)
        if task is None:
            continue
        cases += 1
        spec = spec_of(task)
        got = {c["attribute"]: c for c in record.get("constraints", [])}

        for attribute, wanted in spec.items():
            counts = per_attribute.setdefault(attribute, Counter())
            counts["stated"] += 1
            constraint = got.get(attribute)
            if constraint is None:
                counts["missed"] += 1
                rows.append({"case": cid, "attribute": attribute, "outcome": "missed",
                             "wanted": str(wanted), "got": None})
                continue
            counts["recorded"] += 1
            surface = recorded_value(constraint)
            if surface is None:
                counts["unscored_value"] += 1
                continue
            if normalize_term(surface) == normalize_term(str(wanted)):
                counts["faithful"] += 1
            else:
                counts["wrong_value"] += 1
                rows.append({"case": cid, "attribute": attribute, "outcome": "wrong_value",
                             "wanted": str(wanted), "got": surface})

        for attribute in got:
            if attribute not in spec:
                invented[attribute] += 1
                rows.append({"case": cid, "attribute": attribute, "outcome": "invented",
                             "wanted": None, "got": recorded_value(got[attribute])})

    if not cases:
        print("no cases scored")
        return 1

    def rate(num, den):
        if not den:
            return "     n/a"
        low, high = wilson(num, den)
        return "%5.1f%% [%.1f, %.1f]" % (100 * num / den, 100 * low, 100 * high)

    print("Extractor scored against the generator's spec. No model call at evaluation time.")
    print("pack        %s" % args.pack)
    print("constraints %s" % args.constraints)
    print("%d cases\n" % cases)

    print("%-14s %6s  %-22s %-22s" % ("attribute", "stated", "recall", "fidelity | recorded"))
    totals = Counter()
    for attribute in sorted(per_attribute):
        counts = per_attribute[attribute]
        totals.update(counts)
        scored = counts["faithful"] + counts["wrong_value"]
        print("%-14s %6d  %-22s %-22s" % (
            attribute, counts["stated"],
            rate(counts["recorded"], counts["stated"]),
            rate(counts["faithful"], scored)))
    scored = totals["faithful"] + totals["wrong_value"]
    print("%-14s %6d  %-22s %-22s" % ("ALL", totals["stated"],
                                      rate(totals["recorded"], totals["stated"]),
                                      rate(totals["faithful"], scored)))
    print()
    # A bound is recorded but its value is not string-compared, so it can never be counted
    # faithful. Leaving those in the denominator scored the extractor down for every price
    # limit it got right — 89.2% against a true 94.6% on the first run of this script.
    end_to_end = totals["stated"] - totals["unscored_value"]
    print("end to end (stated, recorded and faithful)  %s of %d"
          % (rate(totals["faithful"], end_to_end), end_to_end))
    print("  excludes %d bound(s), recorded but not value-compared" % totals["unscored_value"])
    print("invented (recorded, never stated)           %d across %d cases  %s"
          % (sum(invented.values()), cases, dict(invented) or "none"))

    wrong = [r for r in rows if r["outcome"] == "wrong_value"]
    if wrong:
        print("\nwrong values — checkable, and checking the wrong thing:")
        for row in wrong[:12]:
            print("  %-22s %-14s spec %-24r got %r"
                  % (row["case"], row["attribute"], row["wanted"], row["got"]))
    missed = [r for r in rows if r["outcome"] == "missed"]
    if missed:
        print("\nmissed — the gate is blind here, and blind reads as allow:")
        for row in missed[:12]:
            print("  %-22s %-14s spec %r" % (row["case"], row["attribute"], row["wanted"]))

    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print("\nper-attribute rows -> %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
