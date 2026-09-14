"""The dispute artifact: what a returns desk reads, and what it must never be told.

Two kinds of test. The first kind checks that everything the record carries reaches the
page — an omitted row reads as an absence of problems, and this document is read by
someone deciding whether to refuse a real customer's refund. The second kind checks that
nothing reaches the page which the record does not support: no recomputed decision, no
coverage where the record recorded none, no words put in the agent's mouth.

The verification section is tested by running the instructions the document prints,
verbatim, against a really sealed record. Instructions that have never been executed are
a claim, not a procedure.
"""
import ast
import html.parser
import json
import re

import pytest

from approv.artifact import build, render_html, render_text
from approv.artifact import language as lang
from approv.artifact import signature
from approv.artifact.__main__ import main
from approv.artifact.document import FLOOR_REASON, STOP, coverage_classes
from approv.artifact.render import CLOSING, HEADINGS, NO_REQUIREMENTS, UNREAD_MEANS
from approv.receipts.chain import generate_key, public_key_hex, seal
from approv.receipts.record import build_record
from approv.types.core import (
    Attestation, AttributeSpec, Bound, BoundOp, CategorySchema, Certainty, Channel, Claim,
    ComparisonRecord, Completion, Constraint, Count, Criticality, Decision, Dimension,
    Evidence, FieldProfile, Finding, CheckKind, Liability, Money, OrderLine, Quantity,
    ReasonCode, Support, Term,
)

SCHEMA = CategorySchema(
    category_id="bedding", version="3",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="material", dimension=Dimension.NOMINAL,
                      criticality=Criticality.SOFT),
        AttributeSpec(name="weave", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     is_variant_axis=True, certainty=Certainty.EXACT,
                     liability=Liability.MERCHANT_GUARANTEED),
    ),
)

ORDER = OrderLine(order_id="ORD-10238", line_id="1", product_id="prod-1",
                  sku="SKU-TANDEM-KING-STONE", variant_id="var-9", quantity=2,
                  unit_price=Money(amount="118.00", currency="USD"),
                  availability="in stock", catalogue_version="2026-09-12T09:00Z")

SNAPSHOT = {"product_id": "prod-1", "title": "Tandem Stripe Duvet Cover"}


def flat(text):
    """Whitespace-normalised, so a sentence can be looked for without knowing the margin.

    The text rendering wraps to 88 columns and the HTML does not, so a constant that is
    genuinely on both pages appears verbatim in neither. Asserting on the flattened form
    tests what is said rather than where the line happened to break.
    """
    return " ".join(text.split())


def want(attribute, surface, quote=None, channel=Channel.AGENT_MESSAGE, source=None):
    return Constraint(attribute=attribute, value=Term(surface=surface), channel=channel,
                      raw_text=quote, source=source)


def saw(attribute, surface, field_name="variant.size",
        liability=Liability.MERCHANT_GUARANTEED, certainty=Certainty.EXACT):
    return Evidence(attribute=attribute, value=Term(surface=surface), field_name=field_name,
                    liability=liability, certainty=certainty)


def found(attribute, support, criticality, *, check=CheckKind.SATISFACTION,
          confidence=1.0, reasons=(), constraint=None, claim=None, evidence=()):
    return Finding(check=check, attribute=attribute, criticality=criticality,
                   support=support, confidence=confidence, ceiling=1.0, reasons=reasons,
                   constraint=constraint, claim=claim, evidence=evidence)


def record(*, findings=None, constraints=None, order=ORDER, unread=(), sign=True,
           request_text="I need a king size duvet cover in Frost.", **kw):
    """One record through the real assembly path, so coverage is the real mapping.

    `build_record` calls `evaluator.decide` and `criticality.coverage_of` itself. A
    fixture that set `decision` or `coverage` by hand would test the renderer against a
    record shape that cannot occur, and the fields this document is most dangerous about
    are exactly those two.
    """
    constraints = constraints if constraints is not None else (
        want("size", "King", "a king size duvet cover"),
        want("colour", "Frost", "in Frost"),
    )
    findings = findings if findings is not None else (
        found("size", Support.SATISFIED, Criticality.HARD, constraint=constraints[0],
              evidence=(saw("size", "King"),)),
        found("colour", Support.VIOLATED, Criticality.HARD, constraint=constraints[1],
              evidence=(saw("colour", "Stone", "variant.colour"),)),
    )
    built = build_record(
        correlation_id="corr-7f2a", request_text=request_text, constraints=constraints,
        findings=findings, schema=SCHEMA, product_id="prod-1",
        product_snapshot=kw.pop("snapshot", dict(SNAPSHOT)), snapshot_hash="d" * 64,
        model_version="extract-v6", prompt_version="prompt-v6", merchant_id="merchant-42",
        unread=unread, order=order, **kw)
    return seal(built, generate_key()) if sign else built


