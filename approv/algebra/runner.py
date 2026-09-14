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
    Channel,
    CheckKind,
    Claim,
    Count,
    Constraint,
    Criticality,
    Bound,
    Money,
    Dimension,
    Evidence,
    Finding,
    Liability,
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
    if isinstance(value, (Bound, Money)):
        from approv.algebra.numeric import compare_numeric
        return compare_numeric
    if isinstance(value, Quantity):
        return compare_quantity
    if isinstance(value, Term):
        return compare_term
    if isinstance(value, Count):
        return compare_count
    return None


# Channel strength, strongest first. DR 0008's tiers: a structured filter and a
# paraphrase of the same request are not equally disputable.
_CHANNEL_RANK = {channel: rank for rank, channel in enumerate(Channel)}


def _corroborated(claims: list[Claim], spec: AttributeSpec) -> Claim | None:
    """Several statements of one attribute as a single claim, when they agree (DR 0025).

    On-site search states an attribute twice by design: a shopper who filters to Size King
    and types "king duvet" has said the same thing through two channels. Treating that as
    an unresolved disambiguation problem escalated 20 of 24 on-site-search orders, which
    is not a rare shape — it is what a search box is.

    *Which one they meant* is only a question when the two answers differ. So the values
    are compared with the attribute's own operator, which is the same treatment two fields
    of evidence have always had, and it is run **both directions**: half a comparison is
    containment rather than agreement, and a $150 ceiling "satisfied" by a $120 claim one
    way round would silently drop the tighter limit the shopper actually set. Two values
    of different types and two bounds never compare SATISFIED, so they take the existing
    conflict path without needing a case of their own.

    The survivor is the strongest channel's, so the record attributes the constraint to
    the half that needs no extraction step to defend. Both statements stay in
    `request_constraints`; only the comparison collapses, because the shopper having said
    it twice is the strongest thing about this class of order.
    """
    ranked = sorted(claims, key=lambda c: (_CHANNEL_RANK[c.channel], c.model_dump_json()))
    first = ranked[0]
    operator = _operator_for(first.value)
    if operator is None:
        return None
    for other in ranked[1:]:
        if type(other.value) is not type(first.value):
            return None
        if not (_agrees(operator, first, other, spec)
                and _agrees(operator, other, first, spec)):
            return None
    return first


def _agrees(operator, claim: Claim, other: Claim, spec: AttributeSpec) -> bool:
    """One claim read as though it were the evidence the other is checked against.

    The mirror of the peer loop below, which reads one piece of evidence as a claim. The
    wrapper never leaves this function: `certainty` sets a confidence ceiling we do not
    read, and `liability` is about who owes a remedy for a *catalogue* statement, which is
    not what this is.
    """
    stated = Evidence(attribute=spec.name, value=other.value,
                      field_name=other.channel.value, certainty=Certainty.EXACT,
                      liability=Liability.UNATTRIBUTED)
    return operator(claim, stated, spec).support is Support.SATISFIED


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
        from approv.algebra.quantity import _render
        return _render(value)
    return str(value)


