"""The record, the chain, and the tampering each is supposed to catch."""
import json
from datetime import datetime, timezone

import pytest

from approv.receipts.chain import (
    generate_key, public_key_hex, record_hash, seal, verify, verify_chain,
)
from approv.criticality import GUARANTEED, OUT_OF_COVERAGE
from approv.types.core import COVERAGE_GAP_PREFIX, UnreadPolicy, dropped_requirement
from approv.receipts.record import build_record, completeness, floor_is_met
from approv.types.core import (
    AttributeSpec, CategorySchema, Channel, CheckKind, Constraint, Criticality,
    Decision, Dimension, Finding, ReasonCode, Support, Term,
)

SCHEMA = CategorySchema(
    category_id="footwear", version="1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
    ),
    field_profiles=(),
)


def constraint(attribute, surface):
    return Constraint(attribute=attribute, value=Term(surface=surface),
                      channel=Channel.AGENT_MESSAGE)


def finding(attribute, support, confidence=1.0, criticality=Criticality.HARD, reasons=()):
    return Finding(check=CheckKind.SATISFACTION, attribute=attribute, criticality=criticality,
                   support=support, confidence=confidence, ceiling=1.0, reasons=reasons)


def record(findings=None, constraints=None, **kw):
    return build_record(
        correlation_id=kw.pop("correlation_id", "sess-1"),
        request_text="Chelsea boots in dark blue, size 9.",
        constraints=constraints if constraints is not None else (constraint("size", "9"),),
        findings=findings if findings is not None else (finding("size", Support.SATISFIED),),
        schema=SCHEMA, product_id="sku-1",
        product_snapshot={"title": "Magut", "size": "9"}, snapshot_hash="abc123",
        model_version="m-1", prompt_version="p-1",
        timestamp=datetime(2026, 9, 10, tzinfo=timezone.utc), **kw)


# --- what `unread` means, and it means one thing -----------------------------------------

def test_unread_is_a_dropped_requirement_and_not_merely_a_note():
    """DR 0021. `unread` feeds the verification floor, so two definitions of it meant two
    different decision paths. These four are the cases that separated them on the v3 pack.

    The supersession is the one that settles it: the extractor read the correction
    perfectly and logged what it discarded. Counting that as an unread request escalates a
    shopper for having changed their mind.
    """
    assert dropped_requirement(COVERAGE_GAP_PREFIX + "tandem stripe")
    assert dropped_requirement("Unsupported requirement: gift_wrap")
    assert not dropped_requirement("Superseded, discarded: Black (color)")
    assert not dropped_requirement("My last order took forever to arrive.")


# --- narrowing: the guarantee withdrawn where the reading did not finish ----------------

def test_a_narrowed_requirement_is_authorised_but_not_guaranteed():
    """The third option the floor did not contain, wired end to end.

    Before coverage existed the only lever for a partly-read requirement was the floor,
    which had to choose between escalating the sale (0.0% false allow at 48.4% nuisance)
    and guaranteeing it anyway (0.3% at 3.3%). Routing the affected attribute out of
    coverage is neither: the decision is untouched, so nuisance cannot move, and the
    record promises nothing about words it did not finish reading.
    """
    narrowed = Constraint(attribute="color", value=Term(surface="Frost"),
                          channel=Channel.AGENT_MESSAGE,
                          raw_text="a Tandem Stripe in Frost")
    built = record(
        findings=(finding("size", Support.SATISFIED),
                  finding("color", Support.SATISFIED)),
        constraints=(constraint("size", "9"), narrowed),
        unread=(COVERAGE_GAP_PREFIX + "tandem stripe",),
        unread_policy=UnreadPolicy.IGNORE)

    covered = dict(zip((f.attribute for f in built.findings), built.coverage))
    assert covered == {"size": GUARANTEED, "color": OUT_OF_COVERAGE}
    assert built.decision is Decision.ALLOW


def test_narrowing_is_computed_from_the_record_rather_than_passed_in():
    """A caller that has to remember to pass it is a caller that will forget. `unread` is
    already the record's account of what went unread, so this reads that rather than
    asking for the same fact twice — the wiring failure coverage itself had the first
    time round."""
    import inspect
    assert "narrowed" not in inspect.signature(build_record).parameters


# --- completeness: the field that makes fault attributable -----------------------------

def test_completeness_names_what_the_request_was_silent_on():
    """Section 2.2. Request named it and the product violates it: the agent's fault, and
    coverable. Request was silent: nobody's fault. Neither can be established without
    this field, however accurate the findings are."""
    assert completeness(SCHEMA, (constraint("size", "9"),)) == ("brand", "color")
    assert completeness(SCHEMA, ()) == ("brand", "color", "size")
    every = tuple(constraint(a, "x") for a in ("size", "color", "brand"))
    assert completeness(SCHEMA, every) == ()


