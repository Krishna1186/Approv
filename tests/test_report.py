"""The weekly partner report: what it must never claim, and what it must never omit.

The report goes to someone deciding whether to keep paying attention to us, which makes
it the second document in this repo where a sentence that reads well and is not supported
does real damage. The tests are the same two kinds as the dispute artifact's.

**Never overstate.** No rate without its denominator and its interval. No pooled number
across two populations. No outcome-derived figure without the provenance of the feed it
came from. No word that lets a shadow result read as a loss we prevented.

**Never omit.** A metric that cannot be computed is a row saying why. An absent row on a
report reads as a clean result, and on this report the absent rows are the ones a partner
would most want.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from approv.report import metrics as m
from approv.report import outcomes as o
from approv.report import tiers as t
from approv.report.document import CAVEATS, FIXTURE_WARNING, NO_OUTCOMES, SHADOW, build
from approv.report.render import to_html, to_text
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Completion, ComparisonRecord,
    Constraint, Criticality, Decision, Dimension, Evidence, FieldProfile, Finding,
    CheckKind, Liability, Money, OrderLine, Support, Term,
)

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)

SCHEMA = CategorySchema(
    category_id="bedding", version="1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ),
)


def flat(text):
    return " ".join(text.split())


def constraint(attribute="colour", source="acp.colour", channel=Channel.TOOL_ARGUMENT):
    return Constraint(attribute=attribute, value=Term(surface="Frost"), channel=channel,
                      source=source)


def finding(attribute="colour", support=Support.SATISFIED,
            criticality=Criticality.HARD):
    return Finding(check=CheckKind.SATISFACTION, attribute=attribute,
                   criticality=criticality, support=support, confidence=1.0, ceiling=1.0,
                   evidence=(Evidence(attribute=attribute, value=Term(surface="Frost"),
                                      field_name="variant.colour",
                                      liability=Liability.MERCHANT_GUARANTEED,
                                      certainty=Certainty.EXACT),))


def record(order_id="ORD-1", *, decision=Decision.ALLOW, source="acp.colour",
           constraints=None, findings=None, coverage=None, order=True,
           completion=Completion.COMPLETED, unread=(), completeness=(),
           correlation_id=None, **kw) -> ComparisonRecord:
    """A record built directly, so a population or a coverage class can be posed exactly.

    The report reads records; it never builds them. Going through `build_record` here
    would make half these cases unreachable — a record with a guaranteed finding *and* a
    refusal, say — and the report has to be right about records it did not produce.
    """
    constraints = (constraint(source=source),) if constraints is None else constraints
    findings = (finding(),) if findings is None else findings
    return ComparisonRecord(
        correlation_id=correlation_id or ("corr-" + order_id),
        merchant_id="hearth-and-loom", attestation=kw.pop("attestation", "neither"),
        category_id=kw.pop("category_id", "bedding"),
        category_version=kw.pop("category_version", "1"), locale="en-GB",
        request_text="a king duvet in Frost", request_constraints=constraints,
        product_id="duvet-1", product_snapshot={"product_id": "duvet-1"},
        snapshot_hash="d" * 64, completion=completion,
        order=OrderLine(order_id=order_id, line_id="1", product_id="duvet-1",
                        sku="SKU-1", quantity=1,
                        unit_price=Money(amount="118.00", currency="USD"))
        if order else None,
        findings=findings,
        coverage=coverage if coverage is not None else ("guaranteed",) * len(findings),
        completeness=completeness, unread=unread, decision=decision,
        model_version=kw.pop("model_version", "extract-v6"),
        evaluator_version=kw.pop("evaluator_version", "evaluator-v1"),
        prompt_version=kw.pop("prompt_version", "prompt-v6"), timestamp=NOW, **kw)


def outcome(order_id="ORD-1", status=o.Status.KEPT, reason=o.ReasonCode.UNCODED,
            attribute=None, correlation_id=None):
    return o.Outcome(order_id=order_id, line_id="1",
                     correlation_id=correlation_id or ("corr-" + order_id),
                     status=status, reason_code=reason, attribute=attribute)


def feed(*outs, source=o.FeedSource.PARTNER, description="weekly returns export"):
    return o.OutcomeFeed(source=source, description=description, outcomes=outs)


def returned(order_id, attribute=None):
    return outcome(order_id, o.Status.RETURNED, o.ReasonCode.NOT_AS_DESCRIBED, attribute)


# --- shadow mode is the framing, not a footnote -------------------------------------------

def test_the_report_says_it_blocked_nothing_before_it_says_anything_else():
    """A shadow result must never read as a loss prevented. The partner fulfilled every
    order in the period themselves; the word throughout is "would have"."""
    text = to_text(build([record()], feed(outcome())))
    assert flat(SHADOW) in flat(text)
    assert text.index("SHADOW MODE") < text.index("THE HEADLINE")


def test_no_rendering_claims_a_loss_was_prevented_or_money_saved():
    """The sentence a partner most wants to read is the one we cannot support. In shadow
    mode nothing was prevented, and a money-saved figure would be an estimate of a
    counterfactual we did not run."""
    document = build([record(decision=Decision.REFUSE), record("ORD-2")],
                     feed(returned("ORD-1"), outcome("ORD-2")))
    # The words appear once, inside the sentence that denies them. Removing the two
    # blocks we control and then banning the words from everything that is left is the
    # only version of this guard that keeps meaning something.
    for rendering in (to_text(document), to_html(document)):
        remainder = flat(rendering).lower()
        for sentence in (SHADOW, *CAVEATS):
            remainder = remainder.replace(flat(sentence).lower(), "")
        for claim in ("prevented", "saved", "avoided", "we stopped", "cost avoided"):
            assert claim not in remainder, claim
        assert "would have refused" in remainder


# --- invariant 6: no number without its denominator ---------------------------------------

def test_a_measure_cannot_hold_a_rate_without_the_counts_that_made_it():
    """The type is the enforcement. There is no path through `Measure` that yields a rate
    without a numerator, a denominator and an interval beside it."""
    measure = m.Measure(name="x", numerator=3, denominator=4, denominator_note="of four")
    assert measure.rate == 0.75
    low, high = measure.interval
    assert 0.0 <= low < measure.rate < high <= 1.0

    # No denominator is no rate, and no interval either. Not zero, and not one: an empty
    # population supplies no number, and inventing 0% for one would read as a result.
    empty = m.Measure(name="x", denominator=0)
    assert empty.rate is None and empty.interval is None and not empty.computable


def test_every_rate_on_the_page_is_printed_with_its_counts_and_its_interval():
    """Scanned off the rendering rather than asserted per metric, because the rule is
    about what reaches the reader: a percentage anywhere on the page must have `n of m`
    and a 95% interval in the same block."""
    records = [record("ORD-%d" % i, decision=Decision.REFUSE if i < 3 else Decision.ALLOW)
               for i in range(8)]
    text = to_text(build(records, feed(*(returned("ORD-%d" % i) for i in range(8)))))
    blocks = [b for b in text.split("\n\n") if "%" in b]
    assert blocks
    for block in blocks:
        if "95% CI" in block or "of" in block:
            continue
        raise AssertionError("a percentage with no denominator or interval:\n" + block)


def test_every_measure_carries_the_population_it_was_computed_over():
    document = build([record()], feed(outcome()))
    for block in document.populations:
        for measure in (block.precision, block.recall_strict, block.recall_flagged,
                        block.payout_proxy, block.aborted):
            assert measure.population, measure.name


# --- invariant 7: two populations, never pooled -------------------------------------------

def test_agent_stated_and_on_site_search_are_reported_separately_and_never_merged():
    """They carry different amounts of the customer's actual request and fail differently.
    A blended rate would describe neither population."""
    records = [record("ORD-1", source="acp.colour"),
               record("ORD-2", source="search.query"),
               record("ORD-3", source="search.filters.colour")]
    document = build(records, feed(outcome("ORD-1"), outcome("ORD-2"), outcome("ORD-3")))

    origins = [block.origin for block in document.populations]
    assert origins == [m.Origin.AGENT_STATED, m.Origin.ONSITE_SEARCH]
    assert [block.observed for block in document.populations] == [1, 2]


def test_the_module_exposes_no_way_to_pool_the_two_populations():
    """Structural, not a matter of discipline: there is no function here that takes two
    populations and returns one rate, so a later caller cannot accidentally average them."""
    joined = m.join([record()], feed(outcome()))
    for name in ("precision", "recall", "payout_proxy", "attribution", "open_window"):
        function = getattr(m, name)
        # Every outcome metric requires an origin. One that did not would be one that
        # could be called over everything at once.
        with pytest.raises(TypeError):
            function(joined)


def test_orders_with_no_stated_request_are_counted_but_never_measured():
    """Nothing was stated, so there is nothing to be right or wrong about. They belong in
    the volume table — they are the provenance gap — and in no rate."""
    records = [record("ORD-1", constraints=()), record("ORD-2")]
    document = build(records, feed(outcome("ORD-1"), outcome("ORD-2")))
    assert [b.origin for b in document.populations] == list(m.MEASURED)
    assert "orders with no stated request ....." in to_text(document).replace(".. ", "...")


# --- precision: the headline, and the easiest number to inflate ---------------------------

def test_precision_excludes_orders_whose_return_window_is_still_open():
    """Counting an unknown as a kept order inflates precision by exactly the share of
    returns that have not happened yet. Open orders are excluded and counted in their own
    row so the exclusion is visible rather than quiet."""
    records = [record("ORD-1", decision=Decision.REFUSE),
               record("ORD-2", decision=Decision.REFUSE),
               record("ORD-3", decision=Decision.REFUSE)]
    joined = m.join(records, feed(returned("ORD-1"), outcome("ORD-2"),
                                  outcome("ORD-3", o.Status.OPEN)))
    precision = m.precision(joined, m.Origin.AGENT_STATED)

    assert (precision.numerator, precision.denominator) == (1, 2)
    assert m.open_window(joined, m.Origin.AGENT_STATED).numerator == 1
    assert "still open are excluded" in precision.denominator_note


def test_precision_counts_only_the_partners_own_wrong_item_coding():
    """A changed mind is not a verification failure. Counting one would be claiming credit
    for their ordinary return rate."""
    records = [record("ORD-%d" % i, decision=Decision.REFUSE) for i in range(1, 4)]
    joined = m.join(records, feed(
        returned("ORD-1"),
        outcome("ORD-2", o.Status.RETURNED, o.ReasonCode.CHANGED_MIND),
        outcome("ORD-3", o.Status.RETURNED, o.ReasonCode.DAMAGED)))

    assert m.precision(joined, m.Origin.AGENT_STATED).numerator == 1


def test_a_thin_denominator_says_so_beside_the_rate():
    """Two of three is not 67%, it is three orders. The number is still printed — a
    suppressed one invites the reader to imagine a worse one — with the interval and a
    sentence saying to read it instead."""
    records = [record("ORD-%d" % i, decision=Decision.REFUSE) for i in range(3)]
    joined = m.join(records, feed(*(returned("ORD-%d" % i) for i in range(3))))
    assert m.precision(joined, m.Origin.AGENT_STATED).thin

    text = to_text(build(records, feed(*(returned("ORD-%d" % i) for i in range(3)))))
    assert "Read the interval, not the rate" in flat(text)


# --- recall, both readings of it ----------------------------------------------------------

def test_recall_is_reported_strictly_and_broadly_because_flagged_is_ambiguous():
    """Left to pick, a reader picks the flattering one. The strict number counts refusals;
    the broad one counts escalations too, and in shadow mode nobody acted on those."""
    records = [record("ORD-1", decision=Decision.REFUSE),
               record("ORD-2", decision=Decision.CONFIRM),
               record("ORD-3", decision=Decision.ALLOW)]
    joined = m.join(records, feed(returned("ORD-1"), returned("ORD-2"), returned("ORD-3")))

    strict = m.recall(joined, m.Origin.AGENT_STATED)
    broad = m.recall(joined, m.Origin.AGENT_STATED, flagged=True)
    assert (strict.numerator, strict.denominator) == (1, 3)
    assert (broad.numerator, broad.denominator) == (2, 3)
    text = to_text(build(records, joined.feed))
    assert "counting refusals and escalations" in text


# --- attribution --------------------------------------------------------------------------

def test_attribution_partitions_every_wrong_item_return():
    """Five buckets, and they sum. A return that fell out of the table would be one the
    report quietly declined to explain."""
    records = [record("ORD-1", findings=(finding(support=Support.VIOLATED),),
                      coverage=("refused",)),
               record("ORD-2"),
               record("ORD-3", constraints=(), findings=(), coverage=()),
               record("ORD-4", unread=("Unsupported requirement: hotel weight",),
                      findings=(finding(support=Support.UNSTATED),),
                      coverage=("out_of_coverage",))]
    joined = m.join(records, feed(*(returned("ORD-%d" % i) for i in range(1, 5))))
    table = m.attribution(joined, m.Origin.AGENT_STATED)

    assert sum(table.counts.values()) == table.total
    assert table.counts[m.Attribution.AGENT_AGAINST_REQUEST] == 1
    assert table.counts[m.Attribution.VERIFIED_AND_STILL_WRONG] == 1
    assert table.counts[m.Attribution.APPROV_DID_NOT_READ] == 1


def test_our_own_failure_to_read_is_never_hidden_behind_nobody_asked():
    """An unread requirement looks exactly like silence from inside the engine, and the two
    attribute to opposite parties. Ours is checked first."""
    unread = record("ORD-1", unread=("Unsupported requirement: hotel weight",),
                    completeness=("weave",),
                    findings=(finding(support=Support.UNSTATED),),
                    coverage=("out_of_coverage",))
    assert m.attribute_return(unread, returned("ORD-1", attribute="weave")) is \
        m.Attribution.APPROV_DID_NOT_READ


def test_a_verified_attribute_that_still_came_back_is_not_called_a_catalogue_error():
    """From our side a catalogue that published the wrong value and a warehouse that
    shipped the wrong item are the same event. Naming it a catalogue error would assert a
    fault the record cannot establish, in a report addressed to the party being blamed."""
    verified = record("ORD-1")
    assert m.attribute_return(verified, returned("ORD-1", attribute="colour")) is \
        m.Attribution.VERIFIED_AND_STILL_WRONG
    text = m.ATTRIBUTION_MEANS[m.Attribution.VERIFIED_AND_STILL_WRONG]
    assert "cannot tell those two apart" in text
    assert "catalogue error" not in to_text(build([verified],
                                                  feed(returned("ORD-1")))).lower()


def test_the_report_says_how_much_of_the_attribution_rests_on_the_weaker_instrument():
    """Where the desk coded the attribute, that coding decides it. Where it did not, the
    record as a whole does, and a reader is entitled to know how many rows are which."""
    records = [record("ORD-1"), record("ORD-2")]
    joined = m.join(records, feed(returned("ORD-1", attribute="colour"),
                                  returned("ORD-2")))
    table = m.attribution(joined, m.Origin.AGENT_STATED)
    assert (table.total, table.coded) == (2, 1)
    assert "attributed from your desk's own attribute coding" in to_text(
        build(records, joined.feed))


# --- the payout proxy ---------------------------------------------------------------------

def test_the_payout_proxy_is_never_presented_as_a_payout():
    """PRD §6: no coverage contract exists and every term of one is open. This is the count
    of orders where a guarantee would have been tested, and it says so wherever it appears."""
    records = [record("ORD-1"), record("ORD-2", coverage=("out_of_coverage",))]
    joined = m.join(records, feed(returned("ORD-1"), returned("ORD-2")))
    proxy = m.payout_proxy(joined, m.Origin.AGENT_STATED)

    assert (proxy.numerator, proxy.denominator) == (1, 1)
    text = to_text(build(records, joined.feed))
    assert "A proxy and not a payout" in flat(text)
    # Word boundaries, because "would have allowed" contains "owed" and the thing being
    # banned is the language of a debt, not the letters.
    assert not re.search(r"we will pay|owed|payable", text.lower())


# --- provenance and the invisible denominator ---------------------------------------------

def test_provenance_says_its_denominator_is_orders_that_reached_us():
    """The number a partner will over-read. An order their system never sent us is
    invisible to every figure in the report, and the denominator has to say so."""
    records = [record("ORD-1"), record("ORD-2", constraints=())]
    measure = build(records, feed(outcome("ORD-1"), outcome("ORD-2"))).provenance
    assert (measure.numerator, measure.denominator) == (1, 2)
    assert "submitted to Approv" in measure.denominator_note


def test_outcomes_that_match_no_receipt_are_their_own_row():
    """Orders the returns desk saw and Approv never did. No metric in the report can see
    them, which is exactly why the count is printed."""
    joined = m.join([record("ORD-1")], feed(outcome("ORD-1"), returned("ORD-9")))
    assert len(joined.outcomes_without_record) == 1
    text = to_text(build([record("ORD-1")], joined.feed))
    assert "Outcomes with no receipt" in text
    assert "not reaching us" in flat(text)


# --- what cannot be computed is still a row -----------------------------------------------

def test_a_report_with_no_outcome_data_prints_every_outcome_row_unanswered():
    """A pilot's real first week. The receipt side is complete; the outcome side is a list
    of rows saying why it is not, because an omitted row reads as a clean result."""
    document = build([record(), record("ORD-2")])
    text, page = to_text(document), to_html(document)

    assert flat(NO_OUTCOMES) in flat(text)
    for block in document.populations:
        assert block.precision.unavailable
        assert block.recall_strict.unavailable
        assert block.payout_proxy.unavailable
    assert "NOT COMPUTED" in text and "NOT COMPUTED" in page
    # And the rows are still there to be seen, not dropped.
    assert text.count("NOT COMPUTED") >= 6


def test_an_empty_feed_is_not_labelled_a_fixture():
    """A row that could not be computed came from nothing, not from invented data. The
    tag means "this number came from a fixture", and there is no number."""
    document = build([record()])
    assert "[FIXTURE]" not in to_text(document)
    assert "FIXTURE" not in to_html(document).split("<style>")[0]


def test_a_fixture_feed_marks_every_row_it_produced():
    """A shadow report circulated internally must not be mistakable for partner data."""
    document = build([record(decision=Decision.REFUSE)],
                     feed(returned("ORD-1"), source=o.FeedSource.FIXTURE,
                          description="seeded generator"))
    text, page = to_text(document), to_html(document)

    assert flat(FIXTURE_WARNING) in flat(text)
    assert text.count("[FIXTURE]") >= 5
    assert 'class="fixture"' in page and "FIXTURE" in page
    # The receipt side is ours and is never tagged.
    volume = text[text.index("2. WHAT WAS OBSERVED"):text.index("3. WHAT APPROV")]
    assert "[FIXTURE]" not in volume


def test_a_feed_that_does_not_say_where_it_came_from_is_refused(tmp_path):
    """Defaulting the source either way is how a fixture number ends up in front of a
    partner. The loader refuses to guess."""
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps({"outcomes": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="declare its source"):
        o.load(path)


# --- records the report must not count ----------------------------------------------------

def test_a_comparison_with_no_order_line_is_not_an_order_event():
    """A shelf-time comparison was never sold and cannot be returned. Counting one in a
    volume figure a partner reads as orders would inflate it with a non-order."""
    document = build([record("ORD-1"), record("ORD-2", order=False)])
    assert document.volume[0].value == "1"


def test_an_incomplete_verification_is_excluded_from_the_decision_distribution():
    """DR 0004: an aborted check escalates, and that `confirm` is a fact about us. Counting
    it would report our downtime as caution about their catalogue."""
    records = [record("ORD-1", decision=Decision.ALLOW),
               record("ORD-2", decision=Decision.CONFIRM,
                      completion=Completion.PROVIDER_UNAVAILABLE)]
    document = build(records)
    block = document.populations[0]

    assert block.decisions[Decision.CONFIRM].denominator == 1
    assert block.decisions[Decision.CONFIRM].numerator == 0
    assert block.aborted.numerator == 1
    assert "did not complete" in to_text(document)


# --- the record's own limits carry into the report ----------------------------------------

def test_the_report_never_prints_a_customers_own_words():
    """Invariant 10 keeps personal data off the record. The outcome feed is not the record
    and a returns desk's `reason_text` can carry anything, so the report renders none of
    it: a weekly email is exactly where a customer's words would leak."""
    leak = o.Outcome(order_id="ORD-1", line_id="1", correlation_id="corr-ORD-1",
                     status=o.Status.RETURNED, reason_code=o.ReasonCode.NOT_AS_DESCRIBED,
                     reason_text="Jane said the colour was wrong, call 555-0100")
    document = build([record("ORD-1")], feed(leak))
    for rendering in (to_text(document), to_html(document)):
        assert "Jane" not in rendering and "555-0100" not in rendering


