"""CONFIRM as an evidentiary challenge: name the gap, take one citation, resolve.

This replaces repair advice. The old design told the agent to pick a different product and
measured +0.0 pp against a content-free "look again" control, three times, because a
generic re-read carries more repair than a narrow note about one item. Redirecting the
agent's search was the wrong interaction: it asks the agent to do the shopping again.

The interaction here is adversarial-but-cooperative and it is bounded. Approv says which
attribute it could not establish and what would establish it. The agent gets exactly one
round to say *where to look*. Approv reads that source itself and re-runs the same
comparison. The result is ALLOW or REFUSE — never another CONFIRM, because a state that
can recur is a negotiation, and a checker that can be negotiated with is not a checker.

**The agent supplies a citation, never a value.** This is the whole safety property. If an
agent could assert "it is size 9" and have that clear a HARD attribute, then planting one
sentence moves the decision and the check is an injection channel wearing a lanyard. DR
0009's monotone rule and the advice ladder both say the same thing: a party with an
interest in the outcome may lower confidence, never raise it. So the agent points, and
Approv looks.

Resolution needs no new comparison logic. A citation becomes an `Evidence` read by the
caller's own reader, appended to what was already known, and `check_constraints` runs
again — so source conflict, certainty ceilings and liability ranking all behave exactly as
they do everywhere else. A cited field that contradicts a known one produces
FIELD_CONFLICT and the attribute stays unresolved, which is correct and which falls out
for free.
"""

from __future__ import annotations

from typing import Callable

from approv.algebra.runner import check_constraints
from approv.evaluator import HARD_CONFIDENCE_FLOOR, decide
from approv.types.core import (
    CategorySchema, Certainty, Constraint, Criticality, Decision, Evidence, Finding,
    Liability, ReasonCode, Support,
)
from pydantic import BaseModel, ConfigDict, Field

VERSION = "challenge-v1"

_BLOCKING = (Criticality.HARD, Criticality.BOUND)

# What a source has to clear to settle each kind of gap. A value read from prose cannot
# carry a HARD attribute alone (DR 0016 §4), so a challenge raised because the only source
# was weak is not answered by another weak source.
_MINIMUM = {
    ReasonCode.PRODUCT_SILENT: (Liability.SELLER_STATED, Certainty.PARSED),
    ReasonCode.NO_CLAIM: (Liability.SELLER_STATED, Certainty.PARSED),
    ReasonCode.LOW_CERTAINTY_SOURCE: (Liability.SELLER_STATED, Certainty.EXACT),
    ReasonCode.LOW_LIABILITY_SOURCE: (Liability.MERCHANT_GUARANTEED, Certainty.PARSED),
    ReasonCode.FIELD_CONFLICT: (Liability.MERCHANT_GUARANTEED, Certainty.EXACT),
    ReasonCode.UNRESOLVED_TERM: (Liability.SELLER_STATED, Certainty.EXACT),
    ReasonCode.ADVICE_ONLY: (Liability.SELLER_STATED, Certainty.PARSED),
    ReasonCode.UNTRUSTED_SOURCE: (Liability.MERCHANT_GUARANTEED, Certainty.PARSED),
}
_DEFAULT_MINIMUM = (Liability.MERCHANT_GUARANTEED, Certainty.EXACT)

_LIABILITY_RANK = {Liability.MERCHANT_GUARANTEED: 0, Liability.SELLER_STATED: 1,
                   Liability.PLATFORM_DERIVED: 2, Liability.UNATTRIBUTED: 3}
_CERTAINTY_RANK = {Certainty.EXACT: 0, Certainty.PARSED: 1, Certainty.INFERRED: 2}


class Challenge(BaseModel):
    """One attribute Approv could not establish, and what would establish it."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    reasons: tuple[ReasonCode, ...] = ()
    # Fields already read for this attribute. Naming them stops the agent answering with
    # the same weak source that raised the challenge, which is the obvious way to make a
    # bounded round into an unbounded one.
    consulted: tuple[str, ...] = ()
    needs_liability: Liability
    needs_certainty: Certainty


class Citation(BaseModel):
    """The agent's answer: where to look. Deliberately carries no value.

    There is no `value` field and that absence is the design. An agent that could state
    the value could clear its own check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    attribute: str
    field_name: str = Field(min_length=1)
    locator: str | None = None


class Outcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: Decision
    reasons: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    admitted: tuple[Citation, ...] = ()
    rejected: tuple[tuple[Citation, str], ...] = ()