# --- nothing machine-readable reaches the page ------------------------------------------

ENUM_MAPS = (
    (lang.VERDICT, Support), (lang.DECISION_HEADLINE, Decision),
    (lang.DECISION_MEANS, Decision), (lang.DECISION_DOES_NOT_MEAN, Decision),
    (lang.WEIGHT, Criticality), (lang.WEIGHT_MEANS, Criticality),
    (lang.ATTESTATION, Attestation), (lang.CHECK, CheckKind),
    (lang.LIABILITY, Liability), (lang.CERTAINTY, Certainty),
    (lang.REASON, ReasonCode), (lang.BOUND_WORD, BoundOp),
)


@pytest.mark.parametrize("mapping,enum", ENUM_MAPS,
                         ids=[enum.__name__ + "-" + str(i) for i, (_, enum)
                              in enumerate(ENUM_MAPS)])
def test_every_member_of_every_printed_enum_has_words(mapping, enum):
    """A missing entry falls through to the enum's own value.

    `out_of_coverage` printed raw on a document that settles a refund is not a cosmetic
    defect: the reader either guesses what it means or stops trusting the page, and both
    are worse than the sentence we failed to write.
    """
    assert set(mapping) == set(enum), sorted(set(enum) - set(mapping))


def test_every_channel_and_coverage_class_has_words():
    assert set(lang.PROVENANCE) == {c.value for c in Channel}
    assert set(lang.COVERAGE_LABEL) == set(lang.COVERAGE_MEANS) == set(lang.COVERAGE_TALLY)


def machine_tokens():
    """Every enum value that is unmistakably a token rather than a word.

    Restricted to values carrying an underscore on purpose. `refuse` and `guaranteed` are
    ordinary English and appear in the prose legitimately, so a blanket ban on enum values
    would fail on sentences that are exactly right.
    """
    tokens = {lang.OUT_OF_COVERAGE, lang.UNRECORDED, FLOOR_REASON}
    for enum in (Support, Decision, Criticality, Channel, Attestation, Liability,
                 Certainty, CheckKind, ReasonCode, BoundOp):
        tokens |= {m.value for m in enum if "_" in m.value}
    return sorted(tokens)


def test_no_machine_token_survives_into_the_plain_text_document():
    """Checked on the text rendering, which is the one a person reads end to end.

    The HTML legitimately contains tokens a reader never sees — CSS class names and the
    embedded record — so the same assertion there would be a test of our stylesheet.
    """
    text = render_text(record(unread=("Unsupported requirement: hotel weight",)))
    leaked = [token for token in machine_tokens() if token in text]
    assert not leaked, leaked


# --- coverage, which is the section that may not be soft ---------------------------------

def test_a_satisfied_finding_nobody_asked_for_is_printed_as_not_covered():
    """`coverage_of`: an unstated attribute is out of coverage even when satisfied.

    The record cannot claim to have honoured a requirement nobody made, and a returns
    agent must not be able to read one that way — so the words are on the row, not only
    in a summary further down the page.
    """
    unstated = found("weave", Support.SATISFIED, Criticality.SOFT,
                     evidence=(saw("weave", "percale", "description"),))
    doc = build(record(findings=(unstated,)))
    row = next(f for f in doc.findings if f.attribute == "weave")

    assert row.coverage == lang.OUT_OF_COVERAGE
    assert row.coverage_label == "NOT covered"
    for rendering in (render_text(doc.record), render_html(doc.record)):
        assert "NOT covered" in rendering
        assert flat(lang.COVERAGE_MEANS[lang.OUT_OF_COVERAGE]) in flat(rendering)


def test_coverage_the_record_does_not_carry_is_never_invented():
    """The record is the authority on coverage, including when it is silent about it.

    A `ComparisonRecord` can be assembled without `coverage` — it defaults to empty, and
    anything built before the field existed has none. Calling `criticality.coverage_of`
    here to fill the gap would put a promise on the page that nobody signed, and it would
    be invisible precisely because it looked complete.
    """
    bare = ComparisonRecord(
        correlation_id="corr-1", attestation=Attestation.NEITHER, category_id="bedding",
        category_version="3", locale="en-GB", request_text="a king duvet in Frost",
        request_constraints=(want("size", "King", "a king duvet"),),
        product_id="prod-1", product_snapshot=dict(SNAPSHOT), snapshot_hash="d" * 64,
        findings=(found("size", Support.SATISFIED, Criticality.HARD),),
        decision=Decision.ALLOW, model_version="m", evaluator_version="e",
        prompt_version="p", timestamp=record().timestamp)

    assert coverage_classes(bare) == (lang.UNRECORDED,)
    text = render_text(bare)
    assert "NOT recorded" in text
    assert lang.COVERAGE_MEANS[lang.GUARANTEED] not in text
    assert any(a.severity == STOP and "covered" in a.text for a in build(bare).alerts)


