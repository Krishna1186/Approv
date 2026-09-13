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

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from approv.algebra.runner import check_constraints
from approv.intake import (
    AgentPresence, Artifact, Extractor, FreeText, Intake, Search, Structured, Surface,
    Undeclared, intake,
)
from approv.receipts.chain import canonical_json, seal
from approv.receipts.record import build_record
from approv.types.core import (
    Attestation, CategorySchema, ComparisonRecord, Completion, Count, Evidence, Finding,
    OrderLine, Term, UnreadPolicy, Value,
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
    # Whether this channel earns coverage at all, and why not when it does not. Intake's
    # verdict, kept off the record because it is policy about the channel rather than a
    # fact about the comparison.
    covered: bool
    intake_notes: tuple[str, ...] = ()


def _dig(snapshot: Mapping[str, object], field_name: str):
    """`variant.size` as a nested lookup, falling back to the flat key.

    Both spellings occur in real catalogue exports and guessing wrong loses evidence
    silently, which routes an attribute to PRODUCT_SILENT and escalates a sale for a
    reason that is ours rather than the merchant's.
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
    if isinstance(raw, str):
        return Term(surface=raw)
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return Count(n=raw)
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
        value = _as_value(_dig(snapshot, profile.field_name))
        if value is None:
            continue
        for attribute in profile.attributes:
            out.append(Evidence(attribute=attribute, value=value,
                                field_name=profile.field_name, liability=profile.liability,
                                certainty=profile.certainty, is_advice=profile.is_advice))
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
    signing_key=None,
    prev_hash: str | None = None,
    unread_policy: UnreadPolicy = UnreadPolicy.WITHDRAW,
    returns: Mapping[str, float] | None = None,
    budget_seconds: float | None = None,
) -> VerificationResult:
    """One order line in, one signed record out.

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
        prev_hash=prev_hash,
        unread=taken.unread,
        unread_policy=unread_policy,
        order=request.order,
        completion=completion,
        completion_detail=detail,
    )
    if signing_key is not None:
        record = seal(record, signing_key, prev_hash)

    # No coverage may ever be inferred from a verification that did not complete (DR
    # 0004). Intake's verdict is about the channel and knows nothing about whether the
    # check finished, so the two are combined here rather than leaving a caller to read
    # `covered: true` beside a provider outage.
    return VerificationResult(
        record=record, receipt_id=request.correlation_id,
        covered=taken.covered and completion is Completion.COMPLETED,
        intake_notes=taken.notes)


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
