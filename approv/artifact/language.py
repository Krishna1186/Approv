"""Enum to plain language, for one audience: a returns desk.

Wording is rendered at the boundary and never stored (§2.7). `algebra/feedback.py` does
the same job for a different reader — an agent that has to repair a request — and its
sentences are imperative and technical for that reason. This one is read by a person
deciding whether to refuse a real customer's refund, so nothing here abbreviates and
nothing here tells that person what to decide.

Every member of every enum this document prints has an entry below, asserted by test. A
missing entry would fall through to the enum's own value, and `out_of_coverage` printed
raw on a document that settles a refund is exactly the failure this module exists to
prevent.
"""

from __future__ import annotations

from decimal import Decimal

from approv.types.core import (
    Attestation, Bound, BoundOp, Certainty, CheckKind, Count, Criticality, Decision,
    Liability, Money, Quantity, ReasonCode, Support, Term, Value,
)

VERSION = "artifact-language-v1"

# --- the three words a returns desk acts on ---------------------------------------------

VERDICT: dict[Support, str] = {
    Support.SATISFIED: "Met",
    Support.VIOLATED: "NOT MET",
    Support.UNSTATED: "Not checked",
}

# What the decision was, and — the half usually missed — what it does not mean. An
# `allow` is not a statement that everything matched: a preference can be contradicted
# under one, and a returns agent who reads "authorised" as "nothing was wrong" will tell
# a customer something this record does not support.
#
# Templates, because the subject is not always an order. A record built at shelf time
# carries no order line, and a headline saying "this order" would assert a purchase the
# record cannot show — the largest sentence on the page claiming the one thing missing
# from it.
DECISION_HEADLINE: dict[Decision, str] = {
    Decision.ALLOW: "Approv authorised %s",
    Decision.CONFIRM: "Approv did not authorise %s on its own",
    Decision.REFUSE: "Approv refused %s",
}

ORDER_SUBJECT = "this order"
NO_ORDER_SUBJECT = "this product comparison"

DECISION_MEANS: dict[Decision, str] = {
    Decision.ALLOW: (
        "Approv compared the request it was given against %s and found no blocking "
        "requirement contradicted and none left unresolved."
    ),
    Decision.CONFIRM: (
        "At least one blocking requirement could not be settled from the merchant's own "
        "catalogue data, so Approv asked for confirmation before purchase instead of "
        "authorising %s. Unknown never authorises."
    ),
    Decision.REFUSE: (
        "The merchant's own catalogue data contradicted a blocking requirement, so "
        "Approv refused %s. If it was fulfilled anyway it was fulfilled against this "
        "decision, and this record does not defend it."
    ),
}

DECISION_DOES_NOT_MEAN: dict[Decision, str] = {
    Decision.ALLOW: (
        "It does not mean every requirement was checked, that the catalogue was true, or "
        "that the customer is satisfied. Anything marked Not checked or NOT covered "
        "below played no part in it."
    ),
    Decision.CONFIRM: (
        "It is not a finding that the order was wrong. It is a finding that Approv could "
        "not settle it either way. Whether it was confirmed, and by whom, is not "
        "recorded here."
    ),
    Decision.REFUSE: (
        "It does not mean the customer was harmed and it does not say what happened "
        "next. It says the catalogue contradicted the request at the moment of decision."
    ),
}


def subject(*, has_order: bool) -> str:
    return ORDER_SUBJECT if has_order else NO_ORDER_SUBJECT


def headline(decision: Decision, *, has_order: bool) -> str:
    return DECISION_HEADLINE[decision] % subject(has_order=has_order)


def means(decision: Decision, *, has_order: bool) -> str:
    """The decision's meaning, with the subject the record can actually support.

    All three sentences carry the placeholder, because `%` against a string that has none
    raises rather than passing the text through — so a sentence rewritten without it would
    fail loudly here instead of quietly printing "this order" over a record that has none.
    """
    return DECISION_MEANS[decision] % subject(has_order=has_order)


# --- how much an attribute counted ------------------------------------------------------

WEIGHT: dict[Criticality, str] = {
    Criticality.HARD: "Blocking",
    Criticality.BOUND: "Blocking",
    Criticality.SOFT: "Preference",
    Criticality.COSMETIC: "Recorded only",
}

