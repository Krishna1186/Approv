"""The dispute artifact: a ComparisonRecord arranged the way a returns desk reads it.

DR 0020 makes the record a dispute artifact whose primary forum is the merchant's own
returns desk. Until now it was JSON, which means the company's central claim — that a
merchant settles a refund with this — had never been demonstrated end to end. A returns
agent cannot be handed a signed blob and told the answer is inside it.

**Nothing here decides anything and nothing here computes coverage.** The decision and
the per-finding coverage class are read off the signed record exactly as they were
sealed. Recomputing either would mean the printed document could disagree with the signed
one, and the printed document is the half a human acts on — so the disagreement would be
invisible until a dispute. Where the record is silent this says so in words rather than
filling the gap: `coverage` absent is printed as NOT recorded, not derived by calling
`criticality.coverage_of` behind the reader's back.

Two rules govern every line of output.

**Never overstate.** This may be read by someone deciding whether to refuse a real
customer's refund. An `allow` is not "everything matched": a preference can be
contradicted under one. Coverage is not a promise to pay; PRD §6 leaves the contract
unanswered, so the document names the class and says where the promise actually lives.

**Never omit.** An absent row reads as an absence of problems. Missing evidence, a
missing order line, a missing coverage class and a missing signature are each printed as
their own row, saying what is missing and what that costs.

The split that carries the liability story is `unread` against `completeness`. Both look
like an absent requirement from inside the engine and they attribute to opposite parties:
silence is nobody's fault and buys no coverage, whereas a requirement we failed to read
is **ours**. They are two sections here, worded so they cannot be read as the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from approv.artifact import language as lang
from approv.types.core import (
    CheckKind, ComparisonRecord, Completion, Criticality, Decision, Finding, Support,
)

VERSION = "artifact-v1"

# The record's own words for the pseudo-attribute `evaluator.decide` returns when the
# verification floor was not met. It is not an attribute and must not be printed as one.
FLOOR_REASON = "verification_floor"

# Severity of a line in the read-this-first block. STOP means the document cannot carry
# the weight a dispute would put on it; WARN means it can, with something read alongside.
STOP = "stop"
WARN = "warn"


@dataclass(frozen=True)
class Row:
    """One labelled fact. `missing` prints the row and says the value is absent."""

    label: str
    value: str
    missing: bool = False
    note: str | None = None


@dataclass(frozen=True)
class Alert:
    severity: str
    text: str


@dataclass(frozen=True)
class Requirement:
    """One requirement as Approv read it, next to the words it was read from."""

    attribute: str
    value: str
    quote: str | None
    provenance: str
    source: str | None


@dataclass(frozen=True)
class AttributeFinding:
    """One comparison, arranged for a reader who has never seen the schema."""

    attribute: str
    support: Support
    verdict: str
    weight: str
    weight_means: str
    coverage: str
    coverage_label: str
    coverage_means: str
    blocking: bool = False
    asked_for: str | None = None
    agent_said: str | None = None
    catalogue: tuple[str, ...] = ()
    catalogue_missing: bool = False
    notes: tuple[str, ...] = ()
    drove_decision: bool = False


@dataclass(frozen=True)
class Document:
    """Everything the renderers print, and nothing about how it is printed."""

    record: ComparisonRecord
    headline: str
    summary: str
    means: str
    does_not_mean: str
    alerts: tuple[Alert, ...] = ()
    identity: tuple[Row, ...] = ()
    request_text: str = ""
    request_text_missing: bool = False
    request_text_note: str | None = None
    requirements: tuple[Requirement, ...] = ()
    unread: tuple[str, ...] = ()
    never_asked: tuple[str, ...] = ()
    order: tuple[Row, ...] = ()
    order_missing: bool = False
    product: tuple[Row, ...] = ()
    findings: tuple[AttributeFinding, ...] = ()
    coverage_buckets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    integrity: tuple[Row, ...] = ()
    signed: bool = False
    # DR 0023: whether the channel this order arrived through earns coverage at all, and
    # why not. A per-finding class means nothing over a channel that earns none, and this
    # document is where the two would otherwise contradict each other in front of a reader.
    channel_covered: bool = True
    channel_notes: tuple[str, ...] = ()


# --------------------------------------------------------------------------------------
# Coverage, read rather than recomputed
# --------------------------------------------------------------------------------------


def coverage_classes(record: ComparisonRecord) -> tuple[str, ...]:
    """The coverage class of each finding, aligned by index, or UNRECORDED throughout.

    `ComparisonRecord.coverage` is aligned with `findings` by position, so a length
    mismatch is not a partial answer to be salvaged — it means the alignment is unknown,
    and a coverage class attached to the wrong attribute is worse than none, because it
    would be read as a promise about something else. One misalignment therefore
    invalidates the whole column rather than the rows past the end.

    A class this document has no wording for is UNRECORDED for the same reason: printing
    a token we cannot explain asserts an authority we do not have.
    """
    if len(record.coverage) != len(record.findings):
        return (lang.UNRECORDED,) * len(record.findings)
    return tuple(c if c in lang.COVERAGE_LABEL else lang.UNRECORDED for c in record.coverage)


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------


def _evidence_lines(finding: Finding) -> tuple[tuple[str, ...], bool]:
    """What the merchant's own catalogue said, with the field it came from.

    The field name is not decoration. DR 0016's question is *from which field*, and a
    value the merchant publishes in a dedicated field and a value parsed out of prose
    carry different weight in a dispute — the first is theirs, the second is our reading
    of theirs.
    """
    lines = []
    for item in finding.evidence:
        source = "the field %s, %s, %s" % (
            item.field_name, lang.LIABILITY[item.liability], lang.CERTAINTY[item.certainty])
        if item.is_advice:
            source += ", seller guidance rather than a published fact"
        lines.append("%s - from %s" % (lang.value(item.value), source))
    if lines:
        return tuple(lines), False
    return ("The catalogue published no value Approv could read for this attribute.",), True


def _finding_notes(finding: Finding, drove: bool) -> tuple[str, ...]:
    notes = [lang.CHECK[finding.check]]
    if finding.constraint is not None and finding.constraint.raw_text:
        notes.append('Read from the request: "%s"' % finding.constraint.raw_text.strip())
    notes.extend(lang.REASON[code] for code in finding.reasons if code in lang.REASON)
    if drove:
        notes.append("This attribute is one the decision turned on.")
    return tuple(notes)


def _asked_and_said(finding: Finding) -> tuple[str | None, str | None]:
    """What the request required, and separately what the agent asserted — if it did.

    On a SATISFACTION check the finding's `claim` is not something the agent said about
    the product: `algebra.runner.check_constraints` manufactures one from the constraint
    so the operators have a uniform shape to compare. Printing that as "the agent said
    the product is X" would put words in the agent's mouth on a document that settles a
    refund, and it would read as corroboration — two parties agreeing — when there is
    only one statement in the record. `algebra.feedback` draws the same line with
    `_demand_word`; this one has to be firmer, because a returns desk cannot check.
    """
    if finding.check is CheckKind.SATISFACTION:
        stated = finding.constraint or finding.claim
        return (lang.value(stated.value) if stated is not None else None), None
    asked = lang.value(finding.constraint.value) if finding.constraint is not None else None
    said = lang.value(finding.claim.value) if finding.claim is not None else None
    return asked, said


_ORDER = {Support.VIOLATED: 0, Support.UNSTATED: 1, Support.SATISFIED: 2}


def attribute_findings(record: ComparisonRecord) -> tuple[AttributeFinding, ...]:
    """Every finding, worst first, each carrying its own coverage class.

    Ordering is presentation and nothing is dropped by it: a reader with a minute spends
    it on what was not met, and a contradicted blocking attribute is the one that decides
    a refund. Satisfied attributes stay on the page because a record that printed only
    problems would read as a list of accusations rather than as evidence.
    """
    classes = coverage_classes(record)
    drove = set(record.decision_reasons)
    rows = []
    for finding, covered in zip(record.findings, classes):
        catalogue, missing = _evidence_lines(finding)
        asked, said = _asked_and_said(finding)
        rows.append(AttributeFinding(
            attribute=lang.attribute(finding.attribute),
            support=finding.support,
            verdict=lang.VERDICT[finding.support],
            weight=lang.WEIGHT[finding.criticality],
            weight_means=lang.WEIGHT_MEANS[finding.criticality],
            blocking=finding.criticality in (Criticality.HARD, Criticality.BOUND),
            coverage=covered,
            coverage_label=lang.COVERAGE_LABEL[covered],
            coverage_means=lang.COVERAGE_MEANS[covered],
            asked_for=asked,
            agent_said=said,
            catalogue=catalogue,
            catalogue_missing=missing,
            notes=_finding_notes(finding, finding.attribute in drove),
            drove_decision=finding.attribute in drove,
        ))
    return tuple(sorted(
        rows, key=lambda r: (_ORDER[r.support], not r.blocking, r.attribute)))


def requirements(record: ComparisonRecord) -> tuple[Requirement, ...]:
    """The request as Approv read it — the second half of "in whose words"."""
    return tuple(
        Requirement(
            attribute=lang.attribute(c.attribute),
            value=lang.value(c.value),
            quote=(c.raw_text.strip() if c.raw_text else None),
            provenance=lang.provenance(c.channel),
            source=c.source,
        )
        for c in record.request_constraints
    )


NO_WORDING = (
    "No free-text wording accompanied this request. Every requirement below arrived as a "
    "field the agent filled in, so the line above is whatever the channel recorded rather "
    "than anything the requester typed."
)


def request_text_note(record: ComparisonRecord) -> str | None:
    """Whether the words above are anybody's words at all.

    A protocol call carries no wording, and `surface.verification` writes a note in its
    place so the field is not empty — but under a heading saying "in the requester's own
    words" that note reads as a quotation. Derived from the constraints rather than from
    the shape of that string: if not one requirement carried a quote, there was no
    wording, whatever the sentence above happens to say.
    """
    if record.request_constraints and not any(
            c.raw_text for c in record.request_constraints):
        return NO_WORDING
    return None


def order_rows(record: ComparisonRecord) -> tuple[Row, ...]:
    """What was sold, line by line. Absent fields are printed as absent.

    The line total is the only computed figure on this document and it is arithmetic on
    the two rows above it, labelled as such. A refund is denominated in money and a
    returns desk should not have to multiply.
    """
    line = record.order
    if line is None:
        return (Row("Order line", "", missing=True,
                    note="No order line is bound to this record, so it cannot show which "
                         "SKU, how many, or at what price anything was sold."),)
    total = Decimal(line.unit_price.amount) * line.quantity
    return (
        Row("Order", line.order_id),
        Row("Line", line.line_id or "", missing=line.line_id is None),
        Row("SKU", line.sku),
        Row("Variant", line.variant_id or "", missing=line.variant_id is None),
        Row("Quantity", str(line.quantity)),
        Row("Unit price", lang.value(line.unit_price)),
        Row("Line total", "%s %s" % (format(total, "f"), line.unit_price.currency),
            note="quantity multiplied by unit price"),
        Row("Availability at decision time", line.availability or "",
            missing=line.availability is None,
            note="the merchant's own term, recorded word for word. Approv decided "
                 "nothing on it."),
        Row("Checkout state", line.checkout_state or "",
            missing=line.checkout_state is None,
            note="the merchant's own term, recorded word for word."),
        Row("Catalogue version", line.catalogue_version or "",
            missing=line.catalogue_version is None),
    )


_TITLE_FIELDS = ("title", "name", "product_name")


def product_rows(record: ComparisonRecord) -> tuple[Row, ...]:
    """The product as the catalogue described it, marked as the merchant's own words.

    Catalogue text is untrusted (invariant 5), first-party included, so the title is
    attributed rather than asserted: this is what the merchant published, not something
    Approv establishes. It is here because a returns agent needs to recognise the item,
    and a bare product id does not let them.
    """
    title = next((str(record.product_snapshot[f]) for f in _TITLE_FIELDS
                  if isinstance(record.product_snapshot.get(f), (str, int, float))), None)
    return (
        Row("Product", record.product_id),
        Row("As the catalogue described it", title or "", missing=title is None,
            note="the merchant's own catalogue text, quoted rather than verified."),
        Row("Catalogue snapshot digest", record.snapshot_hash,
            note="the digest of the catalogue record as it stood at decision time."),
    )


def identity_rows(record: ComparisonRecord) -> tuple[Row, ...]:
    return (
        Row("Decided at", record.timestamp.isoformat()),
        Row("Merchant", record.merchant_id or "", missing=record.merchant_id is None),
        Row("Agent", record.agent_id or "", missing=record.agent_id is None,
            note="the agent that placed the order, where it identified itself."),
        Row("Correlation id", record.correlation_id,
            note="the key that joins this record to the agent's half of it."),
        Row("Category", "%s, version %s" % (record.category_id, record.category_version)),
    )


def integrity_rows(record: ComparisonRecord) -> tuple[Row, ...]:
    signed = bool(record.hash and record.signature)
    rows = [
        Row("Signed", "yes" if signed else "no", missing=not signed,
            note=None if signed else "An unsigned record cannot be shown to be unaltered."),
        Row("Record digest", record.hash or "", missing=record.hash is None),
        Row("Signature", record.signature or "", missing=record.signature is None),
    ]
    if record.prev_hash:
        rows.append(Row("Follows record", record.prev_hash,
                        note="the digest of the record sealed before this one."))
    elif signed:
        rows.append(Row("Follows record",
                        "none - this is the first record in its chain"))
    else:
        rows.append(Row("Follows record", "", missing=True))
    rows.extend((
        # Which published key, not merely that one exists. Keys rotate, a receipt stays
        # verifiable under the key that signed it, and a reader handed "Approv's public
        # key" during a later rotation would check this record against the wrong one and
        # conclude it was forged.
        Row("Signing key", record.key_id or "", missing=record.key_id is None,
            note="the published Approv key that signed this record."),
        Row("Signature format", record.signature_version),
        # Printed on every record, including the ordinary one. "Completed" is a fact a
        # reader needs stated rather than inferred from the absence of a warning.
        Row("Verification", "ran to a conclusion"
            if record.completion is Completion.COMPLETED
            else "did NOT complete: " + record.completion.value.replace("_", " "),
            missing=record.completion is not Completion.COMPLETED,
            note=record.completion_detail),
        Row("Who signed which half", lang.ATTESTATION[record.attestation]),
        Row("Engine version", record.evaluator_version),
        Row("Reading version", "%s, prompt %s" % (record.model_version,
                                                  record.prompt_version)),
    ))
    return tuple(rows)


def alerts(record: ComparisonRecord) -> tuple[Alert, ...]:
    """What a reader has to know before reading anything else.

    Each line is a limit on what this document can be used for, and each is derived from
    a field being absent or from the decision's own semantics. None of them is a
    judgement about the order.
    """
    out: list[Alert] = []
    if not (record.hash and record.signature):
        out.append(Alert(STOP,
                         "This record carries no signature. Nothing in it can be shown "
                         "to be unaltered, so it cannot carry a dispute on its own."))
    if record.order is None:
        out.append(Alert(STOP,
                         "No order line is bound to this record. It is a comparison "
                         "about a product, not a verification of a purchase."))
    if not record.request_constraints:
        out.append(Alert(STOP,
                         "No requirement was recovered from the request, so this record "
                         "cannot show that the order matched anything that was asked "
                         "for."))
    if record.completion is not Completion.COMPLETED:
        out.append(Alert(STOP,
                         "This verification did not run to a conclusion (%s). Its "
                         "decision is a fact about Approv's own availability, not a "
                         "judgement about this order, and nothing on it is covered."
                         % record.completion.value.replace("_", " ")))
    if not record.covered:
        out.append(Alert(STOP,
                         "The channel this order arrived through earns no coverage at "
                         "all. Whatever the per-attribute classes below say, this record "
                         "carries no promise about this order."))
    if record.findings and lang.UNRECORDED in coverage_classes(record):
        out.append(Alert(STOP,
                         "This record does not carry a usable coverage class for its "
                         "findings. Nothing in it may be presented to a customer as "
                         "covered."))
    if record.unread:
        out.append(Alert(WARN,
                         "Approv failed to read %d part(s) of the request. That is "
                         "Approv's failure, not the requester having said nothing, and "
                         "it is set out in full below." % len(record.unread)))
    # An `allow` with a contradicted preference is the case this document exists to keep
    # honest: the order was authorised and a requirement was still not met. Nothing in
    # the decision says so, because SOFT and COSMETIC attributes never block.
    soft_misses = sum(1 for f in record.findings
                      if f.support is Support.VIOLATED
                      and f.criticality in (Criticality.SOFT, Criticality.COSMETIC))
    if soft_misses:
        out.append(Alert(WARN,
                         "%d requirement(s) below were not met and were not treated as "
                         "blocking. Approv did not stop the order over them and does not "
                         "cover them." % soft_misses))
    if FLOOR_REASON in record.decision_reasons:
        out.append(Alert(WARN,
                         "Verification did not have what it needed to run in full. The "
                         "decision reflects that, not a fault in the order."))
    return tuple(out)


_TALLY_WORD = {Support.VIOLATED: "not met", Support.UNSTATED: "not checked",
               Support.SATISFIED: "met"}


def summary_line(record: ComparisonRecord) -> str:
    """One line of arithmetic over the rows below it, for the reader with a minute.

    It counts and nothing else — a document whose summary said anything the table did
    not would be the summary people read and the table nobody checked. Worst first, in
    the same order as the table, and a class with nothing in it is not printed rather
    than printed as a zero.
    """
    if not record.findings:
        return "No attribute was compared."
    supports = [
        "%d %s" % (sum(1 for f in record.findings if f.support is support),
                   _TALLY_WORD[support])
        for support in (Support.VIOLATED, Support.UNSTATED, Support.SATISFIED)
        if any(f.support is support for f in record.findings)
    ]
    classes = coverage_classes(record)
    covered = [
        "%d %s" % (classes.count(key), lang.COVERAGE_TALLY[key])
        for key in (lang.GUARANTEED, lang.REFUSED, lang.OUT_OF_COVERAGE, lang.UNRECORDED)
        if classes.count(key)
    ]
    return "%d requirement(s) compared: %s. Coverage: %s." % (
        len(record.findings), ", ".join(supports), ", ".join(covered))


def _buckets(record: ComparisonRecord) -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {key: [] for key in lang.COVERAGE_LABEL}
    for finding, covered in zip(record.findings, coverage_classes(record)):
        name = lang.attribute(finding.attribute)
        if name not in out[covered]:
            out[covered].append(name)
    return {key: tuple(names) for key, names in out.items()}


def build(record: ComparisonRecord) -> Document:
    """Arrange one signed record as a document. Reads the record and adds no facts."""
    decision: Decision = record.decision
    text = (record.request_text or "").strip()
    return Document(
        record=record,
        headline=lang.headline(decision, has_order=record.order is not None),
        summary=summary_line(record),
        means=lang.means(decision, has_order=record.order is not None),
        does_not_mean=lang.DECISION_DOES_NOT_MEAN[decision],
        alerts=alerts(record),
        identity=identity_rows(record),
        request_text=text,
        request_text_missing=not text,
        request_text_note=request_text_note(record),
        requirements=requirements(record),
        unread=tuple(record.unread),
        never_asked=tuple(lang.attribute(a) for a in record.completeness),
        order=order_rows(record),
        order_missing=record.order is None,
        product=product_rows(record),
        findings=attribute_findings(record),
        coverage_buckets=_buckets(record),
        integrity=integrity_rows(record),
        signed=bool(record.hash and record.signature),
        channel_covered=record.covered,
        channel_notes=tuple(record.coverage_notes),
    )
