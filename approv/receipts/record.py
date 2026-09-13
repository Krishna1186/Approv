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

from approv.criticality import coverage_of, narrowed_attributes, unread_requirements
from approv.evaluator import VERSION as EVALUATOR_VERSION, decide
from approv.types.core import (
    AgentTurn, Attestation, CategorySchema, Claim, ComparisonRecord, Completion,
    Constraint, Criticality, Finding, OrderLine, ReasonCode, UnreadPolicy,
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


def floor_is_met(findings: tuple[Finding, ...], unread: tuple[str, ...] = ()) -> bool:
    """Whether verification had its preconditions at all.

    Read off the findings rather than recomputed from the schema, so there is exactly one
    place that decides a floor was missed. Two implementations of the same rule drift,
    and this one gates a `confirm`.

    An unread part of the request fails the floor too, and that is not a stretch of the
    idea — the floor is the set of things without which verification was never possible,
    and not having finished reading the request is the strongest case of that there is.
    Measured on the fresh corpus: every false allow in the first gate scoring was one
    case, `fresh-42`, whose request said "Stone Two Tone" and whose extractor recorded
    that it could not encode it. The gate then allowed three comforters in the wrong
    colour. The extractor had already said the words; nothing was listening.

    Routing to `confirm` rather than `refuse` is the point. The purchase is not blocked,
    it is escalated, which is the only branch that is recoverable (section 2.6).

    Whether to apply this at all is `unread_policy`, and it is a business parameter rather
    than a constant, because section 2.6 says a false allow and a false refuse do not cost
    the same and the ratio differs per merchant. DR 0022 measured all three and made
    WITHDRAW the default: escalating charges the merchant for our extraction miss. The two
    operating points below are the older two-way trade, measured on the fresh corpus,
    1,057 pairs over 34 requests:

        escalate   false allow  0.0% [0.0, 0.4]   nuisance confirm  48.4%
        ignore     false allow  0.3% [0.1, 0.9]   nuisance confirm   3.3%

    Both were measured before DR 0021, when `unread` still meant every interpretation
    note, and before DR 0022 added the third option. They stand as measured rather than as
    corrected; the v3 pack numbers under the current definitions are in DR 0022.

    Neither is obviously right and picking one here would be picking a merchant's risk
    appetite for them. What the numbers do say is that the gate is the wrong place to fix
    this: 35 of the 44 nuisance confirms are one request whose unread note was "not
    backordered", which is a restatement of the availability requirement the extractor had
    already captured. Nothing was lost and the gate escalated anyway. The repair belongs in
    extraction — a note that duplicates a constraint should not be recorded as a note —
    and until that lands this parameter is how a merchant chooses which error to eat. DR
    0021 did that repair at the definition instead: "not backordered" is a free-text
    `unverified` entry, not a dropped requirement, so it no longer reaches the floor at
    all. The fresh corpus has not been re-run under the new definition, so the 48.4% above
    stands as measured rather than as corrected.

    Coverage has since narrowed what this parameter has to carry. The case it existed to
    catch — a requirement read too narrowly and then guaranteed — is now handled by
    `criticality.narrowed_attributes`, which routes that attribute out of coverage and
    costs no nuisance at all because it never touches the decision. What is left here is
    the genuinely unattributable gap: dropped text belonging to no constraint's quote.
    """
    if unread:
        return False
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
    # Notes meaning a checkable requirement went unchecked, and only those. The producer
    # filters, because the record records what it is told rather than second-guessing it —
    # `types.core.dropped_requirement` is the one definition. DR 0021.
    unread: tuple[str, ...] = (),
    # What an unread request does to the answer. DR 0022: the default withdraws the
    # guarantee rather than escalating, because an unread requirement is our defect and
    # pausing the merchant's checkout over it charges them for it.
    unread_policy: UnreadPolicy = UnreadPolicy.WITHDRAW,
    order: OrderLine | None = None,
    # DR 0004. A verification that did not run to a conclusion never authorises and never
    # carries coverage; it says so in the record rather than being indistinguishable from
    # a clean allow.
    completion: Completion = Completion.COMPLETED,
    completion_detail: str | None = None,
) -> ComparisonRecord:
    """Assemble one unsigned ComparisonRecord and decide it.

    `order` is the merchant order line this comparison is a defence of, and passing it is
    what turns a comparison about a product into a verification of a purchase. It is
    validated against `product_id` by `ComparisonRecord` itself, so a record cannot be
    assembled that names one SKU in the order and compares another.

    `product_snapshot` is the catalogue record as it stood when the comparison ran, and
    `snapshot_hash` is its digest. Both are kept: the hash proves the listing has not
    moved under us, and the snapshot is what a dispute is actually argued against. A hash
    alone would prove only that we are consistent with something nobody can read.

    The decision comes from `evaluator.decide` and from nowhere else. If a caller ever
    wants to override it, that caller is the decision path and the company's central
    claim is false.
    """
    # Narrowed once, here, so that what the record stores and what the decision acts on
    # are the same set. DR 0022: a gap that is nothing but the shopper's hedge words names
    # no unread requirement, and storing it would say we failed to read something we read.
    unread = unread_requirements(constraints, unread)
    escalate = unread if unread_policy is UnreadPolicy.ESCALATE else ()
    # An incomplete check is the clearest possible case of the floor not being met — the
    # preconditions for verification were not there — so the failure is expressed in the
    # input `decide` already takes rather than by overriding its answer. `decide` cannot
    # return ALLOW with `floor_met=False`, which is the property that matters: today
    # `decide(())` returns ALLOW, so an extractor that fails and yields no constraints
    # authorises the purchase. That is the fail-open bypass, reachable without an attacker.
    incomplete = completion is not Completion.COMPLETED
    decision, reasons = decide(
        findings, floor_met=not incomplete and floor_is_met(findings, escalate))
    # Computed here and not passed in, so that a caller cannot forget it. `unread` is
    # already the record's honest account of what went unread; this reads it rather than
    # asking for the same thing twice.
    narrowed = narrowed_attributes(constraints, unread)
    # IGNORE is the only policy that guarantees over words nobody read. Both of the others
    # acknowledge the gap; they differ in whether the sale pauses for it.
    request_unread = bool(unread) and unread_policy is not UnreadPolicy.IGNORE
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
        order=order,
        completion=completion,
        completion_detail=completion_detail,
        findings=findings,
        coverage=tuple(coverage_of(f, narrowed=f.attribute in narrowed,
                                   request_unread=request_unread, incomplete=incomplete)
                       for f in findings),
        completeness=completeness(schema, constraints),
        unread=unread,
        decision=decision,
        decision_reasons=reasons,
        model_version=model_version,
        evaluator_version=EVALUATOR_VERSION,
        prompt_version=prompt_version,
        timestamp=timestamp or datetime.now(timezone.utc),
        prev_hash=prev_hash,
    )
