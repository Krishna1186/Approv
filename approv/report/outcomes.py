"""What happened to the order afterwards - the half of the report we do not produce.

Every number a partner actually cares about is a join between two things: the receipt
chain, which is ours and is signed, and the outcome of the order, which is theirs and is
not. Approv can say what it would have decided. Only the partner can say whether the
customer sent it back.

**The ingestion path now carries what the report asked for, and the constraint moved.**
`types.core.OrderOutcome` is the real wire shape: a stream of shipped / returned /
disputed / refunded events joined by `correlation_id`, with the merchant's reason kept as
verbatim free text — and, since the fields landed, the desk's own `reason_code`, the
`ship_date` and the return window. All of them optional, which is the right call and the
reason this module exists in its current shape: the question is no longer *what can
ingestion carry* but *what did this partner actually send*, and partners arrive at
different tiers. `approv.report.tiers` names those rungs; `from_order_outcomes` folds the
events and declares which rungs the result reaches.

`Outcome` below is therefore two things at once: the enriched view the report needs, and
the specification of what a feed has to deliver to support each row. A feed says which
rows it can support, and a metric that needs what it cannot support prints the reason
rather than a number.

**The shape, and why each field is on it.**

`status` is three-valued on purpose. An order still inside its return window is not a
kept order — it is an unknown, and counting it as kept is the single easiest way to
overstate precision. `open` orders are excluded from every outcome denominator and
counted in their own row.

`reason_code` is the partner's returns desk coding, not ours. `not_as_described` and
`wrong_item` are the two that this product is about; everything else is recorded and
excluded, because a changed mind is not a verification failure and must never be counted
as one.

`attribute` is optional and rare: most desks do not code which attribute the customer
complained about. Where it exists, attribution gets sharper. Where it does not, the
report says so rather than guessing.

`merchant_fault` is the partner's own assessment where they record one. It is never
inferred and never overridden — if their desk concluded the fault was theirs, that is
evidence about their process and it belongs in the report as theirs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "report-outcomes-v1"


class Status(str, Enum):
    """What is known about this order line today.

    OPEN is not a third kind of result, it is the absence of one. It exists so that
    "we do not know yet" cannot be silently absorbed into "the customer kept it".
    """

    KEPT = "kept"
    RETURNED = "returned"
    OPEN = "open"


class ReasonCode(str, Enum):
    """The partner's returns coding, as they coded it.

    Deliberately their vocabulary rather than ours. A desk that codes `not_as_described`
    has made a judgement we are not entitled to re-make, and mapping their codes into an
    Approv taxonomy would let us reclassify the very evidence we are being measured on.
    """

    NOT_AS_DESCRIBED = "not_as_described"
    WRONG_ITEM = "wrong_item"
    DAMAGED = "damaged"
    CHANGED_MIND = "changed_mind"
    LATE = "late"
    OTHER = "other"
    UNCODED = "uncoded"


# The two codes this product claims to be about. Everything else is a return we never
# said anything about, and a report that counted them would be claiming credit for the
# partner's ordinary return rate.
WRONG_ITEM_CODES = frozenset({ReasonCode.NOT_AS_DESCRIBED, ReasonCode.WRONG_ITEM})


class Outcome(BaseModel):
    """One order line, after the fact, as the partner's systems know it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(min_length=1)
    line_id: str | None = None
    # The join key we would rather have: it is on the receipt and it is unguessable.
    # Optional because a partner's returns export is keyed on their order id and may
    # never have carried ours.
    correlation_id: str | None = None

    status: Status
    reason_code: ReasonCode = ReasonCode.UNCODED
    # The code the desk actually sent, when it was not one we publish. Kept rather than
    # flattened into OTHER: a report that says "17 returns carried a code we do not
    # recognise: RTN-SIZE" is actionable, and one that says "17 other" is not.
    reason_code_raw: str | None = None
    # The customer's own words, where the desk kept them. Untrusted text like any other:
    # quoted on a report, never parsed into a finding.
    reason_text: str | None = None
    # Which attribute the customer complained about, if the desk coded one at all.
    attribute: str | None = None
    # The partner's own fault assessment. Theirs, recorded as theirs.
    merchant_fault: bool | None = None
    # Whether this order line became a dispute or a chargeback. Separate from `status`
    # because it is a different cost: a return is money and logistics, a chargeback is
    # the ratio that decides whether the merchant keeps card acceptance at all.
    disputed: bool = False
    resolved_at: datetime | None = None
    window_closes_at: datetime | None = None
    # Whether this line's return window had closed at the moment the report describes.
    #
    # **This is the survivorship guard and it is not optional.** A return resolves on the
    # day it happens; a kept order resolves only when its window closes. So in a period
    # reported soon after it ended, every resolved order is a return and no kept order
    # exists yet - and a rate over "orders with a known outcome" is 100% by construction
    # for the second time, arriving through a door the capability flags do not watch.
    # Counting a return only once its own window has closed removes the bias: the
    # denominator becomes orders whose windows have all closed, returns and keeps alike.
    #
    # Defaults true because a feed that says nothing about windows cannot exclude
    # anything on that basis, and every rate over such a feed is blocked anyway.
    window_closed: bool = True

    @model_validator(mode="after")
    def _a_return_has_a_shape(self):
        if self.status is Status.RETURNED and self.reason_code is ReasonCode.UNCODED:
            # Not an error: plenty of desks record a return with no code at all. It is
            # kept and counted separately, because an uncoded return cannot be read as
            # either supporting or contradicting a decision.
            pass
        if self.status is not Status.RETURNED and self.reason_code is not ReasonCode.UNCODED:
            raise ValueError("a reason code on an order that was not returned")
        return self

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.order_id, self.line_id)

    @property
    def wrong_item(self) -> bool:
        """Returned, and coded as one of the two codes this product is about."""
        return self.status is Status.RETURNED and self.reason_code in WRONG_ITEM_CODES

    @property
    def resolved(self) -> bool:
        """Whether this line belongs in a rate at all.

        Two conditions, and the second is the one that is easy to forget. The status has
        to be known - OPEN never counts as an outcome - and the return window has to have
        closed, because a period whose windows are still open contains every return that
        has happened and none of the keeps that have not finished happening.
        """
        return self.status is not Status.OPEN and self.window_closed