def test_the_standing_caveats_are_printed_every_week_in_full():
    """They do not improve with more data, and a reader who forgets them over-reads the
    table above them."""
    for rendering in (to_text(build([record()])), to_html(build([record()]))):
        for caveat in CAVEATS:
            assert flat(caveat) in flat(rendering)


def test_the_version_triple_behind_the_numbers_is_on_the_page():
    """Invariant 6 asks for the model and prompt version on every published number. One
    row for the period, and a warning when the period mixes versions — a week whose
    extractor changed part-way through is two populations reported as one."""
    one = to_text(build([record()]))
    assert "evaluator-v1 / extract-v6 / prompt-v6 (1 receipts)" in one

    mixed = build([record("ORD-1"), record("ORD-2", model_version="extract-v7")])
    row = next(r for r in mixed.sources if r.label.startswith("Engine, reader"))
    assert row.missing and "More than one version ran" in row.note


def test_the_period_is_read_off_the_receipts_not_only_off_the_label():
    """A label is what somebody typed. The first and last receipt are what happened."""
    document = build([record()], period="7-13 September 2026")
    row = next(r for r in document.sources if r.label.startswith("First and last"))
    assert NOW.isoformat() in row.value


# --- the page --------------------------------------------------------------------------

def test_both_renderings_carry_the_same_sections():
    from approv.report.render import HEADINGS
    document = build([record()], feed(outcome()))
    text, page = to_text(document), to_html(document)
    for heading in HEADINGS:
        assert heading in text and heading in page


