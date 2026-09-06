"""Tests for the quantity comparison operator.

Every expected outcome in this file is one the founder already stated:

  - same value            -> passes
  - different value       -> fails
  - different unit, same dimension (oz/ml, lb/kg) -> convert and compare, not inference
  - different dimension   -> stays unverified, because converting mass to volume
                             needs a density we do not have

The inputs are hand-built. No product page is read. This operator is deliberately
small: by the time it runs, extraction has either produced a typed Quantity with a
real unit or it has produced nothing. "1x1x1" with no unit never reaches here.
"""

from decimal import Decimal

import pytest

from approv.algebra.quantity import compare_quantity
from approv.types.core import (
    AttributeSpec,
    Certainty,
    Channel,
    Claim,
    Criticality,
    Dimension,
    Evidence,
    Liability,
    Quantity,
    ReasonCode,
    Support,
)

SPEC = AttributeSpec(
    name="net_weight", dimension=Dimension.MASS, criticality=Criticality.HARD
)


def claim_of(magnitude: str, unit: str, dimension: Dimension) -> Claim:
    return Claim(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(magnitude), unit=unit, dimension=dimension),
        channel=Channel.AGENT_MESSAGE,
    )


def evidence_of(magnitude: str, unit: str, dimension: Dimension) -> Evidence:
    return Evidence(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(magnitude), unit=unit, dimension=dimension),
        field_name="net_weight",
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.EXACT,
    )


def test_same_value_same_unit_is_satisfied():
    """Agent said 5 kg, the page says 5 kg."""
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("5", "kg", Dimension.MASS),
        SPEC,
    )

    assert result.support is Support.SATISFIED


def test_different_value_same_unit_is_violated():
    """Agent said 5 kg, the page says 1 kg."""
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("1", "kg", Dimension.MASS),
        SPEC,
    )

    assert result.support is Support.VIOLATED


def test_same_amount_different_unit_is_satisfied():
    """5 kg and 5000 g are the same mass. Converting is arithmetic, not inference.

    This is the test that proves the operator converts rather than comparing
    unit strings. If it ever compares "kg" to "g" as text, this fails.
    """
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("5000", "g", Dimension.MASS),
        SPEC,
    )

    assert result.support is Support.SATISFIED


def test_different_value_and_different_unit_is_violated():
    """Agent said 5 kg, the page says 500 g. Converts to 5000 g vs 500 g."""
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("500", "g", Dimension.MASS),
        SPEC,
    )

    assert result.support is Support.VIOLATED


def test_different_dimension_is_unstated_and_says_why():
    """Agent said 5 kg, the page publishes 500 ml. Mass to volume needs a density.

    Asserting the reason as well as the outcome matters here: UNSTATED alone would
    also pass if the operator silently gave up for the wrong reason.
    """
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("500", "ml", Dimension.VOLUME),
        SPEC,
    )

    assert result.support is Support.UNSTATED
    assert ReasonCode.INCOMMENSURABLE in result.reasons


# ----------------------------------------------------------------------------------
# The other three fields on a Finding: reasons, confidence, ceiling.
# ----------------------------------------------------------------------------------


def test_prose_sourced_evidence_is_capped_below_certainty():
    """The page says 5 kg, but only in marketing prose, not in a weight field.

    The answer is right and the source is weak. Support is SATISFIED, but the ceiling
    holds it below the level a HARD attribute needs — which is what stops planted text
    from clearing a hard constraint no matter how confident it sounds.
    """
    evidence = Evidence(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal("5"), unit="kg", dimension=Dimension.MASS),
        field_name="description",
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.INFERRED,
    )

    result = compare_quantity(claim_of("5", "kg", Dimension.MASS), evidence, SPEC)

    assert result.support is Support.SATISFIED
    assert result.ceiling < 1.0
    assert result.confidence <= result.ceiling


def test_structured_field_is_not_capped():
    """The same claim, read out of a real weight field, is not held back."""
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("5", "kg", Dimension.MASS),
        SPEC,
    )

    assert result.ceiling == 1.0
    assert result.confidence == 1.0


def test_nothing_compared_means_no_confidence():
    """When no comparison ran, no fact was established, so confidence is zero.

    The ceiling still describes the source, because that is a property of where the
    text came from and not of how the comparison turned out.
    """
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("500", "ml", Dimension.VOLUME),
        SPEC,
    )

    assert result.confidence == 0.0


def test_unknown_unit_is_unstated_not_violated():
    """Real feeds contain "sachet" and "pouch". That is not a mismatch."""
    result = compare_quantity(
        claim_of("5", "kg", Dimension.MASS),
        evidence_of("2", "sachet", Dimension.MASS),
        SPEC,
    )

    assert result.support is Support.UNSTATED
    assert ReasonCode.UNRESOLVED_TERM in result.reasons


def test_pairing_two_different_attributes_raises():
    """A weight claim against a volume field is a caller bug, not a finding.

    It must fail loudly. A bug that returns a plausible answer is a bug that ships.
    """
    volume_evidence = Evidence(
        attribute="net_volume",
        value=Quantity(magnitude=Decimal("1"), unit="l", dimension=Dimension.VOLUME),
        field_name="net_volume",
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.EXACT,
    )

    with pytest.raises(ValueError):
        compare_quantity(claim_of("5", "kg", Dimension.MASS), volume_evidence, SPEC)
