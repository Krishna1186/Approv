"""Network-free regressions for acquisition accounting and independent source checks."""
from copy import deepcopy
import json

import pytest

from approv.schema import propose_schema
from approv.schema.public_catalogues import audit, fetch, oracle
from approv.types.core import Money, OrderLine, Term


@pytest.fixture
def records():
    return [{"id": 17, "title": "Example", "options": [{"name": "Finish / tone", "position": 1, "values": ["Blue", "Red"]}],
             "variants": [{"id": 171, "sku": "one", "option1": "Blue", "price": "12.00",
                           "featured_image": {"width": 1600, "height": 900, "src": "https://example.invalid/image.png"}},
                          {"id": 172, "sku": "two", "option1": "Red", "price": "12.00"}]}]


def test_key_uses_explicit_position_and_rejects_duplicate_table_positions(records):
    product = deepcopy(records[0])
    product["options"][0]["position"] = 2
    expected, ambiguous = oracle.option_key(product, {"option1": "wrong", "option2": "chosen"})
    assert expected[0]["raw"] == "chosen"
    assert expected[0]["field_name"] == (
        "/variants/*/option2#name=Finish%20%2F%20tone&table=%2Foptions")
    assert not ambiguous
    product["options"].append({"name": "Other", "position": 2, "values": []})
    assert oracle.option_key(product, {"option2": "chosen"}) == ([], [2])


def test_oracle_has_no_producer_or_algebra_import():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(oracle.__file__).read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names]
    assert not any(name and name.startswith("approv") for name in imports)


def test_probes_select_exact_variant(records):
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["correct_selected_slots"]["numerator"] == 2
    assert result["rates"]["wrong_selected_slots"]["numerator"] == 0
    assert result["human_review_status"] == "pending"


def test_image_metadata_is_never_proposed_as_a_product_attribute(records):
    proposal = propose_schema(records, category_id="synthetic")
    assert not [p for p in proposal.proposed_schema.field_profiles if "/featured_image/" in p.field_name]


def test_published_selected_label_counts_agree_with_reader():
    records = [{"id": 1, "options": [{"name": "Waist/Length", "values": ["30/32L", "34/32L"]}],
                "variants": [{"id": 11, "sku": "a", "option1": "30/32L"},
                             {"id": 12, "sku": "b", "option1": "34/32L"}]}]
    proposal = propose_schema(records, category_id="synthetic")
    result = audit.check_probes(records, proposal)
    assert result["rates"]["variants_with_publication_reader_disagreement"]["numerator"] == 0


def test_independent_probe_catches_confident_wrong_variant(monkeypatch, records):
    reader = audit.evidence_from_snapshot
    def wrong_reader(snapshot, schema):
        return tuple(e.model_copy(update={"value": Term(surface="borrowed-neighbour")}) if "#name=" in e.field_name else e
                     for e in reader(snapshot, schema))
    monkeypatch.setattr(audit, "evidence_from_snapshot", wrong_reader)
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["wrong_selected_slots"]["numerator"] == 2
    assert result["rates"]["missing_selected_slots"]["numerator"] == 0


def test_no_evidence_is_counted_separately_from_wrong_evidence(monkeypatch, records):
    monkeypatch.setattr(audit, "evidence_from_snapshot", lambda *_: ())
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["missing_selected_slots"]["numerator"] == 2
    assert result["rates"]["wrong_selected_slots"]["numerator"] == 0


def test_reader_error_keeps_expected_slots_in_denominator(monkeypatch, records):
    def broken_reader(*_):
        raise ValueError("unreadable")
    monkeypatch.setattr(audit, "evidence_from_snapshot", broken_reader)
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["unread_selected_slots"]["numerator"] == 2
    assert result["rates"]["correct_selected_slots"]["denominator"] == 2


def test_wrong_attribute_is_not_counted_as_absence(monkeypatch, records):
    reader = audit.evidence_from_snapshot
    def wrong_reader(snapshot, schema):
        return tuple(e.model_copy(update={"attribute": "unrelated"}) if "#name=" in e.field_name else e
                     for e in reader(snapshot, schema))
    monkeypatch.setattr(audit, "evidence_from_snapshot", wrong_reader)
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["wrong_selected_slots"]["numerator"] == 2
    assert result["rates"]["missing_selected_slots"]["numerator"] == 0


def test_raw_order_identifiers_do_not_accept_title_as_sku(records):
    product = records[0]
    product["variants"][0].update(id=None, sku="", title="some name")
    counts, _ = oracle.raw_inventory(records)
    assert counts["variant_rows"] == 2
    assert counts["no_order_addressable_identifier"] == 1
    assert counts["blank_sku"] == 1


def test_missing_sku_does_not_manufacture_a_binding_failure(records):
    records[0]["variants"][0]["sku"] = ""
    result = audit.check_probes(records, propose_schema(records, category_id="synthetic"))
    assert result["rates"]["binding_unassessed_missing_sku"]["numerator"] == 1
    assert result["rates"]["reader_or_binding_errors"]["numerator"] == 0
    assert result["rates"]["correct_selected_slots"]["numerator"] == 2


def test_sample_is_stable_bounded_and_does_not_depend_on_schema(records):
    assert oracle.probe_rows(records, 1) == oracle.probe_rows(deepcopy(records), 1)
    assert len(oracle.probe_rows(records, 1)) == 1
    assert oracle.probe_rows([], 20) == []