def test_a_misaligned_coverage_column_invalidates_the_whole_column():
    """One misalignment is not a partial answer. Coverage is aligned with findings by
    index, so if the lengths disagree the class on row two might belong to row one, and a
    promise attached to the wrong attribute is worse than no promise at all."""
    good = record()
    skewed = good.model_copy(update={"coverage": (lang.GUARANTEED,)})
    assert len(skewed.findings) == 2
    assert coverage_classes(skewed) == (lang.UNRECORDED, lang.UNRECORDED)


def test_a_channel_that_earns_no_coverage_is_stated_before_any_attribute_class(tmp_path):
    """DR 0023 put the channel's own verdict on the record. This is the module it was put
    there for.

    Two different things are called coverage: whether this kind of order earns a promise
    at all, and which of its attributes would carry one if it did. Printing only the
    second is exactly how a page ends up promising something on an order that was ruled
    out before any attribute was compared — which is the failure DR 0023 closed.
    """
    uncovered = record().model_copy(update={
        "hash": None, "signature": None, "covered": False,
        "coverage_notes": ("this order could not be classified as agent-placed, so it is "
                           "out of coverage",)})
    doc = build(uncovered)

    assert doc.channel_covered is False and doc.channel_notes
    assert any(a.severity == STOP and "earns no coverage" in a.text for a in doc.alerts)
    for rendering in (render_text(uncovered), render_html(uncovered)):
        assert "earns NO coverage" in flat(rendering)
        assert "could not be classified as agent-placed" in flat(rendering)


def test_a_covered_channel_says_so_rather_than_staying_silent():
    """The ordinary case is a statement too. A reader who only ever sees the warning
    cannot tell the difference between a covered channel and a field we forgot to print."""
    assert "is one that earns coverage" in flat(render_text(record()))


def test_a_verification_that_did_not_complete_says_so_before_its_decision_is_read(tmp_path):
    """DR 0004. An aborted check confirms, and that confirm is a fact about Approv's own
    availability rather than a judgement about the order. A returns desk reading it as
    caution about the catalogue would be reading our outage as their problem."""
    aborted = record().model_copy(update={
        "hash": None, "signature": None, "completion": Completion.PROVIDER_UNAVAILABLE,
        "completion_detail": "extractor timed out after 8s"})
    doc = build(aborted)

    assert any(a.severity == STOP and "did not run to a conclusion" in a.text
               for a in doc.alerts)
    text = flat(render_text(aborted))
    assert "did NOT complete: provider unavailable" in text
    assert "extractor timed out after 8s" in text


def test_an_ordinary_record_still_says_the_verification_completed():
    assert "ran to a conclusion" in render_text(record())


def test_a_row_marked_as_bad_news_still_prints_the_value_it_has():
    """`missing` marks a row as bad news; it does not mean the value is absent.

    Found by the test above: the completion row printed "(not recorded)" over "did NOT
    complete: provider unavailable" — the one row saying the check failed, rendered as an
    empty field. Only an actually empty value earns the placeholder.
    """
    from approv.artifact.document import Row
    from approv.artifact.render import _row_lines

    told = _row_lines(Row("Verification", "did NOT complete: provider unavailable",
                          missing=True))
    assert "did NOT complete: provider unavailable" in " ".join(told)
    assert "(not recorded)" not in " ".join(told)

    absent = _row_lines(Row("Variant", "", missing=True))
    assert "(not recorded)" in " ".join(absent)


def test_the_coverage_caveat_is_on_both_renderings():
    """PRD §6: the coverage contract is unanswered, so nothing here may read as a promise
    to pay. The document names the class and says in the same place where the promise
    actually lives, because a merchant reading "Covered" will otherwise supply the rest of
    that sentence themselves."""
    for rendering in (render_text(record()), render_html(record())):
        assert flat(lang.COVERAGE_CAVEAT) in flat(rendering)


def test_a_refusal_is_not_printed_as_a_promise():
    doc = build(record())
    colour = next(f for f in doc.findings if f.attribute == "colour")
    assert colour.coverage == lang.REFUSED
    assert "no promise" in colour.coverage_label


# --- the liability split: our failure against nobody's fault -----------------------------

