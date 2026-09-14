"""What a partner gets for what a partner gives.

Partners will not all land at the same place. One can send an order feed and nothing
else; one has a returns export with their desk's own coding; one can send chargebacks.
The report has to be *honest at each of those*, which is a stronger requirement than
being correct at the top: a partner at the minimum tier must receive a report that says
clearly what it cannot yet say, not one that looks broken.

So the tier is **derived from the feed's declared capabilities, never asserted**. Nobody
tells this module which tier a partner is at; it reads what the feed says it can support
and names the rung. A feed cannot flatter itself into a higher tier, and a metric blocked
at a given rung prints the rung that would unlock it and the exact field that gets there.

**The ladder is the common path, the capabilities are the truth.** Real feeds are a
lattice, not a line — a partner could send reason codes and no window close date, which
is above MINIMUM on one axis and below it on another. `tier_of` returns the highest rung
whose every requirement is met, so such a feed reads as RETURNS_ONLY, and the report
prints the capability flags beside the rung so the partner is never described as having
sent less than they did.

**None of this is a pricing ladder.** It is a data ladder. No tier here implies a
commercial term, and a report at BEST is not a covered report — coverage attaches per
channel under DR 0020 and nothing in this module speaks to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

VERSION = "report-tiers-v1"


class Tier(IntEnum):
    """How much of the outcome side a partner's data can support.

    Ordered on purpose: a blocked row says which rung it needs, and comparing rungs is
    how it works out what to print. An `IntEnum` rather than the usual string enum for
    exactly that — the order is the semantics here, not an afterthought.
    """

    NONE = 0
    RETURNS_ONLY = 1
    MINIMUM = 2
    GOOD = 3
    BEST = 4


@dataclass(frozen=True)
class TierSpec:
    """One rung: what it costs the partner, what it buys, and what it still cannot buy.

    `cannot` is not a disclaimer. It is the reason the next rung exists, and it is the
    half of this table a partner would never be told by anyone selling them something.
    """

    tier: Tier
    name: str
    headline: str
    supplies: tuple[str, ...]
    unlocks: tuple[str, ...]
    cannot: tuple[str, ...]


TIERS: dict[Tier, TierSpec] = {
    Tier.NONE: TierSpec(
        tier=Tier.NONE, name="NO OUTCOME DATA",
        headline="Order events reach Approv; nothing comes back about what happened.",
        supplies=("the order events you already send to be verified",),
        unlocks=(
            "volume observed, split by where the stated request came from",
            "what Approv would have decided, and how often it would have refused",
            "how much of your traffic carries a stated request we can recover at all",
            "which of your channels earn coverage, and which earn none",
            "a signed receipt per order, and a ledger you can check yourself with the "
            "published key and none of our code",
        ),
        cannot=(
            "anything at all about what happened after the order. Every outcome row on "
            "the report prints unanswered, which is the honest shape of a first week.",
        )),
    Tier.RETURNS_ONLY: TierSpec(
        tier=Tier.RETURNS_ONLY, name="RETURNS ONLY",
        headline="We know which orders came back. We cannot tell a kept order from one "
                 "still inside its window.",
        supplies=("which orders came back, joined on correlation id or order and line",),
        unlocks=(
            "returns matched to a receipt, counted rather than rated",
            "orders your returns desk saw that Approv never did - the share of your "
            "traffic that is not reaching us, which no other number here can see",
        ),
        cannot=(
            "any rate whose denominator needs kept orders. An order that was kept looks "
            "exactly like one still inside its window, so the only orders with a known "
            "outcome are the ones that came back, and every rate over that denominator "
            "is 100% by construction. Approv will not print such a number.",
        )),
    Tier.MINIMUM: TierSpec(
        tier=Tier.MINIMUM, name="MINIMUM",
        headline="Kept is derivable, so rates become possible. Why anything came back "
                 "is still unknown.",
        supplies=("ship date per order line",
                  "the length of your return window, so a closed window with no return "
                  "is a kept order"),
        unlocks=(
            "the return rate of orders Approv would have refused, beside the return rate "
            "of orders it would have allowed - the comparison between those two rows is "
            "the first real signal in this report",
            "how much of the period is still open, as a caveat on everything above it",
        ),
        cannot=(
            "precision, recall or attribution. Those all rest on *why* an order came "
            "back, and at this tier every return counts the same: a changed mind, a "
            "damaged parcel and a wrong colour are one number.",
            "any claim that a return was a verification failure. Approv never claimed to "
            "predict a changed mind and must not be credited with one.",
        )),
    Tier.GOOD: TierSpec(
        tier=Tier.GOOD, name="GOOD",
        headline="Your desk's own coding arrives, so the report can finally separate the "
                 "returns this product is about from the ones it is not.",
        supplies=("your returns desk's own reason code, as a coded field and not as free "
                  "text",
                  "optionally, which attribute the customer complained about"),
        unlocks=(
            "PRECISION: of the orders Approv would have refused, the share that came "
            "back coded not-as-described or wrong-item. The headline of this report.",
            "RECALL: of the wrong-item returns, the share Approv had said something about",
            "attribution: whether the record shows the agent chose against the request, "
            "the published data matched and the item still did not, nobody asked, or "
            "Approv failed to read part of the request",
            "the payout proxy: orders carrying a finding we would have stood behind that "
            "came back as the wrong item anyway",
        ),
        cannot=(
            "measure the expensive tail. A return is a cost; a chargeback is a threat to "
            "your card acceptance, and nothing at this tier can tell them apart.",
            "re-code your desk's judgement. Approv records their code as theirs and "
            "never classifies the free text: grading our own work against a taxonomy we "
            "chose would measure nothing.",
        )),
    Tier.BEST: TierSpec(
        tier=Tier.BEST, name="BEST",
        headline="Disputes and chargebacks arrive, so the report can price the tail "
                 "rather than only count the returns.",
        supplies=("dispute and chargeback events, joined the same way",),
        unlocks=(
            "of the orders that became a dispute, the share Approv would have refused",
            "the dispute rate of would-have-refused orders beside would-have-allowed "
            "orders, which is the exposure a guarantee would actually be priced against",
        ),
        cannot=(
            "tell you what a guarantee would cost. No coverage contract exists, every "
            "term of one is open, and nothing on this report is a payout figure.",
            "see an order your system never submitted to Approv. That denominator is "
            "yours at every tier, and it is the limit of this whole report.",
        )),
}

LADDER = tuple(TIERS[tier] for tier in sorted(TIERS))

# What the ladder is, said once, on the page. A partner reading a blocked row needs to
# know the block is about their data rather than about their result.
LADDER_MEANS = (
    "Every row this report could not compute was blocked by a field that is missing from "
    "the outcome feed, not by a result that came out badly. This is what each further "
    "field would buy. Nothing here is a price list: it is a data list, and the rung you "
    "are on is read off the feed you sent rather than agreed in advance."
)

CAPABILITIES_ARE_THE_TRUTH = (
    "The rung is the highest one whose every requirement your feed meets. If you sent "
    "something unusual - reason codes but no window close date, say - the rung will read "
    "lower than the flags listed above, and those flags are what the report acts on."
)


def tier_of(feed) -> Tier:
    """The highest rung whose every requirement this feed meets.

    Read off the feed's own capability flags. Deliberately the *highest complete* rung
    rather than the highest flag set: a feed missing a lower rung's requirement has not
    reached the higher one, whatever else it carries, and saying otherwise would put a
    partner on a rung whose unlocked rows then print NOT COMPUTED.
    """
    if not feed.outcomes:
        return Tier.NONE
    if not feed.records_window_close:
        return Tier.RETURNS_ONLY
    if not feed.records_reason_code:
        return Tier.MINIMUM
    if not feed.records_disputes:
        return Tier.GOOD
    return Tier.BEST


def capability_flags(feed) -> tuple[tuple[str, bool], ...]:
    """The flags themselves, for the page. What the report acts on, rung aside."""
    return (
        ("outcomes supplied at all", bool(feed.outcomes)),
        ("can tell a kept order from an open one", feed.records_window_close),
        ("carries your desk's own reason code", feed.records_reason_code),
        ("carries dispute and chargeback events", feed.records_disputes),
    )


def needs(current: Tier, required: Tier) -> str:
    """The sentence appended to a blocked row: which rung, and the field that gets there.

    Printed beside the reason the metric is uncomputable rather than instead of it. The
    reason says why the number would be wrong; this says what would fix it. A row that
    said only the second would read as a sales prompt attached to a missing number.
    """
    if required <= current:
        return ""
    spec = TIERS[required]
    # Every rung between here and there, not only the target one. A partner two rungs
    # down who is told to send dispute events will send them and still get NOT COMPUTED,
    # because the row also needs the kept orders and the coding underneath - and a second
    # accurate-looking instruction that does not work is worse than none.
    climb = [item for rung in sorted(TIERS)
             if current < rung <= required for item in TIERS[rung].supplies]
    return ("This row needs the %s tier and this feed is at %s. To reach %s, send: %s."
            % (spec.name, TIERS[current].name, spec.name, "; ".join(climb)))
