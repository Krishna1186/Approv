"""approv.types.core — the shared vocabulary.

DR 0002 fixes this module as types and enums only: no logic, no I/O, and no import from
anywhere else in `approv`. It is the one module both `semantic/` and `evaluator/` are
permitted to import, which is what makes §4.1 enforceable — the evaluator can speak the
same language as the semantic stage without importing it.

DR 0016 fixes what is being compared. Approv does not ask "does this product match the
user's intent". It asks "did the agent read this product correctly, and from which
field". Everything below is built around that question.

Nothing here decides anything. These are nouns.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------


class Dimension(str, Enum):
    """What a value is measured in, at the level where comparison is even meaningful.

    Two values may only be compared if they share a dimension. 500 g against 250 ml is
    not False — it is INCOMMENSURABLE, and that distinction is the whole reason this
    enum exists rather than everything being a string.
    """

    MASS = "mass"
    VOLUME = "volume"
    LENGTH = "length"
    COUNT = "count"
    MONEY = "money"
    TIME = "time"
    NOMINAL = "nominal"


class Liability(str, Enum):
    """Who owes a remedy if this text turns out to be wrong. DR 0016 §3, axis one.

    Legacy source-attribution labels. These do not establish legal liability,
    enforceability, collectability or insurance coverage; contracts must do that.
    """

    MERCHANT_GUARANTEED = "merchant_guaranteed"
    SELLER_STATED = "seller_stated"
    PLATFORM_DERIVED = "platform_derived"
    UNATTRIBUTED = "unattributed"


class Certainty(str, Enum):
    """How sure we are that we read the value correctly. DR 0016 §3, axis two.

    Independent of Liability. A merchant's description is high liability and low
    certainty at the same time.
    """

    EXACT = "exact"
    PARSED = "parsed"
    INFERRED = "inferred"


class Criticality(str, Enum):
    """How much this attribute being wrong actually costs.

    HARD      wrong value means a return. Silence routes to confirm.
    BOUND     a limit that may be tightened but never widened (price ceiling).
    SOFT      a preference. Silence is tolerable.
    COSMETIC  never blocks anything; recorded for the receipt only.
    """

    HARD = "hard"
    BOUND = "bound"
    SOFT = "soft"
    COSMETIC = "cosmetic"


class Support(str, Enum):
    """The per-attribute ternary. §2.1 vocabulary, DR 0016 semantics.

    SATISFIED  the product data supports the claim
    VIOLATED   the product data contradicts the claim
    UNSTATED   the product data is silent, so no comparison was run
    """

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNSTATED = "unstated"


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    REFUSE = "refuse"


class Mode(str, Enum):
    """Whether this decision gated a real transaction or only watched one.

    A shadow run is how a merchant finds out what Approv would have done before it does
    anything — the only honest way to price the nuisance and false-allow rates on their own
    traffic rather than on our corpus.

    **A shadow receipt must never be presentable as though it gated a real transaction.**
    So the mode is on the record and inside the digest, it is deployment configuration
    rather than request payload (a caller who could send `enforce` could defeat sandbox
    isolation with one JSON field), and it defaults to SHADOW everywhere. The two mistakes
    are not symmetric: a shadow record mislabelled `enforce` is a false claim in a dispute,
    while an enforce record mislabelled `shadow` merely under-claims and is recoverable.
    Only the second is reachable by forgetting.
    """

    SHADOW = "shadow"
    ENFORCE = "enforce"


class OutcomeKind(str, Enum):
    """What actually happened to an order, long after the decision.

    The measurement a shadow run exists to produce, and the input DR 0012's pricing needs:
    a false allow nobody notices costs nothing, and only the outcome says which is which.
    """

    SHIPPED = "shipped"
    RETURNED = "returned"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


class OrderOutcome(BaseModel):
    """One later fact about one verified order, joined by `correlation_id`.

    `merchant_reason` is the merchant's own words, recorded verbatim and **decided on by
    nothing**. It is the field most likely to be quietly turned into a signal — a reason
    code, a classifier, a criticality input — and the moment it is, a merchant's free text
    is in the decision path and §1's central claim is false. A test asserts that neither
    `evaluator/` nor `algebra/` nor `criticality` imports this module's outcome types.

    `mode` travels with the outcome so a sandbox result can never be joined to a live
    record. Nothing here is a decision; it is evidence about one already made.

    **Everything below `merchant_reason` is optional, and that is the point.** Partners
    arrive at different tiers: some send a returns export with nothing but a date, some
    code every return, some can say when a window closed. A feed must degrade honestly
    rather than refuse — a required field would turn "this partner cannot answer that yet"
    into "this partner cannot be onboarded", and the report already knows how to print the
    reason a row cannot be computed instead of a number.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    correlation_id: str = Field(min_length=1)
    kind: OutcomeKind
    occurred_at: datetime
    mode: Mode = Mode.SHADOW
    merchant_id: str | None = None
    merchant_reason: str | None = None
    # The returns desk's **own** code, verbatim and as a field of its own rather than a
    # reading of the free text beside it.
    #
    # A string, deliberately not an enum of ours. Classifying `merchant_reason` into an
    # Approv taxonomy would mean grading our own work against categories we chose, which
    # measures nothing: we would decide what counts as "wrong item" and then report how
    # often we got "wrong item" right. Their coding is evidence because they chose it, and
    # they chose it before knowing what we would do with it. A consumer that recognises
    # the code may use it; one that does not keeps it raw and says so.
    reason_code: str | None = None
    # When the line shipped and how long the customer has to send it back. Between them
    # these make **kept** derivable — window closed, nothing came back — and without one
    # of them it is not derivable at all.
    #
    # This is the difference between a precision figure and a tautology. A return is known
    # on the day it happens; a keep is only ever known by a window expiring. So a feed of
    # shipped/returned events alone has a denominator containing every return and no keeps,
    # and any rate over it is 100% by construction. `report.outcomes` refuses to print such
    # a number, correctly, and these fields are what let it print one instead.
    ship_date: datetime | None = None
    return_window_days: int | None = Field(default=None, ge=0)
    # The close date outright, where the partner can send it. Preferred over ship-plus-days
    # by anything that reads both: a partner computing this has already applied their own
    # holiday rules, extensions and goodwill exceptions, and recomputing it from a nominal
    # window length would overwrite their answer with our arithmetic.
    return_window_closes_at: datetime | None = None
    # What the merchant shipped or took back, when they say. Free of any claim that it
    # matches the order line: a returns desk records what came back, not what was owed.
    sku: str | None = None
    quantity: int | None = Field(default=None, ge=0)