def test_what_we_failed_to_read_is_ours_and_what_nobody_asked_is_nobodys():
    """The whole liability story, and the two halves must not read as the same thing.

    Silence is nobody's fault and buys no coverage. A requirement we failed to read is
    ours. Both look like an absent constraint from inside the engine (DR 0021), so the
    document is where the distinction either survives or is lost.
    """
    text = render_text(record(unread=("Unsupported requirement: hotel weight",)))

    assert "WHAT APPROV FAILED TO READ (1)" in text
    assert flat(UNREAD_MEANS) in flat(text)
    assert "hotel weight" in text
    # The attributes nobody named are their own section, and the unread note is not in it.
    nobody = text.index("WHAT NOBODY ASKED FOR")
    assert "hotel weight" not in text[nobody:text.index(HEADINGS[1])]
    assert "material, weave" in flat(text[nobody:])


def test_both_sections_are_printed_even_when_empty():
    """An omitted section reads as an absence of problems. "Approv read everything it
    could" is a claim worth printing; leaving the heading out is not the same statement."""
    text = render_text(record(constraints=(
        want("size", "King"), want("colour", "Frost"), want("material", "linen"),
        want("weave", "percale"))))
    assert "WHAT APPROV FAILED TO READ (0)" in text
    assert "WHAT NOBODY ASKED FOR (0)" in text
    assert "Nothing. Approv encoded every part of the request it could check." in flat(text)


def test_a_request_with_nothing_recoverable_says_so_before_anything_else():
    """DR 0020: the record's strength is proportional to the specificity of the request.
    With no constraints there is nothing to be proportional to, and the document says that
    at the top rather than presenting an empty table as a clean bill."""
    doc = build(record(constraints=(), findings=()))
    assert any(a.severity == STOP and "No requirement was recovered" in a.text
               for a in doc.alerts)
    assert flat(NO_REQUIREMENTS) in flat(render_text(doc.record))


def test_a_protocol_call_is_not_presented_as_the_requesters_words():
    """A structured call carries no wording, and `surface.verification` writes a note in
    place of it so the field is not empty. Under a heading saying "in the requester's own
    words" that note reads as a quotation, which is the one place this document could put
    words in a person's mouth without printing anything untrue."""
    fields = (Constraint(attribute="size", value=Term(surface="King"),
                         channel=Channel.TOOL_ARGUMENT, source="acp.size"),)
    doc = build(record(constraints=fields, findings=(
        found("size", Support.SATISFIED, Criticality.HARD, constraint=fields[0],
              evidence=(saw("size", "King"),)),),
        request_text="(no wording: acp protocol call, see request_constraints)"))

    assert doc.request_text_note is not None
    for rendering in (render_text(doc.record), render_html(doc.record)):
        assert "No free-text wording accompanied this request" in flat(rendering)
    # And it is derived from the constraints, not from the shape of that sentence.
    assert build(record()).request_text_note is None


# --- never put words in anyone's mouth ---------------------------------------------------

def test_a_satisfaction_finding_never_quotes_the_agent():
    """`check_constraints` manufactures a `Claim` from each constraint so the operators
    have a uniform shape. Rendering that as "the agent said the product is X" would invent
    a second statement, and two parties agreeing is corroboration a returns desk would
    reasonably weigh. There is only one statement in the record."""
    constraint = want("size", "King", "a king size duvet cover")
    manufactured = found("size", Support.SATISFIED, Criticality.HARD,
                         check=CheckKind.SATISFACTION, constraint=constraint,
                         claim=Claim(attribute="size", value=Term(surface="King"),
                                     channel=Channel.AGENT_MESSAGE))
    row = next(f for f in build(record(findings=(manufactured,))).findings
               if f.attribute == "size")

    assert row.asked_for == "King"
    assert row.agent_said is None
    assert "The agent said" not in render_text(record(findings=(manufactured,)))


def test_a_grounding_finding_does_quote_the_agent():
    """The other half of the same rule. On a grounding check the claim really is the
    agent's own assertion about the product, and that assertion is often the dispute."""
    grounded = found("size", Support.VIOLATED, Criticality.HARD, check=CheckKind.GROUNDING,
                     claim=Claim(attribute="size", value=Term(surface="King"),
                                 channel=Channel.TOOL_ARGUMENT),
                     evidence=(saw("size", "Queen"),))
    text = render_text(record(findings=(grounded,)))
    assert "The agent said the product is: King" in flat(text)


def test_the_decision_is_read_off_the_record_and_never_recomputed():
    """If this document ran the evaluator it could disagree with the record it prints, and
    the disagreement would surface in a dispute rather than in a test. The findings here
    contradict the decision on purpose: the page must say what was signed."""
    signed = record()
    tampered = signed.model_copy(update={"decision": Decision.ALLOW})
    assert any(f.support is Support.VIOLATED for f in tampered.findings)
    assert "AUTHORISED THIS ORDER" in render_text(tampered).upper()