def test_completeness_is_silence_not_failure():
    """An attribute the request named and we could not check is a finding with a reason
    code. An attribute nobody mentioned is completeness. Collapsing them would let a
    coverable miss hide inside a claim that the request was vague."""
    stated = record(constraints=(constraint("size", "9"),),
                    findings=(finding("size", Support.UNSTATED, 0.0),))
    assert "size" not in stated.completeness
    assert stated.decision is Decision.CONFIRM


# --- the decision comes from the evaluator and nowhere else ----------------------------

def test_the_record_carries_the_evaluator_decision_and_its_named_attributes():
    sealed = record(findings=(finding("size", Support.VIOLATED),
                              finding("color", Support.SATISFIED)))
    assert sealed.decision is Decision.REFUSE
    assert sealed.decision_reasons == ("size",)
    assert sealed.evaluator_version


def test_an_unmet_floor_confirms_through_the_record():
    floored = SCHEMA.model_copy(update={"floor": frozenset({"size"})})
    findings = (finding("size", Support.UNSTATED, 0.0, reasons=(ReasonCode.FLOOR_NOT_MET,)),)
    assert not floor_is_met(findings)
    built = build_record(
        correlation_id="c", request_text="boots", constraints=(), findings=findings,
        schema=floored, product_id="p", product_snapshot={}, snapshot_hash="h",
        model_version="m", prompt_version="p")
    assert built.decision is Decision.CONFIRM


def test_unknown_never_authorises_through_this_path():
    """Section 2.3 and invariant 4, asserted where decisions are actually issued."""
    for support, confidence in ((Support.UNSTATED, 0.0), (Support.SATISFIED, 0.9)):
        built = record(findings=(finding("size", support, confidence),))
        assert built.decision is not Decision.ALLOW


# --- the record holds the request ------------------------------------------------------

def test_the_record_holds_the_stated_request_with_the_chosen_product():
    """Section 1's entire claim. Findings carry one constraint each, which recovers only
    the attributes that produced a finding, so neither the shopper's words nor the full
    set of requirements survived until these fields existed."""
    built = record(constraints=(constraint("size", "9"), constraint("color", "dark blue")),
                   findings=(finding("size", Support.SATISFIED),))
    assert built.request_text == "Chelsea boots in dark blue, size 9."
    assert {c.attribute for c in built.request_constraints} == {"size", "color"}
    assert built.product_id == "sku-1"
    assert built.product_snapshot["title"] == "Magut"


# --- sealing and verification ----------------------------------------------------------

def test_a_sealed_record_verifies_under_its_public_key():
    key = generate_key()
    sealed = seal(record(), key)
    verify(sealed, public_key_hex(key))
    assert sealed.hash and sealed.signature and sealed.prev_hash is None


def test_an_unsealed_record_is_not_verifiable():
    with pytest.raises(ValueError, match="unsealed"):
        verify(record(), public_key_hex(generate_key()))


def test_editing_a_sealed_record_breaks_it():
    """The threat is us, after the outcome is known: turning a confirm we issued into
    the allow that a dispute needs."""
    key = generate_key()
    sealed = seal(record(findings=(finding("size", Support.UNSTATED, 0.0),)), key)
    assert sealed.decision is Decision.CONFIRM
    forged = sealed.model_copy(update={"decision": Decision.ALLOW})
    with pytest.raises(ValueError, match="does not match its hash"):
        verify(forged, public_key_hex(key))


def test_a_record_signed_by_another_key_does_not_verify():
    sealed = seal(record(), generate_key())
    with pytest.raises(ValueError, match="does not verify"):
        verify(sealed, public_key_hex(generate_key()))


def test_the_signature_covers_the_link():
    """If prev_hash sat outside the signature, a record could be lifted out of one chain
    and pasted into another with its signature still valid."""
    key = generate_key()
    sealed = seal(record(), key, prev_hash="aaaa")
    relinked = sealed.model_copy(update={"prev_hash": "bbbb"})
    with pytest.raises(ValueError, match="does not match its hash"):
        verify(relinked, public_key_hex(key))


# --- the chain -------------------------------------------------------------------------

def chain_of(key, n=3):
    out, previous = [], None
    for i in range(n):
        sealed = seal(record(correlation_id="sess-%d" % i), key, prev_hash=previous)
        out.append(sealed)
        previous = sealed.hash
    return out


def test_an_intact_chain_verifies_end_to_end():
    key = generate_key()
    verify_chain(chain_of(key), public_key_hex(key))


