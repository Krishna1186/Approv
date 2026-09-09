"""Findings in, one decision out. Hand-checkable, deterministic, no I/O.

DR 0002 and CLAUDE.md §4.1 fix the boundary this module sits behind: it imports
`approv.types` and nothing else from the project. It never calls a model, never reads a
file, and never sees a product. If it ever needs any of those, the central claim of the
company — that a deterministic engine authorises and a model only describes — has become
false, and the import that broke it is the evidence.

The rules are few on purpose. A merchant's engineer has to be able to read them in one
sitting and say whether they agree, and an underwriter has to be able to point at the one
that fired.
"""

from approv.types.core import Criticality, Decision, Finding, Support

VERSION = "evaluator-v1"

# Certainty ceilings mean a value read from prose cannot clear a HARD constraint on its
# own (DR 0016 §4). This is the level at which a HARD attribute counts as established.
HARD_CONFIDENCE_FLOOR = 0.95


def decide(findings: tuple[Finding, ...], *, floor_met: bool = True) -> tuple[Decision, tuple[str, ...]]:
    """Return the decision and the attributes that drove it.

    Three rules, in order:

    1. A contradicted HARD or BOUND attribute refuses. The listing itself says the request
       is not met, and no amount of other agreement repairs that.
    2. Anything unresolved on a HARD or BOUND attribute confirms — silence, a source too
       weak to clear the bar, a floor the category requires and the request never stated.
       §2.3: unknown never authorises. This is the rule that makes the record
       adjudicable, because it separates "we checked and it was wrong" from "nobody ever
       said", and only the first is anyone's fault.
    3. Otherwise allow.

    SOFT and COSMETIC attributes never block. They are recorded for the receipt, and a
    shopper who cares about them can say so, which promotes them in the schema rather
    than here.

    Returning the reasons alongside the decision is not decoration. A refusal an operator
    cannot attribute to a named attribute is one they will switch off within a week.
    """
    blocking = (Criticality.HARD, Criticality.BOUND)

    violated = tuple(f.attribute for f in findings
                     if f.support is Support.VIOLATED and f.criticality in blocking)
    if violated:
        return Decision.REFUSE, violated

    unresolved = tuple(f.attribute for f in findings
                       if f.criticality in blocking
                       and (f.support is Support.UNSTATED
                            or f.confidence < HARD_CONFIDENCE_FLOOR))
    if not floor_met:
        return Decision.CONFIRM, unresolved or ("verification_floor",)
    if unresolved:
        return Decision.CONFIRM, unresolved

    return Decision.ALLOW, ()
