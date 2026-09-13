import json
from pathlib import Path

import pytest

from approv.schema import propose_schema
from approv.schema.locators import Locator, format_locator, parse_locator


@pytest.mark.parametrize("parts,label", [
    (("details", "size"), None),
    (("stock", "editions", None, "selections", None, "selection"), "Bore"),
    (("a.b", "a/b", "~1", "*", "#name=x"), "Couleur / été #1"),
    (("options", None, "value"), " Space + % "),
])
def test_locator_codec_preserves_keys_and_exact_selector(parts, label):
    encoded = format_locator(parts, selector=label)
    assert parse_locator(encoded) == Locator(parts, label)
    assert format_locator(parse_locator(encoded).segments, selector=label) == encoded


@pytest.mark.parametrize("invalid", [
    "details.size", "", "/", "//size", "/a~", "/a~4", "/a*b", "/a#other=x",
    "/a#name=", "/a#name=%", "/a#name=%FF", "/a#name=two words",
    "/a#name=Size#name=Color", "/a#name=%53ize", "/a#name=%c3%a9",
])
def test_malformed_locators_never_fall_back_to_another_lookup(invalid):
    with pytest.raises(ValueError):
        parse_locator(invalid)


def test_every_profile_in_acceptance_fixtures_obeys_the_shared_wire_grammar():
    root = Path(__file__).parent / "fixtures"
    for name in ("industrial_catalogue.json", "shopify_cached_sample.json", "shopify_raw_sample.json"):
        proposal = propose_schema(json.loads((root / name).read_text(encoding="utf-8")), category_id=name)
        assert proposal.proposed_schema.field_profiles
        for profile in proposal.proposed_schema.field_profiles:
            locator = parse_locator(profile.field_name)
            assert format_locator(locator.segments, selector=locator.selector) == profile.field_name
