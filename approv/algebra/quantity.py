"""Quantity comparison.

DR 0002 puts this layer between `semantic/` and `evaluator/`: it takes typed values and
returns a per-attribute ternary. It calls no model, reads no I/O, and makes no decision —
`allow`/`confirm`/`refuse` is the evaluator's job, not this module's.

The operator is deliberately small. By the time it runs, extraction has either produced a
`Quantity` with a real unit or it has produced nothing. An ambiguous "1x1x1" never arrives
here; it dies upstream. Anything this module cannot do, it says it cannot do — it never
guesses, because the moment an operator guesses, the decision path stops being
deterministic and §1's central claim stops being true.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from approv.types.core import (
    AttributeSpec,
    Certainty,
    CheckKind,
    Claim,
    Evidence,
    Finding,
    Quantity,
    ReasonCode,
    Repair,
    Resolution,
    Support,
)

# Unit -> (dimension, how many base units it is worth).
#
# One canonical base per dimension: gram, millilitre, millimetre. Conversion is a lookup
# and a multiply, and every factor here is an exact definition rather than a measurement
# (1 lb IS 453.59237 g, by international agreement), so Decimal arithmetic stays exact.
#
# Written by hand rather than pulled from a units library on purpose: this sits on the
# decision path, and a table you can read in thirty seconds is defensible to a merchant's
# engineer in a way that a twenty-thousand-line dependency is not.
_UNITS: dict[str, tuple[str, Decimal]] = {
    "mg": ("mass", Decimal("0.001")),
    "g": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "oz": ("mass", Decimal("28.349523125")),
    "lb": ("mass", Decimal("453.59237")),
    "ml": ("volume", Decimal("1")),
    "cl": ("volume", Decimal("10")),
    "l": ("volume", Decimal("1000")),
    "us_fl_oz": ("volume", Decimal("29.5735295625")),
    "imperial_fl_oz": ("volume", Decimal("28.4130625")),
    "mm": ("length", Decimal("1")),
    "cm": ("length", Decimal("10")),
    "m": ("length", Decimal("1000")),
    "in": ("length", Decimal("25.4")),
    "ft": ("length", Decimal("304.8")),
}

# How much confidence the *source* of the evidence permits, at most.
#
# DR 0016 §4: these are a ranking at v1, not calibrated probabilities. Calibration needs
# thousands of observed outcomes and we have none. They order claims by how much scrutiny
# they deserve; they must not be published as probabilities until §4.6 can be satisfied.
#
# Ceiling comes from Certainty and not from Liability, because the two axes answer
# different questions: certainty is "did we read it right", liability is "who owes a
# remedy if it is wrong". Liability is carried on the record and priced elsewhere.
_CEILING_BY_CERTAINTY: dict[Certainty, float] = {
    Certainty.EXACT: 1.0,
    Certainty.PARSED: 0.9,
    Certainty.INFERRED: 0.6,
}


def _render(quantity: Quantity) -> str:
    # normalize() strips trailing zeros but returns 5E+3 for 5000, which is unreadable in
    # a message an agent or a human is meant to act on. The 'f' format forces plain
    # notation back.
    number = format(quantity.magnitude, "f")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return f"{number} {quantity.unit}"


def _to_base(quantity: Quantity) -> Decimal | None:
    entry = _UNITS.get(quantity.unit.lower())
    if entry is None:
        return None
    dimension, factor = entry
    if dimension != quantity.dimension.value:
        raise ValueError("unit contradicts declared dimension")
    with localcontext() as context:
        context.prec = 80
        return quantity.magnitude * factor


def compare_quantity(claim: Claim, evidence: Evidence, spec: AttributeSpec) -> Finding:
    """Compare one quantity claim against one piece of product evidence.

    Raises on malformed input rather than returning a tidy answer. A caller that pairs a
    weight claim with a volume field has a bug, and a bug that returns something plausible
    is a bug that ships.
    """
    if claim.attribute != evidence.attribute:
        raise ValueError(
            f"attribute mismatch: claim is about {claim.attribute!r}, "
            f"evidence is about {evidence.attribute!r} — these should never be paired"
        )

    if not isinstance(claim.value, Quantity) or not isinstance(evidence.value, Quantity):
        raise TypeError("compare_quantity requires Quantity values on both sides")
    if spec.name != claim.attribute or spec.dimension != claim.value.dimension:
        raise ValueError("claim does not match attribute specification")

    ceiling = _CEILING_BY_CERTAINTY[evidence.certainty]
    claimed_text = _render(claim.value)
    observed_text = _render(evidence.value)

    def finding(
        support: Support,
        confidence: float,
        resolution: Resolution,
        *reasons: ReasonCode,
    ) -> Finding:
        return Finding(
            check=CheckKind.GROUNDING,
            attribute=spec.name,
            criticality=spec.criticality,
            support=support,
            confidence=confidence,
            ceiling=ceiling,
            reasons=reasons,
            repair=Repair(
                resolution=resolution,
                attribute=spec.name,
                claimed=claimed_text,
                observed=observed_text,
                observed_field=evidence.field_name,
            ),
            claim=claim,
            evidence=(evidence,),
        )

    claim_base = _to_base(claim.value)
    evidence_base = _to_base(evidence.value)

    # A unit we have never seen is not a mismatch. "sachet" and "pouch" appear in real
    # feeds; the honest answer is that no comparison was run. The agent can act on this —
    # a listing that publishes a standard unit is comparable.
    if claim_base is None or evidence_base is None:
        return finding(
            Support.UNSTATED,
            0.0,
            Resolution.PICK_DIFFERENT_PRODUCT,
            ReasonCode.UNRESOLVED_TERM,
        )

    # Mass against volume needs a density we do not have. Returning False here would be a
    # lie: we are not saying the product is wrong, we are saying we could not look.
    if claim.value.dimension is not evidence.value.dimension:
        return finding(
            Support.UNSTATED,
            0.0,
            Resolution.RESTATE_CLAIM,
            ReasonCode.INCOMMENSURABLE,
        )

    # Both sides are now in the same base unit, so this is ordinary arithmetic. Whatever
    # doubt exists is doubt about the reading, never about the comparison — which is why
    # confidence is exactly the ceiling and this operator adds no uncertainty of its own.
    with localcontext() as context:
        context.prec = 80
        difference = abs(claim_base - evidence_base)
        allowed = abs(evidence_base) * spec.tolerance

    if difference > allowed:
        return finding(
            Support.VIOLATED,
            ceiling,
            Resolution.PICK_DIFFERENT_PRODUCT,
        )

    # Everything below here matched. Anything still worth telling the agent is about the
    # *source*, not the number — which is the whole point of separating the two axes.
    reasons: list[ReasonCode] = []
    resolution = Resolution.NONE_NEEDED

    if difference != 0:
        reasons.append(ReasonCode.WITHIN_TOLERANCE)

    if evidence.certainty is not Certainty.EXACT:
        reasons.append(ReasonCode.LOW_CERTAINTY_SOURCE)
        resolution = Resolution.FIND_BETTER_SOURCE

    return finding(Support.SATISFIED, ceiling, resolution, *reasons)
