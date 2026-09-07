"""Turning findings into something an agent can act on.

A verdict an agent cannot act on is worth very little. Coding agents got good because a
compiler says *which line* and *what is wrong*, not because it says "no". Approv should
behave the same way: every non-clean outcome names the move that resolves it.

This module is the only place wording lives. The signed record holds fields (§2.7); the
sentence is rendered from those fields at the boundary and never stored. That means the
wording can change without invalidating a single existing receipt, and two receipts with
identical fields are byte-identical regardless of how we phrase things this month.

Rendering never invents. Every value in the output came from the Finding.
"""

from __future__ import annotations

from approv.types.core import Finding, ReasonCode, Repair, Resolution, Support

_WHY: dict[ReasonCode, str] = {
    ReasonCode.INCOMMENSURABLE: (
        "the claim and the listing measure different things, so no comparison is possible"
    ),
    ReasonCode.UNRESOLVED_TERM: "the listing uses a unit we cannot compare",
    ReasonCode.LOW_CERTAINTY_SOURCE: (
        "the value was read from free text rather than a dedicated field, "
        "so it cannot clear a hard constraint on its own"
    ),
    ReasonCode.WITHIN_TOLERANCE: "the values differ slightly but within the allowed margin",
    ReasonCode.PRODUCT_SILENT: "the listing does not publish this attribute",
    ReasonCode.NO_CLAIM: "no claim was made about this attribute, so nothing was checked",
    ReasonCode.FIELD_CONFLICT: "two fields on the listing disagree with each other",
    ReasonCode.ADVICE_CONTRADICTS: (
        "seller guidance contradicts the structured field; advice cannot override a fact"
    ),
    ReasonCode.FLOOR_NOT_MET: "this category cannot be verified without this attribute",
    ReasonCode.LOW_LIABILITY_SOURCE: (
        "the value came from text nobody is answerable for, such as a review"
    ),
    ReasonCode.AGENT_SELF_CONTRADICTION: (
        "this contradicts what was asked for earlier in the same session"
    ),
    ReasonCode.UNATTESTED_COUNTERPARTY: "one side of the record was not signed",
}

_ACTION: dict[Resolution, str] = {
    Resolution.NONE_NEEDED: "No action needed.",
    Resolution.PICK_DIFFERENT_PRODUCT: "Choose a different product.",
    Resolution.RESTATE_CLAIM: "Restate the claim in terms the listing publishes.",
    Resolution.FIND_BETTER_SOURCE: (
        "Confirm this from a structured field, or mark it unverified."
    ),
    Resolution.STATE_THE_ATTRIBUTE: "State this attribute explicitly so it can be checked.",
    Resolution.NOT_RESOLVABLE: (
        "Nothing can fix this — the listing does not carry the data. Do not retry."
    ),
}

_HEADLINE: dict[Support, str] = {
    Support.SATISFIED: "OK",
    Support.VIOLATED: "MISMATCH",
    Support.UNSTATED: "UNVERIFIED",
}


def _observed_clause(repair: Repair) -> str:
    if repair.observed is None:
        return "the listing is silent"
    if repair.observed_field is None:
        return f"the listing says {repair.observed}"
    return f"the listing says {repair.observed} (field: {repair.observed_field})"


def explain(finding: Finding) -> str:
    """Render one finding as a single line an agent can read and act on.

    Shape: `STATUS attribute: claimed X, <observed>. <why>. <action>`
    """
    parts = [f"{_HEADLINE[finding.support]} {finding.attribute}:"]

    repair = finding.repair
    if repair is not None:
        detail = []
        if repair.claimed is not None:
            detail.append(f"claimed {repair.claimed}")
        detail.append(_observed_clause(repair))
        parts.append(", ".join(detail) + ".")

    # Every reason, not only the first. An agent that fixes one problem and resubmits
    # into a second one has wasted a round trip, and round trips are the cost model.
    for reason in finding.reasons:
        if reason in _WHY:
            parts.append(_WHY[reason].capitalize() + ".")

    if repair is not None:
        parts.append(_ACTION[repair.resolution])

    return " ".join(parts)


def explain_all(findings: tuple[Finding, ...]) -> str:
    """Render every finding, worst first, so the agent sees the full picture at once.

    Ordering is deliberate: an agent given one problem at a time will fix them one at a
    time. Mismatches come before unverified because a mismatch is actionable with
    certainty and an unverified attribute may not be actionable at all.
    """
    order = {Support.VIOLATED: 0, Support.UNSTATED: 1, Support.SATISFIED: 2}
    ranked = sorted(findings, key=lambda f: (order[f.support], f.attribute))
    return "\n".join(explain(f) for f in ranked)
