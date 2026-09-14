"""The backtest: what a partner's first export must never be able to do quietly.

The importer is the partner's first experience of Approv, and its failure mode is not
crashing - it is being helpful. A date read one of two ways, a comma taken for a decimal
point, a row dropped because it did not parse, a column matched because the name was
close: each of those produces a report about a dataset nobody has seen, and none of them
looks like an error.

So these tests are mostly about refusals, and each asserts the refusal **says where**. A
rejection without a line number is a rejection a partner cannot act on, which in practice
is a partner who stops sending exports.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from approv.receipts.chain import generate_key
from approv.receipts.store import ReceiptStore
from approv.report import backtest as bt
from approv.report import importing as imp
from approv.report import tiers as t
from approv.report.importing import Ambiguous, Column, ExportRejected, Severity
from approv.report.render import to_text
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Criticality, Dimension, FieldProfile,
    Liability,
)

FIXTURES = Path(__file__).parent / "fixtures" / "backtest"
MESSY = FIXTURES / "messy"
BROKEN = FIXTURES / "broken"

SCHEMA = CategorySchema(
    category_id="bedding", version="pilot-1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL,
                      criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL,
                      criticality=Criticality.HARD),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     is_variant_axis=True, certainty=Certainty.EXACT,
                     liability=Liability.MERCHANT_GUARANTEED),
    ))
SCHEMAS = {"bedding": SCHEMA}


def problems_of(directory, **kw):
    try:
        bt.load(directory, merchant_id="hearth-and-loom", **kw)
    except ExportRejected as rejected:
        return list(rejected.problems)
    return []


def load_messy(**kw):
    return bt.load(MESSY, merchant_id="hearth-and-loom", day_first=True, window_days=21,
                   **kw)


def run_messy(tmp_path, **kw):
    store = ReceiptStore(tmp_path / "receipts.sqlite", namespace="sandbox")
    return bt.run(load_messy(), schemas=SCHEMAS, store=store, signing_key=generate_key(),
                  as_of=datetime(2026, 6, 1, tzinfo=timezone.utc), **kw)


# --- never coerce silently ----------------------------------------------------------------

def test_an_ambiguous_date_is_refused_and_says_which_line():
    """`03/04/2026` is the third of April and the fourth of March. An importer that picks
    one has invented a fact about a return window, and the number that fact lands in is a
    precision figure."""
    problems = problems_of(MESSY, window_days=21)
    ambiguous = [p for p in problems if p.code == "ambiguous"]

    assert ambiguous, "the fixture's dates are ambiguous and were read anyway"
    first = ambiguous[0]
    assert first.line and first.column
    assert "Approv will not pick one" in first.detail
    # And declaring the convention reads the same file without complaint.
    assert not [p for p in load_messy().problems if p.code == "ambiguous"]


def test_a_date_that_reads_the_same_either_way_is_not_ambiguous():
    """`04/04/2026` has exactly one meaning. Refusing it would be refusing a value for
    looking like a class it is not in."""
    parsed, _ = imp.parse_timestamp("04/04/2026")
    assert parsed.date().isoformat() == "2026-04-04"


def test_a_comma_that_might_be_a_decimal_point_is_refused():
    """A unit price is what a refund is denominated in. `1,23` is one and twenty-three
    hundredths in half of Europe and one hundred and twenty-three in the other half."""
    with pytest.raises(Ambiguous) as caught:
        imp.parse_money("1,23")
    assert "decimal point" in str(caught.value)
    # The two that *are* readable, because the last separator settles it.
    assert imp.parse_money("1.234,56") == imp.parse_money("1,234.56")
    assert imp.parse_money("GBP 1,234") == 1234


def test_a_missing_required_value_is_refused_with_its_line_and_column(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("order_id,quantity\nSO-1,\n", encoding="utf-8")
    _, _, problems = imp.read_rows(path, (Column("order_id", required=True),
                                          Column("quantity", required=True,
                                                 parse=imp.parse_int)))
    bad = [p for p in problems if p.severity is Severity.FATAL]
    assert len(bad) == 1
    assert (bad[0].line, bad[0].column, bad[0].code) == (2, "quantity", "missing_value")


def test_no_row_is_dropped_without_being_counted(tmp_path):
    """The quiet failure. A file of 40,000 rows of which 300 parsed describes the
    partner's business as a fortieth of its size, and nothing about the report would say
    so."""
    path = tmp_path / "orders.csv"
    path.write_text("order_id,quantity\nSO-1,2\nSO-2,many\nSO-3,3\n", encoding="utf-8")
    rows, mapped, problems = imp.read_rows(
        path, (Column("order_id", required=True),
               Column("quantity", required=True, parse=imp.parse_int)))

    assert (mapped.rows_seen, mapped.rows_read) == (3, 2)
    assert any(p.code == "rows_dropped" and "1 of 3" in p.detail for p in problems)


# --- read what an export actually looks like ----------------------------------------------

def test_a_byte_order_mark_does_not_hide_the_first_column():
    """The single most common reason a required column "goes missing": a spreadsheet on
    Windows writes a BOM and the first header becomes `﻿Order Ref.`."""
    export = load_messy()
    assert export.orders, "the BOM ate the order_id column"
    assert any(p.code == "byte_order_mark" for p in export.problems)


def test_a_file_that_is_not_utf8_is_read_and_the_partner_is_told_which_byte():
    """A customer's smart quote from a Windows desk. Read as cp1252 rather than refused,
    and never silently: a mojibake apostrophe quoted back on a dispute artifact months
    later is worse than a note today."""
    export = load_messy()
    note = next(p for p in export.problems if p.code == "not_utf8")
    assert "0x93" in note.detail and note.line
    assert note.severity is Severity.NOTE


def test_their_column_names_and_their_delimiter_both_resolve():
    """`Order Ref.` is `order_id` and a semicolon is a delimiter. Neither is a fuzzy
    match: case, spaces and punctuation are formatting, and nothing else is collapsed."""
    export = load_messy()
    mapped = export.mappings["orders"]
    assert mapped.by_column["order_id"] == "Order Ref."
    assert mapped.by_column["availability"] == "Stock Status"
    assert "Warehouse" in mapped.unmatched_headers, "their own columns are kept out, not fatal"


def test_a_required_column_that_is_missing_lists_every_name_that_was_tried(tmp_path):
    """A partner whose column is called `dispatch_reference` needs to know we looked for
    `order_id` and six other things, not that something went wrong."""
    path = tmp_path / "orders.csv"
    path.write_text("dispatch_reference,qty\nX,1\n", encoding="utf-8")
    _, _, problems = imp.read_rows(path, (Column("order_id", ("order", "order_ref"),
                                                 required=True),))
    assert problems[0].code == "missing_column"
    assert "order_ref" in problems[0].detail
    assert "dispatch_reference" in problems[0].detail, "their header is quoted back"


def test_an_exact_duplicate_is_collapsed_and_a_disagreeing_one_is_refused(tmp_path):
    """Not the same event. An export run twice and concatenated loses nothing by
    collapsing; two answers for one order line cannot be resolved by picking either."""
    export = load_messy()
    assert any(p.code == "duplicate_rows" for p in export.problems)
    assert len([r for r in export.orders if r.get("order_id") == "SO-1001"]) == 1

    path = tmp_path / "orders.csv"
    path.write_text("order_id,quantity\nSO-1,1\nSO-1,4\n", encoding="utf-8")
    rows, _, _ = imp.read_rows(path, (Column("order_id", required=True),
                                      Column("quantity", parse=imp.parse_int)))
    _, problems = imp.deduplicate(rows, lambda r: (r.get("order_id"),), file="orders.csv")
    assert problems[0].code == "conflicting_duplicate"
    assert "line 2" in problems[0].detail and problems[0].line == 3
    assert "quantity" in problems[0].detail


def test_an_order_with_no_catalogue_record_is_refused_rather_than_compared():
    """Running it would produce a receipt whose evidence side is empty, and an empty
    evidence side reads as "we checked and found nothing wrong"."""
    problems = problems_of(BROKEN)
    missing = next(p for p in problems if p.code == "no_catalogue_record")
    assert missing.line == 2 and "duvet-not-in-catalogue" in missing.detail
    assert "will not compare an order against a snapshot it does not have" in missing.detail


def test_an_outcome_for_an_order_we_never_saw_is_kept_and_not_fatal():
    """The most interesting row in the export: their returns desk saw an order Approv
    never did, which is the share of their traffic that is not reaching us."""
    export = load_messy()
    note = next(p for p in export.problems if p.code == "outcome_without_order")
    assert note.severity is Severity.NOTE
    assert "never reached Approv" in note.detail or "never reached" in note.detail


def test_an_event_word_is_mapped_and_a_reason_code_never_is(tmp_path):
    """`dispatched` and `shipped` are two names for one event; mapping them reads their
    file. `RTN-COLOUR` and `wrong_item` are two judgements, and mapping those would be
    making one of them up."""
    export = load_messy()
    events, problems = bt._outcome_events(export, correlations={})
    kinds = {e.kind.value for e in events}
    assert "shipped" in kinds, "`dispatched` is their word for it"
    assert "disputed" in kinds, "and `chargeback` is their word for that"
    assert not problems

    codes = {e.reason_code for e in events if e.reason_code}
    assert "RTN-COLOUR" in codes, "their unrecognised code is carried verbatim"
    feed = bt.from_order_outcomes(events, source=bt.FeedSource.PARTNER,
                                  as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert "RTN-COLOUR" in feed.unrecognised_codes
    assert all(o.wrong_item is False or o.reason_code_raw is None for o in feed.outcomes)


def test_an_event_word_we_do_not_know_is_refused_with_its_line():
    """Bucketing it as `other` would put an event of unknown meaning into a denominator."""
    export = bt._lenient(BROKEN, "hearth-and-loom", None, None, [])
    _, problems = bt._outcome_events(export, correlations={})
    assert problems[0].code == "unknown_event"
    assert problems[0].line == 2 and "vanished" in problems[0].detail


# --- the dry run ---------------------------------------------------------------------------

def test_the_dry_run_verifies_nothing_and_still_describes_a_broken_export():
    """The artifact the founder sends back after the first data conversation. A dry run
    that refused to answer for a broken export would be useless exactly when it is needed:
    the first export is usually broken and the point is to say how."""
    result = bt.survey(MESSY, merchant_id="hearth-and-loom", window_days=21)
    page = bt.survey_text(result)

    assert result.readable is False, "undeclared dates, so it cannot be run yet"
    assert result.counts["orders"] > 0, "and it still says how big the export is"
    assert "No verification was run" in page
    assert "THIS EXPORT CANNOT BE RUN YET" in page

    # The rung is computed over the rows that parsed, and rows were refused - so it reads
    # lower than the same export reads once the date convention is declared. Saying "you
    # are at GOOD" over a broken export would send a partner off to add fields they
    # already have instead of fixing a format.
    assert result.tier is t.Tier.GOOD
    assert bt.survey(MESSY, merchant_id="hearth-and-loom", window_days=21,
                     day_first=True).tier is t.Tier.BEST
    assert "AT LEAST" in page
    assert "is a floor rather than a reading" in " ".join(page.split())


def test_the_dry_run_names_the_rung_and_what_reaches_the_next(tmp_path):
    """One question, answered without running the engine: which rung, and what is missing."""
    export = tmp_path / "export"
    export.mkdir()
    (export / "orders.csv").write_text(
        "order_id,line_id,category_id,product_id,sku,quantity,unit_price,currency,"
        "ordered_at\nSO-1,1,bedding,duvet-1,SKU-1,1,118.00,GBP,2026-04-03\n",
        encoding="utf-8")
    (export / "catalogue.json").write_text(
        json.dumps({"duvet-1": {"variant": {"size": "King", "colour": "Frost"}}}),
        encoding="utf-8")
    (export / "outcomes.csv").write_text(
        "order_id,line_id,event,date\nSO-1,1,returned,2026-04-10\n", encoding="utf-8")

    result = bt.survey(export, merchant_id="hearth-and-loom")
    page = bt.survey_text(result)

    assert result.tier is t.Tier.RETURNS_ONLY
    assert "TO REACH MINIMUM" in page
    assert "ship date" in page
    assert "100% by construction" in page, "and why the rung above matters"


def test_a_column_that_exists_and_is_empty_buys_nothing(tmp_path):
    """The rung is read off the values, not off the header. A `reason_code` column that
    is blank in every row would otherwise put a rung on the page that the numbers
    underneath then refuse."""
    export = tmp_path / "export"
    export.mkdir()
    (export / "orders.csv").write_text(
        "order_id,line_id,category_id,product_id,sku,quantity,unit_price,currency,"
        "ordered_at\nSO-1,1,bedding,duvet-1,SKU-1,1,118.00,GBP,2026-04-03\n",
        encoding="utf-8")
    (export / "catalogue.json").write_text(
        json.dumps({"duvet-1": {"variant": {"size": "King"}}}), encoding="utf-8")
    (export / "outcomes.csv").write_text(
        "order_id,line_id,event,date,shipped_at,window_days,return_code\n"
        "SO-1,1,returned,2026-04-10,2026-04-04,21,\n", encoding="utf-8")

    assert bt.survey(export, merchant_id="hearth-and-loom").tier is t.Tier.MINIMUM


# --- the run -------------------------------------------------------------------------------

def test_the_whole_path_runs_from_files_to_a_verifiable_ledger(tmp_path):
    """Files -> batch verification -> stored receipts -> the report, with nothing of the
    partner's touched and a chain a stranger can check."""
    result = run_messy(tmp_path)

    assert result.verified == len(load_messy().orders) == 12
    assert result.records, "the comparisons are sealed"
    assert all(r.hash and r.signature for r in result.records)
    assert result.document.tier is t.Tier.BEST
    text = to_text(result.document)
    assert "12" in text
    assert result.throughput > 0


