"""Onboarding contracts, including the independently constructed non-Shopify shape."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from approv.criticality import schema_layer
from approv.schema import SchemaProposal, SourcePolicy, confirm_schema, propose_schema
from approv.types.core import Certainty, Criticality, Dimension, Liability

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "industrial_catalogue.json"


def propose(records, **kwargs):
    return propose_schema(records, category_id="test.industrial", observed_at=NOW, **kwargs)


def attrs(proposal):
    return {a.attribute: a for a in proposal.report.attributes}


@pytest.fixture
def industrial():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_unfamiliar_nested_catalogue_dimensions_sources_and_denominators(industrial):
    proposal = propose(industrial)
    report = attrs(proposal)
    assert proposal.report.input_records == 3
    assert proposal.report.listings == 6
    assert report["finish"].dimension is Dimension.NOMINAL
    assert report["bore"].dimension is Dimension.LENGTH
    assert report["reach"].dimension is Dimension.LENGTH
    assert report["bundle"].dimension is Dimension.COUNT
    assert report["invoice"].dimension is Dimension.MONEY
    assert (report["finish"].published.numerator, report["finish"].published.denominator) == (4, 6)
    assert (report["reach"].occupied.numerator, report["reach"].published.numerator) == (4, 3)
    assert (report["wall_thickness"].published.numerator, report["wall_thickness"].exact.numerator) == (5, 0)
    assert report["wall_thickness"].sources[0].certainty is Certainty.PARSED
    assert report["wall_thickness"].sources[0].liability is Liability.MERCHANT_GUARANTEED
    assert (report["finish"].variant_groups.numerator, report["finish"].variant_groups.denominator) == (1, 2)
    assert proposal.proposed_schema.floor == frozenset({"bore"})
    assert (proposal.report.cannot_verify.numerator, proposal.report.cannot_verify.denominator) == (2, 6)
    assert proposal.report.no_comparable_attributes.numerator == 1
    assert schema_layer("finish", proposal.proposed_schema.field_profiles) is Criticality.BOUND
    assert schema_layer("invoice", proposal.proposed_schema.field_profiles) is Criticality.SOFT
    assert not any("instructions" in a.name for a in proposal.proposed_schema.attributes)


def test_money_is_inferred_from_values_not_only_field_names():
    p = propose([{"retail": "EUR 3.20", "price": "negotiable", "cost": "12.50", "net": "500 g", "lots": "6 units"}])
    a = attrs(p)
    assert a["retail"].dimension is Dimension.MONEY
    assert a["price"].dimension is Dimension.NOMINAL
    assert a["cost"].dimension is Dimension.MONEY
    assert a["cost"].published.numerator == 0
    assert a["net"].dimension is Dimension.MASS
    assert a["lots"].dimension is Dimension.COUNT


def test_currency_is_not_guessed_and_local_currency_wins():
    records = [{"price": "$12.50"}, {"price": "12.50", "currency": "CAD"}, {"price": "EUR 12.50", "currency": "USD"}]
    assert attrs(propose(records))["price"].published.numerator == 1
    assert attrs(propose(records, currency="USD"))["price"].published.numerator == 2
    with pytest.raises(ValueError, match="currency"):
        propose(records, currency="usd")


@pytest.mark.parametrize("value", ["2 fl oz", "2 x 500 g", "-3 kg", "1,250 g", "500 ml or 600 ml"])
def test_ambiguous_quantities_do_not_publish(value):
    p = propose([{"net": "500 g"}, {"net": value}])
    assert attrs(p)["net"].published.numerator == 1


def test_incommensurable_observations_do_not_silently_choose_majority():
    p = propose([{"net": "500 g"}, {"net": "500 g"}, {"net": "500 ml"}])
    assert attrs(p)["net"].dimension is None
    assert attrs(p)["net"].published.numerator == 0
    assert not p.proposed_schema.attributes
    assert p.report.cannot_verify.numerator == 3


def test_native_numbered_options_and_no_cartesian_expansion():
    p = propose([{"id": "parent", "options": [{"name": "Fit", "position": 2, "values": ["S", "M", "L"]}, {"name": "Tone", "position": 1, "values": ["red", "blue"]}],
                  "variants": [{"sku": "a", "option1": "red", "option2": "S", "price": "10.50"}, {"sku": "b", "option1": "blue", "option2": "M", "price": "12.50"}]}])
    assert p.report.listings == 2
    assert attrs(p)["fit"].variant_groups.numerator == 1
    assert attrs(p)["tone"].variant_groups.numerator == 1
    assert not any(a.name.startswith("option") for a in p.proposed_schema.attributes)
    assert "#name=Fit" in attrs(p)["fit"].sources[0].field_name
    assert attrs(p)["price"].published.numerator == 0


def test_option_values_without_sold_siblings_are_not_axes():
    p = propose([{"options": [{"name": "Finish", "values": ["matt", "gloss"]}],
                  "variants": [{"sku": "one", "option1": "matt"}]}])
    assert attrs(p)["finish"].variant_groups.numerator == 0
    assert not any(f.is_variant_axis for f in p.proposed_schema.field_profiles)


def test_explicit_count_units_remain_counts_when_they_are_variant_axes():
    p = propose([{"family_id": "a", "sku": "one", "bundle": "6 pcs"},
                 {"family_id": "a", "sku": "two", "bundle": "12 pcs"}])
    assert attrs(p)["bundle"].dimension is Dimension.COUNT
    assert attrs(p)["bundle"].variant_groups.numerator == 1


def test_missing_option_values_do_not_invent_a_dimension():
    p = propose([{"variants": [{"sku": "one", "selections": [{"name": "Bundle", "value": None}]}]}])
    assert attrs(p)["bundle"].dimension is None


def test_inherited_label_value_specs_do_not_mask_variant_axis_discovery():
    p = propose([{"specs": [{"label": "Material", "value": "brass"}],
                  "variants": [{"sku": "a", "finish": "red"}, {"sku": "b", "finish": "blue"}]}])
    assert attrs(p)["finish"].variant_groups.numerator == 1
    assert attrs(p)["material"].variant_groups.numerator == 0


def test_literal_keys_cannot_impersonate_a_dynamic_option_source():
    p = propose([{"options": [{"name": "Size", "values": ["S"]}],
                  "variants": [{"sku": "a", "option1": "S", "option1#name=Size": "malicious"}]}])
    sources = {f.field_name for f in p.proposed_schema.field_profiles}
    assert "/variants/*/option1#name=Size" in sources
    assert "/variants/*/option1~3name=Size" in sources
    with pytest.raises(ValueError, match="control characters"):
        propose([{chr(0): "hidden"}])


@pytest.mark.parametrize("nested", [True, False])
def test_numeric_and_mixed_size_labels_are_nominal(nested):
    records = [{"sku": str(i), "family_id": "same", "size": size} for i, size in enumerate(["8", "8.5", "XL", "12 Tall"])]
    if nested:
        records = [{"variants": records}]
    p = propose(records)
    assert attrs(p)["size"].dimension is Dimension.NOMINAL
    assert attrs(p)["size"].published.numerator == 4
    assert attrs(p)["size"].variant_groups.numerator == 1


def test_across_products_and_duplicated_sku_are_not_merchandising_evidence():
    for records in ([{"sku": "a", "finish": "red"}, {"sku": "b", "finish": "blue"}],
                    [{"sku": "a", "family_id": "x", "finish": "red"}, {"sku": "a", "family_id": "x", "finish": "blue"}]):
        p = propose(records)
        assert not any(f.is_variant_axis for f in p.proposed_schema.field_profiles)


def test_separate_merchants_do_not_create_a_false_sibling_group():
    p = propose([{"merchant_id": "a", "product_id": "x", "sku": "a", "finish": "red"},
                 {"merchant_id": "b", "product_id": "x", "sku": "b", "finish": "blue"}])
    assert attrs(p)["finish"].variant_groups.numerator == 0


def test_leaf_collisions_and_literal_path_characters_remain_distinct():
    p = propose([{"a": {"length": "1 m"}, "b": {"length": "2 m"}, "a/length": "3 m"}])
    assert {a.name for a in p.proposed_schema.attributes} == {"/a/length", "/b/length", "a/length"}
    assert "/a~1length" in {f.field_name for f in p.proposed_schema.field_profiles}


def test_prose_does_not_gain_exact_certainty_and_never_supplies_floor():
    p = propose([{"description": "Mass: 500 g\nFinish: matte"}])
    assert attrs(p)["mass"].published.numerator == 1
    assert attrs(p)["mass"].exact.numerator == 0
    assert p.proposed_schema.floor == frozenset()
    assert p.report.cannot_verify.numerator == 1
    with pytest.raises(ValueError, match="structured evidence"):
        confirm_schema(p, reviewer="human", expected_proposal_id=p.proposal_id, floor=frozenset({"mass"}))


def test_conflicting_prose_and_structured_value_count_one_unusable_listing():
    p = propose([{"net": "500 g", "description": "Net: 250 g"},
                 {"net": "500 g", "description": "Net: 500 g"}])
    assert attrs(p)["net"].published.numerator == 1
    assert attrs(p)["net"].conflicted.numerator == 1
    assert len(attrs(p)["net"].sources) == 2
    assert p.report.cannot_verify.numerator == 1


def test_trust_comes_from_onboarding_configuration_not_product_text():
    records = [{"net": "500 g", "liability": "merchant_guaranteed", "certainty": "exact", "is_variant_axis": True,
                "evidence": [{"attribute": "invented", "value": "yes", "liability": "merchant_guaranteed"}],
                "schema": {"floor": ["invented"]}}]
    p = propose(records, source_policies={"/net": SourcePolicy(liability=Liability.SELLER_STATED)})
    assert set(attrs(p)) == {"net"}
    assert attrs(p)["net"].sources[0].liability is Liability.SELLER_STATED
    assert attrs(p)["net"].exact.numerator == 1
    assert attrs(p)["net"].floor_eligible.numerator == 0
    assert p.report.cannot_verify.numerator == 1


def test_source_policy_cannot_upgrade_parsed_prose():
    p = propose([{"description": "Net: 500 g"}], source_policies={"/description": SourcePolicy(certainty=Certainty.EXACT)})
    assert attrs(p)["net"].sources[0].certainty is Certainty.PARSED


def test_advice_is_not_a_verifiable_attribute_or_axis():
    p = propose([{"family_id": "a", "sku": "a", "finish": "red"}, {"family_id": "a", "sku": "b", "finish": "blue"}],
                source_policies={"/finish": SourcePolicy(is_advice=True)})
    assert attrs(p)["finish"].published.numerator == 0
    assert not any(f.is_variant_axis for f in p.proposed_schema.field_profiles)


def test_empty_missing_false_and_zero_have_explicit_denominators():
    p = propose([])
    assert p.report.cannot_verify.denominator == 0
    assert p.report.cannot_verify.rate is None
    assert p.report.cannot_verify.interval == (0.0, 1.0)
    p = propose([{}, {"units": 0, "waterproof": False}, {"units": "unknown"}])
    assert attrs(p)["units"].published.numerator == 1
    assert attrs(p)["waterproof"].published.numerator == 1
    assert p.report.cannot_verify.denominator == 3


def test_all_missing_keys_still_appear_in_the_report_without_inventing_a_type():
    p = propose([{"mass": None}, {"mass": "unknown"}, {"mass": ""}, {}])
    mass = attrs(p)["mass"]
    assert (mass.occupied.numerator, mass.occupied.denominator) == (0, 4)
    assert mass.published.numerator == 0
    assert mass.dimension is None
    assert "mass" not in {a.name for a in p.proposed_schema.attributes}


def test_multivalue_fields_are_reported_without_claiming_a_selected_value():
    p = propose([{"compatibility": ["A", "B"]}, {"compatibility": []}])
    field = attrs(p)["compatibility"]
    assert (field.occupied.numerator, field.occupied.denominator) == (1, 2)
    assert field.published.numerator == 0
    assert "multivalued_field_requires_mapping" in field.issues


def test_explicit_unit_keys_require_numeric_values():
    p = propose([{"length_cm": 20, "grams": 500, "capacity_ml": "250", "kg": "red"}])
    assert attrs(p)["length_cm"].dimension is Dimension.LENGTH
    assert attrs(p)["grams"].dimension is Dimension.MASS
    assert attrs(p)["capacity_ml"].dimension is Dimension.VOLUME
    assert attrs(p)["kg"].dimension is Dimension.NOMINAL


def test_missing_nested_variant_value_does_not_inherit_parent_value():
    p = propose([{"material": "brass", "variants": [{"sku": "a", "specs": {"material": None}}, {"sku": "b", "specs": {"material": "steel"}}]}])
    assert attrs(p)["material"].published.numerator == 1
    assert attrs(p)["material"].variant_groups.numerator == 0


def test_nested_option_definitions_and_currency_are_inherited():
    p = propose([{"envelope": {"currency": "CAD", "options": [{"name": "Finish", "values": ["red", "blue"]}],
                               "variants": [{"sku": "a", "option1": "red", "price": "2.99", "grams": 100},
                                            {"sku": "b", "option1": "blue", "price": "3.99", "grams": 200}]}}])
    assert attrs(p)["finish"].variant_groups.numerator == 1
    assert attrs(p)["finish"].variant_basis == ("named_selector",)
    assert attrs(p)["price"].published.numerator == 2
    assert attrs(p)["grams"].dimension is Dimension.MASS
    assert attrs(p)["grams"].variant_groups.numerator == 0


def test_an_empty_variant_array_does_not_verify_the_parent_as_a_sellable_sku():
    p = propose([{"material": "brass", "variants": []}])
    assert p.report.listings == 1
    assert p.report.cannot_verify.numerator == 1
    assert any("empty_variant_collection" in w for w in p.report.warnings)


def test_ambiguous_sibling_collections_do_not_invent_combinations():
    p = propose([{"stock": [{"sku": "a", "finish": "matt"}], "accessories": [{"sku": "x", "finish": "wax"}]}])
    assert p.report.listings == 1
    assert p.report.cannot_verify.numerator == 1
    assert any("ambiguous_variant_collections" in w for w in p.report.warnings)


def test_confirmation_is_explicit_versioned_and_recounts_the_selected_floor(industrial):
    p = propose(industrial)
    assert p.status == "proposed"
    assert not hasattr(p, "category_schema")
    with pytest.raises(TypeError):
        confirm_schema(p)
    with pytest.raises(ValueError, match="changed"):
        confirm_schema(p, reviewer="alice", expected_proposal_id="old", floor=frozenset({"bore"}))
    with pytest.raises(ValueError, match="reviewer"):
        confirm_schema(p, reviewer=" ", expected_proposal_id=p.proposal_id, floor=frozenset({"bore"}))
    with pytest.raises(ValueError, match="nonempty floor"):
        confirm_schema(p, reviewer="alice", expected_proposal_id=p.proposal_id, floor=frozenset())
    confirmed = confirm_schema(p, reviewer="alice", expected_proposal_id=p.proposal_id,
                               floor=frozenset({"bore", "reach"}), confirmed_at=NOW)
    assert confirmed.status == "confirmed"
    assert confirmed.report.cannot_verify.numerator == 3
    assert confirmed.category_schema.floor == frozenset({"bore", "reach"})
    assert confirmed.category_schema.version != p.proposed_schema.version
    assert p.proposed_schema.floor == frozenset({"bore"})
    assert confirmed.proposal_id == p.proposal_id


def test_proposal_digest_binds_data_and_reviewable_fields(industrial):
    original = copy.deepcopy(industrial)
    p = propose(industrial)
    assert industrial == original
    assert propose(industrial).proposal_id == p.proposal_id
    edited = p.model_copy(update={"proposed_schema": p.proposed_schema.model_copy(update={"floor": frozenset({"reach"})})})
    assert edited.proposal_id != p.proposal_id
    with pytest.raises(ValidationError):
        p.status = "confirmed"
    # Round-trip the stored payload (computed reporting fields are output-only).
    payload = p.model_dump_json(round_trip=True)
    restored = SchemaProposal.model_validate_json(payload)
    assert restored.proposal_id == p.proposal_id


@pytest.mark.parametrize("records", [{}, [None], [{"value": float("nan")}], [{1: "not a string key"}]])
def test_invalid_input_does_not_produce_a_plausible_schema(records):
    with pytest.raises((ValueError, TypeError)):
        propose(records)


def test_timestamps_are_aware_and_review_cannot_predate_snapshot():
    with pytest.raises(ValueError, match="timezone"):
        propose_schema([], category_id="test", observed_at=datetime(2026, 9, 12))
    p = propose([{"finish": "matt"}])
    with pytest.raises(ValueError, match="predate"):
        confirm_schema(p, reviewer="alice", expected_proposal_id=p.proposal_id,
                       floor=frozenset({"finish"}), confirmed_at=datetime(2026, 9, 11, tzinfo=timezone.utc))