class FeedSource(str, Enum):
    """Where a feed came from, carried to the page.

    PARTNER is the real thing. FIXTURE is a file we wrote to build this report against a
    shape that does not exist yet. The distinction is on every outcome-derived row rather
    than in a footnote, because a report that has to be read carefully to avoid being
    misread is badly built.
    """

    PARTNER = "partner"
    FIXTURE = "fixture"


# Why a row is blocked, written about the *feed* rather than about the wire type. The
# wire type carries all three of these now, as optional fields, so whether a row can be
# computed is a fact about what a given partner sent and not about what Approv can
# receive. Printed verbatim on the report wherever a row is blocked.
NO_WINDOW_CLOSE = (
    "This feed does not record that a return window closed with no return, and carries "
    "no ship date and window length to derive one from. An order that was kept is "
    "therefore indistinguishable from one still inside its window, so the only orders "
    "with a known outcome are the ones that came back - and any rate computed over that "
    "denominator would be 100% by construction. Approv will not print such a number."
)

NO_REASON_CODE = (
    "This feed carries the merchant's reason as verbatim free text with no code. Approv "
    "will not classify it: turning a merchant's words into a signal is exactly what the "
    "outcome fence exists to prevent, and grading our own work against a taxonomy we "
    "chose would measure nothing. The desk's own coding is what makes this measurable."
)

NO_DISPUTES = (
    "This feed does not carry dispute or chargeback events, and a week with none "
    "supplied is not a week with none. A dispute is a different cost from a return - it "
    "is the ratio that decides whether card acceptance survives - and inferring one from "
    "a refund would count ordinary refunds as chargebacks."
)

BLOCKED_WITHOUT = (
    ("a terminal 'kept' fact, or ship date plus window length to derive one",
     NO_WINDOW_CLOSE),
    ("the returns desk's own reason code, as a coded field", NO_REASON_CODE),
    ("dispute and chargeback events", NO_DISPUTES),
)


