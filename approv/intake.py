"""Every shape agent traffic arrives in, normalised to the one input the engine takes.

Two surfaces, one engine, many adapters. The engine compares a stated request against a
product; it has never cared where the stated request came from, and this module is what
keeps that true as the ways of getting one multiply. Everything here ends at the same
place: `tuple[Constraint, ...]`, with an honest `Channel` and a locator saying which part
of which artifact each one came from.

**Adding a traffic shape never touches `algebra/` or `evaluator/`.** A test asserts it,
mirroring invariant 1, and it is asserted rather than trusted for the same reason: without
it, adapter pressure leaks into the engine within a month and "the engine barely changes"
stops being true silently. This module imports only `approv.types`, and nothing in
`algebra/` or `evaluator/` imports this module.

Three shapes, in descending fidelity (DR 0020's table):

    (a) structured    a protocol call — ACP, AP2, storefront MCP, a feed
    (b) search        an on-site query plus its filters: text and structure together
    (c) free text     the declared-intent field, or a user message on the agent surface

and a fourth case that is not a shape but an absence: an order with no recoverable stated
request at all. That is the uncovered slice DR 0020 says bounds the product, and it is
returned explicitly rather than as an empty success, because "we read nothing" and "there
was nothing to read" attribute differently.

**Path (a) carries no `raw_text`, and that is correct rather than a degradation.** A
protocol field has no wording to quote — the agent did not paraphrase, it filled a slot.
The engine must therefore still treat a quoteless constraint as a stated requirement, and
it does: `criticality.request_layer` floors any existing constraint at BOUND whether or
not a quote survived. That behaviour is load-bearing for this path, not an edge case, and
`tests/test_intake.py` pins it by name.

**Never collapse a mixed artifact into one blob.** Path (b) arrives as a typed filter set
*and* a free-text query, and they are not the same evidence: a filter is a slot the agent
filled, a query is prose we read. Flattening them to one channel would launder the weaker
half up to the stronger, which is the one thing a dispute artifact must not do.

Free-text reading is injected rather than imported. Extraction needs a model and lives in
`harness/intent.py`, two layers up; taking it as a callable is what lets this module hold
the import boundary above while still serving path (c).
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Literal, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field

from approv.types.core import CategorySchema, Channel, Constraint, Term, Value

VERSION = "intake-v1"


class Surface(str, Enum):
    """Who is calling. Both reach the same engine; they differ in what they can offer.

    MERCHANT is DR 0020's surface and the one that exists without anybody's permission:
    the merchant owns the page, the order and the fulfilment record. AGENT is the strictly
    easier input case — the agent operator has the human's actual words rather than its own
    paraphrase — and it is kept because it is the product for the world where agent
    operators are made liable, not because it is a precondition for having a business.
    """

    MERCHANT = "merchant"
    AGENT = "agent"


class Shape(str, Enum):
    STRUCTURED = "structured"
    SEARCH = "search"
    FREE_TEXT = "free_text"
    UNDECLARED = "undeclared"


class AgentPresence(str, Enum):
    """Whether this order was placed by an agent, and on what basis we say so.

    Kept separate from the shape because the basis is what a merchant is arguing from. A
    protocol call is an agent by construction. A checkout heuristic is a guess, and a
    record that calls a guess a fact is worse than one that admits it guessed.
    """

    DECLARED = "declared"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------------------
# The artifacts
# --------------------------------------------------------------------------------------

# A protocol hands over values it has already typed, or plain strings. Both are accepted:
# a `Value` passes through untouched, a string becomes a Term. Nothing here parses a string
# into a quantity or a bound — that is the narrowing failure mode wearing a different hat,
# and an adapter that knows the protocol's own units is the right place for it.
Stated = Union[Value, str]


class Structured(BaseModel):
    """Path (a). Highest fidelity: the agent filled slots, so there is nothing to read."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    shape: Literal[Shape.STRUCTURED] = Shape.STRUCTURED
    protocol: str = Field(min_length=1)
    fields: Mapping[str, Stated] = {}
    # A signed mandate is a stronger assertion than a plain tool argument: the agent
    # committed to it in advance and cannot later say the call was malformed.
    signed_mandate: bool = False


