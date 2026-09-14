"""Shared producer/consumer contract. These tests run in the DEFAULT suite.

The consumer is surface's production reader, not a test resolver. The founder pinned
known gaps individually as strict xfails at 10cd413; passing clauses stay unmarked.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from approv.schema import propose_schema
from approv.schema.locators import VERSION
from approv.surface.verification import evidence_from_snapshot
from approv.types.core import Value

ROOT = Path(__file__).parent / "fixtures"
CONTRACT = json.loads((ROOT / "locator_contract.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in CONTRACT["positive"]}
VALUES = TypeAdapter(Value)


@lru_cache
def catalogue(name):
    records = json.loads((ROOT / name).read_text(encoding="utf-8"))
    return records, propose_schema(records, category_id="locator-contract." + name,
                                   observed_at=datetime(2026, 9, 13, tzinfo=timezone.utc))


def snapshot(case, *, keep_all_variants=False):
    records, proposal = catalogue(case["catalogue_fixture"])
    selected = deepcopy(records[case["record_index"]])
    if "variant_path" in case and not keep_all_variants:
        parent = selected
        for key in case["variant_path"][:-1]:
            parent = parent[key]
        key = case["variant_path"][-1]
        parent[key] = [parent[key][case["variant_index"]]]
    return selected, proposal


@pytest.mark.parametrize("case", CONTRACT["positive"], ids=lambda case: case["id"])
def test_derived_profiles_publish_the_fixture_contract(case):
    _, proposal = snapshot(case)
    assert CONTRACT["version"] == VERSION
    for expected in case["expected"]:
        matches = [profile for profile in proposal.proposed_schema.field_profiles
                   if profile.field_name == expected["field_name"] and expected["attribute"] in profile.attributes]
        assert len(matches) == 1
        assert matches[0].certainty.value == expected.get("certainty", "exact")
        row = next(row for row in proposal.report.attributes if row.attribute == expected["attribute"])
        assert row.published.numerator > 0, (row.attribute, row.published)


@pytest.mark.parametrize("case", CONTRACT["positive"], ids=lambda case: case["id"])
def test_surface_reads_nonzero_typed_evidence_from_the_catalogue_that_derived_its_schema(case):
    selected, proposal = snapshot(case)
    # This is conformance, not deployment or approval of the proposed schema.
    actual = evidence_from_snapshot(selected, proposal.proposed_schema)
    assert actual, f"{case['id']}: surface read zero evidence from a schema's own catalogue"
    for expected in case["expected"]:
        found = [e for e in actual if e.attribute == expected["attribute"] and e.field_name == expected["field_name"]]
        assert len(found) == 1, (case["id"], expected, found)
        assert found[0].value == VALUES.validate_python(expected["value"])
        assert found[0].certainty.value == expected.get("certainty", "exact")
        profile = next(p for p in proposal.proposed_schema.field_profiles if p.field_name == expected["field_name"])
        assert found[0].liability == profile.liability
        assert found[0].is_advice == profile.is_advice
    assert not {e.attribute for e in actual} & set(case.get("absent", ()))


@pytest.mark.parametrize("case", CONTRACT["negative"], ids=lambda case: case["id"])
def test_surface_never_borrows_evidence_from_a_different_selector_or_sku(case):
    selected, proposal = snapshot(CASES[case["base"]], keep_all_variants=case.get("keep_all_variants", False))
    for mutation in case.get("mutations", ()):
        parent = selected
        for key in mutation["path"][:-1]:
            parent = parent[key]
        parent[mutation["path"][-1]] = deepcopy(mutation["value"])
    try:
        actual = evidence_from_snapshot(selected, proposal.proposed_schema)
    except ValueError:
        return  # Explicit unreadable catalogue is also a fail-closed resolution.
    assert not {e.attribute for e in actual} & set(case["absent"])
