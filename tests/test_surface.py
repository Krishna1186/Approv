"""Merchant order verification: the order half, its binding, and the entry point."""
import importlib.util
from datetime import datetime, timezone

import pytest

from approv.evaluator import decide
from approv.intake import AgentPresence, FreeText, Reading, Search, Structured, Undeclared
from approv.receipts.chain import generate_key, public_key_hex, seal, verify
from approv.surface.verification import (
    ModeMismatch, ProductMismatch, UnknownCategory, VerificationRequest,
    evidence_from_snapshot, ingest_outcome, snapshot_digest, verify_order,
)
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Decision,
    Completion, Dimension, FieldProfile, Liability, Mode, Money, OrderLine, OrderOutcome,
    OutcomeKind, Support, Term, UnreadPolicy,
)

SCHEMA = CategorySchema(
    category_id="apparel", version="3",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="pack_count", dimension=Dimension.COUNT, criticality=Criticality.BOUND),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.color", attributes=("color",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="pack_count", attributes=("pack_count",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="description", attributes=("color",),
                     certainty=Certainty.PARSED, liability=Liability.MERCHANT_GUARANTEED),
    ),
)

SCHEMAS = {SCHEMA.category_id: SCHEMA}
SNAPSHOT = {"variant": {"size": "M", "color": "Frost"}, "pack_count": 2,
            "title": "Tandem Stripe Duvet Cover"}


def order(**kw):
    base = dict(order_id="ord-1", product_id="prod-1", sku="SKU-TANDEM-M-FROST",
                variant_id="var-9", quantity=1,
                unit_price=Money(amount="118.00", currency="USD"),
                availability="in_stock", catalogue_version="2026-09-12T09:00Z")
    return OrderLine(**{**base, **kw})


def request(artifact=None, snapshot=None, **kw):
    return VerificationRequest(
        merchant_id="m-1", correlation_id="corr-1",
        category_id=kw.pop("category_id", SCHEMA.category_id),
        order=kw.pop("order", order()),
        artifact=artifact or Structured(protocol="acp",
                                        fields={"size": "M", "color": "Frost"}),
        product_snapshot=SNAPSHOT if snapshot is None else snapshot, **kw)


def reader(text, schema):
    """A stand-in extractor reading the same two requirements out of prose."""
    return Reading(constraints=(
        Constraint(attribute="size", value=Term(surface="M"),
                   channel=Channel.AGENT_MESSAGE, raw_text=text),
        Constraint(attribute="color", value=Term(surface="Frost"),
                   channel=Channel.AGENT_MESSAGE, raw_text=text)))


def colour_only(text, schema):
    return Reading(constraints=(Constraint(attribute="color", value=Term(surface="Frost"),
                                           channel=Channel.AGENT_MESSAGE, raw_text=text),))


def under_read(text, schema):
    """Reads both requirements, and says a third went unread."""
    return Reading(constraints=reader(text, schema).constraints,
                   unread=("Unsupported requirement: monogram",))


# --- DR 0022: what an unread request does -------------------------------------------------

def unread_result(policy):
    return verify_order(request(artifact=FreeText(text="a Frost duvet in M, monogrammed")),
                        schemas=SCHEMAS, extract=under_read, unread_policy=policy)


def test_an_unread_requirement_lets_the_sale_through_and_withdraws_the_guarantee():
    """DR 0022, the default. An unread requirement is our defect, and pausing the
    merchant's checkout over it charges them for it — measured at 58.8% nuisance. The sale
    proceeds; what is withdrawn is the promise."""
    result = unread_result(UnreadPolicy.WITHDRAW)

    assert result.record.decision is Decision.ALLOW
    assert set(result.record.coverage) == {"out_of_coverage"}
    assert result.record.unread == ("Unsupported requirement: monogram",)


def test_withdrawal_is_record_wide_because_the_gap_belongs_to_no_attribute():
    """Narrowing could be attributed to a constraint's own quote; this cannot. Colour and
    size both compare cleanly and neither is guaranteed, because what a guarantee promises
    is that the order was as asked."""
    clean = verify_order(request(artifact=FreeText(text="a Frost duvet in M")),
                         schemas=SCHEMAS, extract=reader)
    assert "guaranteed" in clean.record.coverage
    assert "guaranteed" not in unread_result(UnreadPolicy.WITHDRAW).record.coverage


def test_escalating_is_still_available_because_it_is_a_merchant_preference():
    result = unread_result(UnreadPolicy.ESCALATE)

    assert result.record.decision is Decision.CONFIRM
    assert set(result.record.coverage) == {"out_of_coverage"}


