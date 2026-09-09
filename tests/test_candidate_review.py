"""Software counterexamples, never shopping accuracy labels."""
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from approv.harness.review import check_shelf
from approv.harness.shopping import (
    Action, Arm, Inventory, Product, RunConfig, Session, ShoppingCase, replay,
)
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality,
    Dimension, Evidence, FieldProfile, Liability, Quantity, Term,
)
from scripts.run_forked_study import candidate_followup, pick_stage


def schema(criticality=Criticality.HARD, floor=frozenset()):
    return CategorySchema(category_id="fixture", version="1", floor=floor,
        attributes=(AttributeSpec(name="size", dimension=Dimension.NOMINAL,
                                  criticality=criticality),),
        field_profiles=tuple(FieldProfile(field_name=name, certainty=Certainty.EXACT,
                                          liability=Liability.MERCHANT_GUARANTEED)
                             for name in ("variant.size", "description.size")))


def product(pid, size=None, certainty=Certainty.EXACT):
    evidence = () if size is None else (Evidence(attribute="size", value=Term(surface=size),
        field_name="variant.size", certainty=certainty, liability=Liability.MERCHANT_GUARANTEED),)
    return Product(id=pid, title=pid, evidence=evidence)


def case(**updates):
    return ShoppingCase(id="fixture", request="The original request needs size M.",
        author="software fixture", cluster="fixture", **{
            "constraints": (Constraint(attribute="size", value=Term(surface="M"),
                                       channel=Channel.AGENT_MESSAGE),), **updates})


def test_shelf_names_supported_alternative_and_preserves_source_and_order():
    products = (product("wrong", "S"), product("right", "M"), product("missing"))
    report = check_shelf(case(), products, schema())
    assert report["groups"] == {"supported": ["right"], "contradicted": ["wrong"],
                                "unresolved": ["missing"], "unassessed": []}
    assert [p["product_id"] for p in report["candidates"]] == [p.id for p in products]
    assert report["candidates"][1]["findings"][0]["evidence"][0]["field_name"] == "variant.size"
    assert "rules it out: right." in report["feedback"]


def test_unknown_and_weak_support_never_become_supported_or_all_contradicted():
    report = check_shelf(case(), (product("missing"), product("parsed", "M", Certainty.PARSED),
                                 product("wrong", "S")), schema())
    assert report["groups"]["supported"] == []
    assert report["groups"]["unresolved"] == ["missing", "parsed"]
    assert not report["all_contradicted"]


def test_conflicting_evidence_remains_unresolved():
    item = product("conflicting", "M")
    other = item.evidence[0].model_copy(update={"field_name": "description.size", "value": Term(surface="S")})
    item = item.model_copy(update={"evidence": item.evidence + (other,)})
    assert check_shelf(case(), (item,), schema())["groups"]["unresolved"] == [item.id]


def test_soft_preference_cannot_rule_out_a_shelf():
    report = check_shelf(case(), (product("other", "S"),), schema(Criticality.SOFT))
    assert not report["all_contradicted"]
    assert report["groups"]["contradicted"] == []
    assert report["groups"]["unassessed"] == ["other"]


def test_empty_extraction_and_empty_shelf_do_not_claim_support_or_impossibility():
    for products in ((), (product("one", "M"),)):
        report = check_shelf(case(constraints=()), products, schema())
        assert not report["all_contradicted"]
        assert not report["groups"]["supported"]
        assert report["checked_attributes"] == []


def test_missing_floor_is_unresolved_and_notes_survive():
    report = check_shelf(case(constraints=(), interpretation_notes=("Colour was ambiguous",)),
                         (product("one", "M"),), schema(floor=frozenset({"size"})))
    assert report["groups"]["unresolved"] == ["one"]
    assert "Colour was ambiguous" in report["feedback"]


def test_all_contradicted_is_scoped_to_seen_candidates_and_assessed_count():
    report = check_shelf(case(), (product("wrong", "S"),), schema(), units=2)
    assert report["all_contradicted"]
    assert report["assessed_sale_units"] == 2
    assert "unseen inventory have not been ruled out" in report["feedback"]


def test_cart_total_and_requested_sale_count_are_checked_consistently():
    weight_schema = CategorySchema(category_id="mass", version="1", attributes=(
        AttributeSpec(name="net_weight", dimension=Dimension.MASS, criticality=Criticality.HARD),),
        field_profiles=(FieldProfile(field_name="weight", certainty=Certainty.EXACT,
                                     liability=Liability.MERCHANT_GUARANTEED),))
    value = Quantity(magnitude=500, unit="g", dimension=Dimension.MASS)
    item = Product(id="pack", title="pack", evidence=(Evidence(attribute="net_weight", value=value,
        field_name="weight", certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),))
    request = case(constraints=(Constraint(attribute="net_weight", value=value.model_copy(update={"magnitude": Decimal("1000")}),
                                           channel=Channel.AGENT_MESSAGE),),
                   quantity_scope="cart_total", requested_units=2)
    assert check_shelf(request, (item,), weight_schema, units=2)["groups"]["supported"] == ["pack"]
    assert check_shelf(request, (item,), weight_schema, units=1)["all_contradicted"]
    assert item.evidence[0].value.magnitude == 500


