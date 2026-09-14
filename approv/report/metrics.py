"""The numbers, each carrying the denominator it was computed over.

Invariant 6 is the whole design of this module: no function here returns a bare rate.
Every one returns a `Measure` holding the numerator, the denominator, the population it
was computed over, a sentence saying what that denominator *is*, where the data came
from, and — when it cannot be computed at all — the reason. The renderer cannot print a
number without printing its denominator, because there is no path through the types that
produces one without the other.

Invariant 7 is the second: agent-stated traffic and on-site-search traffic are different
populations and are never pooled. `by_population` returns one measure per population and
there is no function in this module that averages them. A partner reading one blended
number would be reading a number about no population at all, and the difference between
the two is the thing the pilot exists to show.

**Shadow mode governs the vocabulary.** Approv observed and recorded; it blocked nothing.
Every decision counted here is what Approv *would have* done, and the names say so.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from approv.harness.coverage import wilson
from approv.report.outcomes import (
    NO_DISPUTES, NO_REASON_CODE, NO_WINDOW_CLOSE, FeedSource, Outcome, OutcomeFeed,
    Status,
)
from approv.report.tiers import Tier, needs, tier_of
from approv.types.core import (
    ComparisonRecord, Completion, Criticality, Decision, Support,
)

VERSION = "report-metrics-v1"

# Below this many observations a rate is a description of a handful of orders rather than
# a measurement of anything. The report prints the interval either way and adds a line
# saying so — a suppressed number invites the reader to imagine a worse one, and a bare
# 2-of-3 invites them to imagine a better one.
THIN = 30

LEDGER = "receipt ledger"
OUTCOME = "outcome feed"


class Origin(str, Enum):
    """Where the stated request came from, read off the record's own constraints.

    DR 0020 §"Where the stated request comes from" ranks these by fidelity, and the pilot
    report has to keep them apart: a protocol call carries slots the agent filled, an
    on-site search carries what somebody typed into a box, and they fail differently.

    Derived from `Constraint.source`, which intake stamps as `<prefix>.<field>` with the
    prefix being the protocol name, `search.filters`, `search.query` or the declared-intent
    field name. That is a string convention rather than a typed field on the record, and
    it is the weakest link in this module — see `ORIGIN_IS_A_CONVENTION`.
    """

    AGENT_STATED = "agent_stated"
    ONSITE_SEARCH = "onsite_search"
    MIXED = "mixed"
    NO_STATED_REQUEST = "no_stated_request"


ORIGIN_IS_A_CONVENTION = (
    "Origin is derived from the `source` prefix intake stamps on each constraint "
    "(`search.*` for on-site search, the protocol name or declared-intent field "
    "otherwise). It is a string convention, not a field on the signed record, so a new "
    "adapter that picks a different prefix would be classified as agent-stated without "
    "anything failing."
)

POPULATION_LABEL = {
    Origin.AGENT_STATED: "agent-stated orders",
    Origin.ONSITE_SEARCH: "on-site-search orders",
    Origin.MIXED: "orders carrying both",
    Origin.NO_STATED_REQUEST: "orders with no stated request",
}

# The two the report computes rates for. `MIXED` and `NO_STATED_REQUEST` appear in the
# volume table and nowhere else: the first is too rare to measure and too impure to pool,
# the second has nothing to measure because nothing was stated.
MEASURED = (Origin.AGENT_STATED, Origin.ONSITE_SEARCH)


@dataclass(frozen=True)
class Measure:
    """One number, and everything a reader needs to know whether to believe it."""

    name: str
    numerator: int = 0
    denominator: int = 0
    population: str = ""
    # What the denominator *is*, as a sentence. Invariant 6 asks for a denominator; a bare
    # integer is not one — "of 41" says nothing about what the 41 are.
    denominator_note: str = ""
    source: str = LEDGER
    fixture: bool = False
    unavailable: str | None = None

    @property
    def computable(self) -> bool:
        return self.unavailable is None and self.denominator > 0

    @property
    def rate(self) -> float | None:
        if not self.computable:
            return None
        return self.numerator / self.denominator

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.numerator, self.denominator) if self.computable else None

    @property
    def thin(self) -> bool:
        """True when the denominator is too small for the rate to be a measurement."""
        return self.computable and self.denominator < THIN


def unavailable(name: str, why: str, *, population: str = "", source: str = OUTCOME,
                fixture: bool = False) -> Measure:
    """A measure that cannot be computed, printed as a row rather than dropped."""
    return Measure(name=name, population=population, source=source, fixture=fixture,
                   unavailable=why)


# --------------------------------------------------------------------------------------
# Populations
# --------------------------------------------------------------------------------------


def origin_of(record: ComparisonRecord) -> Origin:
    """Which population this order belongs to."""
    sources = [c.source or "" for c in record.request_constraints]
    if not record.request_constraints:
        return Origin.NO_STATED_REQUEST
    search = any(s.startswith("search.") for s in sources)
    other = any(not s.startswith("search.") for s in sources)
    if search and other:
        return Origin.MIXED
    return Origin.ONSITE_SEARCH if search else Origin.AGENT_STATED


def is_evidence(record) -> bool:
    """Whether this receipt is the cart-only product rather than a comparison.

    Read off the record's own signed `kind`. The alternative - "it has no findings, so it
    must be cart-only" - is the inference `OrderEvidenceRecord` was created to remove, and
    it would be wrong anyway: a verification that aborted also has no findings, and the
    two are opposite facts.
    """
    return getattr(record, "kind", "") == "order_evidence"


def comparisons(records: Iterable) -> list:
    """The records that carry a decision. Every rate on the report is over these.

    An order-evidence receipt has no decision, no findings and no stated request, so it
    cannot appear in a decision distribution, a precision figure or a coverage class. It
    is counted in its own row and in provenance's denominator, and nowhere else.
    """
    return [r for r in records if not is_evidence(r)]


def evidence_only(records: Iterable) -> list:
    return [r for r in records if is_evidence(r)]


def orders_only(records: Iterable[ComparisonRecord]) -> list[ComparisonRecord]:
    """Records bound to an order line, which is the only thing a return can happen to.

    A record with no order is a comparison about a product — a real call site, and not an
    order event. Counting one in a volume figure a partner reads as orders would inflate
    it with something that was never sold.
    """
    return [r for r in records if r.order is not None]


def by_origin(records: Iterable[ComparisonRecord]) -> dict[Origin, list[ComparisonRecord]]:
    grouped: dict[Origin, list[ComparisonRecord]] = {origin: [] for origin in Origin}
    for record in records:
        grouped[origin_of(record)].append(record)
    return grouped


def completed(records: Iterable[ComparisonRecord]) -> list[ComparisonRecord]:
    """Only verifications that ran to a conclusion carry a decision worth counting.

    DR 0004: an aborted verification confirms, and that `confirm` is a statement about our
    availability rather than about the order. Counting it in a decision distribution would
    report our downtime as caution about their catalogue.
    """
    return [r for r in records if r.completion is Completion.COMPLETED]


# --------------------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Joined:
    """Records matched to outcomes, and everything that failed to match, both ways."""

    pairs: tuple[tuple[ComparisonRecord, Outcome], ...] = ()
    records_without_outcome: tuple[ComparisonRecord, ...] = ()
    outcomes_without_record: tuple[Outcome, ...] = ()
    matched_on_correlation: int = 0
    matched_on_order: int = 0
    feed: OutcomeFeed = field(default_factory=lambda: OutcomeFeed(source=FeedSource.FIXTURE))

    @property
    def fixture(self) -> bool:
        """Whether any number here was derived from data that is not the partner's.

        An empty feed is not a fixture: nothing was derived from it at all, and tagging
        an uncomputable row [FIXTURE] would claim a provenance it does not have. The tag
        means "this number came from invented data", and a number that does not exist
        came from nothing.
        """
        return bool(self.feed.outcomes) and not self.feed.is_real

    def resolved(self) -> list[tuple[ComparisonRecord, Outcome]]:
        """Pairs whose outcome is known. An open return window is not an outcome."""
        return [(r, o) for r, o in self.pairs if o.resolved]


def join(records: Iterable[ComparisonRecord], feed: OutcomeFeed) -> Joined:
    """Match receipts to outcomes on the correlation id, falling back to the order line.

    Both directions of failure are kept. Records with no outcome are usually just orders
    whose window has not closed; **outcomes with no record are the interesting ones** —
    they are orders the partner's returns desk saw and Approv never did, which is the
    share of their traffic that is not reaching us, and no metric below would show it.
    """
    by_correlation = feed.by_correlation()
    by_order = feed.by_order()
    pairs, unmatched_records = [], []
    used: set[int] = set()
    correlation_hits = order_hits = 0

    for record in records:
        outcome = by_correlation.get(record.correlation_id)
        if outcome is not None:
            correlation_hits += 1
        elif record.order is not None:
            outcome = by_order.get((record.order.order_id, record.order.line_id))
            if outcome is None:
                outcome = by_order.get((record.order.order_id, None))
            if outcome is not None:
                order_hits += 1
        if outcome is None:
            unmatched_records.append(record)
        else:
            pairs.append((record, outcome))
            used.add(id(outcome))

    return Joined(pairs=tuple(pairs), records_without_outcome=tuple(unmatched_records),
                  outcomes_without_record=tuple(o for o in feed.outcomes
                                                if id(o) not in used),
                  matched_on_correlation=correlation_hits, matched_on_order=order_hits,
                  feed=feed)


# --------------------------------------------------------------------------------------
# Reading a record
# --------------------------------------------------------------------------------------

BLOCKING = (Criticality.HARD, Criticality.BOUND)
GUARANTEED = "guaranteed"


def would_refuse(record: ComparisonRecord) -> bool:
    return record.decision is Decision.REFUSE


def would_flag(record: ComparisonRecord) -> bool:
    """Refused or escalated. Both are Approv declining to authorise on its own."""
    return record.decision in (Decision.REFUSE, Decision.CONFIRM)


def guarantees(record: ComparisonRecord) -> bool:
    """Whether this record carries any finding inside the guarantee class."""
    return GUARANTEED in record.coverage


def violated_attributes(record: ComparisonRecord) -> set[str]:
    return {f.attribute for f in record.findings
            if f.support is Support.VIOLATED and f.criticality in BLOCKING}


def guaranteed_attributes(record: ComparisonRecord) -> set[str]:
    return {f.attribute for f, c in zip(record.findings, record.coverage)
            if c == GUARANTEED}


# --------------------------------------------------------------------------------------
# Volume and decisions
# --------------------------------------------------------------------------------------


def volume(records: Sequence[ComparisonRecord]) -> dict[Origin, int]:
    return {origin: len(rows) for origin, rows in by_origin(records).items()}


def channel_split(records: Sequence[ComparisonRecord]) -> dict[str, int]:
    """Agent-stated traffic by the fidelity it arrived at, for the volume table only.

    A protocol call and a declared-intent paragraph are both agent-stated and DR 0020
    puts them in the same coverage tier, so rates are computed over the two together.
    The counts are still worth showing apart: they are the merchant's channel mix, and a
    pilot that turns out to be all declared-intent is a different integration from one
    that is all ACP.
    """
    counts: dict[str, int] = {}
    for record in records:
        if origin_of(record) is not Origin.AGENT_STATED:
            continue
        for constraint in record.request_constraints:
            prefix = (constraint.source or "unknown").split(".")[0]
            counts[prefix] = counts.get(prefix, 0) + 1
            break
    return counts


def decisions(records: Sequence[ComparisonRecord], population: str) -> dict[Decision, Measure]:
    """The decision distribution over completed verifications in one population."""
    done = completed(records)
    note = "completed verifications of %s in the period" % population
    return {
        decision: Measure(
            name="would have %s" % {Decision.ALLOW: "authorised",
                                    Decision.CONFIRM: "asked for confirmation",
                                    Decision.REFUSE: "refused"}[decision],
            numerator=sum(1 for r in done if r.decision is decision),
            denominator=len(done), population=population, denominator_note=note)
        for decision in Decision
    }


def aborted(records: Sequence[ComparisonRecord], population: str) -> Measure:
    """Verifications that did not run to a conclusion. Ours, not theirs."""
    return Measure(
        name="verifications that did not complete",
        numerator=sum(1 for r in records if r.completion is not Completion.COMPLETED),
        denominator=len(records), population=population,
        denominator_note="all order events observed for %s" % population)


def provenance(records: Sequence[ComparisonRecord]) -> Measure:
    """Share of observed orders carrying a stated request we could recover at all.

    The denominator is orders *submitted to Approv*, not the partner's orders. An order
    their system never sent us is invisible here, and no number in this report can see it
    — which is why the unmatched-outcome count matters.

    **Order-evidence receipts are in the denominator.** They are orders that arrived with
    no stated request at all — that is the whole reason they are a different receipt — so
    leaving them out would compute the provenance rate over the orders that had provenance
    and return a number close to one every week.
    """
    return Measure(
        name="orders carrying a recoverable stated request",
        numerator=sum(1 for r in comparisons(records)
                      if origin_of(r) is not Origin.NO_STATED_REQUEST),
        denominator=len(records), population="all orders observed",
        denominator_note="order events submitted to Approv in the period, of any origin, "
                         "including those that produced order evidence rather than a "
                         "verification because no stated request reached us")


# --------------------------------------------------------------------------------------
# The outcome-derived numbers
# --------------------------------------------------------------------------------------


def coverage_eligible(records: Sequence[ComparisonRecord], population: str) -> Measure:
    """Share of orders arriving through a channel that earns coverage at all.

    DR 0023 put this on the record, inside the digest, so it is read rather than inferred
    from the origin. The two are not the same question: origin says where the request came
    from, `covered` says whether that channel earns a promise under DR 0020's gradient —
    and an incomplete verification is uncovered whatever channel it arrived on (DR 0004).

    The number a partner needs before any coverage conversation: an uncovered channel is
    one where a guarantee, if it existed, would not attach, and the mix is a fact about
    their integration rather than about their catalogue.
    """
    return Measure(
        name="orders on a channel that earns coverage",
        numerator=sum(1 for r in records if r.covered), denominator=len(records),
        population=population,
        denominator_note="all order events observed for %s" % population)


def _blocked(joined: Joined, name: str, population: str, *,
             needs_window: bool = True, needs_code: bool = True,
             needs_disputes: bool = False) -> Measure | None:
    """The reason this metric cannot be computed from this feed, if there is one.

    One guard rather than a check inside each metric: a capability the feed lacks blocks
    the same way everywhere, and a metric that forgot to ask would quietly compute a
    number over a denominator that cannot mean what it says.

    The reason has two halves and needs both. The capability sentence says why the number
    would be wrong; `needs()` says which data tier would fix it and what to send. Either
    alone reads badly - the first as a dead end, the second as a sales prompt stapled to
    a blank.
    """
    current = tier_of(joined.feed)
    # The rung this particular row sits on, so a blocked dispute row does not tell a
    # partner with no outcome feed at all that the minimum tier would fix it.
    required = (Tier.BEST if needs_disputes else Tier.GOOD if needs_code
                else Tier.MINIMUM)
    if not joined.feed.outcomes:
        return unavailable(
            name, "no outcome data has been ingested for this period. "
                  + needs(current, required),
            population=population, fixture=joined.fixture)
    # The capability sentence names the *first* missing thing, because that is why the
    # number would be wrong today. The tier sentence names this row's own rung and every
    # rung between, because that is what it takes to get this row - and a partner told
    # only about the first one sends it, gets NOT COMPUTED again, and stops asking.
    if needs_window and not joined.feed.records_window_close:
        return unavailable(name, NO_WINDOW_CLOSE + " " + needs(current, required),
                           population=population, fixture=joined.fixture)
    if needs_code and not joined.feed.records_reason_code:
        return unavailable(name, NO_REASON_CODE + " " + needs(current, required),
                           population=population, fixture=joined.fixture)
    if needs_disputes and not joined.feed.records_disputes:
        return unavailable(name, NO_DISPUTES + " " + needs(current, required),
                           population=population, fixture=joined.fixture)
    return None


def _population_pairs(joined: Joined, origin: Origin) -> list[tuple[ComparisonRecord, Outcome]]:
    return [(r, o) for r, o in joined.resolved()
            if origin_of(r) is origin and r.completion is Completion.COMPLETED]


def precision(joined: Joined, origin: Origin) -> Measure:
    """Of the orders Approv would have refused, how many came back as the wrong item.

    **The report's headline, and the easiest number in it to overstate.** Two rules make
    it honest. Orders still inside their return window are excluded from the denominator,
    because counting an unknown as a kept order inflates precision by exactly the share of
    returns that have not happened yet. And the numerator counts only the partner's own
    `not_as_described` and `wrong_item` coding — a changed mind is not a verification
    failure and counting one would be claiming credit for their ordinary return rate.
    """
    population = POPULATION_LABEL[origin]
    name = "precision: would-have-refused orders that came back as the wrong item"
    blocked = _blocked(joined, name, population)
    if blocked is not None:
        return blocked
    pairs = [(r, o) for r, o in _population_pairs(joined, origin) if would_refuse(r)]
    return Measure(
        name=name,
        numerator=sum(1 for _, o in pairs if o.wrong_item), denominator=len(pairs),
        population=population, source=OUTCOME, fixture=joined.fixture,
        denominator_note=("%s Approv would have refused whose return window has closed; "
                          "orders still open are excluded and counted separately"
                          % population))


def recall(joined: Joined, origin: Origin, *, flagged: bool = False) -> Measure:
    """Of the wrong-item returns, how many Approv had said something about.

    Reported twice on purpose. "Flagged" is ambiguous between *would have refused* and
    *would not have authorised on its own*, and a reader left to pick will pick the
    flattering one. The strict number is the product claim; the broad one includes the
    escalations, which in shadow mode nobody acted on.
    """
    population = POPULATION_LABEL[origin]
    name = ("recall, counting refusals and escalations" if flagged
            else "recall: wrong-item returns Approv would have refused")
    # Recall needs the coding, but not the window: a return that happened is a fact
    # whatever is still open, so only the denominator's completeness is at issue and that
    # is what `open_window` prints beside it.
    blocked = _blocked(joined, name, population, needs_window=False)
    if blocked is not None:
        return blocked
    returns = [(r, o) for r, o in _population_pairs(joined, origin) if o.wrong_item]
    hit = would_flag if flagged else would_refuse
    return Measure(
        name=name, numerator=sum(1 for r, _ in returns if hit(r)),
        denominator=len(returns), population=population, source=OUTCOME,
        fixture=joined.fixture,
        denominator_note=("%s returned and coded not-as-described or wrong-item by the "
                          "partner's own desk, and matched to a receipt" % population))


def payout_proxy(joined: Joined, origin: Origin) -> Measure:
    """Orders Approv would have stood behind that came back as the wrong item anyway.

    A proxy, and labelled as one wherever it is printed. No coverage contract exists —
    PRD §6 leaves every term of it open — so this is not a payout and must never be
    presented as one. What it is: the count of orders where a guarantee, had one been in
    force, would have been tested. It is the number that decides whether the guarantee is
    priceable, and on a shadow pilot it is usually small enough that its interval is the
    only honest thing to read.
    """
    population = POPULATION_LABEL[origin]
    name = "payout proxy: guaranteed orders that came back as the wrong item"
    blocked = _blocked(joined, name, population)
    if blocked is not None:
        return blocked
    guaranteed = [(r, o) for r, o in _population_pairs(joined, origin) if guarantees(r)]
    return Measure(
        name=name, numerator=sum(1 for _, o in guaranteed if o.wrong_item),
        denominator=len(guaranteed), population=population, source=OUTCOME,
        fixture=joined.fixture,
        denominator_note=("%s carrying at least one finding inside the guarantee class, "
                          "whose return window has closed" % population))


def open_window(joined: Joined, origin: Origin) -> Measure:
    """How much of the period is still undecided. The denominator's honest caveat.

    Counts orders that have already come back as well, when their own window has not
    closed yet. That reads oddly for a second - the order came back, what is undecided? -
    and it is the whole point: a return that is inside its window is excluded from every
    rate above, because including it while the keeps it should be compared against are
    still open is what makes a young period read as a catastrophe.
    """
    population = POPULATION_LABEL[origin]
    pairs = [(r, o) for r, o in joined.pairs if origin_of(r) is origin]
    return Measure(
        name="orders whose return window has not closed",
        numerator=sum(1 for _, o in pairs if not o.resolved),
        denominator=len(pairs), population=population, source=OUTCOME,
        fixture=joined.fixture,
        denominator_note=("%s matched to an outcome record. Orders counted here are "
                          "excluded from every rate above, returns included: a rate over "
                          "a half-closed period counts the returns that have happened "
                          "against the keeps that have not finished happening."
                          % population))


DECISION_WORD = {
    Decision.REFUSE: "would have refused",
    Decision.CONFIRM: "would have asked for confirmation on",
    Decision.ALLOW: "would have authorised",
}


def return_rate(joined: Joined, origin: Origin, decision: Decision) -> Measure:
    """How often orders in one decision class came back, for any reason at all.

    **This is not precision and must never be printed as though it were.** It counts every
    return in the denominator's class - a changed mind, a damaged parcel, a duvet that
    looked different in the room - and Approv never claimed to predict any of those. On
    its own the number says almost nothing.

    What it is for: the minimum data tier. A partner who can say when an order shipped and
    how long their window is, but cannot say why anything came back, can still be shown
    the return rate of the orders Approv would have refused *beside* the return rate of
    the ones it would have authorised. The comparison is the signal; either row alone is
    a description of their ordinary return rate. It is the first real thing this report
    can say, and it arrives one tier before the headline does.
    """
    population = POPULATION_LABEL[origin]
    name = "return rate of orders Approv %s, counting every reason" % DECISION_WORD[decision]
    blocked = _blocked(joined, name, population, needs_code=False)
    if blocked is not None:
        return blocked
    pairs = [(r, o) for r, o in _population_pairs(joined, origin)
             if r.decision is decision]
    return Measure(
        name=name, numerator=sum(1 for _, o in pairs if o.status is Status.RETURNED),
        denominator=len(pairs), population=population, source=OUTCOME,
        fixture=joined.fixture,
        denominator_note=("%s Approv %s whose return window has closed. Every return "
                          "counts here, including ones no verification could have "
                          "predicted." % (population, DECISION_WORD[decision])))


def dispute_rate(joined: Joined, origin: Origin, decision: Decision) -> Measure:
    """How often orders in one decision class became a dispute or a chargeback.

    The expensive tail, and the only row on this report that speaks to the thing CLAUDE.md
    §1 calls existential: above a network's dispute-ratio threshold a merchant loses card
    acceptance, which is not a cost line. A return is money and logistics; a chargeback is
    the ratio.

    Reported the same way as the return rate and for the same reason - the refused class
    beside the authorised class, because the absolute number is a fact about their
    business and only the difference is a fact about the check.
    """
    population = POPULATION_LABEL[origin]
    name = "dispute or chargeback rate of orders Approv %s" % DECISION_WORD[decision]
    blocked = _blocked(joined, name, population, needs_code=False, needs_disputes=True)
    if blocked is not None:
        return blocked
    pairs = [(r, o) for r, o in _population_pairs(joined, origin)
             if r.decision is decision]
    return Measure(
        name=name, numerator=sum(1 for _, o in pairs if o.disputed),
        denominator=len(pairs), population=population, source=OUTCOME,
        fixture=joined.fixture,
        denominator_note=("%s Approv %s whose return window has closed and for which "
                          "dispute events were supplied"
                          % (population, DECISION_WORD[decision])))


# --------------------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------------------


class Attribution(str, Enum):
    """Who the record says the wrong item is attributable to.

    `VERIFIED_AND_STILL_WRONG` is deliberately not called "catalogue error". From our side
    a catalogue that published the wrong value and a warehouse that shipped the wrong item
    are the same event: the record says the published data matched the request, and the
    customer says what arrived did not. Naming it "catalogue error" would assert a fault
    the record cannot establish, in a report addressed to the party being blamed.
    """

    AGENT_AGAINST_REQUEST = "agent_against_request"
    VERIFIED_AND_STILL_WRONG = "verified_and_still_wrong"
    NOBODY_ASKED = "nobody_asked"
    APPROV_DID_NOT_READ = "approv_did_not_read"
    NOT_ATTRIBUTABLE = "not_attributable"


ATTRIBUTION_MEANS = {
    Attribution.AGENT_AGAINST_REQUEST: (
        "The merchant's own catalogue contradicted the stated request, and the order was "
        "placed anyway. The agent chose against what it said it wanted."
    ),
    Attribution.VERIFIED_AND_STILL_WRONG: (
        "The record shows the published data matched the request on the attribute at "
        "issue, and the customer says what arrived did not. Either the catalogue was "
        "wrong or the wrong item shipped; this record cannot tell those two apart."
    ),
    Attribution.NOBODY_ASKED: (
        "The request never mentioned the attribute the customer complained about. Nobody "
        "is at fault and nothing was covered: a record cannot honour a requirement nobody "
        "made."
    ),
    Attribution.APPROV_DID_NOT_READ: (
        "Part of the request was one Approv failed to encode, so we cannot rule out that "
        "the missed requirement is the reason this came back. Ours, not theirs."
    ),
    Attribution.NOT_ATTRIBUTABLE: (
        "Nothing in the record speaks to what the customer complained about."
    ),
}


@dataclass(frozen=True)
class Attributed:
    counts: dict[Attribution, int]
    total: int
    # How many were decided using the desk's own attribute coding rather than by falling
    # back to the record as a whole. The fallback is the weaker instrument and the report
    # says how much of the table rests on it.
    coded: int
    fixture: bool
    # Why the table is empty, when it is empty because the data cannot support it rather
    # than because nothing came back.
    blocked: str | None = None


def attribute_return(record: ComparisonRecord, outcome: Outcome) -> Attribution:
    """One wrong-item return, attributed from the record and the desk's coding.

    Ordered so the strongest evidence wins and our own failure is never hidden behind a
    weaker attribution: a requirement we did not read is checked before "nobody asked",
    because an unread requirement *looks* exactly like silence from inside the engine.
    """
    complained = outcome.attribute
    violated = violated_attributes(record)
    guaranteed = guaranteed_attributes(record)

    if complained is not None:
        if complained in violated:
            return Attribution.AGENT_AGAINST_REQUEST
        if complained in guaranteed:
            return Attribution.VERIFIED_AND_STILL_WRONG
        if record.unread:
            return Attribution.APPROV_DID_NOT_READ
        if complained in record.completeness:
            return Attribution.NOBODY_ASKED
        return Attribution.NOT_ATTRIBUTABLE

    if violated:
        return Attribution.AGENT_AGAINST_REQUEST
    if record.unread:
        return Attribution.APPROV_DID_NOT_READ
    if guaranteed:
        return Attribution.VERIFIED_AND_STILL_WRONG
    if not record.request_constraints:
        return Attribution.NOBODY_ASKED
    return Attribution.NOT_ATTRIBUTABLE


def attribution(joined: Joined, origin: Origin) -> Attributed:
    """Attribution over wrong-item returns, or nothing when the coding is not there.

    `blocked` carries the reason to the page. Attributing over *all* returns instead would
    be the tempting fallback and it would be wrong: a changed mind attributed to "the agent
    chose against the request" is a false accusation aimed at the partner's own customer.
    """
    current = tier_of(joined.feed)
    # A feed with nothing in it blocks too. Without this the table printed "No wrong-item
    # returns matched a receipt in this population" over a week where no outcome data
    # existed at all - which is the exact failure this report is built against: an empty
    # result reading as a clean one. Found by walking the tiers, not by any case here.
    if not joined.feed.outcomes:
        blocked = ("no outcome data has been ingested for this period. "
                   + needs(current, Tier.GOOD))
    elif not joined.feed.records_reason_code:
        blocked = NO_REASON_CODE + " " + needs(current, Tier.GOOD)
    else:
        blocked = None
    if blocked is not None:
        return Attributed(counts={member: 0 for member in Attribution}, total=0, coded=0,
                          fixture=joined.fixture, blocked=blocked)
    returns = [(r, o) for r, o in _population_pairs(joined, origin) if o.wrong_item]
    counts = {member: 0 for member in Attribution}
    for record, outcome in returns:
        counts[attribute_return(record, outcome)] += 1
    return Attributed(counts=counts, total=len(returns),
                      coded=sum(1 for _, o in returns if o.attribute),
                      fixture=joined.fixture)
