"""Merchant order verification: the entry point, with no web framework in it.

PRD §3. Until now the centre of gravity was `ShoppingCase` + `Inventory` — harness objects
built for experiments — and there was no service surface at all. That gap was the distance
between the pitch and the build: a merchant cannot call an experiment.

**The framework is not here.** Everything in this module is Pydantic and pure functions, so
the whole request path is testable without a server, and the FastAPI router in `api.py` is
a thin adapter over `verify_order`. §9 allows FastAPI at the surface layer only, and the
cheapest way to keep that true is for the surface layer to be two files, one of which does
not import it.

The pipeline is assembly, not judgement. Intake normalises the stated request whatever
shape it arrived in; the schema's own field profiles read the merchant's catalogue snapshot
into evidence; `algebra` compares; `evaluator.decide` decides; `receipts` assembles and
signs. Nothing here decides anything, and a caller that wanted to override the decision
would be the decision path, which is the one thing §1 says we do not have.

**`unread_policy` defaults to withdrawing the guarantee, not to escalating** (DR 0022).
An unread requirement is our defect; pausing the merchant's checkout over it charges them
for it, and it was measured at 58.8% nuisance. Withdrawing instead lets the sale proceed
and promises nothing about a request we could not finish reading — same decisions as
ignoring it, 23.2 pp fewer findings claimed as guaranteed. It stays a constructor argument
because ESCALATE is a legitimate merchant preference and §2.6 says the threshold is a
business parameter, not a constant.
"""

from __future__ import annotations

import hashlib
import time
from typing import Annotated, Callable, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from approv.algebra.runner import check_constraints
from approv.intake import (
    AgentPresence, Artifact, Extractor, FreeText, Intake, Search, Structured, Surface,
    Undeclared, intake,
)
from approv.receipts.chain import canonical_json
from approv.receipts.record import build_order_evidence, build_record
from approv.schema.catalogue import Cell, discover, is_identifier, variant_collections
from approv.schema.values import semantic_key
from approv.types.core import (
    Attestation, CategorySchema, Completion, Count, Dimension, Evidence, Finding, Mode,
    Money, OrderLine, OrderOutcome, Quantity, Receipt, Term, UnreadPolicy, Value,
)

VERSION = "surface-v1"

# The same discriminated union `approv.intake` defines, told to Pydantic how to pick a
# member off the wire. Intake keeps it as a plain Union because it never parses one from
# JSON; a request body does.
ArtifactBody = Annotated[
    Union[Structured, Search, FreeText, Undeclared], Field(discriminator="shape")]

# Merchant catalogue snapshot -> what the merchant's own data says. Injected for the same
# reason the extractor is: the default below reads the schema's field profiles, which is
# right for a merchant whose snapshot is shaped like their schema and wrong for one who
# needs a real adapter.
Reader = Callable[[Mapping[str, object], CategorySchema], tuple[Evidence, ...]]

# Where an ingested outcome is kept. Injected for the same reason the reader is: storage is
# the store's and this module may not reach into it.
Sink = Callable[[OrderOutcome], None]

# The discriminated value union, for a catalogue that exports typed values.
_VALUE_ADAPTER = TypeAdapter(Value)

# Only the unambiguous units. A bare number with no unit, or a unit we do not recognise,
# yields no evidence rather than a guessed dimension.
_DIMENSIONS = {
    **dict.fromkeys(("mg", "g", "kg", "oz", "lb"), Dimension.MASS),
    **dict.fromkeys(("ml", "cl", "l"), Dimension.VOLUME),
    **dict.fromkeys(("mm", "cm", "m", "in", "ft"), Dimension.LENGTH),
}


class UnknownCategory(LookupError):
    """The request named a category this deployment has no schema for."""


class ProductMismatch(ValueError):
    """The catalogue snapshot and the order line name different products."""


class VariantMismatch(ProductMismatch):
    """A multi-SKU snapshot that does not contain the ordered line.

    The same defect as posting product A's snapshot with product B's order line, one level
    down, and it is reported the same way. A snapshot holding six sizes and an order line
    naming a seventh cannot be compared at all: the only readings available belong to
    somebody else's SKU.
    """


