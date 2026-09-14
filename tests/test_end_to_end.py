"""The whole path, once, in order: order event to a document a stranger can check.

    merchant order event
      -> surface/verification.py      the request, the order line, the comparison
      -> evaluator                    the deterministic decision
      -> receipts/store.py            sealed, chained, appended, checkpointed
      -> artifact/                    the document a returns desk reads
      -> scripts/verify_receipt.py    checked with a published key and none of our code

Four modules were built by four people against four readings of the same types, and
until this file nothing called them in sequence. Every other test in this repo exercises
one module with hand-made inputs for its neighbours; the defects that survive that are
exactly the ones that live between modules, where each side is individually right.

**What this file does not do.** It does not translate between modules to make a case
pass. Where two modules disagree the test says so out loud — `xfail(strict=True)` on the
behaviour that *should* hold, so the suite carries the seam as a known gap and fails the
day someone fixes it without removing the marker. A green test built on a private
adapter would hide the one thing this file exists to find. The seams are listed at the
bottom of this module.

**What this file deliberately avoids asserting.** The unread policy and the strict/lenient
floor are business parameters under active measurement (§2.6, DR 0021, DR 0022), so
nothing here pins a decision that a tuning change is allowed to move. What is pinned is
composition: that the record the store sealed is the record the document prints, and that
a stranger with the published key reaches the same conclusion.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from approv.artifact import build, render_html, render_text
from approv.artifact import language as lang
from approv.artifact import signature as artifact_signature
from approv.intake import FreeText, Reading, Search, Structured, Undeclared
from approv.receipts.chain import generate_key, public_key_hex
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore, ReplayError
from approv.schema import confirm_schema, propose_schema
from approv.surface.verification import (
    VerificationRequest, evidence_from_snapshot, verify_order,
)
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, ComparisonRecord, Constraint,
    Criticality, Decision, Dimension, FieldProfile, Liability, Money, OrderLine, Support,
    Term,
)

VERIFIER = Path("scripts/verify_receipt.py")

# --------------------------------------------------------------------------------------
# One merchant: a catalogue, a schema over it, and the orders an agent places
# --------------------------------------------------------------------------------------

CATALOGUE = {
    "duvet-tandem": {
        "product_id": "duvet-tandem",
        "title": "Tandem Stripe Duvet Cover",
        "variant": {"size": "King", "colour": "Frost"},
        "description": "Brushed cotton percale, woven in Portugal.",
    },
    # The near miss: the same product, one variant along. §7 puts this first in the attack
    # catalogue because it needs no attacker and dominates first-party catalogues.
    "duvet-tandem-stone": {
        "product_id": "duvet-tandem-stone",
        "title": "Tandem Stripe Duvet Cover",
        "variant": {"size": "King", "colour": "Stone"},
        "description": "Brushed cotton percale, woven in Portugal.",
    },
    # The merchant publishes no colour for this line at all. Not a mistake on anyone's
    # part, and the reason `confirm` exists.
    "duvet-halden": {
        "product_id": "duvet-halden",
        "title": "Halden Linen Duvet Cover",
        "variant": {"size": "King"},
        "description": "Washed linen.",
    },
}

SCHEMA = CategorySchema(
    category_id="bedding", version="merchant-authored-1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="colour", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="material", dimension=Dimension.NOMINAL,
                      criticality=Criticality.SOFT),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.colour", attributes=("colour",),
                     is_variant_axis=True, certainty=Certainty.EXACT,
                     liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="description", attributes=("material",),
                     certainty=Certainty.PARSED, liability=Liability.MERCHANT_GUARANTEED),
    ),
)


def extractor(*requirements, unread=()):
    """A stand-in for `harness/intent.py`, which needs a model and does not belong here.

    Free text is the case where the reading can be wrong, so the quote travels with each
    constraint — that is what the artifact prints as "read from the words", and what a
    structured call has none of.
    """
    def extract(text, schema):
        return Reading(
            constraints=tuple(
                Constraint(attribute=attribute, value=Term(surface=value),
                           channel=Channel.AGENT_MESSAGE, raw_text=quote)
                for attribute, value, quote in requirements),
            unread=tuple(unread))
    return extract


def order_for(product_id, **kw):
    base = dict(order_id="ORD-" + product_id, line_id="1", product_id=product_id,
                sku=product_id.upper() + "-KING", variant_id="v-king", quantity=2,
                unit_price=Money(amount="118.00", currency="USD"),
                availability="in_stock", catalogue_version="2026-09-13T08:00Z")
    return OrderLine(**{**base, **kw})


def place(store, key, *, correlation_id, product_id, artifact, extract=None, **kw):
    """One order, all the way through. The composition itself, in five lines.

    **`verify_order` is deliberately called without `signing_key`.** Both the surface and
    the store can seal, the store owns the chain head, and the surface does not know what
    it is — so a record sealed at the surface carries `prev_hash=None` and the store
    rejects it from the second receipt onward. Seam 2 below; the order here is the one
    that works.
    """
    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id=correlation_id,
            category_id="bedding", order=order_for(product_id, **kw), artifact=artifact,
            product_snapshot=dict(CATALOGUE[product_id])),
        schemas={"bedding": SCHEMA}, extract=extract)
    return store.append(result.record, key), result


@pytest.fixture(scope="module")
def merchant(tmp_path_factory):
    """One ledger carrying all three outcomes, built once and read by several tests."""
    directory = tmp_path_factory.mktemp("ledger")
    store = ReceiptStore(directory / "receipts.sqlite")
    key = generate_key()

    records = {}
    # 1. Allow. A protocol call: the agent filled in fields, so there is no wording and
    #    nothing was extracted.
    records["allow"], _ = place(
        store, key, correlation_id="corr-allow", product_id="duvet-tandem",
        artifact=Structured(protocol="acp", fields={"size": "King", "colour": "Frost"}))
    # 2. Refuse. Free text, read by an extractor, against the near-miss variant.
    records["refuse"], _ = place(
        store, key, correlation_id="corr-refuse", product_id="duvet-tandem-stone",
        artifact=FreeText(text="I need a king size duvet cover, it must be Frost."),
        extract=extractor(("size", "King", "a king size duvet cover"),
                          ("colour", "Frost", "it must be Frost")))
    # 3. Confirm. The request names a colour the merchant's own catalogue never publishes.
    records["confirm"], _ = place(
        store, key, correlation_id="corr-confirm", product_id="duvet-halden",
        artifact=Structured(protocol="acp", fields={"size": "King", "colour": "Ash"}))
    return {"store": store, "key": key, "public": public_key_hex(key), "records": records,
            "directory": directory}


def run_verifier(*arguments):
    done = subprocess.run([sys.executable, str(VERIFIER), *arguments],
                          capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def written(directory, name, payload):
    path = Path(directory) / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def run_printed_procedure(record: ComparisonRecord, public_key: str, directory) -> None:
    """Execute the instructions the artifact prints, against this record.

    Not a paraphrase of them: `artifact.signature.snippet` is the text on the page, and
    the page is what a merchant hands to a counterparty who has none of our code.
    """
    path = Path(directory) / (record.correlation_id + ".json")
    path.write_text(record.model_dump_json(), encoding="utf-8")
    exec(compile(artifact_signature.snippet(public_key, path.as_posix()),
                 "<printed instructions>", "exec"), {})


# --------------------------------------------------------------------------------------
# The three outcomes, each all the way to a document
# --------------------------------------------------------------------------------------


def test_an_authorised_order_arrives_at_a_document_that_names_what_is_covered(merchant):
    """The whole point of the path, in its ordinary case.

    An `allow` is the outcome a merchant sees most, and it is the one where overstating is
    easiest: the document must say which findings carry a promise without implying the
    order was checked in ways it was not.
    """
    record = merchant["records"]["allow"]
    document = build(record)

    assert record.decision is Decision.ALLOW
    assert record.order.sku == "DUVET-TANDEM-KING" and record.order.quantity == 2
    assert lang.GUARANTEED in record.coverage
    assert document.coverage_buckets[lang.GUARANTEED]

    text = render_text(record, public_key=merchant["public"])
    # The text rendering shouts the headline, so the comparison is against its own form.
    assert lang.headline(Decision.ALLOW, has_order=True).upper() in text
    assert "118.00 USD" in text and "236.00 USD" in text
    assert lang.COVERAGE_CAVEAT.split(".")[0] in " ".join(text.split())


def test_a_refusal_gives_a_returns_desk_the_two_values_it_has_to_compare(merchant):
    """What a refund argument actually turns on: what was asked for, what was sold, and
    which field of the merchant's own catalogue says so."""
    record = merchant["records"]["refuse"]
    document = build(record)
    colour = next(f for f in document.findings if f.attribute == "colour")

    assert record.decision is Decision.REFUSE
    assert record.decision_reasons == ("colour",)
    assert colour.verdict == "NOT MET"
    assert colour.asked_for == "Frost"
    assert any("Stone" in line and "variant.colour" in line for line in colour.catalogue)
    assert colour.coverage == lang.REFUSED

    text = " ".join(render_text(record).split())
    assert "it must be Frost" in text          # the requester's own words, quoted
    assert "Stone" in text                     # the merchant's own field, quoted


