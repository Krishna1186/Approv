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
