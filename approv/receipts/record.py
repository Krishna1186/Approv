"""Building the object the company signs.

Everything upstream of here produces findings. This is where findings become a
*decision* and a *record*, which is the step that was specified in week one and never
built: `decide()` had zero call sites outside its own test, and `ComparisonRecord` had
never been constructed.

Nothing here decides anything itself. It assembles inputs, asks `evaluator/` for the
decision, and returns an unsigned record. Signing is `chain.py`'s job, deliberately
separate: a record that cannot be built without a private key cannot be built in a test.
"""

from __future__ import annotations

from datetime import datetime, timezone

from approv.evaluator import VERSION as EVALUATOR_VERSION, decide
from approv.types.core import (
    AgentTurn, Attestation, CategorySchema, Claim, ComparisonRecord, Constraint,
    Finding, ReasonCode,
)

VERSION = "receipt-v1"


def completeness(schema: CategorySchema, constraints: tuple[Constraint, ...]) -> tuple[str, ...]:
    """The attributes this category defines that the request never mentioned.

    §2.2 calls this the load-bearing field, and the reason is that it is the only thing
    in the record that distinguishes *"the agent got it wrong"* from *"nobody ever said"*.
    Those two attribute fault to different parties and only the first is coverable, so a
    record without this field cannot be adjudicated no matter how accurate its findings
    are.

    Silence, not failure. An attribute the request named and we could not check is a
    finding with a reason code; an attribute nobody mentioned is this. Collapsing them
    would let a coverable miss hide inside "the request was vague".
    """
    named = {c.attribute for c in constraints}
    return tuple(sorted(spec.name for spec in schema.attributes if spec.name not in named))


def floor_is_met(findings: tuple[Finding, ...]) -> bool:
    """Whether every attribute the category cannot be verified without was supplied.

    Read off the findings rather than recomputed from the schema, so there is exactly one
    place that decides a floor was missed. Two implementations of the same rule drift,
    and this one gates a `confirm`.
    """
    return not any(ReasonCode.FLOOR_NOT_MET in f.reasons for f in findings)


def build_record(
    *,
    correlation_id: str,
    request_text: str,
    constraints: tuple[Constraint, ...],
    findings: tuple[Finding, ...],
    schema: CategorySchema,
    product_id: str,
    product_snapshot: dict,
    snapshot_hash: str,
    model_version: str,
    prompt_version: str,
    locale: str = "en-IN",
    turns: tuple[AgentTurn, ...] = (),
    claims: tuple[Claim, ...] = (),
    agent_id: str | None = None,
    merchant_id: str | None = None,
    attestation: Attestation = Attestation.NEITHER,
    prev_hash: str | None = None,
    timestamp: datetime | None = None,
) -> ComparisonRecord:
    """Assemble one unsigned ComparisonRecord and decide it.

    `product_snapshot` is the catalogue record as it stood when the comparison ran, and
    `snapshot_hash` is its digest. Both are kept: the hash proves the listing has not
    moved under us, and the snapshot is what a dispute is actually argued against. A hash
    alone would prove only that we are consistent with something nobody can read.

    The decision comes from `evaluator.decide` and from nowhere else. If a caller ever
    wants to override it, that caller is the decision path and the company's central
    claim is false.
    """
    decision, reasons = decide(findings, floor_met=floor_is_met(findings))
    return ComparisonRecord(
        correlation_id=correlation_id,
        agent_id=agent_id,
        merchant_id=merchant_id,
        attestation=attestation,
        category_id=schema.category_id,
        category_version=schema.version,
        locale=locale,
        request_text=request_text,
        request_constraints=constraints,
        turns=turns,
        claims=claims,
        product_id=product_id,
        product_snapshot=product_snapshot,
        snapshot_hash=snapshot_hash,
        findings=findings,
        completeness=completeness(schema, constraints),
        decision=decision,
        decision_reasons=reasons,
        model_version=model_version,
        evaluator_version=EVALUATOR_VERSION,
        prompt_version=prompt_version,
        timestamp=timestamp or datetime.now(timezone.utc),
        prev_hash=prev_hash,
    )
