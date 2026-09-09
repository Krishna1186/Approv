"""Money and typed numeric bounds; comparisons only, never authorization."""
from approv.algebra.quantity import _to_base, _CEILING_BY_CERTAINTY
from approv.types.core import (
    AttributeSpec, Bound, BoundOp, Certainty, CheckKind, Claim, Count, Dimension,
    Evidence, Finding, Money, Quantity, ReasonCode, Repair, Resolution, Support,
)


def _render_value(value) -> str:
    """Readable text for a money or bound value.

    str() on a pydantic model prints its repr, so a spending limit reached the agent as
    "kind='bound' op=<BoundOp.LTE: 'lte'> limit=Money(kind='money', amount=Decimal('68.00')
    ...)". Wording is the one thing this layer owes the caller, and internals are not it.
    """
    if isinstance(value, Money):
        return f"{value.amount:f} {value.currency}"
    if isinstance(value, Count):
        return str(value.n)
    if isinstance(value, Quantity):
        from approv.algebra.quantity import _render
        return _render(value)
    if isinstance(value, Bound):
        word = {BoundOp.LTE: "at most", BoundOp.LT: "under",
                BoundOp.GTE: "at least", BoundOp.GT: "over"}[value.op]
        return f"{word} {_render_value(value.limit)}"
    return str(value)


def compare_numeric(claim: Claim, evidence: Evidence, spec: AttributeSpec) -> Finding:
    limit = claim.value.limit if isinstance(claim.value, Bound) else claim.value
    actual = evidence.value
    if claim.attribute != evidence.attribute or claim.attribute != spec.name:
        raise ValueError("attribute mismatch")
    dimension = (limit.dimension if isinstance(limit, Quantity) else
                 Dimension.MONEY if isinstance(limit, Money) else Dimension.COUNT)
    if spec.dimension != dimension:
        raise ValueError("numeric value does not match attribute specification")
    reason = None
    if type(limit) is not type(actual):
        reason = ReasonCode.INCOMMENSURABLE
    elif isinstance(limit, Quantity):
        left, right = _to_base(limit), _to_base(actual)
        if limit.dimension != actual.dimension:
            reason = ReasonCode.INCOMMENSURABLE
        elif left is None or right is None:
            reason = ReasonCode.UNRESOLVED_TERM
    elif isinstance(limit, Money):
        left, right = limit.amount, actual.amount
        if limit.currency != actual.currency:
            reason = ReasonCode.INCOMMENSURABLE
    elif isinstance(limit, Count):
        left, right = limit.n, actual.n
    else:
        raise TypeError("numeric comparison requires money or a numeric bound")
    ceiling = _CEILING_BY_CERTAINTY[evidence.certainty]
    if reason:
        support, confidence, reasons = Support.UNSTATED, 0.0, (reason,)
    else:
        if isinstance(claim.value, Bound):
            matched = {BoundOp.LTE: right <= left, BoundOp.LT: right < left,
                       BoundOp.GTE: right >= left, BoundOp.GT: right > left}[claim.value.op]
        else:
            matched = left == right
        support = Support.SATISFIED if matched else Support.VIOLATED
        confidence = ceiling
        reasons = () if evidence.certainty is Certainty.EXACT else (ReasonCode.LOW_CERTAINTY_SOURCE,)
    resolution = (Resolution.FIND_BETTER_SOURCE if reasons else
                  Resolution.NONE_NEEDED if support is Support.SATISFIED else
                  Resolution.PICK_DIFFERENT_PRODUCT)
    return Finding(check=CheckKind.GROUNDING, attribute=spec.name, criticality=spec.criticality,
        support=support, confidence=confidence, ceiling=ceiling, reasons=reasons,
        claim=claim, evidence=(evidence,), repair=Repair(resolution=resolution,
        attribute=spec.name, claimed=_render_value(claim.value), observed=_render_value(actual),
        observed_field=evidence.field_name))