class VerificationRequest(BaseModel):
    """One order line, one stated request, whatever shape it arrived in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    merchant_id: str = Field(min_length=1)
    # Unguessable and bound into both signed halves (DR 0016 §7). Supplied by the caller
    # because it is the join key to the agent's half, which we may never see.
    correlation_id: str = Field(min_length=1)
    category_id: str = Field(min_length=1)
    order: OrderLine
    artifact: ArtifactBody
    product_snapshot: dict[str, object]
    # A merchant whose checkout detects agents says so here. Never inferred on their
    # behalf — a guess recorded as a basis is worse than no basis.
    agent: AgentPresence | None = None
    surface: Surface = Surface.MERCHANT
    attestation: Attestation = Attestation.NEITHER
    agent_id: str | None = None
    locale: str = "en-IN"
    # Field-name mapping for this protocol, if the artifact needs one.
    adapter: dict[str, str] | None = None


class VerificationResult(BaseModel):
    """What the caller gets back. The record is the product; the rest is about it.

    Everything the PRD lists as an output — findings, completeness, decision, reason codes,
    per-finding coverage, snapshot hash, signature, the version triple — lives on the
    record rather than being copied out beside it, because two copies of a decision is one
    copy too many and the record is the thing that gets disputed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Either receipt product. A caller that only ever wants a comparison checks `kind`;
    # one that renders or bills reads it off the record, where it is signed.
    record: Receipt
    receipt_id: str
    # Views onto the record, not a second copy of the fact (DR 0023). They were the fact
    # once, which is how the artifact came to print "Covered" for an order intake had
    # ruled out — it renders the record and could not see them. On an order evidence
    # record the field they view is `eligible`, which is false by construction.
    covered: bool
    intake_notes: tuple[str, ...] = ()


def _catalogue_cells(snapshot: Mapping[str, object]) -> dict[tuple[str, str], Cell]:
    """This snapshot flattened by the same walk that emitted the schema's field paths.

    **The producer is the resolver.** `approv.schema.catalogue.flatten` is the code that
    turns a catalogue record into `(locator, attribute, value)` triples in the first place,
    and every locator in a derived schema was written by it. A second walk on this side
    would have to reproduce its option table, its currency inheritance, its pair
    detection, its labelled-clause extraction and its child-over-parent rule *exactly*, and
    the day one of them drifted the surface would read a merchant's catalogue differently
    from the schema derived out of it — which is seam 1 again, silently. So this calls the
    producer's own walk and indexes the result; agreement is by construction rather than by
    test.

    The key is `(locator, attribute)`, not the locator alone, because a prose field is one
    locator carrying several attributes: `/description` holds both "Finish: matte" and
    "Wall thickness: 2 mm", and handing the whole description to each of them is how a
    description ends up quoted as evidence for an attribute it never mentioned.

    Two rules drop a reading rather than guessing at it, both from the locator contract:

    *A source must resolve to a unique value.* Two pairs both labelled `Finish` are
    ambiguous even when they agree, because "they happen to agree" is not a resolution —
    it is a coincidence that will stop holding on the next record.

    *An unselected multi-SKU array contributes no SKU-specific evidence.* `discover`
    returns one listing per variant, so anything that is not identical across all of them
    belongs to a particular SKU, and we were not told which one. Picking the first, or
    pooling them, is the wrong-variant read this exists to prevent.
    """
    listings, _ = discover([dict(snapshot)])
    if not listings:
        return {}
    per_listing: dict[tuple[str, str], list[list[Cell]]] = {}
    for listing in listings:
        grouped: dict[tuple[str, str], list[Cell]] = {}
        for cell in listing.cells:
            grouped.setdefault((cell.field, cell.name), []).append(cell)
        for key, group in grouped.items():
            per_listing.setdefault(key, []).append(group)
    resolved = {}
    for key, groups in per_listing.items():
        if len(groups) != len(listings) or any(len(group) != 1 for group in groups):
            continue
        found = [group[0] for group in groups]
        if len({(cell.raw, repr(cell.value)) for cell in found}) != 1:
            continue
        resolved[key] = found[0]
    return resolved