@pytest.mark.parametrize(("raw", "value", "expected"), [
    ("Red", {"kind": "term", "surface": "Blue"}, False),
    ("9 M", {"kind": "term", "surface": "9 M"}, True),
    ("9 M", {"kind": "quantity", "magnitude": "9", "unit": "m"}, True),
    ("2 grams", {"kind": "quantity", "magnitude": "2", "unit": "g"}, None),
    ("USD 12", {"kind": "money", "amount": "12", "currency": "USD"}, True),
    ("$12", {"kind": "money", "amount": "12", "currency": "USD"}, False),
])
def test_oracle_type_scope_is_explicit(raw, value, expected):
    assert oracle.value_matches_raw(raw, value) is expected


def fake_responses(monkeypatch, *, products, terms="Plain public terms", robots="User-agent: *\nAllow: /", status=200):
    calls = []
    def get(url, directory, name, interval=1.5):
        calls.append(url)
        body = (robots if name == "robots" else terms if name == "terms" else json.dumps({"products": products})).encode()
        return {"status": status if name.startswith("products-") else 200, "requested_url": url,
                "started_at": "2026-09-14T00:00:00+00:00", "final_url": url, "sha256": "constant-page"}, body
    monkeypatch.setattr(fetch, "get", get)
    return calls


def test_fetch_stops_on_repeated_page_and_keeps_partial_denominator(monkeypatch, tmp_path):
    products = [{"id": n} for n in range(250)]
    calls = fake_responses(monkeypatch, products=products)
    manifest = fetch.fetch_store(["test", "Example", "example.invalid"], tmp_path)
    assert manifest["status"] == "repeated_page"
    assert manifest["products"] == 250
    assert not manifest["pagination_complete"]
    assert len(calls) == 4


@pytest.mark.parametrize("control", ["terms", "robots", "http"])
def test_access_controls_stop_without_backend_or_retry(monkeypatch, tmp_path, control):
    calls = fake_responses(monkeypatch, products=[], terms="Do not scrape data" if control == "terms" else "Public terms",
                           robots="User-agent: *\nDisallow: /products.json" if control == "robots" else "User-agent: *\nAllow: /",
                           status=403 if control == "http" else 200)
    manifest = fetch.fetch_store(["test", "Example", "example.invalid"], tmp_path)
    assert manifest["products"] == 0
    assert len(calls) == (3 if control == "http" else 2)
    assert not manifest["pagination_complete"]


def test_cache_hash_is_verified_before_reuse(tmp_path):
    (tmp_path / "cached.body").write_bytes(b"changed")
    fetch.save(tmp_path / "cached.meta.json", {"body_file": "cached.body", "sha256": "not-the-hash"})
    with pytest.raises(ValueError, match="hash mismatch"):
        fetch.get("https://example.invalid", tmp_path, "cached")


def test_policy_json_is_decoded_before_keyword_screening():
    assert fetch.policy_excerpts(json.dumps({"policy": {"body": "Do not cr\u0061wl or scrape"}}))


def test_failed_store_is_not_a_zero_missingness_catalogue(tmp_path):
    audit.write_index([{"host": "example.invalid", "merchant": "<script>", "sector": "test", "status": "terms_unavailable"}], tmp_path, "revision")
    summary = json.loads((tmp_path / "index.json").read_text())
    assert summary["metrics"]["retrieved_nonempty_catalogues"]["denominator"] == 1
    assert summary["metrics"]["usable_proposals_retrieved"]["rate"] is None
    html = (tmp_path / "index.html").read_text()
    assert "Unmeasured" in html and "<script>" not in html and "&lt;script&gt;" in html


def read_selected(product, proposal, index=0):
    """What the deployed reader emits for one ordered variant of one product."""
    variant = product["variants"][index]
    order = OrderLine(order_id="probe", product_id=str(product["id"]), sku=str(variant["sku"]),
                      variant_id=str(variant["id"]), quantity=1,
                      unit_price=Money(amount=0, currency="XXX"))
    return audit.evidence_from_snapshot(audit.selected_listing(product, order),
                                        proposal.proposed_schema)


def test_prose_holding_two_quantities_is_read_by_neither_half(records):
    """DR 0029, in the shape the cohort found it.

    ILIA writes `Size: 1 fl oz | 30 ml` into a description. Derivation refused it and the
    reader emitted it anyway, as a nominal label on a merchant-guaranteed source -- and a
    label of those exact characters matches no request anybody will ever make, so the
    attribute could only ever come back violated. Both halves now refuse it, by one rule.
    """
    product = deepcopy(records[0])
    product["body_html"] = "<p><strong>What else:</strong><br>Size: 1 fl oz | 30 ml</p>"
    proposal = propose_schema([product], category_id="synthetic")
    prose = [source for row in proposal.report.attributes for source in row.sources
             if source.field_name == "/body_html"]
    assert all(source.published.numerator == 0 for source in prose)
    assert not [e for e in read_selected(product, proposal) if e.field_name == "/body_html"]


def test_a_label_that_only_failed_to_type_is_read_by_both_halves(records):
    """The counter-case, and why DR 0029 is not simply "refuse harder".

    `3XL` is a size label that failed to type because XL is not a unit, and here it sits in
    a plain field rather than a selector. The reader always read it; derivation did not
    count it as published unless a selector had named it. Now both do, and a partner's
    report stops understating an axis we verify.
    """
    product = deepcopy(records[0])
    # A sibling that types cleanly is what settles the attribute as NOMINAL; `3XL` alone
    # gives the schema no dimension to read it in, which is a different gap.
    product["variants"][0]["size"] = "3XL"
    product["variants"][1]["size"] = "Medium"
    proposal = propose_schema([product], category_id="synthetic")
    published = [source for row in proposal.report.attributes for source in row.sources
                 if source.field_name == "/variants/*/size"]
    assert published and all(source.published.numerator == 2 for source in published)
    assert [e for e in read_selected(product, proposal) if e.field_name == "/variants/*/size"]
