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
from urllib.parse import unquote
from typing import Annotated, Callable, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from approv.algebra.runner import check_constraints
from approv.intake import (
    AgentPresence, Artifact, Extractor, FreeText, Intake, Search, Structured, Surface,
    Undeclared, intake,
)
from approv.receipts.chain import canonical_json
from approv.receipts.record import build_record
from approv.types.core import (
    Attestation, CategorySchema, ComparisonRecord, Completion, Count, Dimension, Evidence,
    Finding, Money, OrderLine, Quantity, Term, UnreadPolicy, Value,
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

# The discriminated value union, for a catalogue that exports typed values.
_VALUE_ADAPTER = TypeAdapter(Value)

# The array marker in a derived field path. A sentinel rather than the string "*", so a key
# that really is an asterisk (written `~2` on the wire) cannot collide with it once
# unescaped.
_ANY = type("ArrayMarker", (), {"__repr__": lambda self: "*"})()

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

    record: ComparisonRecord
    receipt_id: str
    # Views onto the record, not a second copy of the fact (DR 0023). They were the fact
    # once, which is how the artifact came to print "Covered" for an order intake had
    # ruled out — it renders the record and could not see them.
    covered: bool
    intake_notes: tuple[str, ...] = ()


def _split_pointer(field_name: str) -> tuple[list, str | None]:
    """A JSON pointer with an optional `#name=` selector, into tokens and the selector.

    `approv.schema` writes a `#` inside a key as `~3` and URL-quotes the selector value, so
    the first `#` is unambiguously the separator. `*` is the array marker; a literal `*` in
    a key arrives as `~2`. Unescaping puts `~0` last, or a key containing `~1` would be
    decoded twice.
    """
    path, _, selector = field_name.partition("#")
    tokens = []
    for token in path.split("/")[1:]:
        if token == "*":
            tokens.append(_ANY)
            continue
        for code, char in (("~1", "/"), ("~2", "*"), ("~3", "#"), ("~0", "~")):
            token = token.replace(code, char)
        tokens.append(token)
    name = unquote(selector[len("name="):]) if selector.startswith("name=") else None
    return tokens, name


def _walk(node: object, tokens: list):
    """Every node this pointer reaches. A `*` fans out over a list rather than indexing."""
    if not tokens:
        yield node
        return
    token, rest = tokens[0], tokens[1:]
    if token is _ANY:
        if isinstance(node, (list, tuple)):
            for item in node:
                yield from _walk(item, rest)
    elif isinstance(node, Mapping) and token in node:
        yield from _walk(node[token], rest)


def _same_label(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def _pointer_values(snapshot: Mapping[str, object], field_name: str) -> list:
    """The values a derived `field_name` names in this snapshot.

    In `/variants/*/options/*/value#name=Colour` the container is a label/value pair and
    the selector is **load-bearing**: the same path also carries Size, and reading it wrong
    crosses two attributes. So a selector must match a sibling of the value, and a
    container labelled with anything else is a *different attribute* rather than a
    fallback — falling back to the path would hand every option value to whichever
    attribute asked first.

    That rule costs one shape. `approv.schema` also writes
    `/variants/*/option1#name=Colour` for flat exports whose option names live in a
    separate table, and there the label is not a sibling at all, so this reader returns
    nothing for it. Deliberate: reading nothing is caught loudly by `_reads_nothing`, and
    reading the wrong attribute is not caught at all. A merchant on that shape supplies
    their own `Reader`.
    """
    tokens, selector = _split_pointer(field_name)
    if not tokens:
        return []
    last = tokens[-1]
    if not isinstance(last, str):
        return []
    candidates = [(parent, parent[last]) for parent in _walk(snapshot, tokens[:-1])
                  if isinstance(parent, Mapping) and last in parent]
    if selector is None:
        return [value for _, value in candidates]
    return [value for parent, value in candidates
            if any(_same_label(sibling, selector)
                   for key, sibling in parent.items()
                   if key != last and isinstance(sibling, str))]


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
    """
    out = []
    for profile in schema.field_profiles:
        if profile.field_name.startswith("/"):
            raw = _pointer_values(snapshot, profile.field_name)
        else:
            found = _dotted(snapshot, profile.field_name)
            raw = [] if found is None else [found]
        for one in raw:
            value = _as_value(one)
            if value is None:
                continue
            for attribute in profile.attributes:
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
    """
    schema = schemas.get(request.category_id)
    if schema is None:
        raise UnknownCategory(request.category_id)
    _bind_snapshot_to_order(request)

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
            lambda: read_evidence(request.product_snapshot, schema),
            Completion.CATALOGUE_UNREADABLE, "reading the catalogue snapshot")
    if failure is None:
        failure = _reads_nothing(evidence, request.product_snapshot, schema)
    if failure is None:
        findings = check_constraints(
            taken.constraints, evidence, schema, returns=returns,
            superseded=frozenset(taken.superseded))
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
    )
    return VerificationResult(record=record, receipt_id=request.correlation_id,
                              covered=record.covered,
                              intake_notes=record.coverage_notes)


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