# Issues `read_value` reports when the raw was not text at all — an object, a list, a
# number it could not parse, or prose too long to be a label. A NOMINAL attribute reads
# the surface text, and for these there is no honest surface text to read: stringifying a
# money object, or copying six hundred characters of description into a Term, would
# manufacture the comparison that having no value at all correctly refuses.
#
# `ambiguous_quantity_expression` joined them under DR 0029, and it is the interesting one.
# It does not mean *we could not type this label*; it means the string holds more than one
# quantity reading -- `1 fl oz | 30 ml`, out of a description. Keeping that as a Term
# manufactures a label no request will ever state, so the attribute can only come back
# violated or unstated, on a guaranteed source, from marketing copy.
_NOT_TEXT = frozenset({"unsupported_object", "invalid_money_amount", "invalid_number",
                       "multivalued_field_requires_mapping", "invalid_typed_value",
                       "prose_requires_labelled_extraction", "ambiguous_quantity_expression"})
# The readings that may still be kept as a label: the whole surface text is what the
# merchant published, and the failure was only to *type* it -- `3XL` is not a unit, `13.5`
# has none. `schema.derive._usable` holds the same pair, and the two must stay identical.
_LABEL_SAFE = frozenset({"unitless_decimal", "unknown_or_ambiguous_unit"})


def _settled_value(cell: Cell, dimension: Dimension | None) -> Value | None:
    """One catalogue cell as the value this attribute is actually compared in.

    Resolving the path is not enough: the cell was typed by looking at one field in
    isolation, and the schema knows something that reading cannot — what the attribute
    settled as across the whole catalogue. Size `3XL` reads as an unrecognised unit and
    size `13.5` as a unitless decimal, and both are simply labels once the schema says the
    attribute is NOMINAL. Taking the surface text there is what the contract means by
    preserving a whole nominal selector as a label.

    Everywhere else the dimensions must agree. A cell read as a Count against an attribute
    compared in MASS is not a near miss to be coerced — the comparison would be
    INCOMMENSURABLE, which is the answer, and inventing a conversion is how a guarantee
    gets made out of a field nobody understood.
    """
    if not cell.present:
        return None
    if dimension is Dimension.NOMINAL:
        if cell.issue in _NOT_TEXT:
            return None
        # DR 0029. The same question was being answered by two rules -- this one and
        # `schema.derive._usable` -- and on real feeds they disagreed.
        return (Term(surface=cell.raw)
                if cell.value is not None or cell.issue in _LABEL_SAFE else None)
    return cell.value if cell.dimension is dimension else None


def _dotted(snapshot: Mapping[str, object], field_name: str):
    """A flat key, or `variant.size` as a nested lookup. The pre-onboarding spelling.

    Kept, and disjoint by construction rather than by guessing: a JSON pointer always
    begins with `/`, so nothing here is ever asked to choose between the two formats.
    Schemas authored before `approv.schema` existed are still in tests and in deployments;
    the derived format is the one to write from here on.
    """
    if field_name in snapshot:
        return snapshot[field_name]
    current: object = snapshot
    for part in field_name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _as_value(raw) -> Value | None:
    """A catalogue value as something the operators can compare, or nothing.

    Nothing is a real answer. A field whose type we cannot honestly read produces no
    evidence, the attribute goes UNSTATED and the decision escalates — which is §2.3 in
    force. Coercing it into a Term instead would manufacture a comparison out of a value
    we did not understand, and a manufactured SATISFIED is a guarantee we cannot keep.
    """
    if isinstance(raw, Mapping) and "kind" in raw:
        return _VALUE_ADAPTER.validate_python(dict(raw))
    # The two typed shapes a real catalogue writes without a `kind` tag, and the two
    # `approv.schema` recognises when it derives the schema. Reading them is not coercion:
    # an amount beside its currency *is* a Money, and refusing it here would leave a price
    # attribute the derivation had already promised reading nothing at all.
    if isinstance(raw, Mapping) and "amount" in raw and set(raw) <= {"amount", "currency"}:
        return _typed(Money, amount=raw.get("amount"), currency=raw.get("currency"))
    if isinstance(raw, Mapping) and "unit" in raw and set(raw) <= {"unit", "value", "magnitude"}:
        return _typed(Quantity, unit=raw.get("unit"),
                      magnitude=raw.get("magnitude", raw.get("value")),
                      dimension=_DIMENSIONS.get(str(raw.get("unit")).strip().casefold()))
    if isinstance(raw, str):
        return Term(surface=raw)
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return Count(n=raw)
    return None