def test_ignoring_is_the_one_that_promises_over_words_nobody_read():
    """Kept only so DR 0022's table reproduces. Same decision as WITHDRAW, and it claims
    the guarantee anyway."""
    ignored = unread_result(UnreadPolicy.IGNORE)

    assert ignored.record.decision is Decision.ALLOW
    assert "guaranteed" in ignored.record.coverage


def test_the_three_policies_differ_on_exactly_two_axes():
    """ESCALATE and WITHDRAW share coverage and differ in the decision; WITHDRAW and
    IGNORE share the decision and differ in coverage. That separation is what made the
    measurement decidable."""
    escalate = unread_result(UnreadPolicy.ESCALATE)
    withdraw = unread_result(UnreadPolicy.WITHDRAW)
    ignore = unread_result(UnreadPolicy.IGNORE)

    assert escalate.record.coverage == withdraw.record.coverage
    assert escalate.record.decision is not withdraw.record.decision
    assert withdraw.record.decision is ignore.record.decision
    assert withdraw.record.coverage != ignore.record.coverage


# --- the order half ---------------------------------------------------------------------

def test_the_record_names_the_exact_variant_quantity_and_price_it_checked():
    """PRD §3. "The product matched" is not a dispute defence. A returns desk needs this
    line of this order, this SKU, this many, at this price."""
    result = verify_order(request(order=order(quantity=3)), schemas=SCHEMAS)
    line = result.record.order

    assert line.sku == "SKU-TANDEM-M-FROST" and line.variant_id == "var-9"
    assert line.quantity == 3
    assert line.unit_price.amount == Money(amount="118.00", currency="USD").amount
    assert line.unit_price.currency == "USD"
    assert line.availability == "in_stock"


def test_a_record_cannot_be_assembled_about_a_different_product_than_its_order():
    """The binding, and the reason it is a validator rather than a convention. A record
    whose order names one SKU and whose findings were computed against another is worse
    than no record, because it looks like evidence."""
    from approv.receipts.record import build_record

    with pytest.raises(ValueError, match="order line names product"):
        build_record(correlation_id="c", request_text="x", constraints=(), findings=(),
                     schema=SCHEMA, product_id="prod-1", product_snapshot={},
                     snapshot_hash="h", model_version="m", prompt_version="p",
                     order=order(product_id="a-different-product"))


def test_a_snapshot_for_one_product_is_not_verified_against_another_order_line():
    """The binding that can actually fail at this surface. `product_id` is taken *from*
    the order, so the record's own check can never fire here — what can go wrong is a
    merchant posting order line A with the catalogue record for B, and the answer would
    look like evidence about the wrong product."""
    with pytest.raises(ProductMismatch, match="catalogue snapshot is product"):
        verify_order(request(snapshot={**SNAPSHOT, "id": "prod-2"}), schemas=SCHEMAS)


def test_a_snapshot_that_does_not_identify_itself_is_accepted():
    """Many catalogue exports carry no id, and rejecting those would invent a requirement
    the format does not have."""
    assert verify_order(request(), schemas=SCHEMAS).record.decision is Decision.ALLOW


def test_the_order_half_is_inside_the_signature():
    """Bound into the digest with everything else, so a price cannot be adjusted after the
    outcome is known. This is the whole reason the fields are on the record rather than in
    the untyped snapshot dict beside it."""
    key = generate_key()
    sealed = seal(verify_order(request(), schemas=SCHEMAS).record, key)
    verify(sealed, public_key_hex(key))

    tampered = sealed.model_copy(update={
        "order": sealed.order.model_copy(update={"quantity": 99})})
    with pytest.raises(ValueError, match="does not match its hash"):
        verify(tampered, public_key_hex(key))


def test_a_shelf_time_comparison_carries_no_order_and_says_so_by_carrying_none():
    """`mark` runs before any order exists. A record without an order is a comparison
    about a product; one with an order is a verification of a purchase. The difference is
    in the record now instead of being a matter of what the caller meant."""
    from approv.receipts.record import build_record
    from approv.types.core import CheckKind, Finding

    record = build_record(
        correlation_id="c", request_text="x", constraints=(), findings=(
            Finding(check=CheckKind.SATISFACTION, attribute="size",
                    criticality=Criticality.SOFT, support=Support.SATISFIED,
                    confidence=1.0, ceiling=1.0),),
        schema=SCHEMA, product_id="prod-1", product_snapshot={}, snapshot_hash="h",
        model_version="m", prompt_version="p")
    assert record.order is None


# --- reading the merchant's own catalogue ------------------------------------------------