class Search(BaseModel):
    """Path (b). On-site search: structure and prose in the same artifact, kept apart."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    shape: Literal[Shape.SEARCH] = Shape.SEARCH
    query: str = ""
    filters: Mapping[str, Stated] = {}


class FreeText(BaseModel):
    """Path (c). The declared-intent field, or a user message on the agent surface.

    On the merchant surface this is the agent's paraphrase and it does not need to be true:
    a paraphrase binds the agent's side, which is all a merchant-defence record requires.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    shape: Literal[Shape.FREE_TEXT] = Shape.FREE_TEXT
    text: str = ""
    field_name: str = "declared_intent"


class Undeclared(BaseModel):
    """Not a shape. An order that carried no stated request at all.

    Off-site discovery, direct arrival at a product page, no declaration, no site search.
    Returned as its own artifact so that the uncovered slice is counted rather than
    silently indistinguishable from a request we failed to read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    shape: Literal[Shape.UNDECLARED] = Shape.UNDECLARED
    why: str = "no stated request accompanied this order"


Artifact = Union[Structured, Search, FreeText, Undeclared]

# Protocol field name -> schema attribute name. The whole of what an adapter is: many of
# them, each a few lines of data, none of them code the engine has to know about. An
# unmapped field is reported rather than dropped, because a protocol field this schema
# cannot express is exactly the kind of thing a returns desk will point at.
Adapter = Mapping[str, str]

class Reading(BaseModel):
    """What an extractor made of a piece of prose: what it read, and what it did not.

    `unread` is not decoration. It is the extractor's own account of request text it could
    not encode, and two things downstream depend on it — the verification floor, and
    `criticality.narrowed_attributes`, which is what keeps a requirement read too narrowly
    from being guaranteed. An intake path that returned constraints alone would drop the
    only signal that distinguishes "read the whole thing" from "read part of it", and the
    free-text paths are exactly the ones where that happens.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    constraints: tuple[Constraint, ...] = ()
    unread: tuple[str, ...] = ()
    # Attributes the shopper corrected, already parsed by the reader. Carried because
    # `algebra.runner` needs them to make a surviving value HARD, and because DR 0021
    # correctly stopped supersession notes counting as unread — which would otherwise have
    # left the signal with nowhere to travel.
    superseded: tuple[str, ...] = ()


# Reads prose into a Reading. Supplied by the caller because it needs a model and this
# module may not import one.
Extractor = Callable[[str, CategorySchema], Reading]