class Completion(str, Enum):
    """Whether the verification ran to a conclusion, and if not, whose problem it was.

    DR 0004. Orthogonal to `Decision` on purpose: a provider outage is not a verdict about
    the purchase, it is a fact about us, and putting it in the same enum would force every
    consumer to handle "the shop is on fire" inside a switch about whether the duvet is the
    right colour. A fourth transaction state has been proposed and killed before; this is
    the axis that was actually missing.

    `CATALOGUE_UNREADABLE` is separate from the rest because *"your catalogue is wrong"*
    and *"our vendor is down"* are the two sentences a merchant needs told apart, and one
    refusal covering both tells them neither.
    """

    COMPLETED = "completed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNREADABLE_RESPONSE = "unreadable_response"
    BUDGET_EXCEEDED = "budget_exceeded"
    CATALOGUE_UNREADABLE = "catalogue_unreadable"
    INTERNAL_ERROR = "internal_error"


class UnreadPolicy(str, Enum):
    """What a request we did not finish reading does to the answer. DR 0022.

    An unread requirement is *our* failure, not the merchant's and not the shopper's, and
    the three ways of handling it put the cost in three different places.

    ESCALATE  fail the verification floor: confirm rather than authorise. The merchant
              pauses their checkout over our extraction miss, which charges them for our
              defect. Measured at 75.5% nuisance on the v3 pack, which is unshippable.
    WITHDRAW  authorise, and withdraw the guarantee. The sale proceeds, the merchant keeps
              the risk on that order, and we promise nothing about a request we could not
              read. The third option coverage created, the same one that fixed hedges and
              fixed narrowing.
    IGNORE    authorise and guarantee anyway. Kept only so DR 0022's table can be
              reproduced; it is the dishonest one, because it sells a promise over words
              nobody read.
    """

    ESCALATE = "escalate"
    WITHDRAW = "withdraw"
    IGNORE = "ignore"