def test_session_reviews_only_seen_candidates_and_replays():
    inventory = Inventory(source="fixture", source_license="fixture",
        captured_at=datetime(2026, 9, 10, tzinfo=timezone.utc), schema=schema(),
        products=(product("wrong", "S"), product("right", "M"), product("unseen", "M")))
    for arm in Arm:
        session = Session(inventory, case(), arm,
                          RunConfig(surface="verify", candidate_review=True))
        session.step(Action(type="inspect", product_id="wrong"))
        session.step(Action(type="inspect", product_id="right"))
        result = session.step(Action(type="select", product_id="wrong"))
        if arm is Arm.APPROV:
            assert result["approv"]["shelf"]["groups"]["supported"] == ["right"]
            assert [a["product_id"] for a in result["approv"]["shelf"]["candidates"]] == ["wrong", "right"]
        else:
            assert "approv" not in result
        replay(session.result(), inventory, case())


def test_abstention_is_assessed_without_false_no_extraction_message():
    original = case().model_dump(mode="json")
    record = {"constraints": original["constraints"], "notes": ["Unverified colour"]}
    report, assessment = candidate_followup(original, record, [product("right", "M")], "ABSTAIN", schema())
    assert assessment["groups"]["supported"] == ["right"]
    assert "No constraints were extracted" not in report
    assert "Unverified colour" in report


def test_answer_constraints_in_original_case_cannot_leak_into_missing_extraction():
    _, assessment = candidate_followup(case().model_dump(mode="json"), {},
                                       [product("right", "M")], "right", schema())
    assert assessment["groups"]["supported"] == []
    assert assessment["checked_attributes"] == []


@pytest.mark.parametrize("record", [{"requested_units": 2}, {"quantity_scope": "cart_total"}])
def test_id_only_study_rejects_quantity_tasks(record):
    with pytest.raises(ValueError, match="ID-only"):
        candidate_followup(case().model_dump(mode="json"), record, [product("one", "M")], "one", schema())


def test_duplicate_candidates_fail_instead_of_manufacturing_counts():
    with pytest.raises(ValueError, match="duplicate"):
        check_shelf(case(), (product("one", "M"), product("one", "S")), schema())


@pytest.mark.parametrize("units", [True, 0, 101, 1.5])
def test_invalid_sale_counts_are_rejected_even_for_empty_shelf(units):
    with pytest.raises(ValueError, match="sale units"):
        check_shelf(case(), (), schema(), units=units)


@pytest.mark.parametrize("answer,finish,expected", [
    ("one", "stop", "one"), ("ABSTAIN", "stop", "ABSTAIN"),
    ("unseen", "stop", "ERROR"), ("one", "length", "ERROR"), (None, "stop", "ERROR"),
])
def test_picker_keeps_invalid_and_truncated_replies_as_errors(tmp_path, monkeypatch, answer, finish, expected):
    stage = [{"case_id": "fixture", "request": "Original", "candidates": [
        {"id": "one", "title": "One", "listing": "M | In stock | description"}]}]
    (tmp_path / "stage2-shelf.json").write_text(json.dumps(stage), encoding="utf-8")
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr("approv.harness.adapters.post_json", lambda *args: {
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps({"id": answer})}}],
        "usage": {"total_tokens": 12}, "model": "fixture",
    })
    pick_stage(tmp_path, "2-shelf", "fixture", "not-a-key", "http://fixture", 0)
    assert json.loads((tmp_path / "answers-shelf.json").read_text(encoding="utf-8"))["fixture"] == expected
    assert json.loads((tmp_path / "answers-shelf.calls.json").read_text(encoding="utf-8"))["fixture"]["usage"]["total_tokens"] == 12
    stage[0]["request"] = "Changed request"
    (tmp_path / "stage2-shelf.json").write_text(json.dumps(stage), encoding="utf-8")
    with pytest.raises(ValueError, match="run identity"):
        pick_stage(tmp_path, "2-shelf", "fixture", "not-a-key", "http://fixture", 0)


def test_followup_rejects_a_missing_frozen_shelf(tmp_path, monkeypatch):
    import scripts.run_forked_study as driver
    inventory = Inventory(source="fixture", source_license="fixture",
        captured_at=datetime(2026, 9, 10, tzinfo=timezone.utc), schema=schema(),
        products=(product("one", "M").model_copy(update={"details": {"title": "One"}}),))
    pack = {"tasks": [{"case": case().model_dump(mode="json"), "split": "heldout"}]}
    monkeypatch.setattr(driver, "load", lambda _: (pack, inventory, {"one": "one"}))
    for name, content in [("answers-baseline.json", {"fixture": "one"}),
                          ("constraints.json", {}), ("stage1-baseline.json", [])]:
        (tmp_path / name).write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["run_forked_study", "followup", "--pack", "fixture",
                                    "--work", str(tmp_path), "--review-scope", "shelf"])
    with pytest.raises(ValueError, match="missing frozen baseline shelves"):
        driver.main()