class Intake(BaseModel):
    """What one order's stated request turned out to be, and what it is worth.

    Durable and queryable on purpose: this is a per-merchant row, and a merchant's
    distribution over shapes — how much of their agent traffic is structured, how much is
    a bare query, how much carries nothing at all — is the first of DR 0020's two
    unmeasured numbers. Storing it is not the analytics product; it is not throwing away
    the input to it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    surface: Surface
    shape: Shape
    agent: AgentPresence
    constraints: tuple[Constraint, ...] = ()
    merchant_id: str | None = None
    covered: bool = False
    # Why coverage was withheld, or what intake itself declined to do. Stated, never
    # implied by an absence. Kept apart from `unread`, which is the extractor's account of
    # request text it could not encode and which feeds the record's floor and its coverage.
    notes: tuple[str, ...] = ()
    unread: tuple[str, ...] = ()
    superseded: tuple[str, ...] = ()
    # Fields the artifact carried that this schema has no attribute for.
    unmapped: tuple[str, ...] = ()


# --------------------------------------------------------------------------------------
# The normaliser
# --------------------------------------------------------------------------------------

def _value(stated: Stated) -> Value:
    return Term(surface=stated) if isinstance(stated, str) else stated


def _from_fields(fields: Mapping[str, Stated], schema: CategorySchema, *,
                 channel: Channel, prefix: str,
                 adapter: Adapter | None) -> tuple[tuple[Constraint, ...], tuple[str, ...]]:
    """Typed slots to constraints. No quote, because there was no wording."""
    known = {spec.name for spec in schema.attributes}
    constraints, unmapped = [], []
    for name, stated in fields.items():
        attribute = (adapter or {}).get(name, name)
        if attribute not in known:
            unmapped.append(name)
            continue
        constraints.append(Constraint(
            attribute=attribute, value=_value(stated), channel=channel,
            raw_text=None, source="%s.%s" % (prefix, name)))
    return tuple(constraints), tuple(unmapped)


def intake(
    artifact: Artifact,
    schema: CategorySchema,
    *,
    surface: Surface = Surface.MERCHANT,
    merchant_id: str | None = None,
    adapter: Adapter | None = None,
    extract: Extractor | None = None,
    agent: AgentPresence | None = None,
) -> Intake:
    """One signature. Any artifact in, one stated request out, honestly labelled.

    `agent` overrides the presence this artifact implies, for a caller with a better
    signal than the shape alone. It can only be supplied, never inferred here: a merchant
    whose checkout detects agents does so with their own data, and guessing on their
    behalf would put a fabricated basis on a dispute record.

    Coverage attaches per channel and is decided here rather than per order downstream. No
    recoverable stated request is no coverage — the gradient is merchant channel policy
    and needs nobody's consent — and an order we cannot classify is out of coverage and
    says so, rather than being quietly treated as an ordinary one.
    """
    presence = agent or _implied_presence(artifact)
    notes: list[str] = []
    unread: tuple[str, ...] = ()
    superseded: tuple[str, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    unmapped: tuple[str, ...] = ()

    if isinstance(artifact, Structured):
        channel = Channel.MANDATE if artifact.signed_mandate else Channel.TOOL_ARGUMENT
        constraints, unmapped = _from_fields(
            artifact.fields, schema, channel=channel, prefix=artifact.protocol,
            adapter=adapter)

    elif isinstance(artifact, Search):
        # Structure and prose, side by side and never merged. The filters are slots the
        # agent filled; the query is prose somebody has to read.
        constraints, unmapped = _from_fields(
            artifact.filters, schema, channel=Channel.TOOL_ARGUMENT,
            prefix="search.filters", adapter=adapter)
        if artifact.query:
            if extract is None:
                notes.append("search query was not read: no extractor was supplied")
            else:
                reading = extract(artifact.query, schema)
                constraints += _sourced(reading.constraints, "search.query")
                unread += reading.unread
                superseded += reading.superseded

    elif isinstance(artifact, FreeText):
        if not artifact.text.strip():
            notes.append("the declared-intent field was present and empty")
        elif extract is None:
            notes.append("declared intent was not read: no extractor was supplied")
        else:
            reading = extract(artifact.text, schema)
            constraints = _sourced(reading.constraints, artifact.field_name)
            unread = reading.unread
            superseded = reading.superseded

    else:
        notes.append(artifact.why)

    if unmapped:
        notes.append("fields this category cannot express: " + ", ".join(sorted(unmapped)))
    if not constraints:
        notes.append("no stated request was recovered, so this order is out of coverage")
    if presence is AgentPresence.UNKNOWN:
        notes.append("this order could not be classified as agent-placed, so it is out "
                     "of coverage")

    return Intake(
        surface=surface, shape=artifact.shape, agent=presence, merchant_id=merchant_id,
        constraints=constraints, unread=unread, superseded=superseded,
        covered=bool(constraints) and presence is not AgentPresence.UNKNOWN,
        notes=tuple(notes), unmapped=unmapped)


def _sourced(constraints: tuple[Constraint, ...], source: str) -> tuple[Constraint, ...]:
    """Stamp the locator on what an extractor read, without it having to know about us."""
    return tuple(c.model_copy(update={"source": source}) if c.source is None else c
                 for c in constraints)


def _implied_presence(artifact: Artifact) -> AgentPresence:
    """What the artifact itself establishes, and no more.

    A protocol call is an agent by construction — nothing else speaks ACP. A field
    addressed to the agent that came back filled in was filled in by one. A search query
    is just a search query: humans use those too, so the shape establishes nothing and the
    merchant has to say.
    """
    if isinstance(artifact, Structured):
        return AgentPresence.DECLARED
    if isinstance(artifact, FreeText) and artifact.text.strip():
        return AgentPresence.DECLARED
    return AgentPresence.UNKNOWN