class OutcomeFeed(BaseModel):
    """A set of outcomes, an account of where they came from, and what they can support.

    The two capability flags are the honest part. A feed folded from today's wire type has
    both false, and every metric that needs one prints the reason instead of a figure — so
    the report degrades to exactly the rows the data supports rather than computing
    something that looks like an answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: FeedSource
    # Free text naming the export, the fixture file, or the ingestion run. Printed.
    description: str = ""
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    outcomes: tuple[Outcome, ...] = ()
    # Can this feed tell a kept order from one whose window is still open?
    records_window_close: bool = True
    # Does it carry the desk's own reason coding, rather than free text we must not read?
    records_reason_code: bool = True
    # Does it carry dispute and chargeback events? Defaults false: the expensive tail is
    # the last thing a partner wires up, and a feed that has not said it carries disputes
    # must not be read as reporting zero of them.
    records_disputes: bool = False
    # Rows whose status could not be decided at all - shipped, nothing since, and no way
    # to tell whether the window has closed. They are held OPEN and counted here, because
    # a row that is open because we cannot tell is not the same fact as a row that is
    # open because the window genuinely has not closed, and only the count says which
    # kind a period is full of.
    undecidable: int = 0

    @property
    def is_real(self) -> bool:
        return self.source is FeedSource.PARTNER

    @property
    def uncoded_returns(self) -> int:
        """Returns the desk sent with no reason code. They count as not-wrong-item.

        Which understates precision rather than overstating it, and is therefore safe -
        but only if it is printed. A partner whose desk codes half its returns is reading
        a number suppressed by their own data quality, and has to be told so.
        """
        return sum(1 for o in self.outcomes
                   if o.status is Status.RETURNED and o.reason_code is ReasonCode.UNCODED)

    @property
    def unrecognised_codes(self) -> tuple[str, ...]:
        """Codes the desk sent that are not ones we publish. Never guessed at."""
        return tuple(sorted({o.reason_code_raw for o in self.outcomes
                             if o.reason_code_raw}))

    def by_correlation(self) -> dict[str, Outcome]:
        return {o.correlation_id: o for o in self.outcomes if o.correlation_id}

    def by_order(self) -> dict[tuple[str, str | None], Outcome]:
        return {o.key: o for o in self.outcomes}


def empty_feed(why: str) -> OutcomeFeed:
    """A feed carrying nothing, and the reason. Used when no outcome data exists at all.

    A report with no outcomes is a real report — volume, decisions and provenance are all
    computable from the ledger alone. Returning an empty feed rather than None keeps the
    outcome rows present and marked uncomputable, which is the whole point: an omitted row
    reads as a clean result.
    """
    return OutcomeFeed(source=FeedSource.FIXTURE, description=why)


def load(path: str | Path) -> OutcomeFeed:
    """Read a feed from JSON, refusing to guess whether it is real.

    `source` is required in the file. A feed that does not say where it came from cannot
    be labelled on the page, and defaulting it either way is exactly the kind of quiet
    assumption that puts a fixture number in front of a partner.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or "source" not in payload:
        raise ValueError(
            "an outcome feed must declare its source: 'partner' for real returns data, "
            "'fixture' for a file written against the shape. Refusing to assume.")
    return OutcomeFeed.model_validate(payload)


def from_rows(rows: Iterable[Mapping], *, source: FeedSource, description: str = "",
              **kw) -> OutcomeFeed:
    """Build a feed from plain dictionaries, for an ingestion path or a fixture builder."""
    return OutcomeFeed(source=source, description=description,
                       outcomes=tuple(Outcome.model_validate(dict(row)) for row in rows),
                       **kw)




# --------------------------------------------------------------------------------------
# What the ingestion path has to deliver, and reading it as it arrives
# --------------------------------------------------------------------------------------

REQUIRED_OF_A_FEED = (
    "A terminal 'kept' fact, or ship date plus the length of the return window so that "
    "'window closed, nothing came back' is derivable. Without one, an order that was "
    "kept cannot be told from one still inside its window and no rate can be computed at "
    "all - see NO_WINDOW_CLOSE. On the wire type.",
    "The desk's own reason code as a coded field, distinct from their free text. Their "
    "`not_as_described` is the measurement; classifying their words on our side would be "
    "grading our own work - see NO_REASON_CODE. On the wire type.",
    "Dispute and chargeback events, which are a different cost from a return and cannot "
    "be inferred from a refund - see NO_DISPUTES. On the wire type as an `OutcomeKind`.",
    "Which attribute the customer complained about, where the desk codes one. **Not on "
    "the wire type.** Optional, and it is what moves attribution off the weaker "
    "record-level fallback: without it a wrong-item return is attributed from the record "
    "as a whole rather than from the thing the customer actually complained about.",
    "The desk's own fault assessment, where they record one. **Not on the wire type.** "
    "Never inferred and never overridden - if their desk concluded the fault was theirs, "
    "that is evidence about their process and it belongs in the report as theirs.",
    "Outcomes for orders Approv never saw, not only for ones it did. Not a field: a "
    "property of the export. Those are what reveal the share of the partner's agentic "
    "traffic that never reached us, and no other number in the report can see it.",
)