def test_the_page_escapes_what_it_is_given():
    """The partner name and the feed description are strings somebody typed."""
    document = build([record()], feed(outcome(), description="<script>alert(1)</script>"),
                     partner="<b>Hearth</b>")
    page = to_html(document)
    assert "<script>alert" not in page
    assert "&lt;b&gt;Hearth&lt;/b&gt;" in page


def test_channel_coverage_is_read_off_the_record_not_inferred_from_the_origin():
    """DR 0023 put `covered` on the record, inside the digest. The report reads it.

    Origin and coverage eligibility are different questions: origin says where the request
    came from, `covered` says whether that channel earns a promise at all under DR 0020's
    gradient — and an incomplete verification is uncovered whatever channel it arrived on.
    Deriving one from the other would reintroduce the disagreement DR 0023 closed.
    """
    records = [record("ORD-1"), record("ORD-2", covered=False,
                                       coverage_notes=("no stated request was recovered",))]
    block = build(records).populations[0]

    assert (block.coverage_eligible.numerator, block.coverage_eligible.denominator) == (1, 2)
    assert "earns coverage" in to_text(build(records))


def test_the_report_does_not_vouch_for_a_chain_it_never_checked():
    """It reads a list of records and never looks at a link. Saying "signed and
    hash-chained" would vouch for integrity nothing here verified, on the one page whose
    whole value is that it does not overstate. It says how many carried a signature and
    points at the verifier that does check."""
    document = build([record("ORD-1"), record("ORD-2", hash=None, signature=None)])
    row = next(r for r in document.sources if r.label == "Receipts read")

    assert row.value == "2, of which 0 carry a signature"
    assert "does not verify the chain" in row.note
    # Anywhere on the page, including the data ladder, which describes what a receipt is
    # worth without claiming this report established it.
    assert "hash-chained" not in to_text(document)


