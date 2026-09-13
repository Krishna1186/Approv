"""What happened to the order afterwards - the half of the report we do not produce.

Every number a partner actually cares about is a join between two things: the receipt
chain, which is ours and is signed, and the outcome of the order, which is theirs and is
not. Approv can say what it would have decided. Only the partner can say whether the
customer sent it back.

**The ingestion path landed while this was being written, and it carries less than the
report needs.** `types.core.OrderOutcome` is the real wire shape: a stream of
shipped / returned / disputed / refunded events joined by `correlation_id`, with the
merchant's reason kept as verbatim free text. `from_order_outcomes` folds it into the
view below, and two things are missing from it that no amount of folding can supply —
both named in `MISSING_FROM_INGESTION` and both printed on the report as the reason a row
could not be computed.

`Outcome` below is therefore two things at once: the enriched view the report needs, and
the specification of what the ingestion path still has to deliver. A feed says which of
the two it can support, and a metric that needs what it cannot support prints the reason
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
from datetime import datetime
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
    # The customer's own words, where the desk kept them. Untrusted text like any other:
    # quoted on a report, never parsed into a finding.
    reason_text: str | None = None
    # Which attribute the customer complained about, if the desk coded one at all.
    attribute: str | None = None
    # The partner's own fault assessment. Theirs, recorded as theirs.
    merchant_fault: bool | None = None
    resolved_at: datetime | None = None
    window_closes_at: datetime | None = None

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
        """Whether this order line has an outcome at all. OPEN never counts as one."""
        return self.status is not Status.OPEN


class FeedSource(str, Enum):
    """Where a feed came from, carried to the page.

    PARTNER is the real thing. FIXTURE is a file we wrote to build this report against a
    shape that does not exist yet. The distinction is on every outcome-derived row rather
    than in a footnote, because a report that has to be read carefully to avoid being
    misread is badly built.
    """

    PARTNER = "partner"
    FIXTURE = "fixture"


# What the report cannot compute from `types.core.OrderOutcome` as it stands today, and
# why folding cannot fix either. Printed verbatim on the report wherever a row is blocked.
NO_WINDOW_CLOSE = (
    "This feed records shipped / returned / disputed / refunded events and never records "
    "that a return window closed with no return. An order that was kept is therefore "
    "indistinguishable from one still inside its window, so the only orders with a known "
    "outcome are the ones that came back - and any rate computed over that denominator "
    "would be 100% by construction. Approv will not print such a number."
)

NO_REASON_CODE = (
    "This feed carries the merchant's reason as verbatim free text with no code. Approv "
    "will not classify it: turning a merchant's words into a signal is exactly what the "
    "outcome fence exists to prevent, and grading our own work against a taxonomy we "
    "chose would measure nothing. The desk's own coding is what makes this measurable."
)

MISSING_FROM_INGESTION = (
    ("a terminal 'kept' fact, or the window close date", NO_WINDOW_CLOSE),
    ("the returns desk's own reason code, as a coded field", NO_REASON_CODE),
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

    @property
    def is_real(self) -> bool:
        return self.source is FeedSource.PARTNER

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
# What the ingestion path has to deliver
# --------------------------------------------------------------------------------------

REQUIRED_OF_INGESTION = (
    "A terminal 'kept' fact, or the window close date. Without one, an order that was "
    "kept cannot be told from one still inside its window, and precision cannot be "
    "computed at all - see NO_WINDOW_CLOSE.",
    "The desk's own reason code as a coded field. Their `not_as_described` is the "
    "measurement; classifying their free text on our side would be grading our own work "
    "- see NO_REASON_CODE.",
    "Which attribute the customer complained about, where the desk codes one. Optional, "
    "and it is what moves attribution off the weaker record-level fallback.",
    "Outcomes for orders Approv never saw, not only for ones it did. Those are what "
    "reveal the share of the partner's agentic traffic that never reached us.",
)


def from_order_outcomes(events: Iterable, *, source: FeedSource,
                        description: str = "", **kw) -> OutcomeFeed:
    """Fold `types.core.OrderOutcome` events into one view per order.

    An order can carry several events — shipped, then returned, then refunded — so the
    fold takes the strongest fact: any of returned, refunded or disputed makes it a
    return, and shipped on its own does **not** make it kept.

    **Shipped is folded to OPEN, never to KEPT.** Nothing in the wire type says a return
    window closed, so "shipped and we have heard nothing since" is an unknown and not a
    kept order. Folding it to KEPT would be the single easiest way to inflate every rate
    on the report, and the resulting feed declares `records_window_close=False` so the
    metrics that depend on the distinction refuse to print a number at all.
    """
    folded: dict[str, Outcome] = {}
    for event in events:
        kind = getattr(event.kind, "value", str(event.kind))
        returned = kind in ("returned", "refunded", "disputed")
        existing = folded.get(event.correlation_id)
        if existing is not None and existing.status is Status.RETURNED:
            continue
        folded[event.correlation_id] = Outcome(
            order_id=event.correlation_id, correlation_id=event.correlation_id,
            status=Status.RETURNED if returned else Status.OPEN,
            # Never parsed. Carried so a person can read it, and read by nothing.
            reason_text=event.merchant_reason,
            resolved_at=event.occurred_at if returned else None)
    return OutcomeFeed(source=source, description=description,
                       outcomes=tuple(folded.values()), records_window_close=False,
                       records_reason_code=False, **kw)
