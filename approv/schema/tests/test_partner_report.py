import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from approv.schema import SchemaProposal, propose_schema
from approv.schema.models import PublicationPattern, Share
from approv.schema.report import ReportContext, build_partner_report, format_share, render_html
from approv.schema.report_cli import main


def audit(records):
    return propose_schema(records, category_id="fixture.industrial",
                          observed_at=datetime(2026, 9, 13, tzinfo=timezone.utc))


def test_report_reuses_measured_counts_and_separates_absent_unusable_and_prose():
    records = json.loads((Path(__file__).parent / "fixtures/industrial_catalogue.json").read_text())
    proposal = audit(records)
    report = build_partner_report(proposal, ReportContext("Estuary Works", "Fixture only", "industrial_catalogue.json"))
    rows = {row["attribute"]: row for row in report["attributes"]}
    for measured in proposal.report.attributes:
        row = rows[measured.attribute]
        assert row["published"] == measured.published.model_dump(mode="json")
        assert row["missing"]["numerator"] + row["present_but_unusable"]["numerator"] + row["published"]["numerator"] == 6
        assert all(row[key]["denominator"] == 6 for key in ("missing", "published", "present_but_unusable", "floor_eligible"))
    assert rows["invoice"]["missing"]["numerator"] == 1
    assert rows["invoice"]["present_but_unusable"]["numerator"] == 1
    assert rows["wall_thickness"]["published"]["numerator"] == 5
    assert rows["wall_thickness"]["floor_eligible"]["numerator"] == 0
    assert any("structured field" in action for action in rows["wall_thickness"]["actions"])
    assert report["measurement"]["cannot_verify"]["numerator"] == 2
    assert report["measurement"]["no_comparable_attributes"]["numerator"] == 1
    html = render_html(report)
    assert "4 / 6 listings" in html
    assert "proposal_requires_human_review" == report["status"]
    assert "share of traffic affected is unmeasured" in html
    assert "none-deterministic" in html and "Wilson 95%" in html
    assert proposal.status == "proposed"


def test_repair_scenarios_respect_other_floor_requirements():
    proposal = audit([{"size": "M", "colour": "blue"}, {"size": "L"}, {"colour": "red"}, {}])
    # A deliberately stricter review scenario, not a call to confirm_schema.
    proposal = proposal.model_copy(update={
        "report": proposal.report.model_copy(update={"floor": ("size", "colour"),
            "cannot_verify": proposal.report.cannot_verify.model_copy(update={"numerator": 3})}),
        "publication_patterns": (
            PublicationPattern(attributes=("size", "colour"), count=1),
            PublicationPattern(attributes=("size",), count=1),
            PublicationPattern(attributes=("colour",), count=1),
            PublicationPattern(attributes=(), count=1)),
    })
    report = build_partner_report(proposal, ReportContext("M", "S", "F"))
    for row in report["attributes"]:
        scenario = row["minimum_repair_scenario"]
        assert scenario["additional_listings_meeting_proposed_minimum"]["numerator"] == 1
        assert scenario["remaining_below_proposed_minimum"]["numerator"] == 2
        assert scenario["remaining_below_proposed_minimum"]["denominator"] == 4


def test_untrusted_report_text_is_escaped_and_empty_counts_are_not_rates():
    attack = '<script>alert("merchant")</script>'
    proposal = audit([{attack: "blue"}])
    html = render_html(build_partner_report(proposal, ReportContext(attack, attack, attack)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    empty = build_partner_report(audit([]), ReportContext("Empty", "No input", "empty.json"))
    assert "0 / 0 listings (rate unavailable; interval unavailable)" in render_html(empty)
    assert "0.0%" not in render_html(empty)
    with pytest.raises(TypeError):
        build_partner_report(proposal.report, ReportContext("M", "S", "F"))


def test_report_cli_generates_reproducible_handoff_and_roundtrip_proposal(tmp_path):
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps([{"fit": "narrow", "price": "19.90"}]))
    prefix = tmp_path / "partner"
    argv = [str(source), "--merchant", "Fixture", "--scope", "Supplied snapshot", "--category", "fixture",
            "--observed-at", "2026-09-13T00:00:00+00:00", "--output", str(prefix)]
    assert main(argv) == 0
    first = prefix.with_suffix(".html").read_bytes()
    report = json.loads(prefix.with_suffix(".json").read_text())
    restored = SchemaProposal.model_validate_json(Path(str(prefix) + ".proposal.json").read_text())
    assert report["proposal_id"] == restored.proposal_id
    price = next(row for row in report["attributes"] if row["attribute"] == "price")
    assert price["published"]["numerator"] == 0
    assert any("ISO currency" in action for action in price["actions"])
    assert main(argv) == 0
    assert prefix.with_suffix(".html").read_bytes() == first


def test_share_formatter_keeps_denominators_at_extreme_rates():
    share = Share(numerator=1, denominator=10001).model_dump(mode="json")
    assert format_share(share).startswith("1 / 10,001 listings (0.0100%;")
    zero = Share(numerator=0, denominator=33485).model_dump(mode="json")
    assert "0.0115%" in format_share(zero)


def test_successful_nominal_labels_do_not_trigger_unit_repairs_and_mixed_titles_need_mapping_review():
    records = [{"product_id": "P", "sku": "A", "size": "13.5", "title": "EUR 1.50"},
               {"product_id": "P", "sku": "B", "size": "M", "title": "A shirt"}]
    rows = {row["attribute"]: row for row in build_partner_report(audit(records), ReportContext("M", "S", "F"))["attributes"]}
    assert rows["size"]["published"]["numerator"] == 2
    assert not rows["size"]["actions"]
    assert rows["title"]["action_scope"] == "category_review"
    assert not any("ISO currency" in action for action in rows["title"]["actions"])
    assert any("source mapping" in action for action in rows["title"]["actions"])