# The optional fields this module looks for on an outcome event, by name. They are read
# with `getattr` rather than declared, because the wire type is not ours to change and
# the fold has to work both before and after they land.
#
# **The hazard, named because a silent miss here is the worst failure this module has.**
# If ingestion lands these under different names, `getattr` finds nothing, every feed
# reads one rung lower than it is, and the report degrades politely while the data was
# there all along. Nothing would fail. The guard is a drift canary in the tests, which
# asserts the known field set of `OrderOutcome` and fails the moment it grows anything -
# so a rename arrives as a red test rather than as a quietly worse report.
INGESTION_FIELDS = (
    ("ship_date", "when the line shipped, which starts the return window"),
    ("return_window_days", "how long that window is, in days"),
    ("return_window_closes_at", "or the close date outright, if it is easier to send"),
    ("reason_code", "the desk's own code for why it came back"),
    ("complained_attribute",
     "which attribute the customer complained about, where it is coded"),
    ("merchant_fault", "the desk's own fault assessment, recorded as theirs"),
)

# The short spelling, still read. The wire type calls it `complained_attribute`; this
# module asked for `attribute` and a fixture or an adapter may still say that. Reading
# both costs a line and the alternative is the exact silent miss the canary exists to
# catch - the field present, the fold not looking at it, and the report a rung lower for
# no reason anybody could see.
ATTRIBUTE_NAMES = ("complained_attribute", "attribute")


def _complained(event):
    for name in ATTRIBUTE_NAMES:
        value = getattr(event, name, None)
        if value is not None:
            return value
    return None


def ingestion_status(outcome_type) -> tuple[tuple[str, str, bool], ...]:
    """Which of the fields above the real wire type carries today.

    Printed by the demo so the gap between what the report can use and what ingestion
    sends is visible on every run rather than remembered. Takes the type as an argument
    so this module keeps importing nothing from `approv.types`.
    """
    fields = set(getattr(outcome_type, "model_fields", {}) or {})
    return tuple((name, why, name in fields) for name, why in INGESTION_FIELDS)


def _coded(raw) -> tuple[ReasonCode, str | None]:
    """The desk's code, accepted only when it is exactly one we publish.

    A strict lookup and never a match: `RTN-SIZE` does not become `wrong_item` because it
    contains a word we recognise. An unrecognised code is `OTHER` with the original kept
    beside it, so it appears on the report as a code we do not know rather than as a
    judgement we invented. This is the line the outcome fence draws - their vocabulary is
    evidence, ours is arithmetic, and mapping between them is the thing not to do.
    """
    if raw is None:
        return ReasonCode.UNCODED, None
    text = getattr(raw, "value", str(raw))
    try:
        return ReasonCode(text), None
    except ValueError:
        return ReasonCode.OTHER, text


def _window_close(event, shipped_at):
    """When this line's return window closes, if the event says enough to know.

    Prefers an explicit close date over ship-plus-length: a partner who can send the date
    outright has already applied their own holiday rules and exceptions, and recomputing
    it from a nominal window length would overwrite their answer with our arithmetic.
    """
    explicit = getattr(event, "return_window_closes_at", None)
    if explicit is not None:
        return explicit
    days = getattr(event, "return_window_days", None)
    start = getattr(event, "ship_date", None) or shipped_at
    if days is None or start is None:
        return None
    return start + timedelta(days=int(days))