def test_an_authorised_order_with_a_contradicted_preference_says_so_at_the_top():
    """The case this document exists to keep honest. SOFT and COSMETIC attributes never
    block, so an `allow` can sit on top of a requirement that was not met, and nothing in
    the word "authorised" says so."""
    constraints = (want("material", "linen", "preferably linen"),)
    soft_miss = found("material", Support.VIOLATED, Criticality.SOFT,
                      constraint=constraints[0],
                      evidence=(saw("material", "cotton", "description"),))
    doc = build(record(constraints=constraints, findings=(soft_miss,)))

    assert doc.record.decision is Decision.ALLOW
    assert any("not met and were not treated as blocking" in a.text for a in doc.alerts)


def test_the_verification_floor_is_not_printed_as_an_attribute():
    """`decide` returns `verification_floor` in place of an attribute name when the floor
    was not met. It is a state of the check, not something the shopper asked for, and a
    row labelled with it would read as a requirement nobody can find in the request.

    The floor is reached through a finding's own reason code rather than through an unread
    request, deliberately: what an unread request does to the decision is a business
    parameter under active measurement (DR 0021, DR 0022), and a rendering test that moved
    with it would be pinning someone else's tuning.
    """
    # `decide` substitutes the pseudo-attribute only when the floor fails and no blocking
    # attribute is itself unresolved, so the finding that fails the floor is a preference.
    floored = found("weave", Support.UNSTATED, Criticality.SOFT,
                    reasons=(ReasonCode.FLOOR_NOT_MET,))
    doc = build(record(findings=(floored,)))
    assert FLOOR_REASON in doc.record.decision_reasons
    assert any("did not have what it needed" in a.text for a in doc.alerts)
    assert FLOOR_REASON not in render_text(doc.record)


# --- nothing is omitted ------------------------------------------------------------------

def test_every_finding_reaches_both_renderings():
    findings = (
        found("size", Support.SATISFIED, Criticality.HARD, evidence=(saw("size", "King"),)),
        found("colour", Support.VIOLATED, Criticality.HARD,
              evidence=(saw("colour", "Stone", "variant.colour"),)),
        found("material", Support.UNSTATED, Criticality.SOFT,
              reasons=(ReasonCode.PRODUCT_SILENT,)),
    )
    built = record(findings=findings)
    for rendering in (render_text(built), render_html(built)):
        for attribute in ("size", "colour", "material"):
            assert attribute in rendering


def test_a_finding_with_no_evidence_prints_the_row_and_says_so():
    """Missing evidence is the case where omission is most tempting and most dangerous: a
    blank cell reads as nothing to report, when what happened is that the merchant's own
    catalogue published nothing to check against."""
    silent = found("material", Support.UNSTATED, Criticality.SOFT,
                   reasons=(ReasonCode.PRODUCT_SILENT,))
    doc = build(record(findings=(silent,)))
    row = next(f for f in doc.findings if f.attribute == "material")

    assert row.catalogue_missing
    assert "The catalogue published no value" in flat(render_text(doc.record))
    assert "The catalogue published no value" in render_html(doc.record)


def test_a_record_with_no_order_line_is_not_headlined_as_an_order():
    """The largest sentence on the page must not assert the one thing missing from the
    record. A shelf-time comparison headlined "Approv authorised this order" is a claim
    about a purchase, printed in the type size people read first."""
    doc = build(record(order=None))
    assert lang.NO_ORDER_SUBJECT in doc.headline and lang.NO_ORDER_SUBJECT in doc.means
    assert lang.ORDER_SUBJECT not in doc.headline
    assert lang.ORDER_SUBJECT in build(record()).headline


def test_a_record_with_no_order_line_says_it_is_not_a_purchase():
    """A record without an order is a comparison about a product. Only the first is a
    dispute defence and the difference has to be legible, or a shelf-time comparison gets
    handed to a returns desk as though it were evidence of what was sold."""
    doc = build(record(order=None))
    assert doc.order_missing
    assert any(a.severity == STOP and "not a verification of a purchase" in a.text
               for a in doc.alerts)
    assert "(not recorded)" in render_text(doc.record)


def test_the_order_half_is_printed_down_to_the_line_total():
    """"The product matched" is not a dispute defence. The defence is this line of this
    order, this SKU, this many, at this price."""
    text = render_text(record())
    for expected in ("ORD-10238", "SKU-TANDEM-KING-STONE", "var-9", "118.00 USD",
                     "236.00 USD", "in stock"):
        assert expected in text


