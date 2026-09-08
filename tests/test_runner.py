"""Tests for the check runner: pairing, dispatch, and reporting everything."""

from decimal import Decimal

from approv.algebra.feedback import explain_all
from approv.algebra.runner import run_checks
from approv.types.core import (
    AttributeSpec,
    CategorySchema,
    Certainty,
    Channel,
    Claim,
    Count,
    Criticality,
    Dimension,
    Evidence,
    FieldProfile,
    Liability,
    Quantity,
    ReasonCode,
    Support,
    Term,
)

SCHEMA = CategorySchema(
    category_id="grocery.staples",
    version="v1",
    attributes=(
        AttributeSpec(name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="net_weight", dimension=Dimension.MASS, criticality=Criticality.HARD),
        AttributeSpec(name="pack_count", dimension=Dimension.COUNT, criticality=Criticality.SOFT),
    ),
    field_profiles=tuple(FieldProfile(field_name=name, liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.INFERRED if name == "description" else Certainty.EXACT)
        for name in ("brands", "quantity", "packaging", "description")),
    floor=frozenset({"net_weight"}),
)


def term_claim(attribute: str, surface: str) -> Claim:
    return Claim(
        attribute=attribute,
        value=Term(surface=surface),
        channel=Channel.AGENT_MESSAGE,
    )


def term_evidence(
    attribute: str, surface: str, field: str, certainty: Certainty = Certainty.EXACT
) -> Evidence:
    return Evidence(
        attribute=attribute,
        value=Term(surface=surface),
        field_name=field,
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=certainty,
    )


def mass_claim(magnitude: str, unit: str) -> Claim:
    return Claim(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(magnitude), unit=unit, dimension=Dimension.MASS),
        channel=Channel.AGENT_MESSAGE,
    )


def mass_evidence(
    magnitude: str, unit: str, field: str = "quantity", certainty: Certainty = Certainty.EXACT
) -> Evidence:
    return Evidence(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(magnitude), unit=unit, dimension=Dimension.MASS),
        field_name=field,
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=certainty,
    )


def by_attribute(findings):
    return {f.attribute: f for f in findings}


def test_every_failure_is_reported_not_just_the_first():
    """Brand wrong AND weight wrong. The agent must hear about both in one pass."""
    findings = run_checks(
        claims=(term_claim("brand", "Amul"), mass_claim("5", "kg")),
        evidence=(
            term_evidence("brand", "Mother Dairy", "brands"),
            mass_evidence("1", "kg"),
        ),
        schema=SCHEMA,
    )
    result = by_attribute(findings)

    assert result["brand"].support is Support.VIOLATED
    assert result["net_weight"].support is Support.VIOLATED
    assert len(findings) == 2


def test_missing_floor_attribute_is_reported_even_with_no_claim():
    """net_weight is in the floor. Saying nothing about it is itself the finding."""
    findings = run_checks(
        claims=(term_claim("brand", "Amul"),),
        evidence=(term_evidence("brand", "Amul", "brands"),),
        schema=SCHEMA,
    )
    result = by_attribute(findings)

    assert result["net_weight"].support is Support.UNSTATED
    assert ReasonCode.FLOOR_NOT_MET in result["net_weight"].reasons


def test_claim_with_no_evidence_says_the_listing_is_silent():
    findings = run_checks(
        claims=(mass_claim("5", "kg"),),
        evidence=(),
        schema=SCHEMA,
    )
    result = by_attribute(findings)

    assert result["net_weight"].support is Support.UNSTATED
    assert ReasonCode.PRODUCT_SILENT in result["net_weight"].reasons


def test_conflicting_fields_require_resolution():
    """Both fields exist. The dedicated field decides; the description does not."""
    findings = run_checks(
        claims=(mass_claim("5", "kg"),),
        evidence=(
            mass_evidence("1", "kg", field="description", certainty=Certainty.INFERRED),
            mass_evidence("5", "kg", field="quantity", certainty=Certainty.EXACT),
        ),
        schema=SCHEMA,
    )
    result = by_attribute(findings)

    assert result["net_weight"].support is Support.UNSTATED
    assert ReasonCode.FIELD_CONFLICT in result["net_weight"].reasons


def test_soft_attribute_absent_on_both_sides_produces_nothing():
    """pack_count is SOFT and neither side mentions it. Silence is not a finding."""
    findings = run_checks(
        claims=(mass_claim("5", "kg"),),
        evidence=(mass_evidence("5", "kg"),),
        schema=SCHEMA,
    )

    assert "pack_count" not in by_attribute(findings)


def test_pack_count_mismatch_is_violated():
    findings = run_checks(
        claims=(
            mass_claim("5", "kg"),
            Claim(attribute="pack_count", value=Count(n=6), channel=Channel.AGENT_MESSAGE),
        ),
        evidence=(
            mass_evidence("5", "kg"),
            Evidence(
                attribute="pack_count",
                value=Count(n=1),
                field_name="packaging",
                liability=Liability.MERCHANT_GUARANTEED,
                certainty=Certainty.EXACT,
            ),
        ),
        schema=SCHEMA,
    )

    assert by_attribute(findings)["pack_count"].support is Support.VIOLATED


def test_worst_problems_are_reported_first():
    """A mismatch is actionable with certainty; an unverified attribute may not be."""
    findings = run_checks(
        claims=(term_claim("brand", "Amul"), mass_claim("5", "kg")),
        evidence=(term_evidence("brand", "Mother Dairy", "brands"),),
        schema=SCHEMA,
    )
    lines = explain_all(findings).splitlines()

    assert lines[0].startswith("MISMATCH")
    assert lines[1].startswith("UNVERIFIED")