# --- the real wire type, and what it cannot yet support -----------------------------------

def order_outcome(correlation_id, kind, reason=None):
    from approv.types.core import OrderOutcome, OutcomeKind
    return OrderOutcome(correlation_id=correlation_id, kind=OutcomeKind(kind),
                        occurred_at=NOW, merchant_reason=reason)


def test_a_shipped_order_is_folded_to_unknown_and_never_to_kept():
    """`OrderOutcome` has no terminal kept fact and no window close date.

    Folding `shipped` to KEPT would be the single easiest way to inflate every rate on the
    report. It is an unknown: shipped and nothing heard since is exactly what an open
    return window looks like.
    """
    folded = o.from_order_outcomes(
        [order_outcome("corr-ORD-1", "shipped"), order_outcome("corr-ORD-2", "returned")],
        source=o.FeedSource.PARTNER)

    by_id = {x.correlation_id: x for x in folded.outcomes}
    assert by_id["corr-ORD-1"].status is o.Status.OPEN
    assert by_id["corr-ORD-2"].status is o.Status.RETURNED
    assert folded.records_window_close is False


def test_a_later_return_wins_over_an_earlier_shipped():
    folded = o.from_order_outcomes(
        [order_outcome("corr-ORD-1", "shipped"), order_outcome("corr-ORD-1", "returned"),
         order_outcome("corr-ORD-1", "refunded")], source=o.FeedSource.PARTNER)
    assert len(folded.outcomes) == 1
    assert folded.outcomes[0].status is o.Status.RETURNED


def test_precision_refuses_to_compute_rather_than_return_one_hundred_per_cent():
    """The most dangerous number this report could print.

    With no way to know an order was kept, the only orders with a known outcome are the
    ones that came back — so precision over that denominator is 100% by construction, and
    it would be the headline. The row prints the reason instead.
    """
    records = [record("ORD-1", decision=Decision.REFUSE),
               record("ORD-2", decision=Decision.REFUSE)]
    feed = o.from_order_outcomes(
        [order_outcome("corr-ORD-1", "returned"), order_outcome("corr-ORD-2", "shipped")],
        source=o.FeedSource.PARTNER, description="ingestion run 2026-09-13")
    joined = m.join(records, feed)

    measure = m.precision(joined, m.Origin.AGENT_STATED)
    # The reason first, then the tier sentence. Both halves are load-bearing: the first
    # says why the number would be wrong, the second says what would fix it, and the
    # second alone would read as a sales prompt stapled to a blank.
    assert measure.unavailable.startswith(o.NO_WINDOW_CLOSE)
    # The window is what blocks it today; the GOOD tier is what this row needs in the
    # end, and both rungs' fields are listed so sending only the first does not produce
    # a second NOT COMPUTED.
    assert "needs the GOOD tier" in measure.unavailable
    assert "ship date per order line" in measure.unavailable
    assert "own reason code" in measure.unavailable
    assert measure.rate is None
    assert "100% by construction" in to_text(build(records, feed))


def test_approv_never_classifies_the_merchants_own_free_text():
    """Turning a merchant's words into a signal is what the outcome fence exists to
    prevent, and grading our own work against a taxonomy we chose would measure nothing.
    The reason text is carried, printed nowhere, and read by nothing."""
    feed = o.from_order_outcomes(
        [order_outcome("corr-ORD-1", "returned", "customer said the colour was wrong")],
        source=o.FeedSource.PARTNER)
    joined = m.join([record("ORD-1")], feed)

    assert feed.outcomes[0].reason_text == "customer said the colour was wrong"
    assert feed.outcomes[0].wrong_item is False, "uncoded, so not counted either way"
    assert m.recall(joined, m.Origin.AGENT_STATED).unavailable.startswith(o.NO_REASON_CODE)
    assert m.attribution(joined, m.Origin.AGENT_STATED).blocked.startswith(o.NO_REASON_CODE)
    assert "colour was wrong" not in to_text(build([record("ORD-1")], feed))