def test_the_snapshot_is_read_through_the_schemas_own_field_profiles():
    """No new vocabulary. `FieldProfile` already names the field, the attributes it speaks
    to and where it sits on both DR 0016 axes, and it was being authored per category
    anyway for the comparison to work at all."""
    evidence = {e.field_name: e for e in evidence_from_snapshot(SNAPSHOT, SCHEMA)}

    assert evidence["variant.size"].value.surface == "M"
    assert evidence["variant.size"].certainty is Certainty.EXACT
    assert evidence["pack_count"].value.n == 2
    assert "description" not in evidence


def test_a_flat_key_and_a_nested_one_both_resolve():
    """Both spellings occur in real catalogue exports, and guessing wrong loses evidence
    silently — which escalates a sale for a reason that is ours, not the merchant's."""
    flat = evidence_from_snapshot({"variant.size": "L"}, SCHEMA)
    assert [e.value.surface for e in flat] == ["L"]


def test_a_value_we_cannot_honestly_read_produces_no_evidence():
    """§2.3 in force at the adapter. Coercing an unreadable field into a Term would
    manufacture a comparison out of a value we did not understand, and a manufactured
    SATISFIED is a guarantee we cannot keep. Nothing is the honest answer, and it
    escalates."""
    assert evidence_from_snapshot({"variant": {"size": 12.5}}, SCHEMA) == ()

    result = verify_order(request(snapshot={"variant": {"size": 12.5, "color": "Frost"}}),
                          schemas=SCHEMAS)
    assert result.record.decision is Decision.CONFIRM


def test_a_typed_catalogue_value_is_taken_as_typed():
    evidence = evidence_from_snapshot(
        {"pack_count": {"kind": "count", "n": 6}}, SCHEMA)
    assert evidence[0].value.n == 6


# --- shadow mode --------------------------------------------------------------------------

def test_a_record_says_whether_it_gated_anything():
    """A shadow run is how a merchant finds out what Approv would have done before it does
    anything, and the receipt has to say which it was."""
    watched = verify_order(request(), schemas=SCHEMAS)
    gated = verify_order(request(), schemas=SCHEMAS, mode=Mode.ENFORCE)

    assert watched.record.mode is Mode.SHADOW
    assert gated.record.mode is Mode.ENFORCE
    assert watched.record.decision is gated.record.decision


def test_enforce_has_to_be_asked_for():
    """The two mistakes are not symmetric. A shadow record mislabelled `enforce` is a false
    claim in a dispute; an enforce record mislabelled `shadow` under-claims and is
    recoverable. Only the second is reachable by forgetting."""
    from approv.receipts.record import build_record

    assert verify_order(request(), schemas=SCHEMAS).record.mode is Mode.SHADOW
    bare = build_record(correlation_id="c", request_text="x", constraints=(), findings=(),
                        schema=SCHEMA, product_id="prod-1", product_snapshot={},
                        snapshot_hash="h", model_version="m", prompt_version="p")
    assert bare.mode is Mode.SHADOW


def test_the_mode_is_deployment_configuration_not_request_payload():
    """A caller who could send `enforce` could defeat sandbox isolation with one JSON
    field. Same argument as the schemas: the party being defended does not get to set the
    terms."""
    assert "mode" not in VerificationRequest.model_fields


def test_the_mode_is_inside_the_signature():
    """A shadow receipt that can be relabelled `enforce` afterwards is exactly the artifact
    this must never produce."""
    key = generate_key()
    sealed = seal(verify_order(request(), schemas=SCHEMAS).record, key)
    verify(sealed, public_key_hex(key))

    with pytest.raises(ValueError, match="does not match its hash"):
        verify(sealed.model_copy(update={"mode": Mode.ENFORCE}), public_key_hex(key))


# --- outcome ingestion ----------------------------------------------------------------

def outcome(**kw):
    base = dict(correlation_id="corr-1", kind=OutcomeKind.RETURNED,
                occurred_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
                mode=Mode.SHADOW, merchant_id="m-1")
    return OrderOutcome(**{**base, **kw})


def test_an_outcome_joins_a_verification_by_correlation_id():
    """The join a shadow run exists to make: the decision says what Approv would have
    done, the outcome says what happened anyway. Without it a shadow run measures what the
    corpus already measures."""
    kept = []
    taken = ingest_outcome(outcome(), record_outcome=kept.append)

    assert kept == [taken]
    assert taken.correlation_id == verify_order(request(), schemas=SCHEMAS).receipt_id


