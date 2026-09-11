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

from pydantic import BaseModel, ConfigDict, Field

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
    """What the agent said it wanted."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    value: Value
    channel: Channel
    raw_text: str | None = None


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

    model_version: str
    evaluator_version: str
    prompt_version: str
    timestamp: datetime

    prev_hash: str | None = None
    hash: str | None = None
    signature: str | None = None
