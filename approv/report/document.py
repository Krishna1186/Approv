"""The weekly partner report, assembled: what is known, what is not, and the denominators.

This is read by someone deciding whether to keep paying attention to us. The discipline
is the dispute artifact's, for the same reason and with one addition.

**Never overstate.** Every number carries its denominator, its population and its
interval. A number that cannot be computed is printed as a row saying why — an omitted
row reads as a clean result, and on a report the absent rows are exactly the ones a
reader would most want.

**Never let a shadow result read as a prevented loss.** Approv observed and recorded; it
blocked nothing. Every order in the period was fulfilled by the partner's own process.
The word is *would have*, everywhere, and there is no money-saved figure anywhere in this
module: that would be an estimate of a counterfactual we did not run.

**Say which half of the report is real.** The receipt side is ours and is signed. The
outcome side arrives from an ingestion path that does not exist yet, so every
outcome-derived row carries the provenance of the feed it came from, and a fixture feed
marks every one of them on the page rather than in a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from approv.report import metrics as m
from approv.report import tiers as t
from approv.report.outcomes import FeedSource, OutcomeFeed, empty_feed
from approv.types.core import ComparisonRecord, Completion, Decision, Mode

VERSION = "report-v1"

SHADOW = (
    "Approv ran in shadow for this period: it observed every order event listed below "
    "and blocked none of them. Every order here was fulfilled by your own process "
    "exactly as it would have been without us. Nothing in this report was prevented, and "
    "no figure in it is an estimate of money saved."
)

ENFORCING = (
    "Approv was enforcing for this period: an order it refused did not proceed. The "
    "counts below are therefore decisions that happened, not decisions that would have. "
    "Read \"would have refused\" in the tables as \"refused\"."
)

MIXED_MODE = (
    "This period contains both shadow and enforcing records (%d shadow, %d enforcing). "
    "They are not the same measurement and are not comparable: in shadow every refused "
    "order was still fulfilled and could still come back, while an enforcing refusal "
    "never became an order at all, so a precision figure over the two together counts "
    "orders that could not have returned. Split the period by mode before reading any "
    "rate below."
)


def mode_note(records) -> tuple[str, bool]:
    """What to say about the mode, read off the records rather than assumed.

    The framing sentence is the most load-bearing one on the page — it decides whether a
    reader takes the whole table as something that happened or something that would have —
    and hardcoding it would make it a claim about deployment configuration this module
    cannot see. `Mode` is on the record and inside the digest (DR 0023's neighbour), so it
    is read.
    """
    modes = {r.mode for r in records}
    if modes == {Mode.ENFORCE}:
        return ENFORCING, False
    if len(modes) > 1:
        shadow = sum(1 for r in records if r.mode is Mode.SHADOW)
        return MIXED_MODE % (shadow, len(records) - shadow), True
    return SHADOW, False

FIXTURE_WARNING = (
    "The outcome half of this report came from a FIXTURE, not from your returns data. "
    "The ingestion path that carries real outcomes is not built yet. Every row marked "
    "[FIXTURE] below is a shape, not a measurement, and none of it describes your "
    "business."
)

NO_OUTCOMES = (
    "No outcome data was supplied for this period, so every row that depends on what "
    "happened after the order is printed unanswered below. The receipt side of the "
    "report - volume, decisions, provenance - is complete and is ours."
)

# The standing limits. Printed every week, in full, at the end. They do not improve with
# more data and a reader who forgets them will over-read the table above them.
CAVEATS = (
    "The denominator throughout is orders your system submitted to Approv, not your "
    "orders. An order that never reached us is invisible to every number here.",
    "Approv compares a stated request against your own published catalogue data. It "
    "cannot tell whether that data was true, whether the item that shipped was the item "
    "picked, or whether the customer was satisfied.",
    "A return coded not-as-described is your desk's judgement, kept as theirs. Approv "
    "does not re-code them, which is the only reason these numbers measure anything: "
    "grading our own work against a taxonomy we chose would measure nothing.",
    "Agent-stated and on-site-search orders are never pooled into one rate. They are "
    "different populations with different fidelity, and a blended number would describe "
    "neither.",
    "A rate over fewer than %d observations is a description of a handful of orders. The "
    "interval is printed beside every rate and is the honest reading of a small week."
    % m.THIN,
    "Every rate is computed only over orders whose return window has closed - returns "
    "included. A week reported days after it ended therefore has small denominators that "
    "fill in as windows close, and the outcome half of any week is three weeks behind "
    "its decision half. Counting the returns that have already happened against the "
    "keeps that have not finished happening would make every young period look like a "
    "catastrophe.",
    m.ORIGIN_IS_A_CONVENTION,
)


# The two decision classes whose rates are printed side by side. `CONFIRM` is excluded
# on purpose: in shadow nobody acted on an escalation, so its orders were fulfilled
# exactly like authorised ones, and a third row would invite a reader to compare three
# numbers of which only two are a contrast.
RATED = (Decision.REFUSE, Decision.ALLOW)


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    note: str | None = None
    missing: bool = False


@dataclass(frozen=True)
class PopulationBlock:
    """Every rate for one population. Nothing here is ever merged with another block."""

    origin: m.Origin
    label: str
    observed: int
    decisions: dict[Decision, m.Measure]
    aborted: m.Measure
    coverage_eligible: m.Measure
    precision: m.Measure
    recall_strict: m.Measure
    recall_flagged: m.Measure
    payout_proxy: m.Measure
    open_window: m.Measure
    attribution: m.Attributed
    # The minimum tier's pair and the best tier's pair. Held as dicts keyed by decision
    # rather than as `refused`/`allowed` fields because the pair is the point: each is
    # meaningless alone, and a shape that lets one be rendered without the other invites
    # exactly that.
    return_rates: dict[Decision, m.Measure] = field(default_factory=dict)
    dispute_rates: dict[Decision, m.Measure] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportDocument:
    partner: str
    period: str
    generated_at: datetime
    shadow_note: str
    feed_note: str
    fixture: bool
    # Which rung of the data ladder this partner's feed reached, derived from the feed's
    # own capability flags and never asserted. It decides which rows below carry a number
    # and which carry the reason they do not.
    tier: t.Tier = t.Tier.NONE
    capabilities: tuple[Row, ...] = ()
    sources: tuple[Row, ...] = ()
    volume: tuple[Row, ...] = ()
    populations: tuple[PopulationBlock, ...] = ()
    provenance: m.Measure = field(default_factory=lambda: m.Measure(name="provenance"))
    join_quality: tuple[Row, ...] = ()
    caveats: tuple[str, ...] = CAVEATS


def _volume_rows(records, grouped) -> tuple[Row, ...]:
    rows = [Row("Order events observed", str(len(records)),
                note="records bound to an order line. A comparison run without an order "
                     "is not an order event and is not counted here.")]
    for origin in m.Origin:
        count = len(grouped[origin])
        # The denominator travels with the share rather than sitting in the row above it
        # (invariant 6). No interval: this is a count of what was observed, not an
        # estimate of anything, and an interval would imply it was sampled.
        share = " (%.1f%%)" % (100 * count / len(records)) if records else ""
        rows.append(Row("  " + m.POPULATION_LABEL[origin],
                        "%d of %d%s" % (count, len(records), share)))
    split = m.channel_split(records)
    if split:
        rows.append(Row("  agent-stated, by channel",
                        ", ".join("%s %d" % (name, count)
                                  for name, count in sorted(split.items())),
                        note="counts only, never rates: the two tiers are one population "
                             "for coverage (DR 0020) and are measured together."))
    incomplete = sum(1 for r in records if r.completion is not Completion.COMPLETED)
    rows.append(Row("Verifications that did not complete", str(incomplete),
                    note="ours, not yours. An aborted check escalates and never "
                         "authorises, and its decision is excluded from every "
                         "distribution below."))
    return tuple(rows)


def _join_rows(joined: m.Joined) -> tuple[Row, ...]:
    if not joined.feed.outcomes:
        return (Row("Outcome records supplied", "", missing=True,
                    note="no outcome feed was supplied for this period."),)
    return (
        Row("Outcome records supplied", str(len(joined.feed.outcomes))),
        Row("  matched on correlation id", str(joined.matched_on_correlation),
            note="the join key on the receipt, and the one to prefer."),
        Row("  matched on order and line", str(joined.matched_on_order),
            note="the fallback. An order with two lines returns one of them, so a match "
                 "without a line id is weaker evidence than it looks."),
        Row("Orders with no outcome yet", str(len(joined.records_without_outcome)),
            note="usually a window that has not closed. Excluded from every rate."),
        Row("Outcomes with no receipt", str(len(joined.outcomes_without_record)),
            missing=bool(joined.outcomes_without_record),
            note="orders your returns desk saw and Approv never did. This is the share "
                 "of your traffic that is not reaching us, and no other number in this "
                 "report can see it."),
    ) + _quality_rows(joined.feed)


def _quality_rows(feed: OutcomeFeed) -> tuple[Row, ...]:
    """What the feed could not settle, printed whether or not it blocked anything.

    Each of these suppresses a number quietly rather than blocking it, which makes them
    more dangerous than the rows that print NOT COMPUTED. An uncoded return is counted as
    not-a-wrong-item and drags precision *down*; a row we could not decide is held open
    and drops out of every denominator. Both are safe directions to be wrong in and
    neither is safe to leave unsaid, because a partner whose desk codes half its returns
    is reading a number set by their data quality and would otherwise read it as ours.
    """
    rows = []
    if feed.uncoded_returns:
        rows.append(Row("Returns with no reason code", str(feed.uncoded_returns),
                        missing=True,
                        note="counted as not-wrong-item, which understates precision "
                             "rather than overstating it. Your desk's coding rate is "
                             "therefore a ceiling on the headline above."))
    if feed.unrecognised_codes:
        rows.append(Row("Reason codes we do not publish",
                        ", ".join(feed.unrecognised_codes), missing=True,
                        note="recorded as sent and counted as `other`. Approv does not "
                             "guess what one of your codes means: tell us which of ours "
                             "it corresponds to and it starts counting."))
    if feed.undecidable:
        rows.append(Row("Orders whose outcome could not be decided",
                        str(feed.undecidable), missing=True,
                        note="shipped, nothing since, and no ship date and window length "
                             "to tell a kept order from an open one. Held open and "
                             "excluded from every rate."))
    return tuple(rows)


def _capability_rows(feed: OutcomeFeed) -> tuple[Row, ...]:
    """The flags the report actually acts on, beside the rung they add up to."""
    return tuple(Row("  " + label, "yes" if value else "no", missing=not value)
                 for label, value in t.capability_flags(feed))


def _versions(records) -> tuple[Row, ...]:
    """The version triple behind every number above. Invariant 6, and a real hazard.

    A period whose extractor or evaluator changed part-way through is two populations
    reported as one, and nothing else on the page would show it. Listing the triples with
    their counts makes a mid-week change visible in the week it happened rather than in
    the argument about why last week looked different.
    """
    seen: dict[tuple[str, str, str], int] = {}
    for record in records:
        key = (record.evaluator_version, record.model_version, record.prompt_version)
        seen[key] = seen.get(key, 0) + 1
    rows = [Row("Engine, reader and prompt versions",
                "; ".join("%s / %s / %s (%d receipts)" % (*key, count)
                          for key, count in sorted(seen.items())) or "none",
                missing=len(seen) > 1,
                note=None if len(seen) <= 1 else
                "More than one version ran in this period, so the numbers above are "
                "computed over a mixture. A version change part-way through a week makes "
                "the week two populations reported as one.")]
    rows.extend(_schemas(records))
    return tuple(rows)


def _schemas(records) -> tuple[Row, ...]:
    """The category schema behind every finding, and whether one changed mid-period.

    Same hazard as an engine change and it needed saying separately: the schema decides
    which attributes are checked at all and at what criticality, so adding one HARD
    attribute part-way through a week moves the refusal rate without anything in the
    engine changing. The week is then two populations reported as one, exactly as a
    version bump would make it, and nothing else on the page would show it.

    Grouped **by category**, which is the part that is easy to get wrong. A partner
    selling bedding and lighting runs two schemas at two versions every week of the pilot
    and that is not a mixture; counting distinct versions across categories would fire the
    warning permanently and train the reader to ignore it. Only a second version *within
    one category* is the event.

    `OrderLine.catalogue_version` is deliberately not here. The merchant's catalogue
    changes whenever they edit a product, which is constantly and by design, and warning
    about it would be warning about them doing their job.
    """
    seen: dict[str, dict[str, int]] = {}
    for record in records:
        seen.setdefault(record.category_id, {})
        versions = seen[record.category_id]
        versions[record.category_version] = versions.get(record.category_version, 0) + 1
    split = sorted(name for name, versions in seen.items() if len(versions) > 1)
    value = "; ".join(
        "%s %s" % (name, ", ".join("%s (%d receipts)" % (version, count)
                                   for version, count in sorted(versions.items())))
        for name, versions in sorted(seen.items())) or "none"
    return (Row("Category schema versions", value, missing=bool(split),
                note=None if not split else
                "The schema changed part-way through this period for: %s. The schema "
                "decides which attributes are checked and at what criticality, so the "
                "rates above are computed over a mixture of two different checks. Split "
                "the period at the change before comparing it with another week."
                % ", ".join(split)),)


def _sources_rows(records, feed: OutcomeFeed, ledger: str | None) -> tuple[Row, ...]:
    # What this report can say about the receipts is how many carried a signature, not
    # that the chain is intact: it reads a list of records and never checks a link. A row
    # claiming "signed and hash-chained" would be vouching for integrity nothing here
    # verified, on the one page whose value is that it does not overstate.
    sealed = sum(1 for r in records if r.hash and r.signature)
    rows = [Row("Receipts read", "%d, of which %d carry a signature" % (len(records),
                                                                       sealed),
                missing=sealed < len(records),
                note="This report does not verify the chain. Check it yourself, with the "
                     "published key and none of our code: scripts/verify_receipt.py "
                     "against the ledger export.")]
    if records:
        stamps = sorted(r.timestamp for r in records)
        rows.append(Row("First and last receipt",
                        "%s to %s" % (stamps[0].isoformat(), stamps[-1].isoformat()),
                        note="read off the receipts themselves, not from the period "
                             "label above."))
    rows.extend(_versions(records))
    if ledger:
        rows.append(Row("Ledger", ledger))
    rows.append(Row("Outcome feed", feed.source.value.upper()
                    + (" - " + feed.description if feed.description else ""),
                    missing=not feed.is_real,
                    note=None if feed.is_real else
                    "not your data. The ingestion path is not built."))
    return tuple(rows)


def build(records: list[ComparisonRecord], feed: OutcomeFeed | None = None, *,
          partner: str = "", period: str = "", ledger: str | None = None,
          generated_at: datetime | None = None) -> ReportDocument:
    """One period of receipts, one outcome feed, one report.

    `feed` may be omitted entirely. That produces a complete receipt-side report with
    every outcome row printed unanswered, which is the correct output for a pilot in its
    first week — and a far better one than quietly dropping the half of the report the
    partner is actually waiting for.
    """
    feed = feed or empty_feed("no outcome feed was supplied")
    orders = m.orders_only(records)
    grouped = m.by_origin(orders)
    joined = m.join(orders, feed)

    blocks = []
    for origin in m.MEASURED:
        rows = grouped[origin]
        label = m.POPULATION_LABEL[origin]
        blocks.append(PopulationBlock(
            origin=origin, label=label, observed=len(rows),
            decisions=m.decisions(rows, label), aborted=m.aborted(rows, label),
            coverage_eligible=m.coverage_eligible(rows, label),
            precision=m.precision(joined, origin),
            recall_strict=m.recall(joined, origin),
            recall_flagged=m.recall(joined, origin, flagged=True),
            payout_proxy=m.payout_proxy(joined, origin),
            open_window=m.open_window(joined, origin),
            attribution=m.attribution(joined, origin),
            return_rates={d: m.return_rate(joined, origin, d) for d in RATED},
            dispute_rates={d: m.dispute_rate(joined, origin, d) for d in RATED}))

    feed_note = NO_OUTCOMES if not feed.outcomes else (
        FIXTURE_WARNING if not feed.is_real else "")
    tier = t.tier_of(feed)
    framing, mixed = mode_note(orders)
    if mixed:
        feed_note = (framing + "  " + feed_note).strip()
    return ReportDocument(
        partner=partner or "the partner",
        period=period or "the period",
        generated_at=generated_at or datetime.now(timezone.utc),
        shadow_note=framing, feed_note=feed_note,
        fixture=bool(feed.outcomes) and not feed.is_real,
        tier=tier, capabilities=_capability_rows(feed),
        sources=_sources_rows(orders, feed, ledger),
        volume=_volume_rows(orders, grouped),
        populations=tuple(blocks),
        provenance=m.provenance(orders),
        join_quality=_join_rows(joined))