def test_an_absent_optional_order_field_prints_as_not_recorded():
    line = ORDER.model_copy(update={"variant_id": None, "catalogue_version": None})
    text = render_text(record(order=line))
    assert text.count("(not recorded)") >= 2
    assert "Variant" in text and "Catalogue version" in text


# --- values -------------------------------------------------------------------------------

def test_money_keeps_its_cents_and_a_measurement_drops_its_padding():
    """118.00 is not 118 on a refund, and 500.000 g is a feed artefact rather than a
    statement about precision."""
    assert lang.value(Money(amount="118.00", currency="USD")) == "118.00 USD"
    assert lang.value(Quantity(magnitude="500.000", unit="g",
                               dimension=Dimension.MASS)) == "500 g"
    assert lang.value(Count(n=2)) == "2"
    assert lang.value(Bound(op=BoundOp.LTE,
                            limit=Money(amount="305.00", currency="USD"))) == (
        "no more than 305.00 USD")


def test_an_attribute_key_is_printed_as_words():
    assert lang.attribute("pack_count") == "pack count"


# --- the signature, checked by running what the document prints ---------------------------

def seal_to_disk(tmp_path, built):
    key = generate_key()
    sealed = seal(built.model_copy(update={"hash": None, "signature": None}), key)
    path = tmp_path / "record.json"
    path.write_text(sealed.model_dump_json(), encoding="utf-8")
    return sealed, public_key_hex(key), path


def test_the_printed_instructions_verify_a_real_record(tmp_path):
    """The instructions are executed rather than described.

    §10's bar is that a stranger checks a receipt with a public key and none of our code.
    A procedure printed on a document nobody has run is a claim; this runs the text
    verbatim, in a namespace with nothing of ours in it.
    """
    sealed, key_hex, path = seal_to_disk(tmp_path, record(sign=False))
    printed = signature.snippet(key_hex, path.as_posix())
    assert flat(printed) in flat(render_text(sealed, public_key=key_hex,
                                             record_file=path.as_posix()))
    exec(compile(printed, "<printed instructions>", "exec"), {})


def test_the_printed_instructions_reject_an_edited_decision(tmp_path):
    sealed, key_hex, path = seal_to_disk(tmp_path, record(sign=False))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decision"] = "allow"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AssertionError, match="altered since it was signed"):
        exec(compile(signature.snippet(key_hex, path.as_posix()), "<printed>", "exec"), {})


def test_the_printed_instructions_use_none_of_our_code():
    """A verifier built out of our code proves only that we agree with ourselves."""
    imported = set()
    for node in ast.walk(ast.parse(signature.snippet("ab" * 32))):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
    assert imported <= {"hashlib", "json", "cryptography"}


def test_the_document_names_which_published_key_signed_it(tmp_path):
    """"Approv's public key" stopped being a single thing when rotation landed.

    A receipt stays verifiable under the key that signed it, so a reader handed today's
    key for a receipt signed under last quarter's would check it against the wrong one
    and conclude the record was forged. The record names its key; the page prints it.
    """
    sealed, key_hex, _ = seal_to_disk(tmp_path, record(sign=False))
    text = render_text(sealed, public_key=key_hex)

    assert sealed.key_id and sealed.key_id in text
    assert sealed.signature_version in text


def test_the_printed_procedure_checks_the_key_and_the_format_not_only_the_digest(tmp_path):
    """Parity with `scripts/verify_receipt.py`, which checks both.

    Two published procedures that differ let a counterparty reach two answers about one
    record, and the one they would quote is whichever suits them. A record verified under
    a key that is not the key it names is inconsistent with itself however well the
    signature checks out.
    """
    sealed, key_hex, path = seal_to_disk(tmp_path, record(sign=False))
    printed = signature.snippet(key_hex, path.as_posix())
    assert "signature_version" in printed and "key_id" in printed

    stranger = public_key_hex(generate_key())
    with pytest.raises(AssertionError, match="different published key"):
        exec(compile(signature.snippet(stranger, path.as_posix()), "<printed>", "exec"), {})


def test_an_unsigned_record_says_so_and_offers_no_procedure():
    """An unsigned record is not a weaker version of a signed one. It cannot be shown to
    be the record Approv issued, so the document says that instead of printing steps that
    would fail halfway through."""
    doc = build(record(sign=False))
    text = render_text(doc.record)
    assert not doc.signed
    assert any(a.severity == STOP and "no signature" in a.text for a in doc.alerts)
    assert flat(signature.UNSIGNED_STEPS[0]) in flat(text)
    assert "hashlib" not in text


def test_the_key_is_named_as_missing_when_it_is_not_supplied():
    """Printing a placeholder where a key should be is the honest failure. Printing the
    steps without mentioning that the key is absent would leave a reader hunting for a
    value the document silently declined to give them."""
    text = render_text(record())
    assert signature.KEY_PLACEHOLDER in text
    assert "Ask Approv for the published key" in flat(text)


