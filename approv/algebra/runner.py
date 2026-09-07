"""Running every check for one product, and reporting all of them.

Three jobs, and they are separate on purpose:

1. Pair each claim with the evidence about the same attribute.
2. Pick the right operator for that attribute's type.
3. Report *everything* — every mismatch, every gap, every weak source.

Point 3 is the product. An agent handed one problem at a time fixes one problem at a
time and pays a round trip for each. An agent handed all of them fixes them in one pass.

This module makes no decision. It returns findings; `evaluator/` turns findings into
allow/confirm/refuse, and per §4.1 it will do that without importing anything from here.
"""

from __future__ import annotations

from approv.algebra.count import compare_count
from approv.algebra.quantity import compare_quantity
from approv.algebra.term import compare_term
from approv.types.core import (
    AttributeSpec,
    CategorySchema,
    Certainty,
    CheckKind,
    Claim,
    Count,
    Dimension,
    Evidence,
    Finding,
    Quantity,
    ReasonCode,
    Repair,
    Resolution,
    Support,
    Term,
)

# Certainty ranks, strongest first. Used to choose between two fields that both speak to
# the same attribute, and to notice when they disagree.
_CERTAINTY_RANK = {Certainty.EXACT: 0, Certainty.PARSED: 1, Certainty.INFERRED: 2}


def _operator_for(value: object):
    if isinstance(value, Quantity):
        return compare_quantity
    if isinstance(value, Term):
        return compare_term
    if isinstance(value, Count):
        return compare_count
    return None


def _bare(
    spec: AttributeSpec,
    support: Support,
    resolution: Resolution,
    reason: ReasonCode,
    *,
    claim: Claim | None = None,
) -> Finding:
    """A finding produced without running any operator, because there was nothing to run."""
    return Finding(
        check=CheckKind.GROUNDING,
        attribute=spec.name,
        criticality=spec.criticality,
        support=support,
        confidence=0.0,
        ceiling=0.0,
        reasons=(reason,),
        repair=Repair(
            resolution=resolution,
            attribute=spec.name,
            claimed=None if claim is None else _surface(claim),
        ),
        claim=claim,
    )


def _surface(claim: Claim) -> str:
    value = claim.value
    if isinstance(value, Term):
        return value.surface
    if isinstance(value, Count):
        return str(value.n)
    if isinstance(value, Quantity):
        return f"{value.magnitude.normalize():f} {value.unit}"
    return str(value)


def run_checks(
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    schema: CategorySchema,
) -> tuple[Finding, ...]:
    """Check every attribute the schema defines, and report all outcomes.

    Attributes with no claim and no evidence are silent on both sides and produce
    nothing. Everything else produces a finding, including the cases where no comparison
    could be run — a gap we can name is worth more than a gap we omit.
    """
    findings: list[Finding] = []

    claims_by_attribute: dict[str, list[Claim]] = {}
    for claim in claims:
        claims_by_attribute.setdefault(claim.attribute, []).append(claim)

    evidence_by_attribute: dict[str, list[Evidence]] = {}
    for item in evidence:
        evidence_by_attribute.setdefault(item.attribute, []).append(item)

    for spec in schema.attributes:
        attribute_claims = claims_by_attribute.get(spec.name, [])
        attribute_evidence = evidence_by_attribute.get(spec.name, [])

        if not attribute_claims:
            # The floor decides whether silence is fatal or merely unremarkable.
            if spec.name in schema.floor:
                findings.append(
                    _bare(
                        spec,
                        Support.UNSTATED,
                        Resolution.STATE_THE_ATTRIBUTE,
                        ReasonCode.FLOOR_NOT_MET,
                    )
                )
            elif attribute_evidence:
                findings.append(
                    _bare(
                        spec,
                        Support.UNSTATED,
                        Resolution.STATE_THE_ATTRIBUTE,
                        ReasonCode.NO_CLAIM,
                    )
                )
            continue

        claim = attribute_claims[0]

        if not attribute_evidence:
            findings.append(
                _bare(
                    spec,
                    Support.UNSTATED,
                    Resolution.NOT_RESOLVABLE,
                    ReasonCode.PRODUCT_SILENT,
                    claim=claim,
                )
            )
            continue

        # Prefer the most certain field. Sorting rather than filtering so the runner-up
        # is still available for the conflict check below.
        ranked = sorted(attribute_evidence, key=lambda e: _CERTAINTY_RANK[e.certainty])
        best = ranked[0]

        operator = _operator_for(claim.value)
        if operator is None or not isinstance(best.value, type(claim.value)):
            findings.append(
                _bare(
                    spec,
                    Support.UNSTATED,
                    Resolution.RESTATE_CLAIM,
                    ReasonCode.INCOMMENSURABLE,
                    claim=claim,
                )
            )
            continue

        finding = operator(claim, best, spec)

        # Two fields speaking to the same attribute that disagree is a fact about the
        # listing worth surfacing even when the winning field agrees with the claim.
        for other in ranked[1:]:
            if not isinstance(other.value, type(claim.value)):
                continue
            if operator(claim, other, spec).support is not finding.support:
                finding = finding.model_copy(
                    update={
                        "reasons": finding.reasons + (ReasonCode.FIELD_CONFLICT,),
                        "evidence": finding.evidence + (other,),
                    }
                )
                break

        findings.append(finding)

    return tuple(findings)


def dimension_of(spec: AttributeSpec) -> Dimension:
    return spec.dimension