def challenges_for(findings: tuple[Finding, ...], schema: CategorySchema) -> tuple[Challenge, ...]:
    """The attributes a CONFIRM is waiting on, each with the bar to clear.

    Only blocking attributes and only unresolved ones. A SOFT attribute never held the
    decision up, so challenging it would spend a round on something that was never going
    to change the answer.
    """
    out = []
    for finding in findings:
        if finding.criticality not in _BLOCKING:
            continue
        unresolved = (finding.support is Support.UNSTATED
                      or finding.confidence < HARD_CONFIDENCE_FLOOR)
        if not unresolved:
            continue
        liability, certainty = _DEFAULT_MINIMUM
        for reason in finding.reasons:
            if reason in _MINIMUM:
                liability, certainty = _MINIMUM[reason]
                break
        out.append(Challenge(
            attribute=finding.attribute,
            reasons=finding.reasons,
            consulted=tuple(dict.fromkeys(e.field_name for e in finding.evidence)),
            needs_liability=liability,
            needs_certainty=certainty,
        ))
    return tuple(out)


def _admissible(citation: Citation, challenge: Challenge, evidence: Evidence | None) -> str | None:
    """Why this citation cannot be used, or None if it can."""
    if evidence is None:
        return "the cited source could not be read"
    if evidence.attribute != citation.attribute:
        return "the source speaks to a different attribute"
    if citation.field_name in challenge.consulted:
        return "that source was already read and is what raised the challenge"
    if evidence.is_advice:
        return "advice may lower confidence, never establish a fact"
    if _LIABILITY_RANK[evidence.liability] > _LIABILITY_RANK[challenge.needs_liability]:
        return "nobody is answerable for that source"
    if _CERTAINTY_RANK[evidence.certainty] > _CERTAINTY_RANK[challenge.needs_certainty]:
        return "that source is not precise enough to settle this"
    return None


def resolve(
    constraints: tuple[Constraint, ...],
    evidence: tuple[Evidence, ...],
    schema: CategorySchema,
    challenges: tuple[Challenge, ...],
    citations: tuple[Citation, ...],
    read_source: Callable[[Citation], Evidence | None],
    *,
    floor_met: bool = True,
) -> Outcome:
    """One bounded round. Returns ALLOW or REFUSE, never CONFIRM.

    `read_source` is the caller's — a merchant adapter, a catalogue reader, a fetcher for
    the cited URL. Approv never takes the agent's word for what the source says, so this
    function's correctness does not depend on the agent being honest, only on the reader
    being the merchant's rather than the agent's.

    A still-unresolved attribute refuses rather than confirming again. That is the point of
    a bounded round: CONFIRM is a question, and an unanswered question is not a yes.
    """
    by_attribute = {c.attribute: c for c in challenges}
    admitted, rejected, extra = [], [], []

    for citation in citations:
        challenge = by_attribute.get(citation.attribute)
        if challenge is None:
            rejected.append((citation, "no challenge was raised for that attribute"))
            continue
        found = read_source(citation)
        why = _admissible(citation, challenge, found)
        if why is not None:
            rejected.append((citation, why))
            continue
        admitted.append(citation)
        extra.append(found)

    findings = check_constraints(constraints, tuple(evidence) + tuple(extra), schema)
    decision, reasons = decide(findings, floor_met=floor_met)
    if decision is Decision.CONFIRM:
        decision = Decision.REFUSE
    return Outcome(decision=decision, reasons=reasons, findings=findings,
                   admitted=tuple(admitted), rejected=tuple(rejected))


def render(challenges: tuple[Challenge, ...]) -> str:
    """The challenge as something an agent can answer.

    Names the attribute, why it is open, and the bar — and asks for a source rather than an
    answer, because the shape of the question is what stops the agent answering it with an
    assertion.
    """
    if not challenges:
        return "Nothing is open."
    lines = ["One round. For each attribute below, name the merchant field or document "
             "that settles it. Do not state the value — it will be read from the source "
             "you name. Anything still open after this round is refused."]
    for challenge in challenges:
        why = ", ".join(r.value for r in challenge.reasons) or "not established"
        already = (" Already read: " + ", ".join(challenge.consulted) + "."
                   if challenge.consulted else "")
        lines.append(f"- {challenge.attribute}: {why}. Needs a source at or above "
                     f"{challenge.needs_liability.value} / {challenge.needs_certainty.value}."
                     + already)
    return "\n".join(lines)
