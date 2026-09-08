"""Nominal identity from whole normalized names, explicit aliases or trusted IDs.

Token containment is useful for search but cannot establish product identity.
"""
from __future__ import annotations

import re
import unicodedata

from approv.types.core import (
    AttributeSpec,
    Certainty,
    CheckKind,
    Claim,
    Evidence,
    Dimension,
    Finding,
    ReasonCode,
    Repair,
    Resolution,
    Support,
    Term,
)

def normalize_term(text: str) -> str:
    """Conservative ordered identity key. Preserve negation and non-Latin marks."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    chars = []
    for char in folded:
        if "LATIN" in unicodedata.name(char, ""):
            chars.extend(c for c in unicodedata.normalize("NFKD", char)
                         if not unicodedata.combining(c))
        else:
            chars.append(char)
    return " ".join("".join(c if c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M") else " " for c in chars).split())


def _tokens(text: str) -> frozenset[str]:
    # Search/diagnostic helper only. Token sets never establish entity identity.
    return frozenset(normalize_term(text).split())


def compare_term(claim: Claim, evidence: Evidence, spec: AttributeSpec) -> Finding:
    """Compare one nominal claim against one piece of product evidence."""
    if claim.attribute != evidence.attribute:
        raise ValueError(
            f"attribute mismatch: claim is about {claim.attribute!r}, "
            f"evidence is about {evidence.attribute!r} — these should never be paired"
        )

    if not isinstance(claim.value, Term) or not isinstance(evidence.value, Term):
        raise TypeError("compare_term requires Term values on both sides")

    if spec.name != claim.attribute or spec.dimension is not Dimension.NOMINAL:
        raise ValueError("claim does not match attribute specification")

    from approv.algebra.quantity import _CEILING_BY_CERTAINTY

    ceiling = _CEILING_BY_CERTAINTY[evidence.certainty]

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
                claimed=claim.value.surface,
                observed=evidence.value.surface,
                observed_field=evidence.field_name,
            ),
            claim=claim,
            evidence=(evidence,),
        )

    claimed = normalize_term(claim.value.surface)
    observed = normalize_term(evidence.value.surface)
    if not claimed or not observed:
        return finding(Support.UNSTATED, 0.0, Resolution.RESTATE_CLAIM,
                       ReasonCode.UNRESOLVED_TERM)

    # IDs/aliases must come from a trusted, versioned adapter. Never infer aliases by
    # combining words across a list of brands or by accepting a substring of prose.
    if claim.value.node_id and evidence.value.node_id:
        matched = claim.value.node_id == evidence.value.node_id
    else:
        matched = claimed in {observed, *(normalize_term(a) for a in evidence.value.aliases)}
    if matched:
        reasons = () if evidence.certainty is Certainty.EXACT else (ReasonCode.LOW_CERTAINTY_SOURCE,)
        resolution = Resolution.NONE_NEEDED if not reasons else Resolution.FIND_BETTER_SOURCE
        return finding(Support.SATISFIED, ceiling, resolution, *reasons)
    if evidence.certainty is not Certainty.EXACT:
        return finding(Support.UNSTATED, 0.0, Resolution.FIND_BETTER_SOURCE,
                       ReasonCode.UNRESOLVED_TERM, ReasonCode.LOW_CERTAINTY_SOURCE)
    if claimed.startswith(observed + " "):
        return finding(Support.UNSTATED, 0.0, Resolution.FIND_BETTER_SOURCE,
                       ReasonCode.CLAIM_MORE_SPECIFIC)
    return finding(Support.VIOLATED, ceiling, Resolution.RESTATE_CLAIM)