def test_a_real_feed_still_produces_the_whole_receipt_side_of_the_report():
    """The half we own is unaffected. A partner's first real report is volume, decisions,
    provenance and coverage eligibility, with the outcome rows saying what is missing."""
    records = [record("ORD-1"), record("ORD-2", decision=Decision.REFUSE)]
    feed = o.from_order_outcomes([order_outcome("corr-ORD-1", "shipped")],
                                 source=o.FeedSource.PARTNER)
    text = to_text(build(records, feed))

    assert "2 of 2" in text                       # volume, with its denominator
    assert "would have refused" in text
    assert text.count("NOT COMPUTED") >= 4
    # This feed knows which orders came back and nothing else, so every blocked row is
    # blocked by the *first* missing thing rather than by all of them. Naming the window
    # is right: a partner told to send four fields at once sends none, and the dispute
    # row cannot have a denominator until kept orders exist either way.
    assert flat(o.NO_WINDOW_CLOSE) in flat(text)
    assert flat(o.NO_REASON_CODE) in flat(text)
    assert "To reach GOOD, send: ship date per order line" in flat(text)


def test_the_framing_sentence_is_read_off_the_records_not_assumed():
    """The most load-bearing sentence on the page: it decides whether a reader takes the
    whole table as something that happened or something that would have. `Mode` is on the
    record and inside the digest, so it is read rather than hardcoded."""
    from approv.report.document import ENFORCING, mode_note
    from approv.types.core import Mode

    assert mode_note([record()])[0] is SHADOW
    assert mode_note([record(mode=Mode.ENFORCE)])[0] is ENFORCING
    assert flat(ENFORCING) in flat(to_text(build([record(mode=Mode.ENFORCE)])))


def test_a_period_mixing_shadow_and_enforcing_records_refuses_to_read_as_one():
    """In shadow a refused order was still fulfilled and could still come back. Under
    enforcement it never became an order at all, so it could not have returned. A
    precision figure over the two together counts orders that had no chance to fail."""
    from approv.types.core import Mode
    records = [record("ORD-1"), record("ORD-2", mode=Mode.ENFORCE)]
    document = build(records)

    assert "1 shadow, 1 enforcing" in document.shadow_note
    assert "not comparable" in document.shadow_note
    assert "Split the period by mode" in flat(to_text(document))


def test_the_plain_text_report_stays_ascii_for_ascii_records():
    """Pasted into ticket systems and email bodies of unknown encoding, like the artifact.
    Our own chrome is ASCII so a record's own content is the only thing that can arrive
    mangled."""
    document = build([record(decision=Decision.REFUSE)],
                     feed(returned("ORD-1"), source=o.FeedSource.FIXTURE))
    text = to_text(document)
    assert text.isascii(), [c for c in text if not c.isascii()][:10]


# --- the data ladder: what a partner gets for what a partner gives ------------------------

class Shipped:
    """An outcome event carrying the fields ingestion is growing, and nothing else.

    A stand-in rather than a mock: `types.core.OrderOutcome` does not have ship date,
    window length or reason code yet, both are landing optional, and the fold reads them
    with `getattr` so it works either side of that. Posing them here is how the higher
    tiers are testable today - and if ingestion lands them under different names, the
    drift canary below fails rather than this suite passing over a fold that reads
    nothing.
    """

    def __init__(self, correlation_id, kind="shipped", *, reason=None, reason_code=None,
                 ship_date=None, return_window_days=None, attribute=None,
                 occurred_at=None):
        self.correlation_id = correlation_id
        self.kind = kind
        self.occurred_at = occurred_at or NOW
        self.merchant_reason = reason
        self.reason_code = reason_code
        self.ship_date = ship_date
        self.return_window_days = return_window_days
        self.attribute = attribute


LATER = datetime(2026, 10, 20, tzinfo=timezone.utc)


def tier_feed(tier, records, *, source=o.FeedSource.FIXTURE):
    """One week of the same orders, sent at each rung of the ladder.

    Deliberately the *same underlying week* at every tier. What changes between these
    feeds is only which fields the partner sent, so any difference in the report is a
    difference in what the data can support and never a difference in what happened.
    """
    events = []
    for index, r in enumerate(records):
        came_back = index % 3 == 0
        window = dict(ship_date=NOW, return_window_days=14) if tier >= t.Tier.MINIMUM else {}
        if came_back:
            events.append(Shipped(
                r.correlation_id, "returned", reason="customer says the colour is wrong",
                reason_code="not_as_described" if tier >= t.Tier.GOOD else None,
                attribute="colour" if tier >= t.Tier.GOOD else None, **window))
            if tier >= t.Tier.BEST and index % 6 == 0:
                events.append(Shipped(r.correlation_id, "disputed", **window))
        else:
            events.append(Shipped(r.correlation_id, "shipped", **window))
    if tier is t.Tier.NONE:
        return o.empty_feed("nothing supplied")
    return o.from_order_outcomes(events, source=source, as_of=LATER,
                                 description="tier fixture")


def a_week():
    return [record("ORD-%d" % i, decision=Decision.REFUSE if i % 2 else Decision.ALLOW)
            for i in range(12)]


@pytest.mark.parametrize("tier", list(t.Tier))
def test_the_tier_is_derived_from_the_feed_and_never_asserted(tier):
    """Nobody tells the report which tier a partner is at. It reads what arrived.

    A feed that could declare its own rung could flatter itself into one, and the rows
    that rung unlocks would then print NOT COMPUTED underneath the claim.
    """
    records = a_week()
    assert build(records, tier_feed(tier, records)).tier is tier


def test_a_feed_that_is_a_lattice_rather_than_a_ladder_reads_as_the_lower_rung():
    """Reason codes with no window close date is above MINIMUM on one axis and below it
    on the other. The rung is the highest *complete* one, so it reads RETURNS_ONLY - and
    the capability flags beside it still say the codes arrived, because a partner must
    never be described as having sent less than they did."""
    records = a_week()
    feed = o.from_order_outcomes(
        [Shipped(r.correlation_id, "returned", reason_code="not_as_described")
         for r in records], source=o.FeedSource.PARTNER)
    document = build(records, feed)

    assert document.tier is t.Tier.RETURNS_ONLY
    flags = {row.label.strip(): row.value for row in document.capabilities}
    assert flags["carries your desk's own reason code"] == "yes"
    assert flags["can tell a kept order from an open one"] == "no"
    # And the row that needs only the coding still computes, rung aside.
    assert build(records, feed).populations[0].recall_strict.unavailable is None


