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


def _run_start(inner: list[str], outer: list[str]) -> int | None:
    """Where `inner` sits inside `outer` as a contiguous run of whole words, if it does.

    Whole words, contiguous, and strictly shorter, because none of the weaker readings
    survive contact with a catalogue. Substring matching makes "red" a narrowing of
    "shredded". A bare token subset makes "navy blue" a narrowing of "blue navy stripe",
    which reorders the name and so is a different name. Requiring an unbroken run of
    whole words keeps the ordered-identity stance this module opens with, and only ever
    downgrades a VIOLATED to an UNSTATED, which per §2.3 is the safe direction.
    """
    if not inner or len(inner) >= len(outer):
        return None
    for start in range(len(outer) - len(inner) + 1):
        if outer[start:start + len(inner)] == inner:
            return start
    return None


# A qualifier can narrow or it can negate, and the two are opposites. "Black Multi" is a
# kind of black; "sugar free" is the absence of sugar. Treating both as contradiction
# false-flags the first; treating both as unknown clears the second. This is the smallest
# closed set that separates them, and it is deliberately short: anything not listed here
# is treated as a narrowing, which routes to confirm rather than to allow.
#
# "not" and "fake" joined the set when the match above stopped being prefix-only. Both
# negate from in front, so no matcher that only looked rightward could ever reach them,
# and "not Amul" was scored a contradiction for the accidental reason that the prefix
# test failed rather than because the word was read. `test_nominal_overlap_is_not_identity`
# had asserted the right answer all along and was passing for the wrong reason.
_NEGATIONS = frozenset({"free", "less", "without", "non", "no", "not", "zero", "anti",
                        "sub", "alternative", "substitute", "replacement", "compatible",
                        "style", "inspired", "imitation", "faux", "fake", "dupe"})


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
    claimed_words, observed_words = claimed.split(), observed.split()

    # The qualifier can sit on either side of the word it qualifies, and an earlier
    # version of this function only looked for it on the right. Measured on the
    # 10 September study: "Orange" against a listing saying "Orange chalk stripe" was
    # correctly UNVERIFIED, while "blue" against "Medium wash blue" — the same relation
    # with English's other adjective order — was reported as a contradiction, and it was
    # a contradiction about the one candidate on the shelf that satisfied the request.
    # No negation guard on this branch: extra words in the *claim* mean the listing is
    # silent about them, never that it denies them.
    if _run_start(observed_words, claimed_words) is not None:
        return finding(Support.UNSTATED, 0.0, Resolution.FIND_BETTER_SOURCE,
                       ReasonCode.CLAIM_MORE_SPECIFIC)
    # "Black" against a listing that says "Black Multi" is not the same kind of answer as
    # "Navy" against "Black", and returning VIOLATED for both asserts a contradiction we
    # cannot support. The listing names something narrower than the request; whether it
    # satisfies the shopper is exactly what we do not know. Per §2.3 an unknown routes to
    # confirm rather than to allow, so the safe direction is to say we could not tell.
    # Extra words in the *listing* are an assertion by the merchant, so here the negation
    # guard applies — and it applies to the words on both sides of the match, because
    # "faux leather" negates "leather" from in front.
    start = _run_start(claimed_words, observed_words)
    if start is not None:
        extra = set(observed_words[:start]) | set(observed_words[start + len(claimed_words):])
        if not extra & _NEGATIONS:
            return finding(Support.UNSTATED, 0.0, Resolution.FIND_BETTER_SOURCE,
                           ReasonCode.LISTING_MORE_SPECIFIC)
    # The listing contradicts the request, so the listing is the thing to change.
    # RESTATE_CLAIM renders as "restate the claim in terms the listing publishes", which
    # asks the agent to rewrite what the customer wanted until it matches the wrong
    # product. Quantity, count and numeric all say PICK_DIFFERENT_PRODUCT here; nominal
    # was the outlier, and it is the advice a size mismatch emits, so it was the advice
    # given most often. Measured 9 September: the report caught 38 of 40 wrong picks and
    # the agent still ended up wrong in 20 of them.
    return finding(Support.VIOLATED, ceiling, Resolution.PICK_DIFFERENT_PRODUCT)