def from_order_outcomes(events: Iterable, *, source: FeedSource, description: str = "",
                        as_of: datetime | None = None,
                        records_reason_code: bool | None = None,
                        records_disputes: bool | None = None, **kw) -> OutcomeFeed:
    """Fold `types.core.OrderOutcome` events into one view per order.

    An order can carry several events - shipped, then returned, then refunded - so the
    fold takes the strongest fact: any of returned, refunded or disputed makes it a
    return, and shipped on its own does **not** make it kept.

    **Shipped is folded to KEPT only when the window is known to have closed.** Nothing
    in the original wire type said a return window closed, so "shipped and we have heard
    nothing since" was an unknown and not a kept order; folding it to KEPT would be the
    single easiest way to inflate every rate on the report. With ship date and window
    length arriving as optional fields, the fold derives the close date where it can,
    calls the order KEPT once that date has passed, and leaves it OPEN - and counted in
    `undecidable` - where it cannot. The feed then declares `records_window_close` only
    when the mechanism was actually present and left nothing undecided, so a partner who
    sends neither still gets the reason printed instead of a number.

    `as_of` is the moment the report is being run for. It defaults to now, and is an
    argument so that a report re-run over an old period does not silently promote orders
    to KEPT whose windows closed after the period it describes.

    The two capability flags can be stated by the caller and are otherwise *inferred from
    what arrived*, which is a floor and not the truth: a week in which no dispute happened
    looks exactly like a week in which disputes are not being sent. An ingestion path that
    knows which fields it forwards should say so rather than let a quiet week read as a
    missing feed.
    """
    as_of = as_of or datetime.now(timezone.utc)
    folded: dict[str, Outcome] = {}
    windowed = undecidable = 0
    saw_code = saw_dispute = False

    grouped: dict[str, list] = {}
    for event in events:
        grouped.setdefault(event.correlation_id, []).append(event)

    for correlation_id, group in grouped.items():
        kinds = [getattr(e.kind, "value", str(e.kind)) for e in group]
        # A dispute is **not** folded into a return. The customer who charges back may
        # never have sent anything back, and the two are different costs to the merchant
        # - which is the whole reason the top tier exists. Counting one as the other
        # would inflate the return count with chargebacks and then measure the inflated
        # number. A refund is kept with returns: the line was written off either way.
        returns = [e for e, k in zip(group, kinds) if k in ("returned", "refunded")]
        disputed = any(k == "disputed" for k in kinds)
        saw_dispute = saw_dispute or disputed
        shipped = next((e for e, k in zip(group, kinds) if k == "shipped"), None)

        if returns:
            event = returns[0]
            code, raw = _coded(getattr(event, "reason_code", None))
            saw_code = saw_code or code is not ReasonCode.UNCODED
            # A return is a terminal fact, and it still waits for its own window before
            # it enters a rate. See `Outcome.window_closed`.
            closes = _window_close(shipped or event, getattr(shipped or event,
                                                             "occurred_at", None))
            folded[correlation_id] = Outcome(
                order_id=correlation_id, correlation_id=correlation_id,
                status=Status.RETURNED, reason_code=code, reason_code_raw=raw,
                # Never parsed. Carried so a person can read it, and read by nothing.
                reason_text=event.merchant_reason,
                attribute=_complained(event),
                merchant_fault=getattr(event, "merchant_fault", None),
                disputed=disputed, resolved_at=event.occurred_at,
                window_closes_at=closes,
                window_closed=closes is None or closes <= as_of)
            continue

        anchor = shipped or group[0]
        closes = _window_close(anchor, getattr(anchor, "occurred_at", None))
        if closes is None:
            undecidable += 1
            folded[correlation_id] = Outcome(
                order_id=correlation_id, correlation_id=correlation_id,
                status=Status.OPEN, reason_text=anchor.merchant_reason,
                disputed=disputed)
            continue
        windowed += 1
        closed = closes <= as_of
        folded[correlation_id] = Outcome(
            order_id=correlation_id, correlation_id=correlation_id,
            status=Status.KEPT if closed else Status.OPEN,
            reason_text=anchor.merchant_reason, disputed=disputed,
            resolved_at=closes if closed else None, window_closes_at=closes)

    return OutcomeFeed(
        source=source, description=description, outcomes=tuple(folded.values()),
        records_window_close=windowed > 0 and undecidable == 0,
        records_reason_code=saw_code if records_reason_code is None
        else records_reason_code,
        records_disputes=saw_dispute if records_disputes is None else records_disputes,
        undecidable=undecidable, **kw)