def _typed(model, **fields) -> Value | None:
    """Build a typed value, or nothing if the catalogue did not supply enough for one.

    A currency-less amount and a dimensionless magnitude are not values, and inventing
    either is how a comparison gets manufactured out of a field nobody stated properly.
    `approv.schema` refuses the same two cases when it derives the schema.
    """
    if any(value is None for value in fields.values()):
        return None
    try:
        return model(**fields)
    except ValidationError:
        return None


def evidence_from_snapshot(snapshot: Mapping[str, object],
                           schema: CategorySchema) -> tuple[Evidence, ...]:
    """The merchant's catalogue snapshot, read through the schema's own field profiles.

    No new vocabulary. `FieldProfile` already names the field, the attributes it speaks to,
    and where it sits on both DR 0016 axes — which is exactly the mapping a product-side
    adapter needs, and it was already being authored per category for the comparison to
    work at all. A merchant whose export is shaped differently supplies their own `Reader`;
    this is the case where they do not have to.

    Two formats, disjoint by construction rather than by guessing: a locator always begins
    with `/`, so nothing here is ever asked to choose. Locators are resolved by the walk
    that wrote them (`_catalogue_cells`). Dotted names predate `approv.schema` and are
    still in tests and deployments, so they keep the flat lookup they have always had.

    **This reader expects one selected listing.** Handed a snapshot whose variant array
    still holds every SKU, it reads only what all of them agree on and leaves the rest
    unstated. Selecting the ordered line is the caller's job, because only the caller has
    the order — `verify_order` does it before this is ever called.
    """
    cells = _catalogue_cells(snapshot) if any(
        profile.field_name.startswith("/") for profile in schema.field_profiles) else {}
    dimensions = {spec.name: spec.dimension for spec in schema.attributes}
    out = []
    for profile in schema.field_profiles:
        for attribute in profile.attributes:
            if profile.field_name.startswith("/"):
                cell = cells.get((profile.field_name, attribute))
                value = None if cell is None else _settled_value(
                    cell, dimensions.get(attribute))
            else:
                found = _dotted(snapshot, profile.field_name)
                value = None if found is None else _as_value(found)
            if value is None:
                continue
            out.append(Evidence(attribute=attribute, value=value,
                                field_name=profile.field_name,
                                liability=profile.liability,
                                certainty=profile.certainty,
                                is_advice=profile.is_advice))
    return tuple(out)



def snapshot_digest(snapshot: Mapping[str, object]) -> str:
    """The snapshot's digest, over the same canonical JSON the record is sealed with.

    One dump format everywhere, so a merchant can recompute this with `json.dumps` and
    three arguments rather than with our code — the same bar `scripts/verify_receipt.py`
    is held to.
    """
    return hashlib.sha256(canonical_json(dict(snapshot)).encode("utf-8")).hexdigest()