def test_an_order_the_catalogue_cannot_settle_confirms_and_promises_nothing(merchant):
    """`confirm` is not a third error, it is a different cost. The merchant published no
    colour for this line, so nobody is at fault and nothing about it is guaranteed."""
    record = merchant["records"]["confirm"]
    document = build(record)
    colour = next(f for f in document.findings if f.attribute == "colour")

    assert record.decision is Decision.CONFIRM
    assert colour.support is Support.UNSTATED
    assert colour.coverage != lang.GUARANTEED
    assert colour.catalogue_missing
    assert lang.headline(Decision.CONFIRM, has_order=True).upper() in render_text(record)


def test_all_three_outcomes_share_one_ledger_and_one_chain(merchant):
    """Three decisions, one append-only chain, checked as a sequence.

    Per-record signatures cannot see a deletion — every surviving record still verifies
    alone. Only the links notice, which is why the export is verified as a whole.
    """
    export = merchant["store"].export()
    assert [r["correlation_id"] for r in export["records"]] == [
        "corr-allow", "corr-refuse", "corr-confirm"]
    assert export["checkpoint"]["count"] == 3
    assert export["records"][0]["prev_hash"] is None
    assert all(later["prev_hash"] == earlier["hash"]
               for earlier, later in zip(export["records"], export["records"][1:]))


