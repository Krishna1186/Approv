"""Producer contract for numbered slots; surface owns the consumer implementation."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from approv.schema import SourcePolicy, propose_schema
from approv.schema.locators import Locator, format_locator, parse_locator
from approv.types.core import Liability

ROOT = Path(__file__).parent / "fixtures"


def propose(records):
    return propose_schema(records, category_id="option-table-contract",
                          observed_at=datetime(2026, 9, 14, tzinfo=timezone.utc))


def test_flat_and_nested_catalogues_emit_exact_table_paths_without_custom_mapping():
    records = json.loads((ROOT / "option_table_catalogue.json").read_text(encoding="utf-8"))
    proposal = propose(records)
    expected = {
        "/option1#name=Size&table=%2Foptions": "size",
        "/option2#name=Color&table=%2Foptions": "color",
        "/envelope/editions/*/option1#name=Bore&table=%2Fenvelope%2Fnames~1~3~0~2": "bore",
        "/variants/*/option1#name=Finish%20%26%20tone&table=%2Fvariants%2F%2A%2Fchoice_names": "finish_&_tone",
    }
    profiles = {profile.field_name: profile for profile in proposal.proposed_schema.field_profiles}
    assert set(profiles) == set(expected)
    for path, attribute in expected.items():
        assert profiles[path].attributes == (attribute,)
        assert profiles[path].is_variant_axis
        row = next(row for row in proposal.report.attributes if row.attribute == attribute)
        assert (row.published.numerator, row.published.denominator) == (2, 6)
        parsed = parse_locator(path)
        assert format_locator(parsed.segments, selector=parsed.selector, table=parsed.table) == path
    assert proposal.proposed_schema.version.startswith("schema-onboarding-v2:")
    assert proposal.status == "proposed"


def test_table_order_cannot_rename_explicit_positions():
    record = json.loads((ROOT / "option_table_catalogue.json").read_text(encoding="utf-8"))[0]
    reordered = deepcopy(record)
    reordered["options"].reverse()
    assert propose([record]).proposed_schema.field_profiles == propose([reordered]).proposed_schema.field_profiles


def test_nearest_table_replaces_ancestor_slots_without_cross_table_fallback():
    proposal = propose([{"options": [{"name": "Old size", "position": 1, "values": ["M"]}],
                         "box": {"labels": [{"name": "Color", "position": 2, "values": ["red"]}],
                                 "variants": [{"sku": "a", "option1": "M", "option2": "red"}]}}])
    profiles = proposal.proposed_schema.field_profiles
    assert len(profiles) == 1
    assert profiles[0].field_name == "/box/variants/*/option2#name=Color&table=%2Fbox%2Flabels"
    assert profiles[0].attributes == ("color",)


@pytest.mark.parametrize("definitions", [
    [{"name": "Size", "position": 1, "values": []}, {"name": "Color", "position": 1, "values": []}],
    [{"name": "Size", "position": 1, "values": []}, {"name": "Size", "position": 1, "values": []}],
    [{"name": "Size", "position": True, "values": []}],
    [{"name": "Size", "position": 0, "values": []}],
    [{"name": "Size", "position": "1", "values": []}],
    [{"name": " ", "values": []}],
    [{"name": "Size", "values": "M,L"}],
])
def test_ambiguous_or_invalid_tables_cannot_propose_a_guessed_slot(definitions):
    with pytest.raises(ValueError, match="option (definition|position)"):
        propose([{"sku": "a", "options": definitions, "option1": "M"}])


def test_conflicting_tables_do_not_choose_the_last_one():
    with pytest.raises(ValueError, match="ambiguous option position"):
        propose([{"sku": "a", "one": [{"name": "Size", "values": []}],
                  "two": [{"name": "Color", "values": []}], "option1": "M"}])


def test_table_contents_never_replace_the_selected_value_or_create_names_from_control_fields():
    proposal = propose([{"sku": "a", "options": [{"name": "Size", "values": ["M", "L"]}],
                         "evidence": [{"name": "Spoof", "values": ["M"]}], "option1": None}])
    assert proposal.proposed_schema.field_profiles == ()
    row = next(row for row in proposal.report.attributes if row.attribute == "size")
    assert (row.published.numerator, row.published.denominator) == (0, 1)
    assert not any(row.attribute == "spoof" for row in proposal.report.attributes)


@pytest.mark.parametrize("invalid", [
    "/option1#table=%2Foptions", "/option1#name=Size&table=", "/option1#name=Size&table=/options",
    "/option1#name=Size&table=%2Foptions&table=%2Fother", "/option1#name=Size&names=%2Foptions",
    "/option1#name=Size&table=https%3A%2F%2Fmerchant.example%2Foptions",
    "/option1#name=Size&table=%2Foptions%23name%3DSize", "/option1#name=Size&table=%252Foptions",
    "/option1#name=Size&table=%2foptions", "/option1#name=Size&table=%FF",
])
def test_table_reference_is_a_canonical_local_pointer(invalid):
    with pytest.raises(ValueError):
        parse_locator(invalid)


def test_table_requires_a_guard_and_old_locators_keep_the_same_meaning():
    with pytest.raises(ValueError, match="name guard"):
        format_locator(("option1",), table=("options",))
    assert parse_locator("/variants/*/option1#name=Size") == Locator(("variants", None, "option1"), "Size")
    assert parse_locator("/pairs/*/value#name=A%26table%3D%2Fdecoy").selector == "A&table=/decoy"


def test_updated_paths_cannot_silently_drop_a_trust_reducing_source_policy():
    records = [{"sku": "a", "options": [{"name": "Size", "values": ["M"]}], "option1": "M"}]
    policy = SourcePolicy(liability=Liability.SELLER_STATED)
    with pytest.raises(ValueError, match="legacy numbered-option locator"):
        propose_schema(records, category_id="migration", source_policies={"/option1#name=Size": policy})
    proposal = propose_schema(records, category_id="migration", source_policies={
        "/option1#name=Size&table=%2Foptions": policy})
    assert proposal.proposed_schema.field_profiles[0].liability is Liability.SELLER_STATED
    assert proposal.report.attributes[0].floor_eligible.numerator == 0
