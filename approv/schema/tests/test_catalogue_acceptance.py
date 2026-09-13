"""Representative acceptance by default; full local catalogues on explicit request.

Neither test reads the hand-authored CategorySchema or the harness's evidence. The
cached study test only unwraps merchant details, listing identity and product URL.
The raw export test only unwraps the host -> products envelope.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from approv.schema import propose_schema
from approv.types.core import Dimension

FIXTURES = Path(__file__).parent / "fixtures"

def cache_file(relative):
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "cache" / relative
        if candidate.is_file():
            return candidate
    pytest.skip(f"local catalogue cache absent: {relative}")


def check_cached_catalogue(records):
    proposal = propose_schema(records, category_id="acceptance.shopify.cached",
                              observed_at=datetime(2026, 9, 12, tzinfo=timezone.utc))
    report = {a.attribute: a for a in proposal.report.attributes}
    assert proposal.report.listings == len(records)
    for name in ("brand", "size", "color", "product_type", "availability"):
        assert report[name].dimension is Dimension.NOMINAL
    assert report["price"].dimension is Dimension.MONEY
    for name in ("size", "color"):
        assert report[name].variant_groups.numerator > 0
        assert report[name].variant_basis == ("sibling_value_variation",)
        assert any(p.is_variant_axis and name in p.attributes for p in proposal.proposed_schema.field_profiles)
    assert not any(p.is_variant_axis and "price" in p.attributes for p in proposal.proposed_schema.field_profiles)
    assert proposal.proposed_schema.floor <= {"size", "color"}
    for attribute in ("size", "color", "price", "brand"):
        expected = sum(bool(r["details"].get(attribute)) for r in records)
        # Counts are independently calculated over every row supplied to this check.
        assert report[attribute].published.numerator == expected
        assert report[attribute].published.denominator == len(records)
    assert proposal.status == "proposed"


def check_raw_catalogue(records):
    expected = sum(len(record.get("variants", [])) or 1 for record in records)
    proposal = propose_schema(records, category_id="acceptance.shopify.raw",
                              observed_at=datetime(2026, 9, 12, tzinfo=timezone.utc))
    report = {a.attribute: a for a in proposal.report.attributes}
    assert proposal.report.listings == expected
    assert report["size"].dimension is Dimension.NOMINAL
    assert report["size"].variant_groups.numerator > 0
    assert "named_selector" in report["size"].variant_basis
    assert report["grams"].dimension is Dimension.MASS
    assert report["grams"].variant_groups.numerator == 0
    assert report["price"].dimension is Dimension.MONEY
    assert report["price"].published.numerator == 0  # raw export declares no currency
    assert not any(a.name.startswith("option1") for a in proposal.proposed_schema.attributes)


def test_cached_shopify_sample_without_existing_schema_or_evidence():
    records = json.loads((FIXTURES / "shopify_cached_sample.json").read_text(encoding="utf-8"))
    check_cached_catalogue(records)


def test_raw_shopify_sample_discovers_option_names_and_every_sampled_variant():
    records = json.loads((FIXTURES / "shopify_raw_sample.json").read_text(encoding="utf-8"))
    check_raw_catalogue(records)


@pytest.mark.schema_exhaustive
def test_all_cached_shopify_variants_without_existing_schema_or_evidence():
    pack = json.loads(cache_file("shopping-study/shopper-v3.json").read_text(encoding="utf-8"))
    records = [{"id": p["id"], "source_url": p["source_url"], "details": p["details"]}
               for p in pack["inventory"]["products"]]
    assert len(records) == 33485
    check_cached_catalogue(records)


@pytest.mark.schema_exhaustive
def test_raw_export_discovers_option_names_and_every_sold_variant():
    hosts = json.loads(cache_file("shopify-raw.json").read_text(encoding="utf-8"))
    records = [dict(product, merchant_id=host) for host, products in hosts for product in products]
    check_raw_catalogue(records)