class CheckKind(str, Enum):
    """Which of DR 0016 §2's three comparisons produced a finding.

    CONSISTENCY  agent's own constraint vs agent's own claim. Needs no catalogue.
    GROUNDING    agent's claim vs the merchant's data. The core check.
    SATISFACTION agent's constraint vs the merchant's data. The classic intent check.
    """

    CONSISTENCY = "consistency"
    GROUNDING = "grounding"
    SATISFACTION = "satisfaction"


class Channel(str, Enum):
    """Where the agent put an assertion on the record. DR 0008's tiers, made concrete.

    TOOL_ARGUMENT is the strongest: the agent typed it into a structured call, so there
    is no extraction step and nothing to dispute about what it said.
    """

    TOOL_ARGUMENT = "tool_argument"
    MANDATE = "mandate"
    AGENT_MESSAGE = "agent_message"
    IMPLIED_BY_SELECTION = "implied_by_selection"


class Attestation(str, Enum):
    """Which halves of the record were signed by their originator. DR 0016 §6.

    A missing half is UNATTESTED, never absence of evidence in that party's favour.
    """

    BOTH_SIGNED = "both_signed"
    AGENT_ONLY = "agent_only"
    MERCHANT_ONLY = "merchant_only"
    NEITHER = "neither"


class ReasonCode(str, Enum):
    """Why a comparison did not produce a clean SATISFIED or VIOLATED.

    Reasons are fields, not prose (§2.7 record spec). Anything a human would want to
    read as a sentence is rendered from these, never stored as one.
    """

    FLOOR_NOT_MET = "floor_not_met"
    NO_CLAIM = "no_claim"
    PRODUCT_SILENT = "product_silent"
    INCOMMENSURABLE = "incommensurable"
    LOW_LIABILITY_SOURCE = "low_liability_source"
    LOW_CERTAINTY_SOURCE = "low_certainty_source"
    FIELD_CONFLICT = "field_conflict"
    ADVICE_CONTRADICTS = "advice_contradicts"
    UNRESOLVED_TERM = "unresolved_term"
    WITHIN_TOLERANCE = "within_tolerance"
    CLAIM_MORE_SPECIFIC = "claim_more_specific"
    LISTING_MORE_SPECIFIC = "listing_more_specific"
    AGENT_SELF_CONTRADICTION = "agent_self_contradiction"
    UNATTESTED_COUNTERPARTY = "unattested_counterparty"
    DUPLICATE_CLAIM = "duplicate_claim"
    UNKNOWN_ATTRIBUTE = "unknown_attribute"
    UNTRUSTED_SOURCE = "untrusted_source"
    ADVICE_ONLY = "advice_only"