def test_each_rung_unlocks_exactly_the_rows_it_pays_for():
    """The whole degradation contract in one table. The same week, four times.

    What must be true at every rung: a row that cannot be computed prints the reason and
    the field that would fix it, and a row that can be computed is not withheld because
    something *else* is missing. Both failures are silent ones - the first reads as a
    clean result, the second as a broken product.
    """
    records = a_week()
    computed = {}
    for tier in t.Tier:
        block = build(records, tier_feed(tier, records)).populations[0]
        computed[tier] = {
            "return rate": block.return_rates[Decision.REFUSE].unavailable is None,
            "precision": block.precision.unavailable is None,
            "recall": block.recall_strict.unavailable is None,
            "attribution": block.attribution.blocked is None,
            "payout proxy": block.payout_proxy.unavailable is None,
            "disputes": block.dispute_rates[Decision.REFUSE].unavailable is None,
        }

    assert computed[t.Tier.NONE] == dict.fromkeys(computed[t.Tier.NONE], False)
    assert computed[t.Tier.RETURNS_ONLY] == dict.fromkeys(computed[t.Tier.NONE], False)
    assert computed[t.Tier.MINIMUM]["return rate"] is True
    assert computed[t.Tier.MINIMUM]["precision"] is False
    assert computed[t.Tier.GOOD]["precision"] is True
    assert computed[t.Tier.GOOD]["recall"] is True
    assert computed[t.Tier.GOOD]["attribution"] is True
    assert computed[t.Tier.GOOD]["disputes"] is False
    assert computed[t.Tier.BEST] == dict.fromkeys(computed[t.Tier.BEST], True)


def test_a_blocked_row_says_which_tier_would_unlock_it_and_what_to_send():
    """Two halves, both required. The reason says why the number would be wrong; the tier
    sentence says what would fix it. The reason alone is a dead end and the tier sentence
    alone is a sales prompt stapled to a blank."""
    records = a_week()
    text = to_text(build(records, tier_feed(t.Tier.MINIMUM, records)))

    assert flat(o.NO_REASON_CODE) in flat(text)
    assert "This row needs the GOOD tier and this feed is at MINIMUM" in flat(text)
    assert "your returns desk's own reason code" in flat(text)


def test_the_minimum_tier_does_not_look_broken():
    """The founder's actual requirement: honest about what it cannot say, not broken.

    A partner at the minimum tier has the headline blocked. They must still receive a
    real number computed from their own data, in the same section, rather than a page of
    NOT COMPUTED and an invitation to send more.
    """
    records = a_week()
    document = build(records, tier_feed(t.Tier.MINIMUM, records))
    text = to_text(document)
    block = document.populations[0]

    assert block.precision.unavailable is not None
    assert block.return_rates[Decision.REFUSE].computable
    assert block.return_rates[Decision.ALLOW].computable
    # In the headline section, above the ladder, where a reader who stops early finds it.
    assert text.index("WHAT YOUR DATA SUPPORTS TODAY") < text.index("2. WHAT WAS OBSERVED")


def test_the_return_rate_is_never_presented_as_precision():
    """It counts changed minds and damaged parcels, which no verification predicts.
    Presenting it as precision would be the same failure as printing a 100% precision:
    a number that is real arithmetic over a denominator that does not mean what a reader
    would take it to mean."""
    records = a_week()
    document = build(records, tier_feed(t.Tier.MINIMUM, records))
    measure = document.populations[0].return_rates[Decision.REFUSE]
    text = to_text(document)

    assert "precision" not in measure.name.lower()
    assert "counting every reason" in measure.name
    assert "including ones no verification could have predicted" in measure.denominator_note
    assert "Not precision, and it must not be read as precision" in flat(text)
    # And the pair is rendered as a pair: one row alone is a fact about their business.
    assert text.count("return rate of orders Approv would have") >= 2


def test_neither_half_of_a_paired_rate_can_be_rendered_without_the_other():
    """The comparison is the signal. A shape that let one row be printed alone would
    invite exactly that, so the pair is held as a dict keyed by decision and the renderer
    walks the same constant the document builds from."""
    from approv.report.document import RATED
    from approv.report import render

    records = a_week()
    block = build(records, tier_feed(t.Tier.BEST, records)).populations[0]
    assert set(block.return_rates) == set(RATED) == set(block.dispute_rates)
    assert Decision.CONFIRM not in RATED, "in shadow nobody acted on an escalation"
    assert "RATED" in render.to_text.__globals__


# --- deriving kept, which is the field that unlocks every rate ----------------------------

def test_kept_is_derived_only_once_the_window_has_actually_closed():
    """Ship date plus window length is the minimum tier's whole purchase, and the
    arithmetic has one dangerous direction: calling an order kept early counts a return
    that has not happened yet as a success."""
    inside = o.from_order_outcomes(
        [Shipped("corr-1", ship_date=NOW, return_window_days=30)],
        source=o.FeedSource.PARTNER, as_of=NOW + timedelta(days=3))
    closed = o.from_order_outcomes(
        [Shipped("corr-1", ship_date=NOW, return_window_days=30)],
        source=o.FeedSource.PARTNER, as_of=NOW + timedelta(days=31))

    assert inside.outcomes[0].status is o.Status.OPEN
    assert inside.outcomes[0].window_closes_at == NOW + timedelta(days=30)
    assert closed.outcomes[0].status is o.Status.KEPT
    # Both feeds carry the mechanism, so both can tell kept from open. The first simply
    # has nothing kept yet, which is a result and not an incapacity.
    assert inside.records_window_close and closed.records_window_close


def test_an_explicit_window_close_date_beats_our_own_arithmetic():
    """A partner who can send the date has already applied their holiday rules and their
    goodwill exceptions. Recomputing it from a nominal window length would overwrite
    their answer with ours."""
    event = Shipped("corr-1", ship_date=NOW, return_window_days=90)
    event.return_window_closes_at = NOW + timedelta(days=2)
    feed = o.from_order_outcomes([event], source=o.FeedSource.PARTNER,
                                 as_of=NOW + timedelta(days=5))
    assert feed.outcomes[0].status is o.Status.KEPT


def test_an_order_with_no_window_information_is_undecidable_and_counted():
    """Held open, excluded from every rate, and printed - because a row that is open
    because we cannot tell is not the same fact as a row that is open because the window
    genuinely has not closed, and only the count says which kind a period is full of."""
    feed = o.from_order_outcomes([Shipped("corr-1"), Shipped("corr-2", ship_date=NOW,
                                                             return_window_days=1)],
                                 source=o.FeedSource.PARTNER, as_of=LATER)
    assert feed.undecidable == 1
    assert feed.records_window_close is False, "one undecidable row and the rate is unsafe"
    row = next(r for r in build([record("ORD-1")], feed).join_quality
               if r.label.startswith("Orders whose outcome could not"))
    assert row.value == "1" and row.missing


def test_a_feed_of_nothing_but_returns_cannot_tell_kept_from_open():
    """The 100%-by-construction trap in its second form. Every row is decided, nothing is
    undecidable, and there is still no kept order anywhere - so the capability is false
    and precision refuses, exactly as it does for a feed with no window at all."""
    feed = o.from_order_outcomes(
        [Shipped("corr-ORD-1", "returned", reason_code="not_as_described")],
        source=o.FeedSource.PARTNER, as_of=LATER)
    assert feed.undecidable == 0
    assert feed.records_window_close is False
    joined = m.join([record("ORD-1", decision=Decision.REFUSE)], feed)
    assert m.precision(joined, m.Origin.AGENT_STATED).unavailable is not None