# --------------------------------------------------------------------------------------
# Two shapes of request, and the record saying which
# --------------------------------------------------------------------------------------


def test_a_protocol_call_and_free_text_produce_records_that_say_which_they_were(merchant):
    """The same engine, two fidelities, and the difference has to survive to the page.

    A protocol call has no wording to quote and nothing to mis-read; free text has both.
    DR 0020 makes that gradient the coverage policy, so a document that rendered them
    identically would hide the strongest thing the record knows about its own weight.
    """
    structured = build(merchant["records"]["allow"])
    prose = build(merchant["records"]["confirm"])
    free_text = build(merchant["records"]["refuse"])

    # Structured: every constraint arrived as a field, so the document says the quoted
    # line is nobody's words rather than presenting it as the requester's.
    for document in (structured, prose):
        assert document.request_text_note is not None
        assert all(requirement.quote is None for requirement in document.requirements)
        assert all("structured field" in requirement.provenance
                   for requirement in document.requirements)

    # Free text: the words are the requester's, and each requirement names the phrase it
    # was read from.
    assert free_text.request_text_note is None
    assert all(requirement.quote for requirement in free_text.requirements)
    assert all("free-text message" in requirement.provenance
               for requirement in free_text.requirements)


def test_the_channel_survives_into_the_signed_record_not_only_the_rendering(merchant):
    """The rendering is allowed to change; the record is not. Channel is what a later
    dispute reads, so it is asserted on the signed object as well as on the page."""
    assert {c.channel for c in merchant["records"]["allow"].request_constraints} == {
        Channel.TOOL_ARGUMENT}
    assert {c.channel for c in merchant["records"]["refuse"].request_constraints} == {
        Channel.AGENT_MESSAGE}


# --------------------------------------------------------------------------------------
# The document against the record it was built from
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["allow", "refuse", "confirm"])
def test_the_document_says_exactly_what_the_signed_record_says(merchant, outcome):
    """The cross-check between module four and the other three.

    The artifact reads the sealed decision and the sealed coverage rather than recomputing
    either, which is only worth anything if it is checked: a page that disagreed with the
    record it prints would be discovered in a dispute rather than here. Compared as
    multisets because a record may carry several findings for one attribute.
    """
    record = merchant["records"][outcome]
    document = build(record)

    printed = sorted((row.attribute, row.coverage) for row in document.findings)
    sealed = sorted((lang.attribute(f.attribute), c)
                    for f, c in zip(record.findings, record.coverage))
    assert printed == sealed
    assert document.headline == lang.headline(record.decision, has_order=True)
    assert len(document.findings) == len(record.findings)