def verify_order(
    request: VerificationRequest,
    *,
    schemas: Mapping[str, CategorySchema],
    read_evidence: Reader = evidence_from_snapshot,
    extract: Extractor | None = None,
    unread_policy: UnreadPolicy = UnreadPolicy.WITHDRAW,
    returns: Mapping[str, float] | None = None,
    budget_seconds: float | None = None,
    mode: Mode = Mode.SHADOW,
) -> VerificationResult:
    """One order line in, one unsealed record out.

    **The surface does not sign.** Only the store knows the chain head, and a signature
    over `prev_hash=None` is a receipt that can be appended exactly once per ledger — the
    first order succeeds and the second raises a chain conflict. Two modules owning sealing
    and neither knowing about the other is not a tuning problem; it is one owner too many.
    So this returns an unsealed record and `ReceiptStore.append` seals it into place.

    `returns` is the merchant's calibrated differ-rate table (criticality layer 3) when
    they have one. Absent, layers 1 and 2 carry the transaction on their own, which is the
    cold-start case the layering exists to survive.

    `budget_seconds` is DR 0004's abort, as a safety property rather than a latency one: a
    verification that blew its budget cannot authorise. It does **not** cut the call short,
    because cancelling in flight needs cooperation from the adapter that owns the HTTP
    client, and claiming otherwise would be the more dangerous error.

    `mode` is deployment configuration and never request payload, for the same reason the
    schemas are: a caller who could send `enforce` could defeat sandbox isolation with one
    JSON field. A shadow deployment cannot emit an enforce record at all.
    """
    schema = schemas.get(request.category_id)
    if schema is None:
        raise UnknownCategory(request.category_id)
    _bind_snapshot_to_order(request)

    # The receipt product is chosen here, before any comparison, and never described
    # afterwards. An order that carried no stated request cannot be compared to one: cart
    # contents say what was bought and nothing about what was asked for. Running the
    # pipeline anyway would produce a verification-headed record with an empty request,
    # a decision nobody's intent drove, and the bad news several fields down in a
    # coverage flag — which is what it used to do (PRD §5).
    if isinstance(request.artifact, Undeclared):
        return _order_evidence(request, schema, mode)

    reading = selected_listing(request.product_snapshot, request.order)

    started = time.monotonic()
    completion, detail = Completion.COMPLETED, None
    findings: tuple[Finding, ...] = ()

    taken, failure = _run(
        lambda: intake(request.artifact, schema, surface=request.surface,
                       merchant_id=request.merchant_id, adapter=request.adapter,
                       extract=extract, agent=request.agent),
        Completion.PROVIDER_UNAVAILABLE, "reading the stated request",
        parse_failure=Completion.UNREADABLE_RESPONSE)
    if failure is None:
        evidence, failure = _run(
            lambda: read_evidence(reading, schema),
            Completion.CATALOGUE_UNREADABLE, "reading the catalogue snapshot")
    if failure is None:
        failure = _reads_nothing(evidence, reading, schema)
    if failure is None:
        findings = check_constraints(
            taken.constraints, evidence, schema, returns=returns,
            superseded=frozenset(taken.superseded))
        # DR 0026, and the one incomplete verification that keeps its findings. The
        # comparison really did run — against a request we had only half of — so the
        # filters we read and the catalogue we read correctly stay on the record. What
        # cannot stand is a guarantee over prose nobody examined: it can contradict
        # everything we did read, and in the case that found this, it did.
        if taken.unprocessed:
            completion = Completion.REQUEST_UNPROCESSED
            detail = ("the stated request carried text nothing read: %s — an empty "
                      "reading of a non-empty request is unknown, not agreement"
                      % ", ".join(taken.unprocessed))
    else:
        completion, detail = failure
        taken = taken if taken is not None else _nothing_read(request, schema)

    elapsed = time.monotonic() - started
    if completion is Completion.COMPLETED and budget_seconds is not None             and elapsed > budget_seconds:
        completion = Completion.BUDGET_EXCEEDED
        detail = "verification took %.0f ms against a %.0f ms budget" % (
            elapsed * 1000, budget_seconds * 1000)

    record = build_record(
        correlation_id=request.correlation_id,
        request_text=_stated_text(request.artifact),
        constraints=taken.constraints,
        findings=findings,
        schema=schema,
        product_id=request.order.product_id,
        product_snapshot=dict(request.product_snapshot),
        snapshot_hash=snapshot_digest(request.product_snapshot),
        model_version=VERSION,
        prompt_version=VERSION,
        locale=request.locale,
        agent_id=request.agent_id,
        merchant_id=request.merchant_id,
        attestation=request.attestation,
        unread=taken.unread,
        unread_policy=unread_policy,
        order=request.order,
        completion=completion,
        completion_detail=detail,
        # No coverage may ever be inferred from a verification that did not complete (DR
        # 0004), and intake's channel verdict knows nothing about whether the check
        # finished, so the two are combined once, here, on the way onto the record.
        covered=taken.covered and completion is Completion.COMPLETED,
        coverage_notes=taken.notes,
        mode=mode,
    )
    return VerificationResult(record=record, receipt_id=request.correlation_id,
                              covered=record.covered,
                              intake_notes=record.coverage_notes)