def test_a_report_re_run_later_does_not_promote_orders_the_period_left_open():
    """`as_of` is the moment the report describes, not the moment it was generated. Last
    week's report has to keep saying what it said."""
    events = [Shipped("corr-ORD-1", ship_date=NOW, return_window_days=14)]
    then = o.from_order_outcomes(events, source=o.FeedSource.PARTNER,
                                 as_of=NOW + timedelta(days=2))
    now = o.from_order_outcomes(events, source=o.FeedSource.PARTNER, as_of=LATER)
    assert then.outcomes[0].status is o.Status.OPEN
    assert now.outcomes[0].status is o.Status.KEPT


# --- disputes are not returns -------------------------------------------------------------

def test_a_dispute_is_not_folded_into_a_return():
    """A customer who charges back may never have sent anything back. Counting one as the
    other inflates the return count with chargebacks and then measures the inflated
    number - and the two costs are the whole reason the top rung exists."""
    feed = o.from_order_outcomes(
        [Shipped("corr-ORD-1", ship_date=NOW, return_window_days=7),
         Shipped("corr-ORD-1", "disputed", ship_date=NOW, return_window_days=7)],
        source=o.FeedSource.PARTNER, as_of=LATER)
    outcome_row = feed.outcomes[0]

    assert outcome_row.disputed is True
    assert outcome_row.status is o.Status.KEPT, "disputed, and nothing came back"
    assert outcome_row.wrong_item is False, "a chargeback is not a returns-desk coding"
    assert feed.records_disputes is True


def test_a_quiet_week_is_not_read_as_a_missing_dispute_feed():
    """Inference is a floor and not the truth: a week with no dispute looks exactly like a
    week where disputes are not being sent. An ingestion path that knows which fields it
    forwards says so, and then a zero is a zero."""
    events = [Shipped("corr-ORD-1", ship_date=NOW, return_window_days=7)]
    inferred = o.from_order_outcomes(events, source=o.FeedSource.PARTNER, as_of=LATER)
    declared = o.from_order_outcomes(events, source=o.FeedSource.PARTNER, as_of=LATER,
                                     records_disputes=True)

    assert inferred.records_disputes is False
    assert declared.records_disputes is True
    joined = m.join([record("ORD-1")], declared)
    measure = m.dispute_rate(joined, m.Origin.AGENT_STATED, Decision.ALLOW)
    assert measure.computable and measure.numerator == 0


def test_the_dispute_row_is_never_folded_into_the_return_row_on_the_page():
    """Different costs, different sections. A merchant reading one number for both would
    be reading their return rate and calling it their dispute exposure."""
    records = a_week()
    text = to_text(build(records, tier_feed(t.Tier.BEST, records)))
    assert "8. THE EXPENSIVE TAIL: DISPUTES AND CHARGEBACKS" in text
    assert text.index("WHAT YOUR DATA SUPPORTS TODAY") < text.index("THE EXPENSIVE TAIL")


# --- their vocabulary, not ours -----------------------------------------------------------

def test_a_code_we_do_not_publish_is_recorded_and_never_guessed_at():
    """`RTN-SIZE` does not become `wrong_item` because it contains a word we recognise.
    Their vocabulary is evidence and ours is arithmetic; mapping between them is the thing
    the outcome fence exists to prevent."""
    feed = o.from_order_outcomes(
        [Shipped("corr-ORD-1", "returned", reason_code="RTN-SIZE",
                 ship_date=NOW, return_window_days=7)],
        source=o.FeedSource.PARTNER, as_of=LATER)
    row = feed.outcomes[0]

    assert row.reason_code is o.ReasonCode.OTHER
    assert row.reason_code_raw == "RTN-SIZE"
    assert row.wrong_item is False
    quality = next(r for r in build([record("ORD-1")], feed).join_quality
                   if r.label.startswith("Reason codes we do not publish"))
    assert quality.value == "RTN-SIZE" and quality.missing
    assert "does not guess what one of your codes means" in quality.note


def test_uncoded_returns_are_counted_against_us_and_the_page_says_so():
    """An uncoded return is not a wrong item, so it sits in precision's denominator and
    not its numerator - which understates precision rather than overstating it, and is
    therefore safe. It is not safe to leave unsaid: a partner whose desk codes half its
    returns is reading a ceiling set by their own data quality."""
    records = [record("ORD-1", decision=Decision.REFUSE),
               record("ORD-2", decision=Decision.REFUSE),
               record("ORD-3", decision=Decision.REFUSE)]
    feed = o.from_order_outcomes(
        [Shipped("corr-ORD-1", "returned", reason_code="not_as_described",
                 ship_date=NOW, return_window_days=7),
         Shipped("corr-ORD-2", "returned", ship_date=NOW, return_window_days=7),
         Shipped("corr-ORD-3", ship_date=NOW, return_window_days=7)],
        source=o.FeedSource.PARTNER, as_of=LATER)
    document = build(records, feed)

    assert feed.records_window_close, "one kept order, so the mechanism is demonstrated"

    assert feed.uncoded_returns == 1
    row = next(r for r in document.join_quality
               if r.label.startswith("Returns with no reason code"))
    assert "understates precision rather than overstating it" in row.note


# --- a schema change splits a week exactly as an engine change does -----------------------

def test_a_schema_change_part_way_through_a_week_is_shown_as_a_mixture():
    """The schema decides which attributes are checked and at what criticality, so adding
    one HARD attribute mid-week moves the refusal rate with nothing in the engine
    changing. The week is then two populations reported as one."""
    document = build([record("ORD-1", category_version="pilot-1"),
                      record("ORD-2", category_version="pilot-2")])
    row = next(r for r in document.sources if r.label == "Category schema versions")

    assert row.missing, "a mid-week schema change is a warning, not a footnote"
    assert "bedding" in row.value and "pilot-1" in row.value and "pilot-2" in row.value
    assert "changed part-way through this period" in row.note


def test_two_categories_at_two_versions_is_not_a_mixture():
    """The easy way to get this wrong. A partner selling bedding and lighting runs two
    schemas at two versions every week of the pilot, and a warning that fires permanently
    is a warning a reader learns to skip."""
    document = build([record("ORD-1", category_version="pilot-1"),
                      record("ORD-2", category_id="lighting", category_version="v9")])
    row = next(r for r in document.sources if r.label == "Category schema versions")

    assert not row.missing and row.note is None
    assert "bedding" in row.value and "lighting" in row.value


# --- the ladder on the page ---------------------------------------------------------------

def test_the_ladder_prints_what_each_rung_still_cannot_say():
    """The half a partner would never be told by anyone selling them something, and the
    reason the next rung exists. Printed at every tier, including the top - a partner at
    BEST still needs to read what BEST cannot say."""
    records = a_week()
    for tier in t.Tier:
        text = flat(to_text(build(records, tier_feed(tier, records))))
        for spec in t.LADDER:
            assert flat(spec.headline) in text
            for sentence in spec.cannot:
                assert flat(sentence) in text, (tier, spec.name)


