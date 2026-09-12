"""How much an attribute being wrong actually costs — decided per transaction.

`AttributeSpec.criticality` is one constant per attribute per schema, copied onto every
finding. Hand-authoring that per category does not scale to every kind of product in the
world, and it is wrong even where it is authored: the same colour mismatch is trivial to
one shopper and the reason for the purchase to the next. A table cannot know which.

Three layers replace it, combined by a pure function at comparison time. No model in the
decision path — every signal below is a deterministic feature of text the shopper wrote,
of the merchant's own schema, or of the merchant's own return history.

    1. request-derived   per transaction, needs no data, works today
    2. schema-derived    structural, free, sector-agnostic
    3. returns-calibrated  per merchant x category, calibrated on human returns

Combination is `max`, with one cap and one floor:

    cap    never stated by the shopper -> never HARD, under any circumstance (2.2)
    floor  no signal anywhere          -> SOFT, never HARD

Both defaults run the same way: a missed check costs nothing until it is tested, and a
wrongly-hard check blocks a real sale immediately, so every ambiguity resolves toward not
blocking.

**Criticality maps to coverage, not only to the decision** (property 6, DR 0020). Under a
guarantee a false SOFT costs us a payout and a false HARD costs the merchant a sale, so
the two errors land on different balance sheets and cannot share one threshold. We never
block on a soft mismatch — we decline to insure it. `coverage_of` is that mapping.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from approv.types.core import (
    AttributeSpec, Bound, CategorySchema, Constraint, Criticality, FieldProfile, Money,
    Quantity, Support, Finding,
)

VERSION = "criticality-v1"

_RANK = {Criticality.COSMETIC: 0, Criticality.SOFT: 1,
         Criticality.BOUND: 2, Criticality.HARD: 3}
_BY_RANK = {rank: level for level, rank in _RANK.items()}


def _strongest(*levels: Criticality | None) -> Criticality | None:
    present = [level for level in levels if level is not None]
    return max(present, key=_RANK.get) if present else None


# --------------------------------------------------------------------------------------
# Layer 1 — the shopper's own phrasing
# --------------------------------------------------------------------------------------

# Word-boundary matching throughout. Substring matching makes "not" fire inside "notebook"
# and "only" inside "colonial", which would turn ordinary requests hard at random.
_EMPHASIS = re.compile(
    r"\b(exactly|must|strictly|specifically|definitely|essential|required|"
    r"has to be|have to be|needs? to be|it needs|only)\b", re.I)
# "nothing with nuts" and "nut-free" are the same statement as "no nuts", and a word
# boundary on `no` reaches neither. Missing a negation is the expensive direction: these
# are allergy, safety and compatibility requirements, so a miss has a consequence outside
# the return window. The compound form needs a word in front of "free", which is what
# keeps "free shipping" out.
_NEGATION = re.compile(
    r"(\b(no|not|non|none|nothing|never|without|avoid|except|excluding|"
    r"free from|free of|allergic|allergy|intolerant)\b|\w+[- ]free\b)", re.I)
_HEDGE = re.compile(
    r"\b(prefer|preferably|preferred|ideally|around|roughly|approximately|about|"
    r"something like|or similar|or so|if possible|would be nice|nice to have|open to)\b", re.I)


def request_layer(constraint: Constraint, *, superseded: bool = False) -> Criticality | None:
    """What the shopper's wording says about how much this one purchase depends on it.

    Two signals are worth defending, and a static table is blind to both.

    **Negation.** "no nuts", "not leather", "without parabens". Almost always allergy,
    safety or compatibility. Getting a negation wrong is the failure mode with a
    consequence outside the return window, so it is HARD regardless of category.

    **Correction.** A shopper who bothers to supersede a value has demonstrated they care
    about it — the effort is the signal. The v5 extractor already records this as
    "Superseded, discarded: <value> (<attribute>)", so it is read from there rather than
    re-derived; `superseded_attributes` parses those notes.

    Everything else is ordinary: emphasis is hard, a hedge is soft, a bound is a bound,
    and a plainly stated value is BOUND — checkable and worth honouring, but not worth
    refusing a sale over on its own.
    """
    quote = constraint.raw_text or ""
    bounded = isinstance(constraint.value, Bound)
    # A negation over a bound is the bound's own direction, not a safety exclusion.
    # "Nothing over $305" is price <= 305, and the word that makes it a negation is the
    # same word that makes it a cap — the operator has already consumed it. Escalating it
    # to HARD reads a budget as an allergy, and it fired on 7 of 34 cases the first time
    # this lexicon was widened. A genuine exclusion ("no nuts") carries a term, not a bound.
    if not bounded and _NEGATION.search(quote):
        return Criticality.HARD
    if superseded:
        return Criticality.HARD
    if _EMPHASIS.search(quote):
        return Criticality.HARD
    # A hedge is checked before the value's own type: "around 500 g" is still a hedge, and
    # the shopper saying "roughly" is a stronger statement about their tolerance than the
    # fact that they happened to use a number.
    if _HEDGE.search(quote):
        return Criticality.SOFT
    # A constraint existing at all means the shopper stated the attribute, so it floors at
    # BOUND whether or not the quote survived. Returning None here instead would collapse
    # "stated, but the channel did not preserve the wording" into "never stated", and only
    # the second earns the §2.2 exemption — a protocol that drops quotes must not also
    # drop the shopper's requirements.
    return Criticality.BOUND


_SUPERSEDED = re.compile(r"^Superseded, discarded:\s*.*\(([^)]+)\)\s*$", re.I)


def superseded_attributes(notes: Iterable[str]) -> frozenset[str]:
    """Attributes the shopper corrected, read off the extractor's own notes."""
    found = set()
    for note in notes or ():
        match = _SUPERSEDED.match(str(note).strip())
        if match:
            found.add(match.group(1).strip())
    return frozenset(found)