def _order_evidence(request: VerificationRequest, schema: CategorySchema,
                    mode: Mode) -> VerificationResult:
    """The cart-only path. A different product, and labelled as one on its own face.

    Intake still runs, and it runs for its own reasons: it is the per-merchant row that
    measures how much of a merchant's agent traffic arrives with nothing attached, which
    is the first of DR 0020's two unmeasured numbers. Nothing it returns is compared
    against anything — an `Undeclared` artifact yields no constraints by construction —
    and its account of why there was no request travels onto the record verbatim.

    `covered` is false and there is nothing to withdraw it from, which is the shape of an
    honest weaker product rather than a degraded stronger one.
    """
    taken = intake(request.artifact, schema, surface=request.surface,
                   merchant_id=request.merchant_id, agent=request.agent)
    record = build_order_evidence(
        correlation_id=request.correlation_id,
        schema=schema,
        order=request.order,
        product_snapshot=dict(request.product_snapshot),
        snapshot_hash=snapshot_digest(request.product_snapshot),
        model_version=VERSION,
        prompt_version=VERSION,
        reasons=taken.notes,
        surface=request.surface,
        agent=taken.agent,
        locale=request.locale,
        agent_id=request.agent_id,
        merchant_id=request.merchant_id,
        attestation=request.attestation,
        mode=mode,
    )
    return VerificationResult(record=record, receipt_id=request.correlation_id,
                              covered=False, intake_notes=taken.notes)


# A malformed answer and no answer at all are different events on the reader boundary —
# "it replied with something we could not parse" against "it did not reply". On the
# catalogue boundary there is no such split: however the merchant's snapshot failed to
# read, it is the merchant's snapshot, and that is the distinction worth keeping.
_PARSE_ERRORS = (ValueError, TypeError, KeyError, AttributeError, IndexError)


def _run(step, failure: Completion, what: str, *, parse_failure: Completion | None = None):
    """Run one fallible boundary. Returns (value, None) or (None, (completion, detail)).

    Only the two *injected* boundaries go through this — the extractor and the catalogue
    reader. They are somebody else's code reaching somebody else's network, and DR 0004 is
    explicit that an abort is a recorded outcome rather than a silent skip: an unrecorded
    one is indistinguishable from a successful allow in the receipt chain.

    A bug in our own assembly deliberately still raises. Laundering a programming error
    into a signed `confirm` record would hide it behind a plausible-looking artifact, which
    is a worse failure than a 500 nobody can miss.
    """
    try:
        return step(), None
    except Exception as error:  # noqa: BLE001 - the boundary is the point
        kind = failure
        if parse_failure is not None and isinstance(error, _PARSE_ERRORS):
            kind = parse_failure
        return None, (kind, "%s: %s: %s" % (what, type(error).__name__, error))


