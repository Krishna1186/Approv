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


def test_a_qualifier_in_front_narrows_exactly_as_one_behind_does():
    """The shopper-110 defect, 10 September study.

    "Orange" against "Orange chalk stripe" was UNVERIFIED and "blue" against
    "Medium wash blue" was MISMATCH. Both are the listing naming a narrower variant of
    what was asked for; only the adjective order differs. The second reading ruled out
    the one candidate on that shelf that satisfied the request.
    """
    behind = compare_term(claim_of("Orange"), evidence_of("Orange chalk stripe"), SPEC)
    infront = compare_term(claim_of("blue"), evidence_of("Medium wash blue"), SPEC)

    assert behind.support is infront.support is Support.UNSTATED
    assert ReasonCode.LISTING_MORE_SPECIFIC in infront.reasons


def test_a_negating_qualifier_in_front_still_contradicts():
    """The reason the branch above cannot simply accept every extra word.

    "faux leather" is not a kind of leather, and it puts the negation on the left, where
    the old trailing-only guard could never have seen it. If this ever returns UNSTATED,
    a request for leather is satisfiable by imitation leather.
    """
    assert compare_term(claim_of("leather"), evidence_of("faux leather"), SPEC).support is Support.VIOLATED
    assert compare_term(claim_of("cola"), evidence_of("sugar free cola"), SPEC).support is Support.VIOLATED


def test_a_narrower_claim_is_unstated_wherever_the_extra_words_sit():
    """Extra words in the claim mean the listing is silent, never that it denies.

    So this branch carries no negation guard: a shopper asking for "sugar free cola"
    against a listing that says only "cola" has not been contradicted, they have been
    left unanswered, and UNSTATED is what routes that to confirm.
    """
    result = compare_term(claim_of("sugar free cola"), evidence_of("cola"), SPEC)

    assert result.support is Support.UNSTATED
    assert ReasonCode.CLAIM_MORE_SPECIFIC in result.reasons


def test_a_reordered_name_is_not_a_narrowing():
    """Whole contiguous words, not a token set. Reordering a name makes a different name,
    and this module's opening claim is ordered identity."""
    assert compare_term(claim_of("navy blue"), evidence_of("blue navy stripe"), SPEC).support is Support.VIOLATED


def test_a_partial_word_is_not_a_narrowing():
    """Substring matching would make "red" a narrowing of "shredded"."""
    assert compare_term(claim_of("red"), evidence_of("shredded wheat"), SPEC).support is Support.VIOLATED


def test_the_negation_lexicon_is_read_in_both_positions():
    """Every negator must work from either side, or the set is a list of coincidences.

    Each pair below is the same word doing the same job in the two adjective orders
    English actually uses. Before the matcher became symmetric only the right-hand
    column was ever consulted, so a left-hand negator returned a contradiction because
    the prefix test happened to fail — not because the word had been read.
    """
    for word in ("non", "no", "not", "faux", "fake", "imitation", "anti"):
        infront = compare_term(claim_of("leather"), evidence_of(f"{word} leather"), SPEC)
        assert infront.support is Support.VIOLATED, word
    for word in ("free", "less", "substitute", "style", "compatible", "dupe"):
        behind = compare_term(claim_of("leather"), evidence_of(f"leather {word}"), SPEC)
        assert behind.support is Support.VIOLATED, word
