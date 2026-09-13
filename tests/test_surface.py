"""Merchant order verification: the order half, its binding, and the entry point."""
import importlib.util

import pytest

from approv.evaluator import decide
from approv.intake import AgentPresence, FreeText, Reading, Search, Structured, Undeclared
from approv.receipts.chain import generate_key, public_key_hex, seal, verify
from approv.surface.verification import (
    ProductMismatch, UnknownCategory, VerificationRequest, evidence_from_snapshot,
    snapshot_digest, verify_order,
)
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Decision,
    Dimension, FieldProfile, Liability, Money, OrderLine, Support, Term, UnreadPolicy,
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
        merchant_id="m-1", correlation_id="corr-1", category_id=SCHEMA.category_id,
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


def test_the_signing_key_seals_on_the_way_out():
    key = generate_key()
    result = verify_order(request(), schemas=SCHEMAS, signing_key=key)
    verify(result.record, public_key_hex(key))


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
def test_health_names_what_this_deployment_can_verify():
    payload = client().get("/v1/health").json()
    assert payload["status"] == "ok" and payload["categories"] == [SCHEMA.category_id]