@pytest.mark.parametrize("outcome", ["allow", "refuse", "confirm"])
def test_both_renderings_survive_a_record_that_came_back_out_of_the_ledger(merchant,
                                                                          outcome):
    """The store returns a record rebuilt from stored JSON, not the object handed to it.

    A field that survives Pydantic on the way in and not on the way out would show up here
    and nowhere else, because every other test renders an object that never left memory.
    """
    stored = merchant["records"][outcome]
    assert stored.hash and stored.signature and stored.key_id
    assert len(render_text(stored)) > 2000
    assert render_html(stored).startswith("<!doctype html>")


# --------------------------------------------------------------------------------------
# A stranger, a published key, and none of our code
# --------------------------------------------------------------------------------------


def test_a_stranger_verifies_the_whole_export_with_the_published_keys(merchant):
    """§10's bar, run as a subprocess so nothing of ours is in the verifier's process."""
    directory = merchant["directory"]
    export = written(directory, "export.json", merchant["store"].export())
    keys = written(directory, "keys.json", merchant["store"].public_keys())

    code, output = run_verifier(export, "--keys", keys)
    assert code == 0, output
    assert "chain intact" in output
    for correlation in ("corr-allow", "corr-refuse", "corr-confirm"):
        assert correlation in output


def test_the_procedure_printed_on_the_document_verifies_the_record_it_is_printed_on(
        merchant, tmp_path):
    """The document's own instructions, executed, for each outcome.

    `scripts/verify_receipt.py` is one published procedure and the artifact prints
    another. If they disagree we have published two standards and a counterparty can
    reach two answers, so both are run against the same records.
    """
    for record in merchant["records"].values():
        run_printed_procedure(record, merchant["public"], tmp_path)


def test_the_two_published_procedures_reach_the_same_answer(merchant, tmp_path):
    """`scripts/verify_receipt.py` and the artifact print two procedures for one record.

    They have to agree in both directions or a counterparty can pick the answer that
    suits them. Checked on a record that is genuine and on the same record offered up
    under a key that did not sign it.
    """
    record = merchant["records"]["allow"]
    path = written(tmp_path, "one.json", json.loads(record.model_dump_json()))
    stranger = public_key_hex(generate_key())

    code, _ = run_verifier(path, "--key", merchant["public"])
    assert code == 0
    run_printed_procedure(record, merchant["public"], tmp_path)

    code, output = run_verifier(path, "--key", stranger)
    assert code == 1 and "does not verify" in output
    with pytest.raises(AssertionError):
        exec(compile(artifact_signature.snippet(stranger, Path(path).as_posix()),
                     "<printed instructions>", "exec"), {})


def test_an_edited_field_is_caught_by_the_procedure_on_the_page(merchant, tmp_path):
    """Every field a dispute would turn on, edited one at a time.

    The decision, the price and the coverage class are the three a party with something
    to gain would move, and coverage is on the list because it is the field this document
    presents as a promise.
    """
    record = merchant["records"]["refuse"]
    path = tmp_path / "edited.json"
    for field, value in (("decision", "allow"),
                         ("coverage", ["guaranteed", "guaranteed", "guaranteed"]),
                         ("correlation_id", "corr-someone-elses")):
        payload = json.loads(record.model_dump_json())
        payload[field] = value
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(AssertionError, match="altered since it was signed"):
            exec(compile(artifact_signature.snippet(merchant["public"], path.as_posix()),
                         "<printed instructions>", "exec"), {})

    payload = json.loads(record.model_dump_json())
    payload["order"]["unit_price"]["amount"] = "18.00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AssertionError, match="altered since it was signed"):
        exec(compile(artifact_signature.snippet(merchant["public"], path.as_posix()),
                     "<printed instructions>", "exec"), {})