class Resolution(str, Enum):
    """What the agent could actually do about a finding.

    A verdict an agent cannot act on is worth very little. Compilers made coding agents
    good by saying *which line* and *what is wrong*, not by saying "no". This enum is the
    equivalent: every non-clean outcome names the move that would resolve it, including
    the honest case where there is no move.
    """

    NONE_NEEDED = "none_needed"
    PICK_DIFFERENT_PRODUCT = "pick_different_product"
    RESTATE_CLAIM = "restate_claim"
    FIND_BETTER_SOURCE = "find_better_source"
    STATE_THE_ATTRIBUTE = "state_the_attribute"
    # Measured 9 September: on ten requests where nothing in the results satisfied the
    # constraint, a control that received no information declined all ten and Approv
    # declined five. Every resolution above sends the agent looking for something else,
    # which reads as encouragement to keep shopping when the honest answer is that the
    # item is not there. Naming the move is the only way an agent can take it.
    DECLINE_NO_MATCH = "decline_no_match"
    # The counterpart DECLINE_NO_MATCH had been missing, and the asymmetry was measured.
    # On the 10 September study the shelf check named the satisfying candidate on five
    # held-out cases and the agent abstained on all five, because the report could tell it
    # to stop shopping and had no way to tell it to proceed. This is a repair resolution
    # like every other member here, addressed to an agent — it is not `Decision.ALLOW`,
    # which only `evaluator/` may return, and its wording keeps the identity caveat.
    SELECT_FROM_SUPPORTED = "select_from_supported"
    NOT_RESOLVABLE = "not_resolvable"


# --------------------------------------------------------------------------------------
# Values
#
# Each carries a literal `kind` so the union below can be discriminated. That is not
# decoration: a ComparisonRecord is signed, so it must round-trip through JSON and
# deserialise to exactly the same object, and an undiscriminated union does not
# guarantee that.
# --------------------------------------------------------------------------------------


class Quantity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["quantity"] = "quantity"
    magnitude: Decimal = Field(ge=0, max_digits=28, decimal_places=12)
    unit: str
    dimension: Dimension


