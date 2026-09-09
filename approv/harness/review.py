"""Candidate evidence review. No ranking, retrieval, labels or purchase decisions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from approv.algebra.feedback import _ACTION, explain_all
from approv.algebra.runner import check_constraints
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, CheckKind, Claim, Count,
    Criticality, Dimension, Evidence, Finding, Liability, Money, Quantity,
    ReasonCode, Resolution, Support,
)

if TYPE_CHECKING:
    from approv.harness.shopping import Product, ShoppingCase

VERSION = "candidate-review-v1"


def check_shelf(case: ShoppingCase, products: tuple[Product, ...],
                schema: CategorySchema, *, units: int = 1,
                proposed: str | None = None) -> dict:
    """Assess only the supplied shelf; preserve order and evidence for every item.

    `proposed` is the agent's standing answer, if it has one, so the report can say
    whether that answer is already among the supported candidates. It is used for that
    sentence and nothing else: it never reorders the shelf, never changes a status, and
    an id that is not on the shelf is simply reported as not being on it.
    """
    if type(units) is not int or not 1 <= units <= 100:
        raise ValueError("sale units must be an integer from 1 to 100")
    if len({p.id for p in products}) != len(products):
        raise ValueError("duplicate candidate IDs")
    assessments = []
    for product in products:
        report = check_product(case, product, schema, units)
        findings = tuple(Finding.model_validate(f) for f in report["findings"])
        required = tuple(f for f in findings
                         if f.criticality in (Criticality.HARD, Criticality.BOUND))
        contradicted = [f.attribute for f in required if f.support is Support.VIOLATED]
        unresolved = [f.attribute for f in required
                      if f.support is Support.UNSTATED or
                      ReasonCode.LOW_CERTAINTY_SOURCE in f.reasons or
                      ReasonCode.LOW_LIABILITY_SOURCE in f.reasons]
        if contradicted:
            status = "contradicted"
        elif unresolved:
            status = "unresolved"
        elif required:
            status = "supported"
        else:
            status = "unassessed"
        assessments.append({"product_id": product.id, "status": status,
                            "contradicted": contradicted, "unresolved": unresolved,
                            **report})
    groups = {status: [a["product_id"] for a in assessments if a["status"] == status]
              for status in ("supported", "contradicted", "unresolved", "unassessed")}
    checked = sorted({c.attribute for c in case.constraints} | schema.floor |
                     ({"sale_units"} if case.requested_units is not None else set()))
    # Ordering is the finding of the 10 September study, not presentation taste. The
    # previous shape led with three lines of scope, buried the satisfying candidates in
    # the middle as a field-status label, and closed on the bare count of candidates that
    # contradict something. On a shelf where the check has isolated the one right answer
    # out of twenty-five, that closing line reads "24 of these are wrong" — a success
    # rendered as a failure statistic, and the last thing the agent reads before
    # answering. It abstained on all five such cases. So: the count is stated as the work
    # the check did, the caveats come before the move rather than after it, and the
    # report ends on the action.
    ruled_out = len(groups["contradicted"])
    lines = [f"Retrieved shelf: {len(products)} candidates, {units} sale unit(s) each; "
             f"quantity scope: {case.quantity_scope}.",
             "Checked fields: " + (", ".join(checked) or "none") + "."]
    if groups["supported"]:
        lines.append(f"{len(groups['supported'])} of {len(products)} candidates satisfy every "
                     f"recorded required field" +
                     (f"; the check ruled out {ruled_out}." if ruled_out else "."))
    else:
        lines.append(f"Candidates with contradicted requirements: {ruled_out}.")
    pending = [a["product_id"] + " (" + ", ".join(a["unresolved"]) + ")"
               for a in assessments if a["status"] == "unresolved"]
    if pending:
        lines.append("Unresolved; inspect evidence: " + "; ".join(pending) + ".")
    if groups["unassessed"]:
        lines.append("No required fields established: " + ", ".join(groups["unassessed"]) + ".")
    all_contradicted = bool(assessments) and ruled_out == len(assessments)
    if case.interpretation_notes:
        lines.append("Unverified request details: " + "; ".join(case.interpretation_notes))
    # The caveat sits here, ahead of the move, because it qualifies the move. Trailing it
    # after the supported list made "OK: availability, size." read as "...but we could not
    # confirm this is the product you asked for", which is true of every candidate equally
    # and so cannot help choose between them.
    lines.append("This checks recorded fields only, and does not confirm product identity. "
                 "Check the original request before selecting.")
    if all_contradicted:
        lines.append("Every retrieved candidate contradicts a required field at this sale "
                     "count. Do not substitute from this shelf at this count. Search further "
                     "if possible, otherwise abstain. Other counts and unseen inventory "
                     "have not been ruled out.")
    elif groups["supported"]:
        if proposed is not None:
            lines.append(f"Your earlier answer {proposed} is "
                         + ("already among the candidates below."
                            if proposed in groups["supported"] else
                            "not among the candidates below."))
        # The imperative requires a complete reading of the request, and an
        # interpretation note is the extractor saying it did not get one. Measured on
        # shopper-49, an unfillable held-out case: the request said "do not substitute a
        # different colour or size", the extractor could not encode the colour, and one
        # candidate then satisfied every field that remained. Under the old wording the
        # agent read a buried status label and correctly declined. "Select one of these"
        # would have told it to buy. §2.3 is the rule that settles it — an unknown never
        # authorises, and not knowing what we were asked is the worst unknown available,
        # strictly worse than not knowing something about the product.
        if case.interpretation_notes:
            lines.append("Fields that were checked are satisfied by: "
                         + ", ".join(groups["supported"]) + ". The unverified request "
                         "details above were not checked. Resolve them against the "
                         "original request before selecting, and abstain if they cannot "
                         "be met.")
        else:
            lines.append(_ACTION[Resolution.SELECT_FROM_SUPPORTED].rstrip(".")
                         + ": " + ", ".join(groups["supported"]) + ".")
    return {"version": VERSION, "scope": "retrieved_candidates_at_assessed_count",
            "assessed_sale_units": units, "quantity_scope": case.quantity_scope,
            "checked_attributes": checked, "interpretation_notes": list(case.interpretation_notes),
            "groups": groups, "all_contradicted": all_contradicted,
            "candidates": assessments, "feedback": "\n".join(lines)}


def check_product(case: ShoppingCase, product: Product, schema: CategorySchema,
                  units: int = 1) -> dict:
    """Compare one exact variant/count against the fixed interpreted request."""
    if type(units) is not int or not 1 <= units <= 100:
        raise ValueError("sale units must be an integer from 1 to 100")
    evidence = []
    for item in product.evidence:
        value = item.value
        if case.quantity_scope == "cart_total":
            if item.attribute in ("net_weight", "net_volume") and isinstance(value, Quantity):
                value = value.model_copy(update={"magnitude": value.magnitude * units})
            elif item.attribute == "price" and isinstance(value, Money):
                value = value.model_copy(update={"amount": value.amount * units})
            elif item.attribute == "pack_count" and isinstance(value, Count):
                value = value.model_copy(update={"n": value.n * units})
        evidence.append(item.model_copy(update={"value": value}))
    findings = check_constraints(case.constraints, tuple(evidence), schema)
    # NO_CLAIM on unrelated optional fields is diagnostic noise for this task.
    requested = {c.attribute for c in case.constraints} | schema.floor
    findings = tuple(f for f in findings if f.attribute in requested)
    if case.requested_units is not None:
        from approv.algebra.count import compare_count
        assertion = Claim(attribute="sale_units", value=Count(n=case.requested_units),
                          channel=Channel.TOOL_ARGUMENT)
        count_finding = compare_count(assertion, Evidence(attribute="sale_units", value=Count(n=units),
            field_name="cart.units", liability=Liability.UNATTRIBUTED, certainty=Certainty.EXACT),
            AttributeSpec(name="sale_units", dimension=Dimension.COUNT, criticality=Criticality.HARD))
        findings += (count_finding.model_copy(update={"check": CheckKind.CONSISTENCY}),)
    return {"findings": [f.model_dump(mode="json") for f in findings],
            "feedback": explain_all(findings) + ("\nUnverified request details: " + "; ".join(case.interpretation_notes) if case.interpretation_notes else ""), "assessed_sale_units": units,
            "quantity_scope": case.quantity_scope}

