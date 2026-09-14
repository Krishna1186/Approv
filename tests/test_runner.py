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


# --- DR 0025: two statements of one attribute that agree ----------------------------------

def test_a_filter_and_a_query_that_agree_collapse_to_one_claim():
    """On-site search states an attribute twice by design. Which one the shopper meant is
    only a question when the two answers differ."""
    findings = run_checks(
        claims=(Claim(attribute="brand", value=Term(surface="Amul"),
                      channel=Channel.TOOL_ARGUMENT),
                term_claim("brand", "amul")),
        evidence=(term_evidence("brand", "Amul", "brands"),),
        schema=SCHEMA,
    )
    brand = [f for f in findings if f.attribute == "brand"]

    assert len(brand) == 1 and brand[0].support is Support.SATISFIED


def test_the_surviving_claim_is_the_one_that_needs_no_extraction_to_defend():
    """DR 0008's tiers. A structured filter and a paraphrase of the same request are not
    equally disputable, so the record attributes the constraint to the filter."""
    findings = run_checks(
        claims=(term_claim("brand", "Amul"),
                Claim(attribute="brand", value=Term(surface="Amul"),
                      channel=Channel.TOOL_ARGUMENT)),
        evidence=(term_evidence("brand", "Amul", "brands"),),
        schema=SCHEMA,
    )

    assert by_attribute(findings)["brand"].claim.channel is Channel.TOOL_ARGUMENT


def test_two_statements_that_disagree_still_go_to_the_conflict_path():
    """Unchanged, and it is the case the rule was written for: an agent asserting two
    different values for one attribute is a real disambiguation problem."""
    findings = run_checks(
        claims=(term_claim("brand", "Amul"), term_claim("brand", "Britannia")),
        evidence=(term_evidence("brand", "Amul", "brands"),),
        schema=SCHEMA,
    )
    brand = [f for f in findings if f.attribute == "brand"]

    assert len(brand) == 2
    assert all(ReasonCode.DUPLICATE_CLAIM in f.reasons for f in brand)


def test_agreement_is_decided_both_ways_round():
    """Half a comparison is containment, not agreement. 5 kg stated once and 4.999 kg
    stated again is inside tolerance either way round; 5 kg and 500 g is not."""
    agreeing = run_checks(
        claims=(mass_claim("5", "kg"), mass_claim("5000", "g")),
        evidence=(mass_evidence("5", "kg"),), schema=SCHEMA)
    differing = run_checks(
        claims=(mass_claim("5", "kg"), mass_claim("500", "g")),
        evidence=(mass_evidence("5", "kg"),), schema=SCHEMA)

    assert by_attribute(agreeing)["net_weight"].support is Support.SATISFIED
    assert all(ReasonCode.DUPLICATE_CLAIM in f.reasons
               for f in differing if f.attribute == "net_weight")


def test_collapsing_does_not_weaken_the_comparison_against_the_catalogue():
    """The safety argument for DR 0025. A collapsed claim is checked exactly as a single
    claim would have been — agreeing with each other is not agreeing with the product."""
    findings = run_checks(
        claims=(Claim(attribute="brand", value=Term(surface="Amul"),
                      channel=Channel.TOOL_ARGUMENT),
                term_claim("brand", "Amul")),
        evidence=(term_evidence("brand", "Britannia", "brands"),),
        schema=SCHEMA,
    )

    assert by_attribute(findings)["brand"].support is Support.VIOLATED
