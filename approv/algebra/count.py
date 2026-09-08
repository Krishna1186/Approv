"""Count comparison — pack sizes, unit counts, "pack of 6".

The simplest operator, and the one guarding the failure §6 calls the dominant one in
first-party grocery catalogues: pack and pair confusion.

No tolerance here, deliberately. A quantity may be 4.99 kg because a feed rounded; a
pack is never 5.99 items. Applying a percentage margin to an integer count would let a
pack of 6 satisfy a claim of 6 and also a claim of 5 at large enough numbers, which is
exactly the confusion this operator exists to catch.

What this operator does *not* do is decide whether "6" means six units or one pack of
six. That is an attribute-naming problem — `unit_count` against `pack_count` — and it is
caught upstream by the attribute check, not here. Two different questions must not be
answered by one comparison.
"""

from __future__ import annotations

from approv.types.core import (
    AttributeSpec,
    Certainty,
    CheckKind,
    Claim,
    Count,
    Dimension,
    Evidence,
    Finding,
    ReasonCode,
    Repair,
    Resolution,
    Support,
)


def compare_count(claim: Claim, evidence: Evidence, spec: AttributeSpec) -> Finding:
    """Compare one integer count claim against one piece of product evidence."""
    if claim.attribute != evidence.attribute:
        raise ValueError(
            f"attribute mismatch: claim is about {claim.attribute!r}, "
            f"evidence is about {evidence.attribute!r} — these should never be paired"
        )

    if not isinstance(claim.value, Count) or not isinstance(evidence.value, Count):
        raise TypeError("compare_count requires Count values on both sides")
    if spec.name != claim.attribute or spec.dimension is not Dimension.COUNT:
        raise ValueError("claim does not match attribute specification")

    from approv.algebra.quantity import _CEILING_BY_CERTAINTY

    ceiling = _CEILING_BY_CERTAINTY[evidence.certainty]

    reasons: list[ReasonCode] = []
    if claim.value.n == evidence.value.n:
        support = Support.SATISFIED
        resolution = Resolution.NONE_NEEDED
        if evidence.certainty is not Certainty.EXACT:
            reasons.append(ReasonCode.LOW_CERTAINTY_SOURCE)
            resolution = Resolution.FIND_BETTER_SOURCE
    else:
        support = Support.VIOLATED
        resolution = Resolution.PICK_DIFFERENT_PRODUCT

    return Finding(
        check=CheckKind.GROUNDING,
        attribute=spec.name,
        criticality=spec.criticality,
        support=support,
        confidence=ceiling,
        ceiling=ceiling,
        reasons=tuple(reasons),
        repair=Repair(
            resolution=resolution,
            attribute=spec.name,
            claimed=str(claim.value.n),
            observed=str(evidence.value.n),
            observed_field=evidence.field_name,
        ),
        claim=claim,
        evidence=(evidence,),
    )
