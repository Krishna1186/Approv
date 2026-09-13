#!/usr/bin/env python3
"""Score the gate as a classifier. No agent, no model call, no rate limit.

    python scripts/score_gate.py --pack PACK --constraints WORK/constraints.json

Every accuracy number this project has published measures a different mechanism from the
one it sells. The forked study shows an agent a report and asks whether its second answer
changes; that is persuasion, it never calls `evaluator.decide`, and it is bounded by how
stubborn the model is and by an n of 46 whose noise floor is about +-8 pp. The product
claim is that a deterministic function refuses a wrong purchase without asking the agent
anything. That function has never been scored.

It also never needed an LLM at evaluation time. `check_constraints` and `decide` are pure,
and the answer key is computed from published merchant fields by code that imports nothing
from `approv.algebra`. So the one measurement that validates the gate is the one that was
being rate-limited, and it can run on every commit over thousands of pairs.

**The constraints must come from the extractor, not from the answer key.** Feeding the
generator's own spec back in would make the gate and the key the same computation over the
same fields, and the matrix would come back near-perfect having measured nothing. The
error surface worth measuring is the model's reading of the request propagated through the
operators, so extraction is done once per request and then paired against many products.

Three outcomes against two truths, because `confirm` is not a third kind of error, it is a
different cost. Confirming a product that does not satisfy the request is a catch.
Confirming one that does is a nuisance that costs a sale. Collapsing them hides the
operating point that section 2.6 exists to expose.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.harness.coverage import wilson
from approv.harness.review import check_product
from approv.harness.shopping import Inventory, ShoppingCase, digest
from approv.receipts.record import build_record
from approv.criticality import GUARANTEED
from approv.types.core import Decision, Finding, UnreadPolicy, dropped_requirement


def pairs_for(task, products_by_id, families, rng, near=8, far=8):
    """One request against the products worth asking about.

    Three populations, because a classifier scored only on what retrieval happened to
    surface is scored on a biased sample. `gold` is what the key accepts. `near` is the
    same product in a different variant, which is the failure this whole project was built
    for and which no keyword ranker separates from the answer. `far` is a different product
    entirely, and is the easy half — reported separately so it cannot flatter the total.
    """
    gold = [a["product_id"] for a in task["gold"]["accepted"] if a["product_id"] in products_by_id]
    seen = set(gold)
    out = [(pid, "gold") for pid in gold]

    for pid in gold:
        product = products_by_id[pid]
        key = (product.details.get("brand", ""), product.details.get("title", ""))
        siblings = [p.id for p in families.get(key, []) if p.id not in seen]
        rng.shuffle(siblings)
        for sibling in siblings[:near]:
            seen.add(sibling)
            out.append((sibling, "near"))

    everything = [pid for pid in products_by_id if pid not in seen]
    for pid in rng.sample(everything, min(far, len(everything))):
        out.append((pid, "far"))
    return out


def failing_attributes(task, product):
    """Which of the key's required attributes this product does not meet.

    The same published-field comparison the answer key itself uses, so "wrong product"
    can be attributed to the attribute that made it wrong. Without that the exposure
    split below cannot be computed: a record almost always carries some guaranteed
    finding about an attribute that is fine, and asking only whether the record contains
    the word "guaranteed" counts every one of those as a payout.
    """
    spec = dict(task["gold"].get("spec") or {})
    if task["gold"].get("kind"):
        spec["kind"] = task["gold"]["kind"]
    detail = product.details
    failing = set()
    for key, wanted in spec.items():
        if key == "price_lte":
            price = (detail.get("price") or "").split()[0] or "0"
            try:
                if float(price) > float(wanted):
                    failing.add("price")
            except ValueError:
                failing.add("price")
            continue
        attribute = {"kind": "product_type"}.get(key, key)
        got = (detail.get(attribute) or "").strip().lower()
        if attribute == "availability":
            got = got.replace(" ", "_")
        if got != str(wanted).strip().lower():
            failing.add(attribute)
    return failing


def unread_notes(notes, definition):
    """Which interpretation notes mean the request was not fully read. DR 0021.

    Two definitions were live at once and both fed the verification floor, which is the
    decision path, so a number produced under one did not mean what a number produced
    under the other said. `dropped_requirement` is the narrower and the honest one: it
    asks whether a *checkable requirement* went unchecked rather than whether the model
    wrote anything down at all.
    """
    if definition == "all":
        return tuple(notes)
    return tuple(n for n in notes if dropped_requirement(n))


def truth(task, product_id):
    """Does this product satisfy the request, per the answer key alone.

    The key is the generator's spec applied to published fields by code importing nothing
    from `approv.algebra`. It is the only thing in this script that is allowed to know the
    right answer, and the gate never sees it.
    """
    return any(a["product_id"] == product_id for a in task["gold"]["accepted"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--constraints", required=True,
                        help="extractor output; the key's own spec must never be used here")
    parser.add_argument("--split", default="heldout")
    parser.add_argument("--near", type=int, default=8)
    parser.add_argument("--far", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--out", default="")
    parser.add_argument("--unread-policy", choices=("withdraw", "escalate", "ignore"),
                        default="withdraw",
                        help="what a request we did not finish reading does to the answer. "
                             "DR 0022: 'withdraw' authorises and withdraws the guarantee, "
                             "'escalate' fails the floor and confirms, 'ignore' guarantees "
                             "anyway. The last two are kept so the table reproduces.")
    parser.add_argument("--unread", choices=("dropped", "all"), default="dropped",
                        help="which interpretation notes count as an unread request. "
                             "'all' is every note; 'dropped' is only those meaning a "
                             "checkable requirement went unchecked. DR 0021.")
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    inventory = Inventory.model_validate(pack["inventory"])
    schema = inventory.category_schema
    by_id = {p.id: p for p in inventory.products}
    families = defaultdict(list)
    for product in inventory.products:
        families[(product.details.get("brand", ""), product.details.get("title", ""))].append(product)

    extracted = json.loads(Path(args.constraints).read_text(encoding="utf-8"))
    tasks = {t["case"]["id"]: t for t in pack["tasks"] if t["split"] == args.split}
    rng = random.Random(args.seed)

    # decision x truth x population
    matrix: Counter = Counter()
    coverage: Counter = Counter()
    exposure: Counter = Counter()
    exposure_attrs: Counter = Counter()
    rows = []
    skipped = 0

    for cid, task in sorted(tasks.items()):
        record = extracted.get(cid)
        if not record or not record.get("constraints"):
            skipped += 1
            continue
        case = ShoppingCase.model_validate({
            **task["case"],
            "constraints": record["constraints"],
            "interpretation_notes": record.get("notes", []),
            "requested_units": record.get("requested_units"),
            "quantity_scope": record.get("quantity_scope", "per_sale_unit"),
        })
        for pid, population in pairs_for(task, by_id, families, rng, args.near, args.far):
            product = by_id[pid]
            report = check_product(case, product, schema)
            findings = tuple(Finding.model_validate(f) for f in report["findings"])
            snapshot = product.model_dump(mode="json", exclude={"raw"})
            built = build_record(
                correlation_id="%s:%s" % (cid, pid), request_text=case.request,
                constraints=case.constraints, findings=findings, schema=schema,
                product_id=pid, product_snapshot=snapshot, snapshot_hash=digest(snapshot),
                model_version="offline", prompt_version="score-gate-v1",
                unread=unread_notes(case.interpretation_notes, args.unread),
                unread_policy=UnreadPolicy(args.unread_policy))
            satisfies = truth(task, pid)
            matrix[(built.decision.value, satisfies, population)] += 1
            coverage.update(built.coverage)
            # A false allow that is out of coverage costs nothing — we authorised it and
            # promised nothing about it. One that is guaranteed costs a payout. Property 6
            # says those land on different balance sheets, so counting them together
            # hides the only number the guarantee is priced against.
            if built.decision is Decision.ALLOW and not satisfies:
                covered = {f.attribute: c for f, c in zip(built.findings, built.coverage)}
                broke = failing_attributes(task, product)
                paid = any(covered.get(a) == GUARANTEED for a in broke)
                exposure["guaranteed" if paid else "uncovered"] += 1
                exposure_attrs.update(
                    "%s:%s" % (a, covered.get(a, "not_checked")) for a in broke)
            rows.append({"case": cid, "product": pid, "population": population,
                         "decision": built.decision.value, "satisfies": satisfies,
                         "coverage": list(built.coverage),
                         "reasons": list(built.decision_reasons)})

    total = len(rows)
    if not total:
        print("no pairs scored; were constraints extracted?")
        return 1

    def count(decision=None, satisfies=None, population=None):
        return sum(n for (d, s, p), n in matrix.items()
                   if (decision is None or d == decision)
                   and (satisfies is None or s == satisfies)
                   and (population is None or p == population))

    def rate(num, den):
        if not den:
            return "     n/a"
        low, high = wilson(num, den)
        return "%5.1f%% [%.1f, %.1f]" % (100 * num / den, 100 * low, 100 * high)

    print("Gate scored as a classifier. No agent, no model call at evaluation time.")
    print("pack        %s" % args.pack)
    print("constraints %s (extractor output, never the answer key)" % args.constraints)
    print("unread      definition=%s (DR 0021), policy=%s (DR 0022)"
          % (args.unread, args.unread_policy))
    print("cases %d scored, %d skipped for no extracted requirements; %d pairs"
          % (len(tasks) - skipped, skipped, total))
    print()
    print("%-10s %8s %8s %8s   %s" % ("", "allow", "confirm", "refuse", "n"))
    for satisfies, label in ((True, "satisfies"), (False, "does not")):
        den = count(satisfies=satisfies)
        print("%-10s %8d %8d %8d   %d" % (label, count("allow", satisfies),
                                          count("confirm", satisfies),
                                          count("refuse", satisfies), den))
    print()
    bad = count(satisfies=False)
    good = count(satisfies=True)
    print("FALSE ALLOW  (wrong product authorised)      %s  of %d" % (rate(count("allow", False), bad), bad))
    print("FALSE REFUSE (right product blocked)         %s  of %d" % (rate(count("refuse", True), good), good))
    print("caught       (wrong product refused)         %s" % rate(count("refuse", False), bad))
    print("escalated    (wrong product confirmed)       %s" % rate(count("confirm", False), bad))
    print("nuisance     (right product confirmed)       %s" % rate(count("confirm", True), good))
    print("clean allow  (right product authorised)      %s" % rate(count("allow", True), good))
    print()
    total_findings = sum(coverage.values())
    print("coverage over %d findings — what the record actually promises (property 6)"
          % total_findings)
    for label in ("guaranteed", "refused", "out_of_coverage"):
        print("  %-16s %s" % (label, rate(coverage[label], total_findings)))
    print()
    false_allows = exposure["guaranteed"] + exposure["uncovered"]
    allows = count("allow")
    print("false allows split by exposure — %d total" % false_allows)
    print("  guaranteed (a payout)      %d" % exposure["guaranteed"])
    print("  out of coverage (no cost)  %d" % exposure["uncovered"])
    if exposure_attrs:
        print("  the attribute that made it wrong, and what we promised about it:")
        for label, n in exposure_attrs.most_common(8):
            print("    %-34s %d" % (label, n))
    # The number a guarantee is priced against, and it needs its denominator stated
    # rather than inferred. A payout can only happen on a transaction we authorised, so
    # the rate is per authorisation; the per-pair rate is given too because the two
    # differ by an order of magnitude and quoting the wrong one understates the price.
    print("  payout rate  per authorised transaction  %s  of %d allows"
          % (rate(exposure["guaranteed"], allows), allows))
    print("  payout rate  per pair scored             %s  of %d pairs"
          % (rate(exposure["guaranteed"], total), total))
    print()
    print("by population — near-misses are the failure this exists for; far pairs are easy")
    for population in ("gold", "near", "far"):
        den_bad = count(satisfies=False, population=population)
        den_good = count(satisfies=True, population=population)
        print("  %-5s n=%-5d false-allow %s   false-refuse %s"
              % (population, count(population=population),
                 rate(count("allow", False, population), den_bad),
                 rate(count("refuse", True, population), den_good)))

    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print("\nper-pair rows -> %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