def test_the_merchants_reason_is_kept_verbatim():
    """Their words, not a reason code. Normalising it here is the first step toward
    deciding with it."""
    words = "customer said the blue was too dark, sending back"
    kept = []
    ingest_outcome(outcome(merchant_reason=words), record_outcome=kept.append)

    assert kept[0].merchant_reason == words


def test_nothing_in_the_decision_path_can_read_an_outcome():
    """The field most likely to be quietly promoted into a signal. The moment a merchant's
    free text reaches criticality or the evaluator, §1's central claim is false — so it is
    asserted the way the other import boundaries are, not trusted."""
    import ast
    import pathlib

    for target in ("approv/evaluator", "approv/algebra", "approv/criticality.py"):
        path = pathlib.Path(target)
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for one in files:
            source = one.read_text(encoding="utf-8")
            names = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.ImportFrom):
                    names.update(alias.name for alias in node.names)
            assert not names & {"OrderOutcome", "OutcomeKind"}, one


def test_an_outcome_from_the_other_mode_is_refused_rather_than_stored():
    """A sandbox result joined to a live record is the cross-contamination the separate
    chain exists to prevent, and a join key is all it would take."""
    kept = []
    with pytest.raises(ModeMismatch):
        ingest_outcome(outcome(mode=Mode.ENFORCE), record_outcome=kept.append,
                       mode=Mode.SHADOW)
    assert kept == []


# --- seam 4: coverage is on the record, inside the digest ---------------------------------

def test_the_channel_verdict_is_on_the_record_not_beside_it():
    """DR 0023. The dispute artifact renders the record and nothing else, so a verdict
    kept beside it was dropped the moment the record was stored or rendered — and the
    document printed "Covered" for an order intake had ruled out."""
    result = verify_order(request(artifact=Undeclared()), schemas=SCHEMAS)

    assert result.record.covered is False
    assert any("out of coverage" in note for note in result.record.coverage_notes)
    # The result still answers, as a view onto the record rather than a second copy.
    assert result.covered is result.record.covered
    assert result.intake_notes == result.record.coverage_notes


def test_an_uncovered_channel_guarantees_nothing():
    """Otherwise the record says the channel earned no coverage and, three fields later,
    that six findings are guaranteed. A renderer picking either would be right, which
    means neither is."""
    uncovered = verify_order(
        request(artifact=Search(query="frost duvet", filters={"size": "M"})),
        schemas=SCHEMAS, extract=colour_only)

    assert uncovered.record.covered is False
    assert "guaranteed" not in uncovered.record.coverage


def test_a_covered_channel_still_guarantees():
    """Stated so the rule is not read as withdrawing coverage from everything."""
    covered = verify_order(request(), schemas=SCHEMAS)

    assert covered.record.covered is True
    assert "guaranteed" in covered.record.coverage


def test_the_channel_verdict_is_inside_the_signature():
    """A coverage claim that can be edited after a dispute opens is not a claim, and the
    party with the motive to edit it is us."""
    key = generate_key()
    sealed = seal(verify_order(request(artifact=Undeclared()), schemas=SCHEMAS).record, key)
    verify(sealed, public_key_hex(key))

    with pytest.raises(ValueError, match="does not match its hash"):
        verify(sealed.model_copy(update={"covered": True}), public_key_hex(key))


def test_coverage_never_gates_the_decision():
    """An uncovered order is authorised or refused on its merits. Coupling the two would
    turn a commercial eligibility rule into a reason to block a sale, which is the
    confusion property 6 exists to prevent."""
    uncovered = verify_order(
        request(artifact=Search(query="frost duvet", filters={"size": "M"})),
        schemas=SCHEMAS, extract=colour_only)

    assert uncovered.record.covered is False
    assert uncovered.record.decision is Decision.ALLOW


# --- invariant 10: no personal data in the record -----------------------------------------

def test_the_record_declares_no_field_that_could_hold_a_person():
    """Invariant 10. The artifact is handed to a returns desk, a PSP and possibly a court;
    one that needs a redaction pass first is not evidence, it is a liability.

    A field-name check rather than a content scan, because content cannot be policed here
    — `request_text` is free text and a surface that lets a shopper's identity into it has
    to redact before the call. What this catches is the day somebody adds
    `customer_email` to the record and nobody notices, which is how personal data actually
    arrives: as a convenience field, not as an attack.
    """
    from approv.types.core import ComparisonRecord, OrderLine

    forbidden = ("email", "phone", "name", "address", "postcode", "zip", "dob",
                 "birth", "customer", "shopper", "buyer", "card", "pan", "iban",
                 "account", "ssn", "tax_id", "passport", "ip_address", "device")
    declared = set(ComparisonRecord.model_fields) | set(OrderLine.model_fields)
    offending = sorted(f for f in declared
                       if any(word in f.lower() for word in forbidden))

    assert not offending, f"invariant 10: record declares {offending}"