def test_a_deleted_receipt_passes_every_per_record_check_and_fails_the_chain(merchant,
                                                                            tmp_path):
    """The insider case the chain exists for, end to end.

    Dropping the refusal leaves two records that each verify perfectly. If the only check
    were per record, the one decision that cost a sale could be made to disappear.
    """
    export = merchant["store"].export()
    survivors = [export["records"][0], export["records"][2]]
    keys = written(tmp_path, "keys.json", merchant["store"].public_keys())

    for record in survivors:
        code, output = run_verifier(written(tmp_path, "one.json", record), "--keys", keys)
        assert code == 0, output

    code, output = run_verifier(written(tmp_path, "gap.json", survivors), "--keys", keys)
    assert code == 1
    assert "removed, reordered or inserted" in output


def test_rotation_leaves_every_earlier_receipt_verifiable(tmp_path):
    """A key rotated after a receipt was signed must not invalidate it.

    The whole value of the record is that it survives to a dispute, and disputes outlive
    key rotations. Run through `KeyStore` rather than raw keys because publication is the
    part a stranger depends on: the file they are handed has to carry the retired key.
    """
    keystore = KeyStore(tmp_path / "keys", password=b"not-the-real-password")
    store = ReceiptStore(tmp_path / "receipts.sqlite")
    first_id = keystore.rotate()
    store.append(place_record(correlation_id="corr-before"), keystore.load_private())
    second_id = keystore.rotate()
    assert second_id != first_id
    store.append(place_record(correlation_id="corr-after"), keystore.load_private())

    published = keystore.publish(tmp_path / "published-keys.json")
    export = written(tmp_path, "export.json", store.export())
    code, output = run_verifier(export, "--keys", str(published))
    assert code == 0, output

    signed_by = [record["key_id"] for record in store.export()["records"]]
    assert signed_by == [first_id, second_id]


def place_record(*, correlation_id, colour="Frost"):
    """One unsigned record, for tests that care about the ledger rather than the decision.

    `colour` varies the content without varying the join key, so a test can tell a
    *different decision* under one correlation id apart from an identical retry of the
    same one. Those are opposite requirements and conflating them is what made seam 3
    unfixable without editing this file.
    """
    return verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id=correlation_id,
            category_id="bedding", order=order_for("duvet-tandem"),
            artifact=Structured(protocol="acp",
                                fields={"size": "King", "colour": colour}),
            product_snapshot=dict(CATALOGUE["duvet-tandem"])),
        schemas={"bedding": SCHEMA}).record


def test_the_ledger_refuses_a_second_decision_under_one_correlation_id(tmp_path):
    """The join key to the agent's half is also the key a replay would reuse.

    A *different* record under an existing correlation id is the attack: swapping one
    decision for another beneath a key the agent already signed against. An identical
    retry is not -- that is a merchant whose first call timed out, and seam 3 requires it
    to return the receipt already written. This test pins the first and says nothing
    about the second.
    """
    store = ReceiptStore(tmp_path / "receipts.sqlite")
    key = generate_key()
    store.append(place_record(correlation_id="corr-one"), key)
    with pytest.raises(ReplayError):
        store.append(place_record(correlation_id="corr-one", colour="Stone"), key)


# --------------------------------------------------------------------------------------
# The seams
#
# Each of these asserts the behaviour that *should* hold across a module boundary, and
# each fails today. `strict=True` means the day one is fixed this file fails until the
# marker is removed, so a fix cannot land silently and the list cannot rot into folklore.
# --------------------------------------------------------------------------------------