def test_a_backtest_receipt_is_never_backdated(tmp_path):
    """A receipt that claimed to have been written at the time of a sale it was not
    present for would be the one forgery this whole system exists to make impossible."""
    result = run_messy(tmp_path)
    ordered = [row.get("ordered_at") for row in load_messy().orders]

    assert all(r.timestamp > max(ordered)
               for r in list(result.records) + list(result.evidence_only))
    assert "historical" in result.document.period
    assert "2026-04-03" in result.document.period, "the export's own dates, in the label"
    assert any("never when the order was placed" in c for c in result.document.caveats)


def test_re_running_a_backtest_returns_the_same_receipts(tmp_path):
    """A partner fixes one column and resubmits. The ids are derived deterministically
    from merchant, order and line precisely so that the second run is a retry rather than
    a second ledger of the same week."""
    store = ReceiptStore(tmp_path / "receipts.sqlite", namespace="sandbox")
    key = generate_key()
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)
    first = bt.run(load_messy(), schemas=SCHEMAS, store=store, signing_key=key, as_of=as_of)
    second = bt.run(load_messy(), schemas=SCHEMAS, store=store, signing_key=key, as_of=as_of)

    assert first.records and [r.hash for r in first.records] == [r.hash for r in second.records]
    assert len(store.export()["records"]) == len(first.records), "one ledger, not two"