def test_the_join_keys_it_does_carry_identify_transactions_not_people():
    """Stated so the invariant is not read as forbidding identifiers altogether. A
    correlation id is the join between two signed halves (DR 0016 §7); an order id and a
    SKU are the merchant's own references to a purchase."""
    from approv.types.core import ComparisonRecord, OrderLine

    assert {"correlation_id", "merchant_id", "agent_id"} <= set(ComparisonRecord.model_fields)
    assert {"order_id", "sku"} <= set(OrderLine.model_fields)


# --- seam 1: the format onboarding actually emits -----------------------------------------

DERIVED_CATALOGUE = [
    {"product_id": "duvet-tandem", "title": "Tandem Stripe Duvet Cover",
     "variants": [{"sku": "TAN-KING-FROST",
                   "options": [{"name": "Size", "value": "King"},
                               {"name": "Colour", "value": "Frost"}],
                   "price": {"amount": "118.00", "currency": "USD"}}]},
    {"product_id": "duvet-halden", "title": "Halden Linen Duvet Cover",
     "variants": [{"sku": "HAL-QUEEN-ASH",
                   "options": [{"name": "Size", "value": "Queen"},
                               {"name": "Colour", "value": "Ash"}],
                   "price": {"amount": "149.00", "currency": "USD"}}]},
]


def derived_schema(catalogue=None):
    from approv.schema import confirm_schema, propose_schema

    proposal = propose_schema(catalogue or DERIVED_CATALOGUE,
                              category_id="bedding.duvets", currency="USD")
    return confirm_schema(proposal, reviewer="founder",
                          expected_proposal_id=proposal.proposal_id,
                          floor=proposal.proposed_schema.floor).category_schema


def test_a_derived_schema_reads_the_catalogue_it_was_derived_from():
    """The regression that should have existed. Onboarding's output is the surface's
    input, or onboarding onboards nothing — and it failed silently, which is the worse
    half: a pilot partner would have seen a 100% confirm rate and no error at all."""
    evidence = evidence_from_snapshot(DERIVED_CATALOGUE[0], derived_schema())

    assert evidence, "a schema derived from this catalogue reads nothing from it"
    assert {e.attribute for e in evidence} == {"title", "colour", "size", "price"}


def test_the_selector_picks_the_right_option_off_a_shared_path():
    """`/variants/*/options/*/value` carries Size and Colour on the same path, so the
    `#name=` selector is load-bearing rather than an annotation. Reading it wrong crosses
    two attributes, which is worse than reading nothing."""
    read = {e.attribute: e.value.surface
            for e in evidence_from_snapshot(DERIVED_CATALOGUE[0], derived_schema())
            if e.attribute in ("size", "colour")}

    assert read == {"size": "King", "colour": "Frost"}


def test_a_container_labelled_with_something_else_yields_nothing():
    """A selector must match a sibling of the value. A container labelled with anything
    else is a *different attribute*, not a fallback — falling back to the path would hand
    every option value to whichever attribute asked first."""
    schema = derived_schema()
    snapshot = {"product_id": "x", "title": "T",
                "variants": [{"sku": "S", "options": [{"name": "Weave", "value": "Sateen"}]}]}

    assert {e.attribute for e in evidence_from_snapshot(snapshot, schema)} == {"title"}


def test_a_typed_catalogue_price_is_read_rather_than_skipped():
    """An amount beside its currency is a Money. Refusing it would leave a price attribute
    the derivation had already promised reading nothing at all."""
    price = next(e for e in evidence_from_snapshot(DERIVED_CATALOGUE[0], derived_schema())
                 if e.attribute == "price")

    assert price.value.currency == "USD" and str(price.value.amount) == "118.00"


def test_an_amount_without_a_currency_is_not_a_price():
    """`approv.schema` refuses the same case when it derives. Inventing a currency is how
    a comparison gets manufactured out of a field nobody stated properly."""
    schema = derived_schema()
    snapshot = {"product_id": "x", "variants": [{"sku": "S", "price": {"amount": "118.00"}}]}

    assert not [e for e in evidence_from_snapshot(snapshot, schema) if e.attribute == "price"]


