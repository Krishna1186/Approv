"""Term comparison — brands, variants, flavours, anything nominal.

Harder than quantity, because "the same brand" is not a well-defined relation. The
listing says "Aashirvaad Select Sharbati Atta 5kg" and the agent says "Aashirvaad".
Those agree. The agent says "Amul Gold" and the listing says "Amul" — those do *not*
disagree, but the listing does not support the claim either, and collapsing that into
either SATISFIED or VIOLATED loses the distinction §2.2 is built on.

So comparison is over token sets, in one direction:

    claim tokens are a subset of evidence tokens  -> SATISFIED
    claim has tokens the evidence does not        -> UNSTATED, claim is more specific
    no tokens shared at all                       -> VIOLATED

Direction matters. Evidence may carry more words than the claim (a title always does)
and the claim is still supported. The reverse is not true: the agent asserting a word
the listing never uses is an unsupported assertion, not a confirmed one.

Known gap, deliberately not fixed here: spelling variants. "Ashirvad" against
"Aashirvaad" shares no tokens and comes back VIOLATED. Fixing that needs the lexicon
from DR 0006, not a fuzzy-match hack — a similarity threshold in this module would be a
tunable that silently decides brand identity, which is exactly the kind of guess §1
forbids on the decision path. Logged in docs/tunables.md as a known limitation.
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
    Finding,
    ReasonCode,
    Repair,
    Resolution,
    Support,
    Term,
)

_SPLIT = re.compile(r"[^\w]+", re.UNICODE)

# Words that carry no identity. Kept deliberately tiny: every entry is a decision that
# two different strings mean the same thing, and a long list here quietly becomes a
# semantic model nobody reviewed.
_NOISE = frozenset({"the", "a", "an", "of", "and", "with", "pack", "packet"})


def _tokens(text: str) -> frozenset[str]:
    # NFKD then ASCII-fold so "Nestlé" and "Nestle" agree. This is normalisation, not
    # similarity: it removes an encoding difference rather than guessing at meaning.
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    parts = (p for p in _SPLIT.split(folded.lower()) if p)
    return frozenset(p for p in parts if p not in _NOISE)


def compare_term(claim: Claim, evidence: Evidence, spec: AttributeSpec) -> Finding:
    """Compare one nominal claim against one piece of product evidence."""
    if claim.attribute != evidence.attribute:
        raise ValueError(
            f"attribute mismatch: claim is about {claim.attribute!r}, "
            f"evidence is about {evidence.attribute!r} — these should never be paired"
        )

    if not isinstance(claim.value, Term) or not isinstance(evidence.value, Term):
        raise TypeError("compare_term requires Term values on both sides")

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

    claim_tokens = _tokens(claim.value.surface)
    evidence_tokens = _tokens(evidence.value.surface)

    if not claim_tokens or not evidence_tokens:
        return finding(
            Support.UNSTATED, 0.0, Resolution.RESTATE_CLAIM, ReasonCode.UNRESOLVED_TERM
        )

    if claim_tokens <= evidence_tokens:
        reasons: list[ReasonCode] = []
        resolution = Resolution.NONE_NEEDED
        if evidence.certainty is not Certainty.EXACT:
            reasons.append(ReasonCode.LOW_CERTAINTY_SOURCE)
            resolution = Resolution.FIND_BETTER_SOURCE
        return finding(Support.SATISFIED, ceiling, resolution, *reasons)

    if claim_tokens & evidence_tokens:
        # Overlap, but the agent said something the listing does not say. Not a
        # contradiction — an assertion the catalogue cannot back up.
        return finding(
            Support.UNSTATED,
            0.0,
            Resolution.FIND_BETTER_SOURCE,
            ReasonCode.CLAIM_MORE_SPECIFIC,
        )

    return finding(Support.VIOLATED, ceiling, Resolution.PICK_DIFFERENT_PRODUCT)
