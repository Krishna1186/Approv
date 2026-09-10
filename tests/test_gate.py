"""The gate: the one call site where a finding stops something.

`mark` badges results and `verify` advises an agent. Neither has consequence. This is
the call site the company is actually about — refuse before the debit fires — and it is
scored separately from the other two, because a lost sale and a missed catch are not the
same error (section 2.6, invariant 7).
"""
from datetime import datetime, timezone

import pytest

from approv.harness.shopping import (
    Action, Arm, Inventory, RunConfig, Session, ShoppingCase, replay, verify_trace,
)
from approv.receipts.chain import generate_key, public_key_hex, verify, verify_chain
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Decision,
    Dimension, Evidence, FieldProfile, Liability, Term,
)

SCHEMA = CategorySchema(
    category_id="test", version="1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
    ),
    # Without a profile every field is an untrusted source and nothing compares, so the
    # gate would confirm on silence rather than refuse on a contradiction. That is the
    # correct behaviour and it made this fixture look like a broken gate.
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ),
)


def product(pid, size=None):
    from approv.harness.shopping import Product
    evidence = ()
    if size is not None:
        evidence = (Evidence(attribute="size", value=Term(surface=size),
                             field_name="variant.size", certainty=Certainty.EXACT,
                             liability=Liability.MERCHANT_GUARANTEED),)
    return Product(id=pid, title="Item " + pid, evidence=evidence, details={"title": pid})


def inventory(*products):
    return Inventory(source="test", source_license="test",
                     captured_at=datetime.now(timezone.utc), schema=SCHEMA,
                     products=products)


def case():
    return ShoppingCase(id="c1", request="size M please", author="test", cluster="t",
                        constraints=(Constraint(attribute="size", value=Term(surface="M"),
                                                channel=Channel.AGENT_MESSAGE),))


def gate_session(inv, key_hex=None, review_rounds=0):
    """review_rounds=0 so the gate fires on the first select.

    The gate sits *after* the review branch on purpose: advise first, gate last. With the
    default single review round a select is answered with feedback and the agent gets one
    chance to change its mind before anything is decided. Tested separately below.
    """
    return Session(inv, case(), Arm.APPROV,
                   RunConfig(surface="gate", receipt_key_hex=key_hex,
                             review_rounds=review_rounds))


def test_the_gate_refuses_a_contradicted_purchase_instead_of_advising_against_it():
    session = gate_session(inventory(product("wrong", "S")))
    session.step(Action(type="search"))
    result = session.step(Action(type="select", product_id="wrong"))

    assert result["status"] == "refused"
    assert result["decision"] == "refuse"
    assert result["reasons"] == ["size"]
    assert session.selection is None


def test_the_gate_allows_a_satisfied_purchase():
    session = gate_session(inventory(product("right", "M")))
    session.step(Action(type="search"))
    result = session.step(Action(type="select", product_id="right"))

    assert result["status"] == "selected"
    assert result["decision"] == "allow"
    assert session.selection == {"product_id": "right", "units": 1}


def test_silence_confirms_and_does_not_authorise():
    """Invariant 4 at the call site that spends money. A listing that publishes nothing
    about the attribute is not a listing that satisfies it."""
    session = gate_session(inventory(product("silent")))
    session.step(Action(type="search"))
    result = session.step(Action(type="select", product_id="silent"))

    assert result["decision"] == "confirm"
    # Confirm is not refuse: the purchase is not blocked, it is escalated.
    assert result["status"] == "selected"


def test_a_refusal_is_recorded_as_a_first_class_outcome():
    """A refusal that leaves no trace is indistinguishable from a session that never
    happened, and refusals are the expensive half of section 2.6."""
    session = gate_session(inventory(product("wrong", "S")))
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="wrong"))

    assert len(session.receipts) == 1
    assert session.receipts[0].decision is Decision.REFUSE
    decisions = [e for e in session.events if e["kind"] == "decision"]
    assert len(decisions) == 1
    assert decisions[0]["payload"]["reasons"] == ["size"]
    verify_trace(session.result())


def test_the_record_carries_completeness_from_a_live_session():
    session = gate_session(inventory(product("right", "M")))
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="right"))

    record = session.receipts[0]
    assert record.completeness == ("color",)
    assert record.request_text == "size M please"
    assert record.product_snapshot["title"] == "Item right"


def test_receipts_from_a_live_session_verify_and_chain():
    key = generate_key()
    key_hex = key.private_bytes_raw().hex()
    inv = inventory(product("wrong", "S"), product("right", "M"))
    session = Session(inv, case(), Arm.APPROV,
                      RunConfig(surface="gate", receipt_key_hex=key_hex, review_rounds=0))
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="wrong"))

    assert session.status == "refused"
    for record in session.receipts:
        verify(record, public_key_hex(key))
    verify_chain(session.receipts, public_key_hex(key))


def test_an_unkeyed_session_still_decides_and_still_records():
    """Without a key the record stays unsigned, which is the honest state. It makes the
    decision path exercisable without inventing a keypair per session."""
    session = gate_session(inventory(product("wrong", "S")))
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="wrong"))

    assert session.receipts[0].decision is Decision.REFUSE
    assert session.receipts[0].signature is None


def test_a_gated_session_replays_exactly():
    """The decision is a side effect of the action that produced it, so it has to
    reproduce. One step now appends three events, which is what broke the old
    compare-against-the-last-event replay."""
    inv = inventory(product("wrong", "S"))
    session = gate_session(inv)
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="wrong"))
    replay(session.result(), inv, case())


def test_mark_and_verify_do_not_gate():
    """Only the gate has consequence. The other two call sites advise."""
    for surface in ("mark", "verify"):
        session = Session(inventory(product("wrong", "S")), case(), Arm.APPROV,
                          RunConfig(surface=surface, review_rounds=0))
        session.step(Action(type="search"))
        result = session.step(Action(type="select", product_id="wrong"))
        assert result["status"] == "selected", surface
        assert session.receipts == [], surface


def test_the_review_round_comes_before_the_gate():
    """Advise first, gate last. The agent gets one chance to change its mind, and nothing
    is decided or recorded until it has taken or declined it. This is the "do not keep
    probing" rule made structural: one round, then a verdict."""
    session = gate_session(inventory(product("wrong", "S"), product("right", "M")),
                           review_rounds=1)
    session.step(Action(type="search"))

    advised = session.step(Action(type="select", product_id="wrong"))
    assert advised["status"] == "review"
    assert session.receipts == [], "nothing is decided during the advisory round"

    changed = session.step(Action(type="select", product_id="right"))
    assert changed["status"] == "selected" and changed["decision"] == "allow"
    assert len(session.receipts) == 1, "exactly one decision per session"


def test_the_agent_gets_one_round_not_a_conversation():
    """A second refusal is final. Re-probing until the agent stumbles onto an allow would
    make the gate a search procedure run by the thing being checked."""
    session = gate_session(inventory(product("wrong", "S")), review_rounds=1)
    session.step(Action(type="search"))
    assert session.step(Action(type="select", product_id="wrong"))["status"] == "review"
    final = session.step(Action(type="select", product_id="wrong"))
    assert final["status"] == "refused"