def test_a_schema_that_reads_nothing_fails_loudly_instead_of_confirming_quietly():
    """The silence is the worse half. A disconnected deployment must not be
    indistinguishable from a cautious one — so it is a named failure carrying a record,
    not an exception and not a silent confirm."""
    dotted = {"variant": {"size": "M", "color": "Frost"}}
    result = verify_order(request(snapshot=dotted),
                          schemas={SCHEMA.category_id: derived_schema()})

    assert result.record.completion is Completion.CATALOGUE_UNREADABLE
    assert "not the same shape" in result.record.completion_detail
    assert result.record.decision is Decision.CONFIRM
    assert not result.covered


def test_a_sparse_snapshot_is_not_a_shape_mismatch():
    """Scoped to the case that can only be a fault. An empty snapshot has nothing to read
    and a schema with no profiles has nothing to read with; failing on either would fire
    on legitimately sparse traffic."""
    assert verify_order(request(snapshot={}), schemas=SCHEMAS).record.completion \
        is Completion.COMPLETED


# --- the entry point ----------------------------------------------------------------------

def test_a_satisfying_order_is_allowed_and_the_findings_are_guaranteed():
    result = verify_order(request(), schemas=SCHEMAS)

    assert result.record.decision is Decision.ALLOW
    covered = dict(zip((f.attribute for f in result.record.findings), result.record.coverage))
    assert covered == {"size": "guaranteed", "color": "guaranteed",
                       # Never stated, so nothing was promised about it even though the
                       # catalogue happens to say 2.
                       "pack_count": "out_of_coverage"}
    assert result.covered


def test_a_wrong_variant_is_refused_and_names_the_attribute():
    result = verify_order(
        request(snapshot={"variant": {"size": "M", "color": "Sand"}}), schemas=SCHEMAS)

    assert result.record.decision is Decision.REFUSE
    assert result.record.decision_reasons == ("color",)


def test_the_surface_decides_nothing_itself():
    """Assembly, not judgement. If a caller could override this, that caller is the
    decision path and §1's central claim is false."""
    result = verify_order(request(snapshot={"variant": {"size": "L", "color": "Frost"}}),
                          schemas=SCHEMAS)
    expected, reasons = decide(result.record.findings, floor_met=True)

    assert result.record.decision is expected
    assert result.record.decision_reasons == reasons


def test_every_intake_shape_reaches_the_same_endpoint():
    """Two surfaces, one engine, many adapters — at the point where it has to be true."""
    structured = verify_order(request(), schemas=SCHEMAS)
    free_text = verify_order(request(artifact=FreeText(text="a Frost duvet")),
                             schemas=SCHEMAS, extract=reader)
    searched = verify_order(
        request(artifact=Search(query="frost duvet", filters={"size": "M"}),
                agent=AgentPresence.INFERRED), schemas=SCHEMAS, extract=colour_only)

    assert all(r.record.decision is Decision.ALLOW
               for r in (structured, free_text, searched))
    # Same answer, different evidentiary weight, and the record says which.
    assert [c.channel for c in structured.record.request_constraints] == [
        Channel.TOOL_ARGUMENT] * 2
    assert [c.channel for c in free_text.record.request_constraints] == [
        Channel.AGENT_MESSAGE] * 2


def test_a_requirement_the_reader_missed_escalates_rather_than_passing():
    """The free-text paths can under-read, and the record must not treat what was not read
    as what was not asked. Size goes unstated, stays blocking, and the sale is confirmed
    rather than authorised."""
    result = verify_order(request(artifact=FreeText(text="a Frost duvet")),
                          schemas=SCHEMAS, extract=colour_only)

    assert result.record.decision is Decision.CONFIRM
    assert result.record.decision_reasons == ("size",)


def test_an_order_with_no_stated_request_is_recorded_and_left_uncovered():
    """DR 0020's uncovered slice reaches the surface as a real answer, not an error. The
    merchant still gets a record saying exactly why it proves nothing."""
    result = verify_order(request(artifact=Undeclared()), schemas=SCHEMAS)

    assert not result.covered
    assert result.record.order is not None
    assert any("out of coverage" in note for note in result.intake_notes)


def test_a_protocol_call_says_it_had_no_wording_rather_than_appearing_silent():
    """`request_text` empty would read, in a dispute, as the agent having said nothing.
    What it said is the slots it filled, and `request_constraints` carries them in full."""
    result = verify_order(request(), schemas=SCHEMAS)

    assert "no wording" in result.record.request_text and "acp" in result.record.request_text
    assert len(result.record.request_constraints) == 2


def test_an_unknown_category_is_refused_before_anything_is_compared():
    with pytest.raises(UnknownCategory):
        verify_order(request(), schemas={})