# --- the HTML page -------------------------------------------------------------------------

def embedded_record(page):
    match = re.search(r'<script type="application/json" id="approv-record">(.*?)</script>',
                      page, re.S)
    assert match, "the page does not carry its own record"
    return json.loads(match.group(1))


def test_the_page_carries_the_record_it_describes_and_it_still_verifies(tmp_path):
    """Document and evidence must not be separable in an email thread. The file a reader
    is told to check is then the file they are already looking at."""
    sealed, key_hex, _ = seal_to_disk(tmp_path, record(sign=False))
    payload = embedded_record(render_html(sealed, public_key=key_hex))
    path = tmp_path / "from-page.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    exec(compile(signature.snippet(key_hex, path.as_posix()), "<printed>", "exec"), {})


def test_catalogue_text_cannot_break_out_of_the_page():
    """Product text is untrusted, first-party catalogues included (invariant 5). A title
    that closes the script element would let a merchant's own catalogue rewrite the
    document a returns desk is reading."""
    hostile = dict(SNAPSHOT,
                   title='</script><script>alert("x")</script><b>Deluxe</b>')
    page = render_html(record(snapshot=hostile))

    assert page.count("</script>") == 1
    assert "<script>alert" not in page
    assert "&lt;b&gt;Deluxe&lt;/b&gt;" in page


def test_the_page_is_balanced_html():
    class Balance(html.parser.HTMLParser):
        void = {"meta", "br", "hr", "img", "input", "link"}

        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            if tag not in self.void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack[-1] == tag, (tag, self.stack[-5:])
            self.stack.pop()

    parser = Balance()
    parser.feed(render_html(record()))
    assert parser.stack == []


def test_both_renderings_carry_the_same_sections():
    """A dispute is argued by reference. If the merchant's printout and the counterparty's
    page number their sections differently the reference stops working."""
    text, page = render_text(record()), render_html(record())
    for heading in HEADINGS:
        assert heading in text and heading in page


def test_the_closing_limits_are_never_dropped():
    """What the document does not say is part of what it says. A record that quietly
    stopped disclaiming the customer's own words would be read as covering them."""
    for rendering in (render_text(record()), render_html(record())):
        for paragraph in CLOSING:
            assert flat(paragraph) in flat(rendering)


# --- the line for the reader with a minute ------------------------------------------------

def test_the_summary_counts_exactly_what_the_table_below_it_shows():
    """A summary that said anything the table did not would be the line people read and
    the table nobody checks. It is arithmetic over the printed rows and nothing else."""
    findings = (
        found("size", Support.SATISFIED, Criticality.HARD, evidence=(saw("size", "King"),)),
        found("colour", Support.VIOLATED, Criticality.HARD,
              evidence=(saw("colour", "Stone", "variant.colour"),)),
        found("material", Support.UNSTATED, Criticality.SOFT),
    )
    doc = build(record(findings=findings))
    assert doc.summary == ("3 requirement(s) compared: 1 not met, 1 not checked, 1 met. "
                           "Coverage: 1 covered, 1 refused, 1 NOT covered.")
    for rendering in (render_text(doc.record), render_html(doc.record)):
        assert doc.summary in flat(rendering)


def test_the_summary_of_a_record_that_compared_nothing_says_so():
    assert build(record(constraints=(), findings=())).summary == "No attribute was compared."


# --- the command line ----------------------------------------------------------------------

def test_the_command_line_writes_both_renderings(tmp_path):
    """A rendering surface only a developer can invoke is not a document anyone is handed.

    The record file's own name is passed through into the instructions, so the file the
    reader is told to check is the file they were given.
    """
    sealed, key_hex, path = seal_to_disk(tmp_path, record(sign=False))
    page, text = tmp_path / "dispute.html", tmp_path / "dispute.txt"

    assert main([str(path), "--key", key_hex, "--html", str(page),
                 "--text", str(text)]) == 0
    assert "record.json" in text.read_text(encoding="utf-8")
    assert key_hex in page.read_text(encoding="utf-8")
    assert embedded_record(page.read_text(encoding="utf-8"))["hash"] == sealed.hash


def test_the_command_line_refuses_a_chain_rather_than_rendering_the_first_of_it(tmp_path):
    """A chain is several decisions. Rendering the first one under a filename that
    promised all of them is how a document ends up answering a question nobody asked."""
    path = tmp_path / "chain.json"
    path.write_text("[%s]" % record().model_dump_json(), encoding="utf-8")
    assert main([str(path)]) == 1