WEIGHT_MEANS: dict[Criticality, str] = {
    Criticality.HARD: "Getting this wrong means a return, so silence on it stops an order.",
    Criticality.BOUND: "A limit that may be tightened but never exceeded.",
    Criticality.SOFT: "A preference. Approv never blocks an order over one.",
    Criticality.COSMETIC: "Recorded for this document only. It never blocks anything.",
}

# --- coverage ---------------------------------------------------------------------------
#
# The one section of this document that may not be soft. PRD §6 is equally firm in the
# other direction: the coverage contract is unanswered, so no wording here may read as a
# promise to pay. Both hold at once — this names the class a finding falls in, and says
# in the same breath that the promise lives in a contract and not in a document.

GUARANTEED = "guaranteed"
REFUSED = "refused"
OUT_OF_COVERAGE = "out_of_coverage"
UNRECORDED = "unrecorded"

COVERAGE_LABEL: dict[str, str] = {
    GUARANTEED: "Covered",
    REFUSED: "Refused, so no promise",
    OUT_OF_COVERAGE: "NOT covered",
    UNRECORDED: "NOT recorded",
}

# The same four classes as one word each, for the tally line. Separate from the labels
# because "1 Refused, so no promise" is not a sentence, and a tally that reads badly is a
# tally people skip.
COVERAGE_TALLY: dict[str, str] = {
    GUARANTEED: "covered",
    REFUSED: "refused",
    OUT_OF_COVERAGE: "NOT covered",
    UNRECORDED: "NOT recorded",
}

COVERAGE_MEANS: dict[str, str] = {
    GUARANTEED: (
        "Inside the class of findings Approv stands behind under the merchant's coverage "
        "agreement."
    ),
    REFUSED: (
        "Approv did not authorise this. A refusal is a decision that already happened, "
        "not a promise about what follows from it."
    ),
    OUT_OF_COVERAGE: (
        "Approv declined to stand behind this finding. Do not present it to a customer "
        "as something Approv guarantees."
    ),
    UNRECORDED: (
        "This record does not say which coverage class this finding falls in, so it has "
        "to be read as carrying no promise."
    ),
}

COVERAGE_CAVEAT = (
    "Coverage terms live in the merchant's agreement with Approv. This record states "
    "which class each finding falls in; it does not by itself create a promise to pay, "
    "and a finding marked NOT covered carries no promise of any kind."
)

# --- where a requirement came from ------------------------------------------------------

PROVENANCE: dict[str, str] = {
    "tool_argument": "the agent put it in a structured field of its own request",
    "mandate": "it was carried in the agent's payment mandate",
    "agent_message": "Approv read it out of the agent's free-text message",
    "implied_by_selection": "it was inferred from what the agent selected, not stated",
}

ATTESTATION: dict[Attestation, str] = {
    Attestation.BOTH_SIGNED: (
        "Both halves of this record were signed by the party they came from."
    ),
    Attestation.AGENT_ONLY: (
        "Only the agent's half was signed by its originator. The merchant's half is "
        "unattested."
    ),
    Attestation.MERCHANT_ONLY: (
        "Only the merchant's half was signed by its originator. The agent's half is "
        "unattested."
    ),
    Attestation.NEITHER: (
        "Neither half was signed by the party it came from. This is Approv's account of "
        "what it was told, not a signed statement by either party."
    ),
}

CHECK: dict[CheckKind, str] = {
    CheckKind.CONSISTENCY: (
        "The agent's own statement was checked against the request it said it had."
    ),
    CheckKind.GROUNDING: (
        "What the agent said about the product was checked against the merchant's "
        "catalogue."
    ),
    CheckKind.SATISFACTION: "The request was checked against the merchant's catalogue.",
}

# --- where a catalogue value came from --------------------------------------------------

LIABILITY: dict[Liability, str] = {
    Liability.MERCHANT_GUARANTEED: "the merchant's own published data",
    Liability.SELLER_STATED: "a seller's own copy",
    Liability.PLATFORM_DERIVED: "data derived by the platform",
    Liability.UNATTRIBUTED: "text nobody is answerable for",
}

CERTAINTY: dict[Certainty, str] = {
    Certainty.EXACT: "read from a dedicated field",
    Certainty.PARSED: "parsed out of text",
    Certainty.INFERRED: "inferred",
}

# --- why a comparison did not come out clean --------------------------------------------