def _reads_nothing(evidence, snapshot: Mapping[str, object], schema: CategorySchema):
    """A schema that reads *nothing* from a non-empty snapshot is disconnected, not careful.

    The silence is the worse half of the field-path defect. When a derived schema's paths
    do not match the catalogue they were derived from, `read_evidence` raises nothing and
    logs nothing: every attribute goes UNSTATED, every order confirms, and the deployment
    looks like a cautious engine rather than a disconnected one. A pilot partner sees a
    100% confirm rate and no error at all, which is the worst shape a failure can take —
    it survives monitoring, it survives a green test suite, and it looks like the product
    working.

    So it is a failed verification with a named reason (DR 0004) rather than an exception:
    the merchant still gets a record, it still cannot authorise, it carries no coverage,
    and `completion_detail` says the schema read nothing. A 500 would hand them nothing to
    keep and invite them to ship anyway.

    Scoped to the case that can only be a fault. A schema with no profiles has nothing to
    read with, and an empty snapshot has nothing to read — neither is evidence of a
    mismatch, and failing on them would fire on legitimately sparse traffic.
    """
    if evidence or not schema.field_profiles or not snapshot:
        return None
    return (Completion.CATALOGUE_UNREADABLE,
            "the schema's %d field paths read no evidence from a snapshot of %d fields; "
            "first path %r — schema and catalogue are not the same shape"
            % (len(schema.field_profiles), len(snapshot),
               schema.field_profiles[0].field_name))


def _nothing_read(request: VerificationRequest, schema: CategorySchema) -> Intake:
    """The empty reading, for a record whose reading never happened.

    Not an `Undeclared` intake: that means the order carried no stated request, which is
    the merchant's channel policy. This means we could not read the one it carried, which
    is ours. `covered` is False either way and `completion` is what tells them apart.
    """
    return Intake(surface=request.surface, shape=request.artifact.shape,
                  agent=request.agent or AgentPresence.UNKNOWN,
                  merchant_id=request.merchant_id, covered=False,
                  notes=("the stated request could not be read; see completion_detail",))


class ModeMismatch(ValueError):
    """An outcome from one mode was offered to a deployment running the other."""


def ingest_outcome(outcome: OrderOutcome, *, record_outcome: Sink,
                   mode: Mode = Mode.SHADOW) -> OrderOutcome:
    """Take one later fact about one verified order. Decide nothing with it.

    A shadow run's whole purpose is this join: the decision says what Approv would have
    done, and the outcome says what happened anyway. Without it a shadow run measures the
    same thing the corpus already measures, and the two numbers DR 0020 says decide the
    business — how much agent traffic carries a recoverable request, and how many clean
    records still get refunded — stay unmeasured.

    **`merchant_reason` is recorded verbatim and read by nothing.** It is the field most
    likely to be quietly promoted into a signal, and the moment it is, a merchant's free
    text is in the decision path. Persisting is the caller's (`record_outcome`), because
    the store owns storage and this module must not.

    The mode has to match. An outcome carrying the other mode is refused rather than
    stored, because a sandbox result joined to a live record would be exactly the
    cross-contamination the separate chain exists to prevent — and a join key is all it
    would take.
    """
    if outcome.mode is not mode:
        raise ModeMismatch("outcome is %s, this deployment is %s"
                           % (outcome.mode.value, mode.value))
    record_outcome(outcome)
    return outcome


# Identifier keys that name a *line* rather than the product it belongs to. The grouping
# keys are deliberately absent: every variant in a record carries the same `product_id`, so
# matching on one would select all of them and call that a selection.
_NOT_A_LINE = frozenset({"product_id", "parent_id", "family_id", "group_id",
                         "item_group_id", "style_id", "merchant_id", "store_id"})


def _is_ordered_line(variant: Mapping[str, object], order: OrderLine) -> bool:
    """Whether this variant is the line that was bought: it answers to one of the order's
    identifiers and contradicts neither.

    Both halves are needed. Matching alone would accept a variant whose `id` is the one the
    order names while its `sku` is somebody else's — a stale variant id on an otherwise
    correct order line, which is a contradiction rather than a match, and resolving it by
    taking whichever identifier happened to hit first is how the wrong SKU gets read with
    full confidence.

    Only a key of the *same kind* can contradict: an order's SKU is compared against the
    variant's SKU, its variant id against the variant's own id. Every other
    identifier-shaped key — `stock_ref` on one export, `color_code` on another — may
    identify the line but never vetoes it, because `color_code` is an attribute wearing an
    identifier's name and vetoing on it would reject every variant in the array.
    """
    matched = False
    for key, value in variant.items():
        if not isinstance(key, str) or not is_identifier(key):
            continue
        name = semantic_key(key)
        if name in _NOT_A_LINE or isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        text = str(value)
        same_kind = order.sku if name.endswith("sku") else (
            order.variant_id if name in {"id", "variant_id"} else None)
        if same_kind is not None and text != str(same_kind):
            return False
        if text in {str(one) for one in (order.variant_id, order.sku) if one}:
            matched = True
    return matched