def test_the_snapshot_digest_is_the_one_dump_format():
    """A merchant recomputes this with json.dumps and three arguments, not with our code —
    the same bar the standalone verifier is held to."""
    import hashlib
    import json
    expected = hashlib.sha256(json.dumps(
        SNAPSHOT, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    assert snapshot_digest(SNAPSHOT) == expected
    assert verify_order(request(), schemas=SCHEMAS).record.snapshot_hash == expected


def test_the_surface_hands_back_an_unsealed_record():
    """Only the store knows the chain head. A signature over `prev_hash=None` is a receipt
    appendable exactly once per ledger — the first order succeeds and the second conflicts
    — so sealing has one owner and it is not this one."""
    import inspect

    result = verify_order(request(), schemas=SCHEMAS)

    assert result.record.hash is None and result.record.signature is None
    assert result.record.prev_hash is None
    assert "signing_key" not in inspect.signature(verify_order).parameters


# --- DR 0004: a verification that did not complete -----------------------------------------

def failing(error):
    def extract(text, schema):
        raise error
    return extract


def incomplete(extract=None, **kw):
    return verify_order(request(artifact=FreeText(text="a Frost duvet in M")),
                        schemas=SCHEMAS,
                        extract=extract or failing(TimeoutError("read timed out")), **kw)


def test_a_provider_that_did_not_answer_never_authorises():
    """The bug this closes is live, not hypothetical: `decide(())` returns ALLOW, so an
    extractor that failed and yielded no constraints authorised the purchase. That is the
    fail-open bypass DR 0004's own attack section describes, reachable without an
    attacker."""
    result = incomplete()

    assert result.record.decision is Decision.CONFIRM
    assert result.record.completion is Completion.PROVIDER_UNAVAILABLE
    assert "timed out" in result.record.completion_detail
    assert not result.covered


def test_a_failure_confirms_rather_than_refusing():
    """A failed check is not evidence the product is wrong. Refusing on our own outage
    bills the merchant for it — a lost sale caused by our vendor — and `confirm` is the
    recoverable branch."""
    assert incomplete().record.decision is not Decision.REFUSE


def test_a_malformed_response_is_told_apart_from_an_absent_one():
    result = incomplete(extract=failing(ValueError("expected object, got list")))
    assert result.record.completion is Completion.UNREADABLE_RESPONSE


def test_our_vendor_being_down_is_told_apart_from_the_catalogue_being_wrong():
    """The two sentences a merchant needs told apart. One refusal covering both tells them
    neither, which is why `catalogue_unreadable` is its own value."""
    def unreadable(snapshot, schema):
        raise KeyError("variant")

    result = verify_order(request(), schemas=SCHEMAS, read_evidence=unreadable)
    assert result.record.completion is Completion.CATALOGUE_UNREADABLE
    assert "catalogue snapshot" in result.record.completion_detail
    # However the merchant's snapshot failed to read, it is the merchant's snapshot. The
    # parse/no-answer split belongs to the reader boundary, where it means something.
    assert not result.covered


def test_an_unreadable_request_is_told_apart_from_an_absent_one():
    """`Undeclared` means the order carried no stated request, which is merchant channel
    policy. A failed read means we could not read the one it carried, which is ours.
    `covered` is False either way, so `completion` is the only thing that separates them."""
    absent = verify_order(request(artifact=Undeclared()), schemas=SCHEMAS)
    unread = incomplete()

    assert not absent.covered and not unread.covered
    assert absent.record.completion is Completion.COMPLETED
    assert unread.record.completion is Completion.PROVIDER_UNAVAILABLE


def test_a_blown_budget_cannot_authorise_even_when_everything_matched():
    """The safety property, not the latency one. Every finding here is SATISFIED and the
    record still neither authorises nor guarantees, because the answer arrived too late to
    be usable."""
    result = verify_order(request(), schemas=SCHEMAS, budget_seconds=0.0)

    assert result.record.decision is Decision.CONFIRM
    assert result.record.completion is Completion.BUDGET_EXCEEDED
    assert "budget" in result.record.completion_detail
    assert [f.support for f in result.record.findings].count(Support.SATISFIED) == 2
    assert "guaranteed" not in result.record.coverage


def test_no_budget_set_is_no_abort():
    assert verify_order(request(), schemas=SCHEMAS).record.completion is Completion.COMPLETED


def test_the_completion_state_is_inside_the_signature():
    """An abort that can be edited afterwards is an abort that never happened. The point of
    recording it is the receipt chain, so it has to be sealed like everything else."""
    key = generate_key()
    sealed = seal(incomplete().record, key)
    verify(sealed, public_key_hex(key))

    tampered = sealed.model_copy(update={"completion": Completion.COMPLETED})
    with pytest.raises(ValueError, match="does not match its hash"):
        verify(tampered, public_key_hex(key))


def test_a_bug_in_our_own_assembly_still_raises():
    """Only the two injected boundaries are caught. Laundering a programming error into a
    signed `confirm` record would hide it behind a plausible-looking artifact, which is
    worse than a 500 nobody can miss."""
    with pytest.raises(UnknownCategory):
        verify_order(request(), schemas={})
    with pytest.raises(ProductMismatch):
        verify_order(request(snapshot={**SNAPSHOT, "id": "prod-2"}), schemas=SCHEMAS)


# --- the HTTP router ----------------------------------------------------------------------

# Skipped per test, never per module: the framework-free half above is meant to run with
# no web framework installed, and a module-level skip would stop it proving that.
requires_api = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None, reason="approv[api] not installed")


def client(**kw):
    from fastapi.testclient import TestClient

    from approv.surface.api import create_app
    return TestClient(create_app(SCHEMAS, **kw))


def body(**kw):
    return {"merchant_id": "m-1", "correlation_id": "corr-1",
            "category_id": SCHEMA.category_id,
            "order": {"order_id": "ord-1", "product_id": "prod-1", "sku": "S",
                      "quantity": 2,
                      "unit_price": {"kind": "money", "amount": "118.00",
                                     "currency": "USD"}},
            "artifact": {"shape": "structured", "protocol": "acp",
                         "fields": {"size": "M", "color": "Frost"}},
            "product_snapshot": SNAPSHOT, **kw}


@requires_api
def test_a_refusal_is_a_successful_verification_with_an_unwelcome_answer():
    """200, not 4xx. An error status invites a caller to treat a refusal as a transport
    failure and retry until it goes away."""
    response = client().post("/v1/verify", json=body(
        product_snapshot={"variant": {"size": "M", "color": "Sand"}}))

    assert response.status_code == 200
    assert response.json()["record"]["decision"] == "refuse"
    assert response.json()["record"]["decision_reasons"] == ["color"]


@requires_api
def test_the_order_half_survives_the_wire():
    line = client().post("/v1/verify", json=body()).json()["record"]["order"]

    assert line["sku"] == "S" and line["quantity"] == 2
    assert line["unit_price"] == {"kind": "money", "amount": "118.00", "currency": "USD"}


@requires_api
def test_an_unknown_category_is_a_404_and_not_a_silent_pass():
    assert client().post("/v1/verify", json=body(category_id="nope")).status_code == 404


@requires_api
def test_a_caller_cannot_supply_their_own_schema():
    """Schemas are deployment configuration. If the party being defended could define what
    counts as a match, the record would be worth nothing."""
    response = client().post("/v1/verify", json=body(schema={"anything": True}))
    assert response.status_code == 422


@requires_api
def test_a_verification_that_did_not_complete_is_a_200_with_the_record():
    """A 5xx hands the merchant nothing to keep, and their integration's most likely
    response to one is to ship anyway — failing open through the error handler rather than
    through the gate."""
    def boom(text, schema):
        raise TimeoutError("read timed out")

    response = client(extract=boom).post("/v1/verify", json=body(
        artifact={"shape": "free_text", "text": "a Frost duvet in M"}))

    assert response.status_code == 200
    assert response.json()["record"]["completion"] == "provider_unavailable"
    assert response.json()["record"]["decision"] == "confirm"


@requires_api
def test_health_names_what_this_deployment_can_verify():
    payload = client().get("/v1/health").json()
    assert payload["status"] == "ok" and payload["categories"] == [SCHEMA.category_id]


@requires_api
def test_a_deployment_with_nowhere_to_put_outcomes_says_so():
    """An ingestion endpoint that silently discards is worse than none, because it reports
    success."""
    response = client().post("/v1/outcomes", json={
        "correlation_id": "corr-1", "kind": "returned",
        "occurred_at": "2026-09-20T00:00:00Z"})

    assert response.status_code == 501


@requires_api
def test_the_wrong_mode_is_a_conflict_over_the_wire():
    kept = []
    api = client(record_outcome=kept.append, mode=Mode.SHADOW)
    response = api.post("/v1/outcomes", json={
        "correlation_id": "corr-1", "kind": "refunded",
        "occurred_at": "2026-09-20T00:00:00Z", "mode": "enforce"})

    assert response.status_code == 409
    assert kept == []


@requires_api
def test_health_says_which_mode_this_deployment_runs():
    payload = client().get("/v1/health").json()
    assert payload["mode"] == "shadow" and payload["outcomes"] is False