# --------------------------------------------------------------------------------------
# Layer 2 — the merchant's own merchandising
# --------------------------------------------------------------------------------------


def schema_layer(attribute: str, profiles: Iterable[FieldProfile], *,
                 in_floor: bool = False) -> Criticality | None:
    """What the merchant's catalogue structure says customers choose on.

    If they made an attribute a **variant axis** — a separate SKU per size or per colour —
    they have already decided it is a thing customers pick between, and they pay for that
    decision in inventory. Nobody carries twelve SKUs of an attribute nobody selects on.
    That is a merchandising judgement we get for free, in every catalogue on every
    platform, without asking anyone anything.

    An attribute that appears only in description prose is the opposite signal: published,
    but not structured enough to sell on.
    """
    # The verification floor is a different claim from either of those: it says this
    # category cannot be checked at all without the attribute. That is about whether a
    # comparison is possible, not about how much the shopper cares, so it survives the
    # per-transaction layers. Letting it fall to SOFT would mean an unmet precondition
    # stopped blocking, which is "unknown authorises" by a side door.
    if in_floor:
        return Criticality.BOUND
    relevant = [p for p in profiles if attribute in p.attributes]
    if not relevant:
        return None
    if any(p.is_variant_axis for p in relevant):
        return Criticality.BOUND
    if all(p.is_advice for p in relevant):
        return Criticality.SOFT
    return Criticality.SOFT


# --------------------------------------------------------------------------------------
# Layer 3 — the merchant's own return history
# --------------------------------------------------------------------------------------


def calibrate_returns(
    pairs: Iterable[tuple[Mapping[str, object], Mapping[str, object]]],
    *,
    prior: Mapping[str, float] | None = None,
    prior_weight: float = 5.0,
) -> dict[str, float]:
    """Differ-rate per attribute, from return-and-reorder pairs.

    **When a customer returns item A and reorders item B, the attributes that differ
    between A and B are the attributes that mattered.** No labels, no reason codes, no
    human judgement — the same instrument as deriving answer keys from published fields
    rather than hand-labelling (§4). A reason code says what someone typed into a dropdown;
    this says what they actually did about it.

    It solves its own cold start. It calibrates on the merchant's existing *human* return
    history, which is plentiful, and applies the result to agentic orders, which are not.

    Low counts are shrunk toward a cross-merchant prior, so a merchant with three returns
    gets the prior rather than a table of 0.0 and 1.0. `prior_weight` is the number of
    pseudo-observations the prior is worth and is a tunable.
    """
    if prior_weight < 0:
        raise ValueError("prior_weight cannot be negative")
    prior = dict(prior or {})
    seen: dict[str, int] = {}
    differed: dict[str, int] = {}

    for returned, reordered in pairs:
        for attribute in set(returned) & set(reordered):
            seen[attribute] = seen.get(attribute, 0) + 1
            if returned[attribute] != reordered[attribute]:
                differed[attribute] = differed.get(attribute, 0) + 1

    rates = {}
    for attribute, total in seen.items():
        base = prior.get(attribute, sum(prior.values()) / len(prior) if prior else 0.0)
        rates[attribute] = ((differed.get(attribute, 0) + prior_weight * base)
                            / (total + prior_weight))
    return rates