class Money(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["money"] = "money"
    amount: Decimal = Field(ge=0, max_digits=28, decimal_places=12)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Count(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["count"] = "count"
    n: int = Field(ge=0, strict=True)


class Term(BaseModel):
    """A word, plus the node it resolved to if it resolved at all.

    `node_id` is None when entity linking failed. That is UNRESOLVED_TERM, not a
    mismatch, and the two must never be collapsed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["term"] = "term"
    surface: str
    node_id: str | None = None
    aliases: tuple[str, ...] = ()


class BoundOp(str, Enum):
    LTE = "lte"
    LT = "lt"
    GTE = "gte"
    GT = "gt"


class Bound(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["bound"] = "bound"
    op: BoundOp
    limit: Union[Quantity, Money, Count]


Value = Annotated[
    Union[Quantity, Money, Count, Term, Bound],
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------------------
# Category schema
#
# This is what makes a new category cost an afternoon instead of a week. Comparison
# operators are written per Dimension, not per category, so a category contributes a
# schema and a criticality table and no new logic.
# --------------------------------------------------------------------------------------


class AttributeSpec(BaseModel):
    """One attribute of a category, and how strictly it is compared.

    `tolerance` is a *relative* fraction, so 0.005 means half a percent either way. It
    exists because real feeds publish 4.99 kg for a 5 kg pack and exact equality would
    call that a violation. It is a tunable — see `docs/tunables.md` — and it must be
    tightened per attribute where precision actually matters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    dimension: Dimension
    criticality: Criticality
    feed_aliases: tuple[str, ...] = ()
    tolerance: Decimal = Field(default=Decimal("0.005"), ge=0, lt=1)


class FieldProfile(BaseModel):
    """A named source of product data, scored on both DR 0016 axes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    field_name: str
    attributes: tuple[str, ...] = ()
    liability: Liability
    certainty: Certainty
    is_advice: bool = False
    # The merchant carries a separate SKU per value of this attribute. That is a
    # merchandising decision they pay for in inventory, and nobody stocks twelve variants
    # of something customers do not choose on — so it is the merchant telling us, for
    # free and in every catalogue on every platform, which attributes are selected on.
    # Read by `criticality.schema_layer`.
    is_variant_axis: bool = False


class CategorySchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category_id: str
    version: str
    attributes: tuple[AttributeSpec, ...]
    field_profiles: tuple[FieldProfile, ...]
    floor: frozenset[str] = frozenset()


# --------------------------------------------------------------------------------------
# The three inputs
# --------------------------------------------------------------------------------------


class Constraint(BaseModel):
    """What the agent said it wanted.

    `channel` is the fidelity tier — how the assertion reached us. `source` is the
    locator inside that tier: which protocol field, which filter, which page field. A
    dispute needs both, because "the agent typed it into a structured call" and "we read
    it out of the agent's paraphrase" are different evidentiary weights, and "which of
    the seven ACP fields" is what a returns desk actually looks at.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    value: Value
    channel: Channel
    raw_text: str | None = None
    source: str | None = None


class Claim(BaseModel):
    """What the agent said is true of the product it picked."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    value: Value
    channel: Channel
    raw_text: str | None = None


class Evidence(BaseModel):
    """What the merchant's own data says, and which field it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    value: Value
    field_name: str
    liability: Liability
    certainty: Certainty
    is_advice: bool = False
    raw_text: str | None = None


# --------------------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------------------


class Repair(BaseModel):
    """What the agent should do about this finding, as fields rather than prose.

    §2.7 requires reasons to be fields. The sentence an agent reads is *rendered* from
    these at the boundary (`approv.algebra.feedback`), never stored. That keeps the
    signed record deterministic and keeps the wording changeable without invalidating
    old receipts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    resolution: Resolution
    attribute: str
    claimed: str | None = None
    observed: str | None = None
    observed_field: str | None = None


class Finding(BaseModel):
    """One comparison, resolved.

    `confidence` and `ceiling` are uncalibrated extraction-assurance rankings.
    They are not probabilities that a physical product has the stated property.
    Certainty describes the reading; source truth, SKU binding and freshness remain
    separate obligations. No authorization decision is made by this object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    check: CheckKind
    attribute: str
    criticality: Criticality
    support: Support
    confidence: float = Field(ge=0.0, le=1.0)
    ceiling: float = Field(ge=0.0, le=1.0)
    reasons: tuple[ReasonCode, ...] = ()
    repair: Repair | None = None
    constraint: Constraint | None = None
    claim: Claim | None = None
    evidence: tuple[Evidence, ...] = ()


class AgentTurn(BaseModel):
    """One tool call as it arrived, plus our typed reading of it.

    Both halves are kept. `raw_arguments` is what was actually on the wire and is what a
    dispute is adjudicated against; `constraints` is our interpretation and may be wrong.
    Storing only the interpretation would make the record unfalsifiable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    tool: str
    raw_arguments: dict[str, object]
    constraints: tuple[Constraint, ...] = ()


class OrderLine(BaseModel):
    """The merchant order half of the record. PRD §3.

    Until this existed the record held the request half well — the words, the constraints,
    what was silent, what went unread, the findings and their coverage — and said of the
    other half only `product_id` plus an untyped `product_snapshot` dict. Those values
    *could* live in the dict and nothing bound or validated them, which is the same as not
    having them: a returns desk cannot be handed a blob and told the right numbers are
    somewhere inside it.

    **"The product matched" is not a dispute defence.** The defence is *this line of this
    order, this SKU, this variant, this many, at this price, in this availability state, as
    the catalogue stood.* Everything here is bound into the digest with the rest of the
    record, so a field cannot be adjusted after the outcome is known.

    Required is what the artifact cannot argue without. `unit_price` is required because a
    refund is denominated in it and a record that cannot say what was charged cannot
    contest one. `availability`, `variant_id`, `catalogue_version` and `checkout_state` are
    optional because not every merchant has them and rejecting an order for missing one
    would buy accuracy in the record at the cost of having no record.

    `availability` and `checkout_state` are the merchant's own terms, recorded verbatim
    rather than mapped onto a vocabulary of ours. Nothing decides on them — they are
    recorded because a dispute turns on what was true at decision time, and DR 0004's
    failure semantics are a separate decision that has not been made.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(min_length=1)
    # Which line of the order. An order with two lines produces two records, and without
    # this they are distinguishable only by product, which fails on a reorder of the same
    # item in two variants.
    line_id: str | None = None
    # The same identity the comparison ran against. `ComparisonRecord` validates that
    # these agree, which is what makes the record provably about this order line rather
    # than merely about a product that happens to share an id.
    product_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    variant_id: str | None = None
    quantity: int = Field(ge=1, strict=True)
    unit_price: Money
    availability: str | None = None
    catalogue_version: str | None = None
    checkout_state: str | None = None


class ComparisonRecord(BaseModel):
    """The signed object. §2.7, extended for DR 0016's two-halves construction.

    `correlation_id` is the join key between the agent's signed half and the merchant's
    signed half. It must be unguessable and bound into both signatures, or a half can be
    attached to someone else's session (DR 0016 §7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: str
    agent_id: str | None = None
    merchant_id: str | None = None
    attestation: Attestation

    category_id: str
    category_version: str
    locale: str

    # The stated request, both verbatim and as read. §1's claim is that nobody in the
    # chain holds the request and the chosen product together — so the record has to hold
    # it, and until this was built it did not: findings carry a `constraint` each, which
    # recovers only the attributes that produced a finding, and the shopper's own words
    # were nowhere at all. A record missing the request cannot settle a dispute about
    # what was asked for, which is the only kind of dispute this exists for.
    request_text: str
    request_constraints: tuple[Constraint, ...] = ()

    turns: tuple[AgentTurn, ...] = ()
    claims: tuple[Claim, ...] = ()
    product_id: str
    product_snapshot: dict[str, object]
    snapshot_hash: str
    # Whether this decision gated a real transaction or only watched one. Inside the digest
    # with everything else: a shadow receipt that could be relabelled `enforce` after the
    # fact is exactly the artifact this must never produce.
    mode: Mode = Mode.SHADOW
    # Whether this verification ran to a conclusion at all, and the specific detail — which
    # reader, how long it took. DR 0004: an abort is a recorded outcome, never a silent
    # skip, because an unrecorded abort is indistinguishable from a successful allow in the
    # receipt chain, which makes the chain useless for the dispute it exists to survive.
    completion: Completion = Completion.COMPLETED
    completion_detail: str | None = None
    # The order half. Optional because a comparison can be run at shelf time, before any
    # order exists, and that is a real call site (`mark`). A record that carries one is a
    # merchant order verification; a record without one is a comparison about a product.
    # Only the first is a dispute defence, and the difference is now visible in the record
    # instead of being a matter of what the caller happened to mean.
    order: OrderLine | None = None

    findings: tuple[Finding, ...]
    completeness: tuple[str, ...] = ()
    decision: Decision
    # The attributes that drove the decision, as `evaluator.decide` returned them.
    # Derivable from `findings` by anyone who runs the evaluator, and stored anyway:
    # §10's bar is that a stranger can verify and read a receipt with a public key and
    # none of our code, and "recompute it with our engine" fails that bar. An operator
    # who cannot attribute a refusal to a named attribute switches the check off.
    decision_reasons: tuple[str, ...] = ()
    # What the request said that we could not encode. Distinct from `completeness`, and
    # the distinction is the whole liability story: silence is nobody's fault and is not
    # covered, whereas a requirement we failed to read is *ours*. Both look like an absent
    # constraint from inside the engine, so without this field an extraction miss is
    # recorded as the shopper having said nothing and absolves everyone.
    unread: tuple[str, ...] = ()
    # Whether the channel this order arrived through earns coverage at all (DR 0020's
    # gradient), and why not when it does not. On the record rather than beside it, and
    # inside the digest, because the dispute artifact renders the record and nothing else:
    # kept outside, it printed "Covered" for an order intake had ruled out, which is the
    # exact failure the document exists to prevent (DR 0023). A coverage claim that can be
    # edited after a dispute opens is not a claim, and the party with the motive to edit it
    # is us.
    covered: bool = True
    coverage_notes: tuple[str, ...] = ()
    # Per-finding coverage, aligned with `findings` by index: guaranteed / refused /
    # out_of_coverage. On a dispute artifact (DR 0020) what is covered is load-bearing
    # rather than a derived nicety — a returns desk reading this needs to see which
    # findings carry a promise and which do not, without running our engine to recompute
    # it. `criticality.coverage_of` is the mapping.
    coverage: tuple[str, ...] = ()

    model_version: str
    evaluator_version: str
    prompt_version: str
    key_id: str | None = None
    signature_version: str = "ed25519-sha256-v1"
    timestamp: datetime

    prev_hash: str | None = None
    hash: str | None = None
    signature: str | None = None

    @model_validator(mode="after")
    def _the_comparison_is_about_this_order_line(self):
        """The binding, enforced by the type rather than by convention.

        `correlation_id` already joins the agent's signed half to the merchant's. What was
        missing is that the comparison is provably about *this order line* and not merely
        about a product id that appears in both — a record whose order names one SKU and
        whose findings were computed against another is worse than no record, because it
        looks like evidence. Checked here so it cannot be assembled wrong anywhere, and
        the digest covers both fields so it cannot be edited apart afterwards.
        """
        if self.order is not None and self.order.product_id != self.product_id:
            raise ValueError(
                "order line names product %r but the comparison ran against %r"
                % (self.order.product_id, self.product_id))
        return self


# --------------------------------------------------------------------------------------
# The reading vocabulary — note prefixes extraction writes and the record reads
# --------------------------------------------------------------------------------------
#
# Here rather than in `harness/intent.py`, where they were authored, because three layers
# have to agree on them and the top layer is the one layer the others cannot import.
# `harness/shopping.py` could not reach `dropped_requirement` without a cycle, which is
# the smell that said the vocabulary was in the wrong place: two producers of `unread`
# then had two different ideas of what it meant. DR 0021.

# The guards reporting that a requirement they could have checked was dropped: an
# attribute outside the schema, a value outside the published vocabulary, a quote that was
# not in the request, a value that would not validate. They mean the reading of the request
# is incomplete in a way better extraction could fix.
DESCRIPTOR_PREFIX = "Descriptive property, not a named value, left unverified: "
# Request words carried forward by no constraint value and no note. Extraction writes it;
# `criticality.narrowed_attributes` reads it to find a value narrower than its own quote.
COVERAGE_GAP_PREFIX = "Text not explicitly accounted for: "
DUPLICATE_PREFIX = "Duplicate requirement for a stated attribute, second value discarded: "

DROPPED_REQUIREMENT_PREFIXES = (
    "Unsupported requirement: ",
    "Value outside the published vocabulary, left unverified: ",
    "Ungrounded interpretation discarded: ",
    "Malformed requirement value discarded: ",
    "Invalid typed requirement discarded: ",
    # Not attribute-shaped and so carries no colon, but the same thing: the shopper asked
    # for a number of packs, the quote did not ground it, and the count was discarded.
    "Sale-unit interpretation has no original quote",
    DESCRIPTOR_PREFIX,
    COVERAGE_GAP_PREFIX,
    DUPLICATE_PREFIX,
)


def dropped_requirement(note: str) -> bool:
    """True when this note means a checkable requirement was not checked.

    The definition of `unread`, and the whole of it (DR 0021). It is deliberately narrower
    than "the extractor wrote something down": the model's free-text `unverified` list is
    mostly the request naming a product type this schema has no attribute for — "chelsea
    boots", "women's", "kid's shoes" — which is unverifiable in principle against this
    catalogue rather than a gap in the reading, and it is true of 35 of 46 requests on the
    10 September pack. A floor that fires on those fires on almost everything.
    """
    return isinstance(note, str) and note.startswith(DROPPED_REQUIREMENT_PREFIXES)
