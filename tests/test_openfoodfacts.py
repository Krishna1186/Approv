"""Parser tests written against strings that actually appear in Open Food Facts.

Every string below was taken from a real fetch of 599 Indian-market records on
2026-09-07. None of them is invented, which matters: a parser tested against strings
the author imagined will pass its tests and fail on the first real feed.
"""

from decimal import Decimal

import pytest

from approv.harness.openfoodfacts import evidence_from, parse_quantity
from approv.types.core import Certainty, Dimension, Liability


@pytest.mark.parametrize(
    "raw,magnitude,unit,dimension",
    [
        ("100 g", "100", "g", Dimension.MASS),
        ("1 kg", "1", "kg", Dimension.MASS),
        ("330 ml", "330", "ml", Dimension.VOLUME),
        ("45gm", "45", "g", Dimension.MASS),
        ("22g", "22", "g", Dimension.MASS),
        ("250ml", "250", "ml", Dimension.VOLUME),
        ("200mL", "200", "ml", Dimension.VOLUME),
        ("1 l", "1", "l", Dimension.VOLUME),
        ("52.5 g", "52.5", "g", Dimension.MASS),
        ("100.0 g", "100.0", "g", Dimension.MASS),
        ("100 gram", "100", "g", Dimension.MASS),
        ("1 litter", "1", "l", Dimension.VOLUME),
    ],
)
def test_real_quantity_strings_parse(raw, magnitude, unit, dimension):
    quantity, _ = parse_quantity(raw)

    assert quantity is not None, raw
    assert quantity.magnitude == Decimal(magnitude)
    assert quantity.unit == unit
    assert quantity.dimension is dimension


@pytest.mark.parametrize("raw", ["1", "75", "70", "6", "25", "250", "10", "4", "18"])
def test_bare_numbers_are_refused_not_guessed(raw):
    """The "1x1x1 box" case, in the wild. 17% of real quantity strings look like this.

    A bare number could be grams, millilitres or pieces. Guessing is the failure the
    whole architecture exists to prevent, so extraction returns nothing.
    """
    quantity, _ = parse_quantity(raw)

    assert quantity is None


@pytest.mark.parametrize("raw", ["1.73 - 3.00", ",", "2pcs", "", None, "   "])
def test_junk_is_refused(raw):
    quantity, _ = parse_quantity(raw)

    assert quantity is None


def test_multipack_totals_and_reports_the_count():
    quantity, count = parse_quantity("2 x 500 g")

    assert quantity.magnitude == Decimal("1000")
    assert quantity.unit == "g"
    assert count == 2


def test_comma_decimal_is_read_but_thousands_comma_is_refused():
    """"1,5 L" is 1.5 litres in most of the world. "1,500 g" is ambiguous, so refuse it."""
    metric, _ = parse_quantity("1,5 l")
    ambiguous, _ = parse_quantity("1,500 g")

    assert metric.magnitude == Decimal("1.5")
    assert ambiguous is None


def test_unknown_unit_is_refused():
    quantity, _ = parse_quantity("5 sachets")

    assert quantity is None


def test_evidence_is_not_marked_merchant_guaranteed():
    """Nobody owes a remedy for a wrong Open Food Facts field.

    Marking contributor data as merchant-guaranteed would let a corpus limitation
    masquerade as a coverable claim.
    """
    evidence = evidence_from(
        {"product_name": "Aashirvaad Atta", "brands": "Aashirvaad", "quantity": "5 kg"}
    )

    assert evidence
    assert all(e.liability is Liability.PLATFORM_DERIVED for e in evidence)


def test_derived_field_is_not_emitted_as_independent_evidence():
    """product_quantity is a parse of quantity 93.4% of the time — one fact, not two.

    Emitting both would manufacture agreement between a value and a copy of itself.
    """
    evidence = evidence_from(
        {"quantity": "5 kg", "product_quantity": 5000, "product_quantity_unit": "g"}
    )
    weight_fields = [e.field_name for e in evidence if e.attribute == "net_weight"]

    assert weight_fields == ["quantity"]


def test_title_and_brand_field_are_separate_evidence_at_different_certainty():
    evidence = evidence_from(
        {"product_name": "Aashirvaad Select Atta 5kg", "brands": "Aashirvaad"}
    )
    by_field = {e.field_name: e for e in evidence}

    assert by_field["brands"].certainty is Certainty.EXACT
    assert by_field["product_name"].certainty is Certainty.PARSED


def test_coverage_counts_records_not_evidence_items():
    """One record yields two pieces of brand evidence. Coverage must not exceed 100%."""
    from approv.harness.coverage import coverage_report

    records = [{"product_name": "Aashirvaad Atta 5kg", "brands": "Aashirvaad"}] * 4
    report = coverage_report(records)

    assert report["brand"].published == 4
    assert report["brand"].rate <= 1.0


def test_wilson_interval_brackets_the_point_estimate():
    """The interval must contain the observed rate and stay inside [0, 1].

    The epsilon is float64, not statistics. At 599/599 the Wilson upper bound is
    provably exactly 1, but the arithmetic returns 0.9999999999999999. Widening the
    assertion is honest here; clamping inside the function would hide a representation
    artifact behind a special case.
    """
    from approv.harness.coverage import wilson

    epsilon = 1e-12
    for successes, total in [(0, 10), (5, 10), (10, 10), (1, 599), (599, 599)]:
        lo, hi = wilson(successes, total)
        rate = successes / total
        assert 0.0 <= lo <= rate + epsilon
        assert rate - epsilon <= hi <= 1.0


def test_wilson_stays_inside_bounds_at_the_extremes():
    """The reason for using Wilson at all: the textbook interval goes below zero here."""
    from approv.harness.coverage import wilson

    lo, hi = wilson(0, 30)

    assert lo == 0.0
    assert hi > 0.0
