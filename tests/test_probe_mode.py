"""Probe mode must not leak the value the benchmark scores against.

These are the tests that keep a published improvement figure honest. If probe mode ever
reveals the observed value, "we improved the agent" collapses into "we told the agent the
answer" — and the number becomes a lie told with a decimal point.
"""

from decimal import Decimal

from approv.algebra.feedback import explain, explain_all
from approv.algebra.quantity import compare_quantity
from approv.algebra.runner import run_checks
from approv.types.core import (
    AttributeSpec,
    CategorySchema,
    Certainty,
    Channel,
    Claim,
    Criticality,
    Dimension,
    Evidence,
    Liability,
    Quantity,
    Term,
)

SPEC = AttributeSpec(
    name="net_weight", dimension=Dimension.MASS, criticality=Criticality.HARD
)


def _pair(claimed: str, observed: str):
    claim = Claim(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(claimed), unit="kg", dimension=Dimension.MASS),
        channel=Channel.AGENT_MESSAGE,
    )
    evidence = Evidence(
        attribute="net_weight",
        value=Quantity(magnitude=Decimal(observed), unit="kg", dimension=Dimension.MASS),
        field_name="quantity",
        liability=Liability.MERCHANT_GUARANTEED,
        certainty=Certainty.EXACT,
    )
    return claim, evidence


def test_probe_mode_hides_the_observed_value():
    finding = compare_quantity(*_pair("5", "1"), SPEC)

    revealed = explain(finding, reveal=True)
    probed = explain(finding, reveal=False)

    assert "1 kg" in revealed
    assert "1 kg" not in probed


def test_probe_mode_still_says_something_actionable():
    """Withholding the answer must not mean withholding the signal."""
    finding = compare_quantity(*_pair("5", "1"), SPEC)
    probed = explain(finding, reveal=False)

    assert "MISMATCH" in probed
    assert "5 kg" in probed
    assert "quantity" in probed
    assert "different product" in probed


def test_explain_all_honours_probe_mode():
    """Regression: explain_all accepted `reveal` and ignored it, so every benchmark
    run through it would silently have leaked the answer."""
    schema = CategorySchema(
        category_id="grocery.staples",
        version="v1",
        attributes=(SPEC,),
        field_profiles=(),
    )
    claim, evidence = _pair("5", "1")
    findings = run_checks((claim,), (evidence,), schema)

    assert "1 kg" in explain_all(findings, reveal=True)
    assert "1 kg" not in explain_all(findings, reveal=False)


def test_probe_mode_hides_an_unsupported_brand_too():
    from approv.algebra.term import compare_term

    brand_spec = AttributeSpec(
        name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD
    )
    claim = Claim(
        attribute="brand", value=Term(surface="Britannia"), channel=Channel.AGENT_MESSAGE
    )
    evidence = Evidence(
        attribute="brand",
        value=Term(surface="Good Day Cashew Cookies"),
        field_name="product_name",
        liability=Liability.PLATFORM_DERIVED,
        certainty=Certainty.PARSED,
    )

    probed = explain(compare_term(claim, evidence, brand_spec), reveal=False)

    assert "Good Day" not in probed
    assert "Britannia" in probed


# ----------------------------------------------------------------------------------
# Scoring bugs found by re-auditing the accepted benchmark design, 2026-09-08.
# ----------------------------------------------------------------------------------


def test_any_listed_brand_counts_as_correct():
    """OFF lists several brands per product; the first is often the legal entity.

    Scoring only against the first marked "Coca-Cola" wrong for a product whose
    brands field is "COCA-COLA SERVICES SA/NV, Coca-Cola".
    """
    from approv.harness.benchmark import _is_correct

    assert _is_correct("Coca-Cola", "COCA-COLA SERVICES SA/NV, Coca-Cola")
    assert _is_correct("COCA-COLA SERVICES SA/NV", "COCA-COLA SERVICES SA/NV, Coca-Cola")
    assert not _is_correct("Pepsi", "COCA-COLA SERVICES SA/NV, Coca-Cola")


def test_abstention_is_not_scored_as_a_wrong_answer():
    """Approv's signal is "unsupported", so an honest UNKNOWN is the right response.

    Counting it as an error would systematically punish arm C for making the agent
    more honest, which is the most likely way this benchmark produces a false negative.
    """
    from approv.harness.benchmark import is_abstention

    assert is_abstention("UNKNOWN")
    assert is_abstention("unknown")
    assert is_abstention("")
    assert not is_abstention("Britannia")


def test_hard_and_trivial_subsets_are_separated():
    from approv.harness.benchmark import brand_in_title

    assert brand_in_title({"product_name": "Aashirvaad Atta 5kg", "brands": "Aashirvaad"})
    assert not brand_in_title({"product_name": "Good Day - Cashew Cookies", "brands": "Britannia"})


# ----------------------------------------------------------------------------------
# Bugs found by reading the transcript of the first live run, 2026-09-08.
# ----------------------------------------------------------------------------------


def test_probe_mode_does_not_call_a_correct_answer_wrong():
    """Regression: probe mode said "disagrees" regardless of the verdict.

    A SATISFIED finding rendered as "OK brand: claimed Nutella, this disagrees with
    the listing's brands" — telling an agent its correct answer was wrong, which is
    worse than silence and silently corrupted the treatment arm.
    """
    from approv.algebra.term import compare_term

    spec = AttributeSpec(
        name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD
    )
    claim = Claim(
        attribute="brand", value=Term(surface="Nutella"), channel=Channel.AGENT_MESSAGE
    )
    evidence = Evidence(
        attribute="brand",
        value=Term(surface="Nutella"),
        field_name="brands",
        liability=Liability.PLATFORM_DERIVED,
        certainty=Certainty.EXACT,
    )

    message = explain(compare_term(claim, evidence, spec), reveal=False)

    assert message.startswith("OK")
    assert "disagrees" not in message
    assert "matches" in message


def test_all_listed_brands_are_evidence_not_just_the_first():
    """Regression: Approv reported MISMATCH against an agent that answered "Perrier"
    for a product whose brands field is "Nestle, Nestle Waters, Perrier"."""
    from approv.algebra.term import compare_term
    from approv.harness.openfoodfacts import evidence_from

    spec = AttributeSpec(
        name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD
    )
    evidence = [
        e for e in evidence_from(
            {"product_name": "Perrier", "brands": "Nestle, Nestle Waters, Perrier"}
        )
        if e.field_name == "brands"
    ][0]
    claim = Claim(
        attribute="brand", value=Term(surface="Perrier"), channel=Channel.AGENT_MESSAGE
    )

    from approv.types.core import Support as S

    assert compare_term(claim, evidence, spec).support is S.SATISFIED


def test_an_abstention_is_not_treated_as_a_brand_claim():
    """Regression: "UNKNOWN" was compared against the catalogue as if it were a brand."""
    from approv.harness.benchmark import _findings_for
    from approv.types.core import ReasonCode, Support as S

    findings = _findings_for("UNKNOWN", {"product_name": "Perly", "brands": "Jaouda"})

    assert all(f.support is not S.VIOLATED for f in findings)
    assert any(ReasonCode.NO_CLAIM in f.reasons for f in findings)