def run_checks(
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    schema: CategorySchema,
    specs: dict[str, AttributeSpec] | None = None,
) -> tuple[Finding, ...]:
    """Check every attribute the schema defines, and report all outcomes.

    Attributes with no claim and no evidence are silent on both sides and produce
    nothing. Everything else produces a finding, including the cases where no comparison
    could be run — a gap we can name is worth more than a gap we omit.
    """
    names = [s.name for s in schema.attributes]
    if len(set(names)) != len(names) or not schema.floor <= set(names):
        raise ValueError("schema has duplicate attributes or an undefined floor")
    # `specs` is the schema with criticality resolved for this transaction. The operators
    # read `spec.criticality` and are untouched by it: per-transaction criticality is a
    # change to how the schema is applied, not to how anything compares.
    if specs is not None:
        if set(specs) != set(names):
            raise ValueError("resolved specs must cover exactly the schema's attributes")
        schema = schema.model_copy(update={
            "attributes": tuple(specs[name] for name in names)})
    profiles = {p.field_name: p for p in schema.field_profiles}
    if len(profiles) != len(schema.field_profiles):
        raise ValueError("duplicate field profiles")
    findings: list[Finding] = []
    for item in sorted({c.attribute for c in claims} - set(names)):
        spec = AttributeSpec(name=item, dimension=Dimension.NOMINAL, criticality=Criticality.HARD)
        findings.append(_bare(spec, Support.UNSTATED, Resolution.RESTATE_CLAIM,
                              ReasonCode.UNKNOWN_ATTRIBUTE))
    normalized = []
    untrusted = set()
    for item in evidence:
        profile = profiles.get(item.field_name)
        if profile is None or (profile.attributes and item.attribute not in profile.attributes):
            untrusted.add(item.attribute)
            continue
        # Profiles are ceilings, not permission to promote inferred content.
        certainty = max((item.certainty, profile.certainty), key=_CERTAINTY_RANK.get)
        normalized.append(item.model_copy(update={"certainty": certainty,
            "liability": profile.liability, "is_advice": item.is_advice or profile.is_advice}))
    evidence = tuple(normalized)


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

        if len(attribute_claims) > 1:
            corroborated = _corroborated(attribute_claims, spec)
            if corroborated is None:
                for duplicate in attribute_claims:
                    findings.append(_bare(spec, Support.UNSTATED, Resolution.RESTATE_CLAIM,
                                          ReasonCode.DUPLICATE_CLAIM, claim=duplicate))
                continue
            attribute_claims = [corroborated]
        claim = attribute_claims[0]
        if spec.name in untrusted:
            findings.append(_bare(spec, Support.UNSTATED, Resolution.FIND_BETTER_SOURCE,
                                  ReasonCode.UNTRUSTED_SOURCE, claim=claim))
        advice = [e for e in attribute_evidence if e.is_advice]
        attribute_evidence = [e for e in attribute_evidence if not e.is_advice]
        if advice:
            findings.append(_bare(spec, Support.UNSTATED, Resolution.FIND_BETTER_SOURCE,
                                  ReasonCode.ADVICE_ONLY, claim=claim))


        if not attribute_evidence:
            if advice or spec.name in untrusted:
                continue
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
        ranked = sorted(attribute_evidence, key=lambda e: (_CERTAINTY_RANK[e.certainty], e.field_name, e.model_dump_json()))
        best = ranked[0]

        operator = _operator_for(claim.value)
        if operator is None or (not isinstance(claim.value, Bound) and not isinstance(best.value, type(claim.value))):
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

        # Compare sources to each other, not just their verdict against the claim.
        conflict = False
        for i, left in enumerate(ranked):
            for right in ranked[i + 1:]:
                peer = _operator_for(left.value)
                if peer is None or type(left.value) is not type(right.value):
                    conflict = True
                    continue
                peer_claim = Claim(attribute=spec.name, value=left.value, channel=claim.channel)
                result = peer(peer_claim, right, spec)
                if result.support is Support.VIOLATED:
                    conflict = True
        if conflict:
            finding = finding.model_copy(update={
                "support": Support.UNSTATED, "confidence": 0.0,
                "reasons": tuple(dict.fromkeys((*finding.reasons, ReasonCode.FIELD_CONFLICT))),
                "evidence": tuple(ranked),
                "repair": Repair(resolution=Resolution.FIND_BETTER_SOURCE,
                                 attribute=spec.name, claimed=_surface(claim)),
            })

        findings.append(finding)

    return tuple(findings)


def dimension_of(spec: AttributeSpec) -> Dimension:
    return spec.dimension


def check_constraints(constraints: tuple[Constraint, ...], evidence: tuple[Evidence, ...],
                      schema: CategorySchema, *,
                      returns=None, superseded=frozenset(),
                      per_transaction: bool = True) -> tuple[Finding, ...]:
    """Compare fixed recorded constraints to inventory. No purchase decision.

    Criticality is resolved per transaction from the shopper's own phrasing, the
    merchant's variant axes and their return history — see `approv.criticality`. Pass
    `per_transaction=False` to fall back to the schema's static constants, which exists
    for comparing against the old behaviour and not for production.
    """
    from approv.criticality import applied
    specs = (applied(schema, constraints, returns=returns, superseded=superseded)
             if per_transaction else None)
    claims = tuple(Claim(attribute=c.attribute, value=c.value, channel=c.channel,
                         raw_text=c.raw_text) for c in constraints)
    findings = run_checks(claims, evidence, schema, specs)
    return tuple(f.model_copy(update={"check": CheckKind.SATISFACTION,
                 "constraint": _constraint_for(f, constraints)}) for f in findings)


def _constraint_for(finding: Finding, constraints: tuple[Constraint, ...]) -> Constraint | None:
    """The constraint this finding is about, when one attribute was stated more than once.

    Matched through the finding's own claim rather than by attribute alone, so a collapsed
    corroboration (DR 0025) names the statement it was decided from and a disagreement
    names each of its own. Falling back to the last is the behaviour every single-statement
    attribute has always had.
    """
    same = [c for c in constraints if c.attribute == finding.attribute]
    if not same:
        return None
    if finding.claim is not None:
        for constraint in same:
            if constraint.channel is finding.claim.channel                     and constraint.value == finding.claim.value:
                return constraint
    return same[-1]