def test_a_derived_schema_reads_the_catalogue_it_was_derived_from():
    """Onboarding's output has to be the surface's input, or onboarding onboards nothing.

    Was seam 1, cleared by a15c548: the resolver walks the pointer paths onboarding
    actually emits, and a schema whose paths read nothing now aborts as
    CATALOGUE_UNREADABLE instead of confirming every order in silence. Kept as a
    regression test, because the failure it guards against was invisible — no exception,
    no log line, just a deployment that looked cautious and was disconnected.
    """
    catalogue = [
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
    proposal = propose_schema(catalogue, category_id="bedding.duvets", currency="USD")
    confirmed = confirm_schema(proposal, reviewer="founder",
                               expected_proposal_id=proposal.proposal_id,
                               floor=proposal.proposed_schema.floor)

    evidence = evidence_from_snapshot(catalogue[0], confirmed.category_schema)
    assert evidence, "a schema derived from this catalogue reads nothing from it"


def test_the_surface_hands_the_ledger_an_unsealed_record(tmp_path):
    """One owner for sealing, and it is the one that knows the chain head.

    Was seam 2, cleared by a5b4134: `verify_order` no longer takes a signing key at all,
    which is the version of the fix that cannot be got wrong — a caller cannot pass one by
    accident. Kept as a regression test because the failure arrived on the *second* order,
    where a smoke test would not have found it.
    """
    store = ReceiptStore(tmp_path / "receipts.sqlite")
    key = generate_key()
    import inspect
    assert "signing_key" not in inspect.signature(verify_order).parameters

    for correlation in ("corr-one", "corr-two", "corr-three"):
        result = verify_order(
            VerificationRequest(
                merchant_id="hearth-and-loom", correlation_id=correlation,
                category_id="bedding", order=order_for("duvet-tandem"),
                artifact=Structured(protocol="acp",
                                    fields={"size": "King", "colour": "Frost"}),
                product_snapshot=dict(CATALOGUE["duvet-tandem"])),
            schemas={"bedding": SCHEMA})
        assert result.record.hash is None and result.record.signature is None
        sealed = store.append(result.record, key)
        assert sealed.hash and sealed.signature

    assert len(store.export()["records"]) == 3


def test_a_retried_verification_returns_the_receipt_it_already_wrote(tmp_path):
    """Idempotent retry is built, and unreachable from the only public entry point.

    This is what a merchant does when the first call times out: same correlation id, same
    order, same catalogue, seconds later.
    """
    store = ReceiptStore(tmp_path / "receipts.sqlite")
    key = generate_key()
    first = store.append(place_record(correlation_id="corr-retry"), key)
    second = store.append(place_record(correlation_id="corr-retry"), key)
    assert first.hash == second.hash


def test_an_order_whose_channel_earns_no_coverage_guarantees_nothing():
    """The two coverage notions have to agree on the page, or one of them is a lie.

    Was seam 4, cleared by DR 0023: `covered` and `coverage_notes` are fields of the
    record now, inside the digest, and `coverage_of` withdraws the guarantee when the
    channel earned none. Kept as a regression test, and extended to assert the verdict
    survives onto the record rather than only into the per-finding classes.

    An on-site search with no agent detection is out of coverage as a channel: DR 0020
    makes the declaration the thing coverage attaches to. The findings underneath are
    perfectly good comparisons and `coverage_of` marks them guaranteed, because per-finding
    coverage has never been told about channel eligibility.

    This is the exact failure the dispute artifact exists to prevent — a returns desk
    reading a promise Approv explicitly declined to make — arriving from outside the module
    that prints it, through a field it cannot see.
    """
    def extract(text, schema):
        return Reading(constraints=(
            Constraint(attribute="size", value=Term(surface="King"),
                       channel=Channel.AGENT_MESSAGE, raw_text="king"),))

    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id="corr-search",
            category_id="bedding", order=order_for("duvet-tandem"),
            artifact=Search(query="king duvet frost"),
            product_snapshot=dict(CATALOGUE["duvet-tandem"])),
        schemas={"bedding": SCHEMA}, extract=extract)

    assert result.covered is False, "this channel is out of coverage by intake's own rule"
    assert result.record.covered is False, "and the record has to carry it"
    assert result.record.coverage_notes, "with the reason, or it cannot be explained"
    document = build(result.record)
    guaranteed = [row.attribute for row in document.findings
                  if row.coverage == lang.GUARANTEED]
    assert not guaranteed, (
        "the document promises %s on an order intake ruled out of coverage" % guaranteed)