def selected_listing(snapshot: Mapping[str, object], order: OrderLine) -> Mapping[str, object]:
    """The snapshot with only the ordered SKU left in its variant array.

    **Evidence is scoped to the variant that was bought.** Reading a neighbouring SKU's
    colour is not a cautious answer that happens to be incomplete — it is a *wrong* one,
    stated with the same confidence as a right one and signed into the same record, and on
    an apparel catalogue every single order has a dozen wrong answers available. Nothing
    downstream can tell that a Frost reading came from the Ash variant.

    The projection keeps the root, its metadata and the enclosing objects, so inherited
    fields — currency, the option-name table, the parent's own attributes — still read.
    Only the array is narrowed. The record keeps the snapshot the merchant actually sent;
    this rule is deterministic from `order`, so a returns desk can reproduce exactly what
    was read from the record alone.

    A snapshot with one variant, or none, is returned untouched. A multi-SKU snapshot that
    does not contain the ordered line raises, because there is no reading of it that is
    about this order.
    """
    try:
        collections = variant_collections(dict(snapshot))
    except ValueError:
        # A malformed record. Left alone so the reader fails on it with a named catalogue
        # reason rather than being rejected here as if the order line were at fault.
        return snapshot
    if len(collections) != 1:
        return snapshot
    path, variants = collections[0]
    if len(variants) < 2:
        return snapshot
    chosen = [variant for variant in variants
              if isinstance(variant, Mapping) and _is_ordered_line(variant, order)]
    if len(chosen) != 1:
        raise VariantMismatch(
            "the snapshot holds %d variants and %d of them is the ordered line "
            "(variant_id=%r, sku=%r); a reading of it would be about a different SKU"
            % (len(variants), len(chosen), order.variant_id, order.sku))
    projected = dict(snapshot)
    node = projected
    for key in path[:-1]:
        node[key] = dict(node[key])
        node = node[key]
    node[path[-1]] = chosen
    return projected


def _bind_snapshot_to_order(request: VerificationRequest) -> None:
    """Refuse to compare a catalogue record against a different order line.

    `ComparisonRecord` validates that the order and the comparison name one product, but
    from inside this function they always would — `product_id` is taken *from* the order,
    so the record's own check can never fire here and would be a guard proving nothing.
    The binding that can actually fail at this surface is between the order line and the
    **snapshot**: a merchant who posts order line A with the catalogue record for B gets a
    record that says the wrong product matched, and it would look like evidence.

    Only checked when the snapshot identifies itself. Many catalogue exports do not carry
    an id, and rejecting those would be inventing a requirement the format does not have.
    """
    named = request.product_snapshot.get("product_id", request.product_snapshot.get("id"))
    if named is not None and str(named) != request.order.product_id:
        raise ProductMismatch(
            "catalogue snapshot is product %r but the order line is %r"
            % (named, request.order.product_id))


def _stated_text(artifact: Artifact) -> str:
    """The shopper's words where there are any, and an honest description where not.

    A protocol call has no wording, so `request_text` cannot be one — and leaving it empty
    would read, in a dispute, as the agent having said nothing. What it said is the slots
    it filled, which `request_constraints` carries in full.
    """
    if isinstance(artifact, FreeText):
        return artifact.text
    if isinstance(artifact, Search):
        return artifact.query
    if isinstance(artifact, Structured):
        return "(no wording: %s protocol call, see request_constraints)" % artifact.protocol
    return "(no stated request accompanied this order)"