def test_a_derived_correlation_id_is_declared_as_one(tmp_path):
    """It is stable, which is what the store needs, and it is not unguessable, which is
    what DR 0016 §7 wants. Those are different properties and the report says which one
    this is."""
    result = run_messy(tmp_path)
    assert any("not unguessable" in c for c in result.document.caveats)
    assert all(r.correlation_id.startswith("bt-")
               for r in list(result.records) + list(result.evidence_only))


def test_a_run_with_no_extractor_says_so_on_the_page_and_counts_it(tmp_path):
    """The most dangerous thing about a backtest. Free text nothing read is recorded as no
    stated request, which is true of the run and is not a fact about their traffic - and
    the provenance rate underneath it would otherwise read as theirs."""
    result = run_messy(tmp_path)
    text = to_text(result.document)

    assert "no extractor configured" in " ".join(text.split())
    assert "NOT a fact about your traffic" in " ".join(text.split())
    assert "5 of 12 orders" in " ".join(text.split())


def test_an_extractor_removes_the_banner_rather_than_the_report_hiding_it(tmp_path):
    """The banner is a fact about the run, so it has to disappear when the run changes."""
    from approv.intake import Reading
    from approv.types.core import Channel, Constraint, Term

    def extract(text, schema):
        return Reading(constraints=(
            Constraint(attribute="size", value=Term(surface="King"),
                       channel=Channel.AGENT_MESSAGE, raw_text=text[:40]),))

    result = run_messy(tmp_path, extract=extract)
    assert "no extractor configured" not in " ".join(to_text(result.document).split())