def test_a_filter_and_a_query_that_agree_are_corroboration_not_a_conflict():
    """The second fidelity tier of DR 0020, made unusable by a rule written for the first.

    A shopper who types "king duvet" into the box and ticks the King filter has stated the
    same requirement on two channels at once. That is the strongest evidence in the record
    that they meant King, and it currently produces the weakest outcome available: both
    findings UNSTATED at confidence 0.0, the attribute unresolved, the order escalated.

    The rule is right for what it was written for — an agent asserting two different values
    for one attribute is a real conflict nobody can resolve. It does not check whether the
    two values differ.
    """
    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id="corr-search-agrees",
            category_id="bedding", order=order_for("duvet-tandem"),
            artifact=Search(query="king duvet in frost", filters={"size": "King"}),
            product_snapshot=dict(CATALOGUE["duvet-tandem"])),
        schemas={"bedding": SCHEMA},
        extract=extractor(("size", "King", "king duvet"),
                          ("colour", "Frost", "in frost")))

    stated = [c for c in result.record.request_constraints if c.attribute == "size"]
    assert len(stated) == 2, "the filter and the query both state size"
    assert len({c.value.surface for c in stated}) == 1, "and they agree"

    size = [f for f in result.record.findings if f.attribute == "size"]
    assert not any(f.support is Support.UNSTATED for f in size), (
        "two agreeing statements of one attribute left it unresolved: %s"
        % [(f.support.value, [r.value for r in f.reasons]) for f in size])


@pytest.mark.xfail(strict=True, reason=(
    "SEAM 7: `verify_order` returns an `OrderEvidenceRecord` for cart-only traffic and "
    "`ReceiptStore.append_many` accepts only a `ComparisonRecord` (`require_unsealed` "
    "raises TypeError), so the one receipt product built for orders with no stated "
    "request cannot be sealed, chained or verified at all. The type and the surface path "
    "landed; the ledger has not been told about them. Found by running the backtest over "
    "an export whose requests file leaves rows undeclared."))
def test_an_order_with_no_stated_request_can_be_sealed_like_any_other_receipt(tmp_path):
    """The cart-only receipt is a receipt or it is nothing.

    Its whole claim is that it is "signed and chained like any other receipt" - that is
    the sentence on the type and the sentence the artifact prints. Until the store accepts
    it, the population DR 0020 most wants measured produces evidence that cannot go in the
    evidence chain, and a backtest either drops those orders or reports them outside the
    ledger it asks the partner to check.
    """
    store = ReceiptStore(tmp_path / "receipts.sqlite")
    result = verify_order(
        VerificationRequest(
            merchant_id="hearth-and-loom", correlation_id="corr-cart-only",
            category_id="bedding", order=order_for("duvet-tandem"),
            artifact=Undeclared(),
            product_snapshot=dict(CATALOGUE["duvet-tandem"])),
        schemas={"bedding": SCHEMA})

    assert result.record.kind == "order_evidence", "cart-only is its own product"
    sealed = store.append(result.record, generate_key())
    assert sealed.hash and sealed.signature


# The open seams, by test name. Named rather than counted so that clearing one is a
# single legible edit by whoever fixed it, instead of a hardcoded number that blocks the
# fix it was meant to protect. Removing a name here is as loud as changing a count was.
#
# Empty: every seam this file found has been fixed by its owner. Seams 1, 2, 4 and 6 were
# cleared earlier; 3 (retry identity) and 5 (agreeing duplicate claims) were cleared in the
# same round, which is why this set met itself in a merge conflict. An empty set is the
# strongest state it can be in and the easiest to regress -- adding a name back means a
# module pair has started disagreeing again.
OPEN_SEAMS = {
    "test_an_order_with_no_stated_request_can_be_sealed_like_any_other_receipt",  # seam 7, claude1 (type) and codex1 (store)
}



def test_the_seams_are_the_only_known_gaps():
    """A roll-call, so a seam cannot be quietly deleted along with its marker.

    If a seam is fixed, its `xfail(strict=True)` fails and the marker comes off, and the
    name comes out of OPEN_SEAMS. If one is *removed* rather than fixed, this set stops
    matching and says so. The names are the claim.
    All six seams have now been cleared by their owners and their tests stayed on as
    regressions -- which is what the strict marker is for: a fix cannot land silently,
    and neither can a seam being deleted instead of fixed.
    """
    marked = {name: obj for name, obj in vars(sys.modules[__name__]).items()
              if callable(obj) and any(mark.name == "xfail"
                                       for mark in getattr(obj, "pytestmark", ()))}
    assert set(marked) == OPEN_SEAMS, sorted(set(marked) ^ OPEN_SEAMS)
    assert all("SEAM" in obj.pytestmark[0].kwargs["reason"] for obj in marked.values())
    assert all(obj.pytestmark[0].kwargs["strict"] for obj in marked.values())