def returns_layer(attribute: str, rates: Mapping[str, float] | None,
                  *, hard_at: float = 0.5, bound_at: float = 0.2) -> Criticality | None:
    """Rank by differ-rate. Thresholds are tunables, not constants.

    Returns None below `bound_at` rather than SOFT: no signal is not the same as evidence
    of unimportance, and only the floor may conclude SOFT from an absence.
    """
    if not rates or attribute not in rates:
        return None
    rate = rates[attribute]
    if rate >= hard_at:
        return Criticality.HARD
    if rate >= bound_at:
        return Criticality.BOUND
    return None


# --------------------------------------------------------------------------------------
# Combination
# --------------------------------------------------------------------------------------


def resolve(
    attribute: str,
    *,
    constraint: Constraint | None,
    profiles: Iterable[FieldProfile] = (),
    returns: Mapping[str, float] | None = None,
    superseded: frozenset[str] = frozenset(),
    in_floor: bool = False,
    hard_at: float = 0.5,
    bound_at: float = 0.2,
) -> Criticality:
    """One attribute, one transaction, one answer.

    `max` across the layers, then the cap, then the floor. The cap is §2.2 in force: an
    attribute the shopper never mentioned can never be HARD however the merchant
    merchandises it or however often it drives returns, because silence is nobody's fault
    and refusing a sale over it would attribute a failure to a party that did not fail.
    """
    stated = request_layer(constraint, superseded=attribute in superseded) if constraint else None
    level = _strongest(
        stated,
        schema_layer(attribute, profiles, in_floor=in_floor),
        returns_layer(attribute, returns, hard_at=hard_at, bound_at=bound_at),
    )
    # An explicit hedge caps rather than merely contributing, and this is the second cap
    # for the same reason as the first. Layers 2 and 3 are priors — customers in general
    # choose on this axis, this attribute in general drives returns. Layer 1 is direct
    # evidence about this transaction. `max` treats all three as equally authoritative, so
    # a signal that points *down* cannot survive it: measured on the v3 pack, every one of
    # the hedged requests produced "preferably in Tan" and "around size M or similar" in
    # the quote, `request_layer` correctly returned SOFT, and `max` then raised all of them
    # back to BOUND because colour and size are variant axes. SOFT stayed at zero of 176.
    #
    # A merchant's merchandising cannot outrank the shopper saying "preferably" about the
    # thing being merchandised. `request_layer` returns SOFT only for a hedge, so this
    # tests exactly that case and nothing else.
    if stated is Criticality.SOFT:
        return Criticality.SOFT
    if constraint is None and level is Criticality.HARD:
        level = Criticality.BOUND
    return level if level is not None else Criticality.SOFT


def applied(schema: CategorySchema, constraints: Iterable[Constraint],
            *, returns: Mapping[str, float] | None = None,
            superseded: frozenset[str] = frozenset()) -> dict[str, AttributeSpec]:
    """The schema's attribute specs with criticality resolved for this transaction.

    Returned as specs rather than bare levels because that is what the operators already
    take. Nothing downstream changes: this is a change to how the schema is applied, not
    to how anything compares.
    """
    by_attribute = {c.attribute: c for c in constraints}
    return {
        spec.name: spec.model_copy(update={"criticality": resolve(
            spec.name, constraint=by_attribute.get(spec.name),
            profiles=schema.field_profiles, returns=returns, superseded=superseded,
            in_floor=spec.name in schema.floor)})
        for spec in schema.attributes
    }


# --------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------

GUARANTEED = "guaranteed"
OUT_OF_COVERAGE = "out_of_coverage"
REFUSED = "refused"


def coverage_of(finding: Finding) -> str:
    """What this finding is worth in a dispute. Property 6, DR 0020.

    The point of the mapping is that a soft mismatch is never a blocked sale — it is
    declined insurance. The merchant keeps the order and keeps the risk on that attribute,
    which is the right answer when we have no evidence the shopper cared.

    An unstated attribute is out of coverage even when satisfied, because the record
    cannot claim to have honoured a requirement nobody made.
    """
    if finding.criticality in (Criticality.HARD, Criticality.BOUND):
        if finding.support is Support.VIOLATED:
            return REFUSED
        if finding.support is Support.SATISFIED:
            return GUARANTEED
    return OUT_OF_COVERAGE