REASON: dict[ReasonCode, str] = {
    ReasonCode.FLOOR_NOT_MET: (
        "This category cannot be checked at all without this attribute, and it was not "
        "available."
    ),
    ReasonCode.NO_CLAIM: "Nothing was said about this attribute, so nothing was checked.",
    ReasonCode.PRODUCT_SILENT: (
        "The catalogue does not publish this attribute, so there was nothing to check "
        "against."
    ),
    ReasonCode.INCOMMENSURABLE: (
        "The request and the catalogue measure different things, so no comparison was "
        "possible."
    ),
    ReasonCode.LOW_LIABILITY_SOURCE: (
        "The only value available came from text nobody is answerable for, such as a "
        "review."
    ),
    ReasonCode.LOW_CERTAINTY_SOURCE: (
        "The value was read out of free text rather than a dedicated field, so it cannot "
        "settle a blocking requirement on its own."
    ),
    ReasonCode.FIELD_CONFLICT: (
        "Two fields in the merchant's own catalogue disagree with each other."
    ),
    ReasonCode.ADVICE_CONTRADICTS: (
        "Seller guidance contradicts the structured field. Guidance cannot override a "
        "published fact."
    ),
    ReasonCode.UNRESOLVED_TERM: "The catalogue uses a word or unit Approv could not compare.",
    ReasonCode.WITHIN_TOLERANCE: (
        "The values differ slightly, within the margin allowed for this attribute."
    ),
    ReasonCode.CLAIM_MORE_SPECIFIC: (
        "The request says more than the catalogue does, so the catalogue neither confirms "
        "nor contradicts it."
    ),
    ReasonCode.LISTING_MORE_SPECIFIC: (
        "The catalogue names a narrower variant than the one asked for, so it neither "
        "confirms nor contradicts it."
    ),
    ReasonCode.AGENT_SELF_CONTRADICTION: (
        "This contradicts what the agent asked for earlier in the same session."
    ),
    ReasonCode.UNATTESTED_COUNTERPARTY: (
        "One side of this record was not signed by the party it came from."
    ),
    ReasonCode.DUPLICATE_CLAIM: (
        "The agent stated this attribute more than once and the statements disagree."
    ),
    ReasonCode.UNKNOWN_ATTRIBUTE: (
        "This attribute is outside the schema configured for this category, so it was "
        "not checked."
    ),
    ReasonCode.UNTRUSTED_SOURCE: "The field this came from has no trusted source profile.",
    ReasonCode.ADVICE_ONLY: (
        "The only support was seller advice, which is not admissible as a product fact."
    ),
}

BOUND_WORD: dict[BoundOp, str] = {
    BoundOp.LTE: "no more than",
    BoundOp.LT: "under",
    BoundOp.GTE: "at least",
    BoundOp.GT: "over",
}


def _number(amount: Decimal, *, trim: bool) -> str:
    """A decimal as a person writes it: no exponent, and no invented precision.

    Money keeps the digits it was recorded with — 118.00 is not 118 on a refund — and a
    measurement drops the trailing zeros a feed happened to publish.
    """
    return format(amount.normalize() if trim else amount, "f")


def value(item: Value) -> str:
    """One recorded value, rendered. It never invents and never rounds a price."""
    if isinstance(item, Bound):
        return "%s %s" % (BOUND_WORD[item.op], value(item.limit))
    if isinstance(item, Money):
        return "%s %s" % (_number(item.amount, trim=False), item.currency)
    if isinstance(item, Quantity):
        return "%s %s" % (_number(item.magnitude, trim=True), item.unit)
    if isinstance(item, Count):
        return str(item.n)
    if isinstance(item, Term):
        return item.surface
    return str(item)  # pragma: no cover - unreachable through the Value union


def attribute(name: str) -> str:
    """`pack_count` as words. The schema's spelling is a key, not a label."""
    return name.replace("_", " ").strip() or name


def provenance(channel) -> str:
    """How a requirement reached us, in words. An unknown channel says so.

    Falling back to a sentence rather than to the enum's own value: a returns desk
    reading `implied_by_selection` learns nothing, and a document that prints a token it
    cannot explain is claiming an authority it does not have.
    """
    return PROVENANCE.get(
        getattr(channel, "value", str(channel)),
        "the channel it arrived on is not one this document can describe",
    )