def test_the_report_ends_on_the_move_not_on_a_failure_statistic():
    """The 10 September defect, measured on five held-out cases.

    On each of them the check had isolated the satisfying candidate and the report still
    closed with "Candidates with contradicted requirements: 24." — the work the check did,
    rendered as a count of what is wrong, and the last thing read before answering. The
    agent abstained on all five. The report must end naming the move.
    """
    report = check_shelf(case(), (product("wrong", "S"), product("right", "M")), schema())
    lines = report["feedback"].splitlines()

    assert lines[-1].startswith("Select one of these")
    assert lines[-1].endswith("right.")
    assert "1 of 2 candidates satisfy every recorded required field" in report["feedback"]
    assert not any(line.startswith("Candidates with contradicted") for line in lines)


def test_a_shelf_with_nothing_supported_still_reports_the_contradiction_count():
    report = check_shelf(case(), (product("missing"),), schema())

    assert "Candidates with contradicted requirements: 0." in report["feedback"]
    assert "Select one of these" not in report["feedback"]


def test_declining_outranks_selecting_when_every_candidate_contradicts():
    """DECLINE_NO_MATCH and SELECT_FROM_SUPPORTED can never both fire: the first needs an
    empty supported set. Asserted because they are each other's opposite and a report
    carrying both would be worse than a report carrying neither."""
    report = check_shelf(case(), (product("wrong", "S"),), schema())

    assert report["all_contradicted"]
    assert "otherwise abstain" in report["feedback"]
    assert "Select one of these" not in report["feedback"]


def test_the_report_says_when_the_standing_answer_is_already_supported():
    """shopper-45, 10 September: the agent's own previous pick was first in the supported
    list and it answered ABSTAIN. The report never told it that it was already right, and
    the review nudge says selections like yours turn out to be wrong."""
    products = (product("wrong", "S"), product("right", "M"))
    already = check_shelf(case(), products, schema(), proposed="right")
    not_yet = check_shelf(case(), products, schema(), proposed="ABSTAIN")

    assert "Your earlier answer right is already among the candidates below." in already["feedback"]
    assert "Your earlier answer ABSTAIN is not among the candidates below." in not_yet["feedback"]
    # The move still has the last word in both.
    assert already["feedback"].splitlines()[-1].startswith("Select one of these")


def test_naming_a_proposal_changes_only_the_wording_never_the_assessment():
    products = (product("wrong", "S"), product("right", "M"))
    without = check_shelf(case(), products, schema())
    with_wrong = check_shelf(case(), products, schema(), proposed="wrong")

    assert without["groups"] == with_wrong["groups"]
    assert without["candidates"] == with_wrong["candidates"]
    assert without["all_contradicted"] == with_wrong["all_contradicted"]


def test_the_identity_caveat_precedes_the_move_and_is_stated_once():
    """Trailing the caveat made "OK: availability, size." read as a doubt about the
    candidate it had just cleared. It is true of every candidate equally, so it cannot
    help choose between them and must not be the closing line."""
    report = check_shelf(case(), (product("wrong", "S"), product("right", "M")), schema())
    lines = report["feedback"].splitlines()
    caveat = [i for i, line in enumerate(lines) if "does not confirm product identity" in line]

    assert len(caveat) == 1
    assert caveat[0] < len(lines) - 1


def test_an_incomplete_reading_of_the_request_withholds_the_imperative():
    """shopper-49, 10 September: an unfillable held-out case that the report nearly sold.

    The request said "do not substitute a different colour or size". The extractor could
    not encode the colour against the published vocabulary and recorded that as a note,
    after which one candidate satisfied every field that remained. Naming it is honest;
    telling the agent to select it is not, because the fields that would have ruled it
    out are the ones we failed to read. §2.3: an unknown never authorises, and not
    knowing what we were asked is the worst unknown there is.
    """
    products = (product("wrong", "S"), product("right", "M"))
    unsure = case().model_copy(update={"interpretation_notes": ("colour, left unverified",)})
    report = check_shelf(unsure, products, schema())

    assert report["groups"]["supported"] == ["right"]
    assert "right" in report["feedback"]
    assert "Select one of these" not in report["feedback"]
    assert "abstain if they cannot be met" in report["feedback"]


def test_the_hedged_report_still_ends_on_an_action_and_still_names_the_candidates():
    """Withholding the imperative must not send the report back to burying the answer.
    The candidates are still named and the last line is still a move."""
    unsure = case().model_copy(update={"interpretation_notes": ("colour, left unverified",)})
    report = check_shelf(unsure, (product("wrong", "S"), product("right", "M")), schema(),
                         proposed="right")
    lines = report["feedback"].splitlines()

    assert lines[-1].startswith("Fields that were checked are satisfied by: right.")
    assert "Your earlier answer right is already among the candidates below." in lines