def test_the_store_is_written_in_batches_not_one_row_at_a_time(tmp_path):
    """Per-order latency is irrelevant to a backtest and throughput is not: the store
    audits its history once per batch, so a per-row append audits it once per row."""
    store = ReceiptStore(tmp_path / "receipts.sqlite", namespace="sandbox")
    calls = []
    original = store.append_many

    def counted(records, key):
        records = list(records)
        calls.append(len(records))
        return original(records, key)

    store.append_many = counted
    bt.run(load_messy(), schemas=SCHEMAS, store=store, signing_key=generate_key(),
           chunk=5, as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    # Three chunks for twelve rows. A chunk containing a cart-only receipt is attempted
    # whole and then re-attempted without it, which is the seam below and shows up here
    # as an extra call rather than as a per-row loop.
    assert [n for n in calls if n == 5][:2] == [5, 5], calls
    assert len(calls) <= 6, "chunked, not one append per row: %r" % calls


def test_a_row_that_cannot_be_verified_does_not_cost_the_partner_the_other_rows(tmp_path):
    """One malformed order out of forty thousand must not lose the other 39,999 - and must
    not vanish either, so it is counted on the report and listed with its line number."""
    export = load_messy()
    export.orders[0].values["category_id"] = "furniture"          # no schema for it
    store = ReceiptStore(tmp_path / "receipts.sqlite", namespace="sandbox")
    result = bt.run(export, schemas=SCHEMAS, store=store, signing_key=generate_key(),
                    as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert result.verified == 11
    not_verified = [p for p in result.failed if p.code == "not_verified"]
    assert len(not_verified) == 1 and not_verified[0].line == 2
    assert "UnknownCategory" in not_verified[0].detail
    assert any("could not be verified" in c for c in result.document.caveats)


# --- the request shape is read, never invented ---------------------------------------------

def test_a_request_shape_is_inferred_from_populated_fields_and_never_from_a_value():
    """A row with filters and a query is an on-site search whatever it is labelled.
    Reading what is there is safe in a way that inventing what is not never is."""
    row = imp.Row(2, {"filters": {"size": "King"}, "query": "king duvet"})
    assert bt._artifact(row).shape.value == "search"

    row = imp.Row(3, {"fields": {"size": "King"}, "protocol": "acp"})
    assert bt._artifact(row).shape.value == "structured"

    assert bt._artifact(None).shape.value == "undeclared"


def test_a_shape_word_we_do_not_know_becomes_no_stated_request_with_the_reason():
    """Guessing which of four shapes a partner meant by `checkout_hint` would put a
    fabricated channel on a signed record, and channel is what coverage attaches to."""
    artifact = bt._artifact(imp.Row(2, {"shape": "checkout_hint"}))
    assert artifact.shape.value == "undeclared"
    assert "not one Approv knows" in artifact.why