def test_the_plain_text_rendering_stays_ascii_for_an_ascii_record():
    """The text rendering is pasted into ticket systems and email bodies of unknown
    encoding. Our own chrome is ASCII so that a record's own content is the only thing
    that can ever arrive mangled."""
    text = render_text(record(unread=("Unsupported requirement: hotel weight",)))
    assert text.isascii(), [c for c in text if not c.isascii()][:10]


# --- the cart-only receipt is a different, lesser document on its face --------------------

def evidence_record(**kw):
    """A cart-only receipt, built through the real builder rather than posed.

    `build_order_evidence` takes no findings and no decision by construction, which is the
    property under test: there is no path by which cart-only traffic becomes a
    verification-shaped object because a caller omitted something.
    """
    from approv.receipts.record import build_order_evidence
    from approv.types.core import Money, OrderLine

    return build_order_evidence(
        correlation_id=kw.pop("correlation_id", "corr-cart"),
        schema=SCHEMA,
        order=OrderLine(order_id="SO-1", line_id="1", product_id="duvet-1", sku="SKU-1",
                        quantity=1, unit_price=Money(amount="118.00", currency="GBP")),
        product_snapshot={"product_id": "duvet-1", "title": "Percale Duvet Cover"},
        snapshot_hash="d" * 64, model_version="extract-v6", prompt_version="prompt-v6",
        reasons=kw.pop("reasons", ("no stated request accompanied this order",)),
        merchant_id="hearth-and-loom", **kw)


def test_the_cart_only_receipt_renders_as_a_different_document_not_a_shorter_one():
    """A returns desk reads the heading. A page headed like the dispute artifact, over a
    record that happens to be shorter, is read as a verification that went quietly - which
    is the exact failure `OrderEvidenceRecord` was created to end, arriving on the reading
    surface instead of in the type."""
    from approv.artifact import evidence, render_text
    from approv.artifact import render as artifact_render

    page = render_text(evidence_record())
    assert page.startswith("~" * evidence.WIDTH), "banded differently, before a word"
    assert "ORDER EVIDENCE" in page
    assert "NOT A VERIFICATION" in page
    assert artifact_render.is_evidence(evidence_record())

    # None of the dispute artifact's load-bearing furniture, because none of it applies.
    for absent in ("THE DECISION", "WHAT WAS CHECKED", "Covered", "Met", "NOT MET"):
        assert absent not in page, absent


def test_the_cart_only_page_states_its_limits_above_the_details():
    """A reader who finds what they came for stops reading, so the four things this
    document does not establish sit above the order line rather than below it."""
    from approv.artifact import render_text

    page = render_text(evidence_record())
    limits = page.index("WHAT THIS DOES NOT ESTABLISH")

    assert limits < page.index("THE ORDER")
    for sentence in ("Nothing was authorised", "No attribute was checked",
                     "Nothing here is covered"):
        assert sentence in " ".join(page.split())


def test_the_cart_only_page_never_prints_a_coverage_promise():
    """`eligible` is hard-wired false on the type. The page must not contain a word that
    could be read as a guarantee attaching to anything."""
    from approv.artifact import render_html, render_text

    for page in (render_text(evidence_record()), render_html(evidence_record())):
        flat = " ".join(page.split()).lower()
        assert "guaranteed" not in flat
        assert "out of coverage" not in flat, "there is no coverage to be out of"
        assert "nothing here is covered" in flat


def test_why_there_was_no_request_is_printed_verbatim_or_its_absence_is():
    """A record that said only "no request" invites the reader to supply their own reason
    for it, and a reader supplying a reason on a dispute document is the problem."""
    from approv.artifact import render_text

    page = render_text(evidence_record(
        reasons=("this order could not be classified as agent-placed, so it is out of "
                 "coverage",)))
    assert "could not be classified as agent-placed" in " ".join(page.split())

    bare = render_text(evidence_record(reasons=()))
    assert "carries no account of why" in " ".join(bare.split())
    assert "not evidence that the order was ordinary" in " ".join(bare.split())


def test_an_unsigned_cart_only_receipt_says_it_cannot_be_checked():
    """Same rule as the dispute artifact: a record with no signature is not evidence, and
    the page says so rather than printing verification instructions that cannot work."""
    from approv.artifact import render_text

    page = " ".join(render_text(evidence_record()).split())
    assert "carries no signature" in page


def test_the_html_page_is_visibly_not_the_dispute_artifact():
    """Across a desk, before reading. Different header, different band, and a limits block
    that is part of the page furniture rather than a footnote."""
    from approv.artifact import render_html
    page = render_html(evidence_record())
    assert "<title>ORDER EVIDENCE" in page
    assert 'class="lesser"' in page
    assert "What this does not establish" in page
    assert page.count("<section>") >= 5