def test_the_ladder_marks_the_rung_the_partner_is_actually_on():
    records = a_week()
    text = to_text(build(records, tier_feed(t.Tier.GOOD, records)))
    assert "YOU ARE AT: GOOD" in text
    assert "> GOOD  (you are here)" in text
    assert "MINIMUM  (already sent)" in text
    assert "BEST  (not yet sent)" in text


def test_no_rung_of_the_ladder_reads_as_a_price():
    """It is a data ladder and not a pricing one. Nothing here may imply a commercial
    term, and BEST is not a covered tier: coverage attaches per channel under DR 0020 and
    nothing in this module speaks to it."""
    records = a_week()
    page = to_text(build(records, tier_feed(t.Tier.BEST, records))).lower()
    for word in ("upgrade", "premium", "plan", "subscription", "per month", "pricing"):
        assert word not in page, word


# --- the fold has to survive ingestion landing the fields ---------------------------------

def test_the_fold_reads_the_ingestion_fields_by_name_and_says_which_have_landed():
    """The gap between what the report can use and what ingestion sends, visible on every
    run rather than remembered."""
    from approv.types.core import OrderOutcome
    status = dict((name, present) for name, _, present in o.ingestion_status(OrderOutcome))
    assert set(status) == {name for name, _ in o.INGESTION_FIELDS}
    # No assertion about which are present: that is claude1's schedule, not a contract.
    # The canary below is what makes a rename visible.
    assert all(isinstance(present, bool) for present in status.values())


def test_the_outcome_wire_type_has_not_grown_a_field_we_are_not_reading():
    """The drift canary, and the guard on the worst silent failure this module has.

    `from_order_outcomes` reads the optional ingestion fields with `getattr`, so if they
    land under different names nothing raises: every feed reads one rung lower than it is
    and the report degrades politely while the data was there all along. Nothing would
    fail. This fails instead - the moment `OrderOutcome` grows or loses anything, someone
    has to decide whether the fold should read it and which rung it unlocks.

    It has already earned its place once: `reason_code`, `ship_date`,
    `return_window_days` and `return_window_closes_at` landed while this module was being
    written, under exactly the names the fold looks for, and this is what said so.

    Fixing it is a one-line edit to this set. Deleting it is the thing not to do.
    """
    from approv.types.core import OrderOutcome
    known = {"correlation_id", "kind", "occurred_at", "mode", "merchant_id",
             "merchant_reason", "sku", "quantity",
             # Landed for the report. Each one moves a partner up a rung.
             "reason_code", "ship_date", "return_window_days",
             "return_window_closes_at"}
    fields = set(OrderOutcome.model_fields)
    assert not fields - known, (
        "OrderOutcome grew %s. Check whether from_order_outcomes should read it (see "
        "INGESTION_FIELDS), which tier it unlocks, and then add it to this set."
        % sorted(fields - known))
    # And the other direction, which matters now that the fold depends on them: a rename
    # or a removal reads as a partner who sent less, with nothing raised.
    for name in ("reason_code", "ship_date", "return_window_days",
                 "return_window_closes_at"):
        assert name in fields, (
            "%s is gone from OrderOutcome. from_order_outcomes reads it by name with "
            "getattr, so every feed now silently reads one rung lower than it is." % name)


# --- the survivorship trap: the 100% that arrives through a different door ----------------

def test_a_period_whose_windows_have_not_closed_refuses_rather_than_reads_as_a_disaster():
    """The second form of the 100%-by-construction number, and the one that got through.

    A return resolves on the day it happens. A kept order resolves only when its window
    closes. So a week reported six days after it shipped contains every return that has
    happened and no keep that has finished happening - and a rate over "orders with a
    known outcome" comes out at 100% with the capability flags all green, because the feed
    genuinely can tell kept from open and simply has not been given time to.

    Found by reading the demo's own tier table, where every return rate printed 100%.
    """
    records = [record("ORD-%d" % i, decision=Decision.REFUSE) for i in range(6)]
    events = []
    for index, r in enumerate(records):
        events.append(Shipped(r.correlation_id, ship_date=NOW, return_window_days=21))
        if index < 2:
            events.append(Shipped(r.correlation_id, "returned", reason_code="wrong_item",
                                  ship_date=NOW, return_window_days=21))
    # Six days in: two orders have come back, four are still inside their window.
    young = o.from_order_outcomes(events, source=o.FeedSource.PARTNER,
                                  as_of=NOW + timedelta(days=6))
    grown = o.from_order_outcomes(events, source=o.FeedSource.PARTNER,
                                  as_of=NOW + timedelta(days=30))

    assert young.records_window_close, "the mechanism is there; only the time is not"
    early = m.precision(m.join(records, young), m.Origin.AGENT_STATED)
    assert early.denominator == 0, (
        "a returned order inside its own window was counted against keeps that have not "
        "finished happening: %d of %d" % (early.numerator, early.denominator))
    assert early.rate is None

    late = m.precision(m.join(records, grown), m.Origin.AGENT_STATED)
    assert (late.numerator, late.denominator) == (2, 6)


def test_an_unclosed_return_is_counted_in_the_open_window_row_not_dropped():
    """It reads oddly for a second - the order came back, what is undecided? - and that is
    the row that explains why the rates above it have a smaller denominator than the
    period does."""
    records = [record("ORD-1", decision=Decision.REFUSE)]
    feed = o.from_order_outcomes(
        [Shipped("corr-ORD-1", ship_date=NOW, return_window_days=21),
         Shipped("corr-ORD-1", "returned", reason_code="wrong_item", ship_date=NOW,
                 return_window_days=21)],
        source=o.FeedSource.PARTNER, as_of=NOW + timedelta(days=6))
    measure = m.open_window(m.join(records, feed), m.Origin.AGENT_STATED)

    assert (measure.numerator, measure.denominator) == (1, 1)
    assert "returns included" in measure.denominator_note


def test_the_caveat_says_the_outcome_half_of_a_week_lags_its_decision_half():
    """A partner comparing this week's refusal count with this week's precision is
    comparing two different weeks, and nothing else on the page would tell them."""
    text = flat(to_text(build([record()], feed(outcome()))))
    assert "three weeks behind its decision half" in text


def test_the_instruction_lists_every_rung_between_here_and_there():
    """A partner two rungs down who is told to send dispute events will send them and
    still get NOT COMPUTED, because the row also needs the kept orders and the coding
    underneath. A second accurate-looking instruction that does not work is worse than
    none."""
    records = a_week()
    document = build(records, tier_feed(t.Tier.RETURNS_ONLY, records))
    blocked = document.populations[0].dispute_rates[Decision.REFUSE].unavailable

    assert "needs the BEST tier and this feed is at RETURNS ONLY" in blocked
    for rung in (t.Tier.MINIMUM, t.Tier.GOOD, t.Tier.BEST):
        for item in t.TIERS[rung].supplies:
            assert item in blocked, (rung, item)
    # And nothing from a rung they are already on.
    assert t.TIERS[t.Tier.RETURNS_ONLY].supplies[0] not in blocked
