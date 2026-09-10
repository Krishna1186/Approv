"""Turning a recorded request into a predicate over the catalogue's own fields.

Measured on the 10 September study: of 46 held-out cases the agent failed to *find* the
answer on 14 and failed to *pick* it on 7. Finding fails twice as often as picking, and
every repair built so far works on picking.

Finding fails for a reason the data makes plain. The catalogue publishes
`variant.option_size = "9"` and `variant.option_color = "Dark blue"` as exact fields,
and the agent searches a concatenated text blob with bag-of-words scoring. It has to hit
those values by accident, against 33,485 variants in which "9", "blue" and "in stock"
appear constantly.

This is also why an earlier attempt failed. Feeding the extracted constraint *values* to
the ranker as extra query terms made retrieval worse — 41.3% against the agent's own
58.7% — because as terms they are noise: every brand sells a small blue thing that is in
stock. The same values used as *predicates over the fields they came from* are decisive.
Same information, wrong operator.

Approv does not retrieve. It holds the typed constraints and the field profiles, so it is
the only component that can state the predicate; executing it is the catalogue's job.
What this module returns is "here is what satisfies the recorded requirements", which is
the `mark` call site of §2.5 widened from a page of results to the shelf behind them.
"""

from __future__ import annotations

from approv.algebra.runner import check_constraints
from approv.algebra.term import normalize_term
from approv.types.core import (
    Bound, CategorySchema, Constraint, Count, Criticality, Money, Quantity, Support, Term,
)

VERSION = "catalogue-filter-v1"


def _key(value) -> str | None:
    """The exact-match index key for a value, or None when it needs a real comparison.

    Only nominal terms are indexed. A bound is an inequality and a quantity carries units,
    and neither is answerable by equality — those fall through to the operators, which
    already know how to compare them.
    """
    if isinstance(value, Term):
        return normalize_term(value.surface)
    return None


def build_index(products, schema: CategorySchema) -> dict[tuple[str, str], set[str]]:
    """(attribute, normalised value) -> product ids that publish it.

    Built once per catalogue and reused across requests. Without it every request is a
    full pass over every variant running the full comparison, which is correct and far
    too slow to sit in a search path — and §2.6's whole point is that a check nobody can
    afford to run is not deployable.
    """
    known = {spec.name for spec in schema.attributes}
    index: dict[tuple[str, str], set[str]] = {}
    for product in products:
        for item in product.evidence:
            if item.attribute not in known or item.is_advice:
                continue
            key = _key(item.value)
            if key is not None:
                index.setdefault((item.attribute, key), set()).add(product.id)
    return index


def satisfying(
    constraints: tuple[Constraint, ...],
    products,
    schema: CategorySchema,
    *,
    index: dict[tuple[str, str], set[str]] | None = None,
    limit: int = 25,
) -> dict:
    """Every variant whose published fields satisfy every recorded requirement.

    Two stages, and the split is deliberate. The index narrows on the nominal constraints
    by exact value, which is cheap and exact. Whatever survives is then run through the
    ordinary `check_constraints`, so "satisfies" means exactly what it means everywhere
    else in the system — the same operators, the same tolerances, the same source
    profiles. A second, faster notion of satisfaction that disagreed with the first would
    be worse than no filter at all.

    A product is kept only when every HARD and BOUND requirement is SATISFIED. Not
    "nothing contradicts": an UNSTATED field means the catalogue is silent, and per §2.3
    silence never authorises. This function is the optimistic half of the pair — it says
    what does satisfy, and stays quiet about what merely might.
    """
    by_id = {p.id: p for p in products}
    blocking = (Criticality.HARD, Criticality.BOUND)
    required = tuple(c for c in constraints
                     if any(s.name == c.attribute and s.criticality in blocking
                            for s in schema.attributes))
    if not required:
        return {"version": VERSION, "checked": [], "matches": [], "scanned": 0,
                "reason": "no required attributes were recorded, so nothing can be filtered"}

    index = build_index(products, schema) if index is None else index

    candidates: set[str] | None = None
    for constraint in required:
        key = _key(constraint.value)
        if key is None:
            continue                      # inequality; the operators handle it below
        hits = index.get((constraint.attribute, key), set())
        candidates = hits if candidates is None else (candidates & hits)
        if not candidates:
            break

    scanned = by_id.keys() if candidates is None else candidates
    matches = []
    for pid in sorted(scanned):
        product = by_id[pid]
        findings = check_constraints(required, product.evidence, schema)
        wanted = {c.attribute for c in required}
        findings = tuple(f for f in findings if f.attribute in wanted)
        if findings and all(f.support is Support.SATISFIED for f in findings):
            matches.append(pid)
            if len(matches) >= limit:
                break

    return {"version": VERSION,
            "checked": sorted(c.attribute for c in required),
            "matches": matches,
            "scanned": len(scanned),
            "truncated": len(matches) >= limit}


def describe(result: dict, products_by_id: dict) -> str:
    """The filter result as one line an agent can act on.

    Names the variants rather than the predicate. An agent handed
    `option_color == "Dark blue"` has to translate it back into a search; an agent handed
    three ids can select one. The predicate is in `checked` for the record.
    """
    if not result["matches"]:
        return ("No variant in the full catalogue satisfies every recorded requirement ("
                + ", ".join(result["checked"]) + "). The request cannot be filled as "
                "stated; do not substitute.")
    named = []
    for pid in result["matches"][:5]:
        product = products_by_id.get(pid)
        named.append(f"{pid} ({product.title})" if product else pid)
    more = "" if len(result["matches"]) <= 5 else f", and {len(result['matches']) - 5} more"
    return ("Variants satisfying every recorded requirement ("
            + ", ".join(result["checked"]) + "), found by filtering the catalogue's own "
            "fields rather than by search: " + "; ".join(named) + more + ".")
