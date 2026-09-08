"""Tests for term comparison — the three-way outcome that quantity does not have."""

import pytest

from approv.algebra.feedback import explain
from approv.algebra.term import compare_term
from approv.types.core import (
    AttributeSpec,
    Certainty,
    Channel,
    Claim,
    Criticality,
    Dimension,
    Evidence,
    Liability,
    ReasonCode,
    Support,
    Term,
)

SPEC = AttributeSpec(
    name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD
)


def claim_of(surface: str) -> Claim:
    return Claim(
        attribute="brand", value=Term(surface=surface), channel=Channel.AGENT_MESSAGE
    )


def evidence_of(
    surface: str, field: str = "brands", certainty: Certainty = Certainty.EXACT
) -> Evidence:
    return Evidence(
        attribute="brand",
        value=Term(surface=surface),
        field_name=field,
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=certainty,
    )


def test_exact_brand_is_satisfied():
    result = compare_term(claim_of("Aashirvaad"), evidence_of("Aashirvaad"), SPEC)

    assert result.support is Support.SATISFIED


def test_brand_mention_in_a_longer_title_requires_entity_resolution():
    """The listing carries more words than the claim. The claim is still supported."""
    result = compare_term(
        claim_of("Aashirvaad"),
        evidence_of("Aashirvaad Select Sharbati Atta", "product_name", Certainty.PARSED),
        SPEC,
    )

    assert result.support is Support.UNSTATED


def test_claim_more_specific_than_listing_is_unstated_not_violated():
    """"Amul Gold" against a listing that only says "Amul".

    The listing does not contradict the claim — it fails to support it. Collapsing this
    into VIOLATED would refuse a possibly-correct purchase; collapsing it into SATISFIED
    would let the agent assert anything it liked as long as one word matched.
    """
    result = compare_term(claim_of("Amul Gold"), evidence_of("Amul"), SPEC)

    assert result.support is Support.UNSTATED
    assert ReasonCode.CLAIM_MORE_SPECIFIC in result.reasons


def test_different_brand_is_violated():
    result = compare_term(claim_of("Amul"), evidence_of("Mother Dairy"), SPEC)

    assert result.support is Support.VIOLATED


def test_case_and_punctuation_do_not_matter():
    result = compare_term(claim_of("mother dairy"), evidence_of("Mother-Dairy"), SPEC)

    assert result.support is Support.SATISFIED


def test_accents_are_folded_not_guessed():
    """"Nestlé" and "Nestle" are the same string in different encodings."""
    result = compare_term(claim_of("Nestle"), evidence_of("Nestlé"), SPEC)

    assert result.support is Support.SATISFIED


def test_prose_sourced_brand_is_capped():
    result = compare_term(
        claim_of("Amul"), evidence_of("Amul", "description", Certainty.INFERRED), SPEC
    )

    assert result.support is Support.SATISFIED
    assert result.ceiling < 1.0
    assert ReasonCode.LOW_CERTAINTY_SOURCE in result.reasons


def test_feedback_distinguishes_unsupported_from_wrong():
    unsupported = compare_term(claim_of("Amul Gold"), evidence_of("Amul"), SPEC)
    wrong = compare_term(claim_of("Amul"), evidence_of("Mother Dairy"), SPEC)

    assert "UNVERIFIED" in explain(unsupported)
    assert "MISMATCH" in explain(wrong)


def test_pairing_two_different_attributes_raises():
    other = Evidence(
        attribute="flavour",
        value=Term(surface="vanilla"),
        field_name="flavour",
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.EXACT,
    )

    with pytest.raises(ValueError):
        compare_term(claim_of("Amul"), other, SPEC)
