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
from datetime import datetime, timezone

import pytest

from approv.report import metrics as m
from approv.report import outcomes as o
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
        category_id="bedding", category_version="1", locale="en-GB",
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
    assert "we will pay" not in text.lower() and "owed" not in text.lower()


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
    assert measure.unavailable == o.NO_WINDOW_CLOSE
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
    assert m.recall(joined, m.Origin.AGENT_STATED).unavailable == o.NO_REASON_CODE
    assert m.attribution(joined, m.Origin.AGENT_STATED).blocked == o.NO_REASON_CODE
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
    for missing, why in o.MISSING_FROM_INGESTION:
        assert flat(why) in flat(text), missing


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