def test_deleting_a_record_is_caught_although_every_survivor_still_verifies():
    """Why the chain is checked as a sequence. A refusal that cost a sale can be dropped
    without touching any remaining signature; only the links notice."""
    key = generate_key()
    records = chain_of(key)
    truncated = records[:1] + records[2:]
    for item in truncated:
        verify(item, public_key_hex(key))
    with pytest.raises(ValueError, match="chain broken"):
        verify_chain(truncated, public_key_hex(key))


def test_reordering_is_caught():
    key = generate_key()
    records = chain_of(key)
    with pytest.raises(ValueError, match="chain broken"):
        verify_chain([records[1], records[0], records[2]], public_key_hex(key))


def test_a_reused_correlation_id_is_a_replay():
    key = generate_key()
    first = seal(record(correlation_id="same"), key)
    second = seal(record(correlation_id="same"), key, prev_hash=first.hash)
    with pytest.raises(ValueError, match="correlation id reused"):
        verify_chain([first, second], public_key_hex(key))


# --- the bytes a stranger has to reproduce ---------------------------------------------

def test_the_sealed_record_round_trips_through_json():
    """Section 10's bar is a stranger verifying with a public key and none of our code,
    so the record has to survive JSON exactly. An undiscriminated union, or a Decimal
    rendered as a float, would deserialise to a different object and hash differently."""
    key = generate_key()
    sealed = seal(record(), key)
    restored = type(sealed).model_validate(json.loads(sealed.model_dump_json()))
    assert record_hash(restored, restored.prev_hash) == sealed.hash
    verify(restored, public_key_hex(key))


# --- the definition of done: a stranger, a public key, none of our code ----------------

def _write_chain(tmp_path, n=3):
    """A chain of `confirm` records.

    Confirm on purpose: the tampering these tests model is ours, after the outcome is
    known, turning a confirm we issued into the allow a dispute needs. An earlier version
    of this fixture sealed `allow` records and then "tampered" the decision to "allow",
    which changed nothing and passed while proving nothing.
    """
    key = generate_key()
    records, previous = [], None
    for i in range(n):
        unresolved = (finding("size", Support.UNSTATED, 0.0),)
        sealed = seal(record(correlation_id="sess-%d" % i, findings=unresolved),
                      key, prev_hash=previous)
        assert sealed.decision is Decision.CONFIRM
        records.append(sealed)
        previous = sealed.hash
    path = tmp_path / "receipts.json"
    path.write_text("[" + ",".join(r.model_dump_json() for r in records) + "]",
                    encoding="utf-8")
    return path, public_key_hex(key), records


def _run_verifier(path, key_hex):
    import subprocess, sys
    return subprocess.run([sys.executable, "scripts/verify_receipt.py", str(path),
                           "--key", key_hex], capture_output=True, text=True)


def test_the_standalone_verifier_accepts_a_real_chain(tmp_path):
    """Section 10, stage D. Run as a subprocess so nothing of ours is in its process."""
    path, key_hex, _ = _write_chain(tmp_path)
    done = _run_verifier(path, key_hex)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "chain intact" in done.stdout


def test_the_standalone_verifier_imports_nothing_of_ours():
    """If it imported approv it would prove only that we agree with ourselves."""
    import ast, pathlib
    source = pathlib.Path("scripts/verify_receipt.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
    assert not {m for m in imported if m == "approv"}
    assert imported <= {"argparse", "hashlib", "json", "sys", "cryptography", "__future__"}


def test_the_standalone_verifier_rejects_an_edited_decision(tmp_path):
    path, key_hex, records = _write_chain(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[1]["decision"] = "allow"
    path.write_text(json.dumps(payload), encoding="utf-8")
    done = _run_verifier(path, key_hex)
    assert done.returncode == 1
    assert "does not match its hash" in done.stdout


def test_the_standalone_verifier_rejects_a_deletion(tmp_path):
    path, key_hex, _ = _write_chain(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps([payload[0], payload[2]]), encoding="utf-8")
    done = _run_verifier(path, key_hex)
    assert done.returncode == 1
    assert "chain broken" in done.stdout


def test_the_standalone_verifier_rejects_the_wrong_key(tmp_path):
    path, _, _ = _write_chain(tmp_path)
    done = _run_verifier(path, public_key_hex(generate_key()))
    assert done.returncode == 1
    assert "does not verify" in done.stdout


def test_our_digest_and_the_strangers_digest_agree(tmp_path):
    """The one that would have failed before the seal was defined over JSON: two
    serialisations of the same record hash differently, and a genuine receipt is
    rejected by an honest verifier."""
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "standalone", pathlib.Path("scripts/verify_receipt.py"))
    standalone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(standalone)
    path, _, records = _write_chain(tmp_path, n=1)
    payload = json.loads(path.read_text(encoding="utf-8"))[0]
    assert standalone.record_hash(payload) == records[0].hash
