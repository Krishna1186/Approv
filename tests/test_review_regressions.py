"""Software counterexamples from the review; not an agent accuracy corpus."""
from decimal import Decimal
import itertools

import pytest
from pydantic import ValidationError

from approv.algebra.feedback import explain_all
from approv.algebra.numeric import compare_numeric
from approv.algebra.quantity import compare_quantity
from approv.algebra.runner import run_checks
from approv.algebra.term import compare_term, normalize_term
from approv.harness.benchmark import _is_correct, is_abstention
from approv.harness.coverage import coverage_report
from approv.harness.openfoodfacts import evidence_from
from approv.types.core import (
    AttributeSpec, Bound, BoundOp, CategorySchema, Certainty, Channel, Claim, Count,
    Criticality, Dimension, Evidence, FieldProfile, Liability, Money, Quantity,
    ReasonCode, Support, Term,
)


def spec(name="brand", dimension=Dimension.NOMINAL):
    return AttributeSpec(name=name, dimension=dimension, criticality=Criticality.HARD)


def claim(value, name="brand"):
    return Claim(attribute=name, value=value, channel=Channel.TOOL_ARGUMENT)


def evidence(value, name="brand", field="brands", **kw):
    return Evidence(attribute=name, value=value, field_name=field,
                    liability=Liability.PLATFORM_DERIVED, certainty=Certainty.EXACT, **kw)


def schema(*names):
    return CategorySchema(category_id="test", version="1", attributes=(spec(),),
        field_profiles=tuple(FieldProfile(field_name=n, certainty=Certainty.EXACT,
            liability=Liability.PLATFORM_DERIVED) for n in names))


def test_forged_dimension_fails_loudly():
    with pytest.raises(ValueError, match="unit contradicts"):
        compare_quantity(claim(Quantity(magnitude=500, unit="g", dimension=Dimension.MASS), "weight"),
            evidence(Quantity(magnitude=500, unit="ml", dimension=Dimension.MASS), "weight"),
            spec("weight", Dimension.MASS))


@pytest.mark.parametrize("a,b", [("Amul", "not Amul"), ("sugar", "sugar free"),
                                  ("Amul Gold", "Amul Taaza"), ("AB", "BA")])
def test_nominal_overlap_is_not_identity(a, b):
    result = compare_term(claim(Term(surface=a)), evidence(Term(surface=b)), spec())
    assert result.support is Support.VIOLATED


def test_explicit_aliases_do_not_combine_into_fictional_brand():
    value = Term(surface="Nestle", aliases=("Nestle Waters", "Perrier"))
    assert compare_term(claim(Term(surface="Perrier")), evidence(value), spec()).support is Support.SATISFIED
    assert compare_term(claim(Term(surface="Nestle Perrier")), evidence(value), spec()).support is not Support.SATISFIED


def test_trusted_ids_are_used():
    assert compare_term(claim(Term(surface="same", node_id="a")),
        evidence(Term(surface="same", node_id="b")), spec()).support is Support.VIOLATED


def test_non_latin_marks_are_not_erased():
    assert normalize_term("क") != normalize_term("कि")


def test_all_duplicate_claims_reported():
    result = run_checks((claim(Term(surface="Amul")), claim(Term(surface="Britannia"))),
                        (evidence(Term(surface="Amul")),), schema("brands"))
    assert len(result) == 2
    assert all(ReasonCode.DUPLICATE_CLAIM in f.reasons for f in result)


def test_unknown_claim_reported():
    result = run_checks((claim(Term(surface="x"), "unknown"),), (), schema())
    assert result[0].reasons == (ReasonCode.UNKNOWN_ATTRIBUTE,)


def test_conflict_is_order_independent_and_actionable():
    items = (evidence(Term(surface="Amul"), field="one"), evidence(Term(surface="Britannia"), field="two"))
    results = [run_checks((claim(Term(surface="Amul")),), order, schema("one", "two"))
               for order in itertools.permutations(items)]
    assert results[0] == results[1]
    assert results[0][0].support is Support.UNSTATED
    assert "No action needed" not in explain_all(results[0])


def test_disagreement_detected_when_both_fields_reject_claim():
    result = run_checks((claim(Term(surface="Amul")),),
        (evidence(Term(surface="Britannia"), field="one"), evidence(Term(surface="Nestle"), field="two")),
        schema("one", "two"))
    assert ReasonCode.FIELD_CONFLICT in result[0].reasons


def test_unprofiled_source_cannot_supply_clean_match():
    result = run_checks((claim(Term(surface="Amul")),), (evidence(Term(surface="Amul")),), schema())
    assert all(f.support is Support.UNSTATED for f in result)
    assert any(ReasonCode.UNTRUSTED_SOURCE in f.reasons for f in result)


def test_profile_caps_spoofed_certainty_and_advice():
    profile = FieldProfile(field_name="brands", certainty=Certainty.INFERRED,
                           liability=Liability.UNATTRIBUTED, is_advice=True)
    scoped = schema().model_copy(update={"field_profiles": (profile,)})
    result = run_checks((claim(Term(surface="Amul")),), (evidence(Term(surface="Amul")),), scoped)
    assert all(f.support is Support.UNSTATED for f in result)
    assert any(ReasonCode.ADVICE_ONLY in f.reasons for f in result)


def test_multipack_keeps_count_and_unit_amount():
    values = {e.attribute: e.value for e in evidence_from({"quantity": "2 x 500 g"})}
    assert values["net_weight"].magnitude == 1000
    assert values["unit_weight"].magnitude == 500
    assert values["pack_count"].n == 2


def test_title_alone_is_not_brand_coverage():
    assert coverage_report([{"product_name": "plain flour"}])["brand"].published == 0


@pytest.mark.parametrize("answer", ["not Amul", "Amul Britannia Nestle", "Amul Gold"])
def test_diagnostic_scorer_rejects_overanswers(answer):
    assert not _is_correct(answer, "Amul")


def test_abstention_requires_whole_response():
    assert not is_abstention("Unknown Brand")
    with pytest.raises(ValueError):
        is_abstention("")


@pytest.mark.parametrize("op,actual,expected", [(BoundOp.LTE, 10, True), (BoundOp.LT, 10, False),
    (BoundOp.GTE, 11, True), (BoundOp.GT, 10, False)])
def test_money_bounds_have_exact_edges(op, actual, expected):
    result = compare_numeric(claim(Bound(op=op, limit=Money(amount=10, currency="INR")), "price"),
        evidence(Money(amount=actual, currency="INR"), "price"), spec("price", Dimension.MONEY))
    assert (result.support is Support.SATISFIED) == expected


def test_currencies_are_incommensurable():
    result = compare_numeric(claim(Money(amount=10, currency="INR"), "price"),
        evidence(Money(amount=10, currency="USD"), "price"), spec("price", Dimension.MONEY))
    assert result.support is Support.UNSTATED


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("1"), Decimal("NaN")])
def test_invalid_tolerance_rejected(value):
    with pytest.raises(ValidationError):
        AttributeSpec(name="x", dimension=Dimension.MASS, criticality=Criticality.HARD, tolerance=value)


def test_boolean_count_rejected():
    with pytest.raises(ValidationError):
        Count(n=True)
