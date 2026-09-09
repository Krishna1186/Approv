"""Harness contract tests using artificial unit fixtures, never performance evidence."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import urllib.request

import pytest

from approv.harness.adapters import AdapterError, ChatAgent, CommandAgent, parse_reply
from approv.harness.experiment import Annotation, GoldSet, report, run_experiment, validate_gold
from approv.harness.inventory import import_off
from approv.harness.shopping import (
    Action, AgentReply, Arm, RunConfig, Session, ShoppingCase, digest, replay, run_session, verify_trace,
)
from approv.harness.storefront import Store, make_server
from approv.types.core import Channel, Constraint, Term


@pytest.fixture
def inventory():
    return import_off([{"code": "a", "product_name": "Test One", "brands": "One", "quantity": "500 g"},
                       {"code": "b", "product_name": "Test Two", "brands": "Two", "quantity": "1 kg"}],
                      datetime(2026, 9, 8, tzinfo=timezone.utc))[0]


@pytest.fixture
def cases():
    return [ShoppingCase(id=f"case-{i}", request="Unit-test request for One", author="unit-test-fixture",
            cluster=f"cluster-{i}", constraints=(Constraint(attribute="brand", value=Term(surface="One"),
            channel=Channel.TOOL_ARGUMENT),)) for i in range(2)]


@pytest.fixture
def gold(inventory, cases):
    return GoldSet(inventory_hash=digest(inventory), provenance="Artificial unit-test fixture ONLY",
        annotations=tuple(Annotation(case_id=c.id, case_hash=digest(c), annotator="unit-test-fixture",
            evidence_notes="Artificial contract test, not accuracy evidence",
            accepted=({"product_id": "a", "units": 1},)) for c in cases))


class Scripted:
    def __call__(self, observation):
        responses = [e["payload"] for e in observation["history"] if e["kind"] == "response"]
        if not responses:
            action = Action(type="search")
        else:
            action = Action(type="select", product_id="a")
        assert "accepted" not in observation and "gold" not in observation
        return AgentReply(action=action)


def experiment(inventory, cases):
    return run_experiment(inventory, cases, RunConfig(max_actions=5), Scripted,
                          agent_metadata={"name": "unit-fixture"})


def test_inventory_ranking_identical_between_arms(inventory, cases):
    pages = [Session(inventory, cases[0], a, RunConfig()).step(Action(type="search", query="Two")) for a in Arm]
    assert [[p["id"] for p in page["products"]] for page in pages] == [["b", "a"]] * 3
    assert "approv" not in pages[0]["products"][0]
    assert "approv" in pages[2]["products"][0]


def test_verify_surface_does_not_annotate_search(inventory, cases):
    session = Session(inventory, cases[0], Arm.APPROV, RunConfig(surface="verify"))
    assert "approv" not in session.step(Action(type="search"))["products"][0]
    assert "approv" in session.step(Action(type="select", product_id="b"))


def test_blind_and_approv_review_equally(inventory, cases):
    for arm in (Arm.BLIND, Arm.APPROV):
        session = Session(inventory, cases[0], arm, RunConfig())
        session.step(Action(type="search"))
        assert session.step(Action(type="select", product_id="a"))["status"] == "review"
        assert session.status == "running"
        assert session.step(Action(type="select", product_id="a"))["status"] == "selected"


def test_bound_budget_cannot_be_bypassed(inventory, cases):
    session = Session(inventory, cases[0], Arm.APPROV, RunConfig(max_actions=2))
    session.step(Action(type="search"))
    session.step(Action(type="select", product_id="a"))
    assert session.status == "budget_exhausted" and session.selection is None
    with pytest.raises(ValueError):
        session.step(Action(type="abstain"))


def test_unknown_or_unseen_id_does_not_select(inventory, cases):
    session = Session(inventory, cases[0], Arm.BASELINE, RunConfig())
    assert "error" in session.step(Action(type="select", product_id="a"))
    assert "error" in session.step(Action(type="inspect", product_id="missing"))
    assert session.status == "running"


def test_traces_replay_against_original_snapshot(inventory, cases):
    result = run_session(Session(inventory, cases[0], Arm.APPROV, RunConfig()), Scripted())
    replay(result, inventory, cases[0])
    altered = inventory.model_copy(update={"source": "other"})
    with pytest.raises(ValueError, match="snapshot"):
        replay(result, altered, cases[0])


@pytest.mark.parametrize("tamper", ["truncate", "edit", "outcome"])
def test_trace_tampering_rejected(inventory, cases, tamper):
    result = run_session(Session(inventory, cases[0], Arm.BASELINE, RunConfig()), Scripted())
    if tamper == "truncate":
        result["events"].pop()
    elif tamper == "edit":
        result["events"][1]["payload"]["action"]["query"] = "changed"
    else:
        result["selection"]["product_id"] = "b"
    with pytest.raises(ValueError):
        replay(result, inventory, cases[0])


def test_observation_is_a_copy(inventory, cases):
    session = Session(inventory, cases[0], Arm.BASELINE, RunConfig())
    session.step(Action(type="search"))
    view = session.observation()
    view["constraints"].clear()
    view["history"][0]["payload"]["action"]["query"] = "mutated"
    assert session.observation()["constraints"]
    verify_trace(session.result())


def test_failures_are_not_abstentions(inventory, cases):
    def broken(_):
        raise AdapterError("empty_response", {"request_hash": "x"})
    result = run_session(Session(inventory, cases[0], Arm.BASELINE, RunConfig()), broken)
    assert result["status"] == "agent_error"
    assert result["events"][-1]["payload"]["metadata"]["request_hash"] == "x"
    replay(result, inventory, cases[0])


def test_gold_is_optional_and_never_used_during_execution(inventory, cases, gold):
    result = experiment(inventory, cases)
    behavior = report(result, inventory, cases)
    assert behavior["measurement"] == "unlabelled behavior only"
    assert not behavior["effects"]
    scored = report(result, inventory, cases, gold)
    assert scored["arms"]["approv"]["correct"] == len(cases)
    assert scored["effects"][0]["difference"] == 0
    assert scored["effects"][0]["cluster_bootstrap_95_interval"] is None


def test_feedback_intervention_is_scored_against_separate_labels(inventory, cases, gold):
    class RespondsToFeedback:
        def __call__(self, observation):
            responses = [e["payload"] for e in observation["history"] if e["kind"] == "response"]
            if not responses:
                return AgentReply(action=Action(type="search"))
            products = responses[0]["products"]
            selected = "b"  # Deliberate software-fixture error, not simulated model accuracy.
            for product in products:
                if "approv" in product and all(f["support"] == "satisfied" for f in product["approv"]["findings"]):
                    selected = product["id"]
            return AgentReply(action=Action(type="select", product_id=selected))
    result = run_experiment(inventory, cases, RunConfig(), RespondsToFeedback,
                            agent_metadata={"name": "artificial feedback contract test"})
    scored = report(result, inventory, cases, gold)
    assert scored["arms"]["blind_review"]["wrong_selections"] == 2
    assert scored["arms"]["approv"]["correct"] == 2
    assert scored["effects"][1]["improved"] == 2


def test_manifest_missing_arm_is_rejected(inventory, cases):
    result = experiment(inventory, cases)
    result["results"].pop()
    result["manifest"]["results_hash"] = digest(result["results"])
    with pytest.raises(ValueError, match="missing or duplicated"):
        report(result, inventory, cases)


def test_gold_requires_matching_cases_and_snapshot(inventory, cases, gold):
    with pytest.raises(ValueError, match="case changed"):
        validate_gold(gold, inventory, [cases[0].model_copy(update={"request": "changed"}), cases[1]])
    with pytest.raises(ValueError, match="exactly"):
        validate_gold(gold, inventory, cases[:1])


def test_action_cannot_inject_provenance():
    with pytest.raises(ValueError):
        Action(type="select", product_id="a", certainty="exact")


def test_cart_total_uses_selected_number_of_packs(inventory, cases):
    from approv.types.core import Quantity, Dimension, Support
    case = cases[0].model_copy(update={"quantity_scope": "cart_total", "requested_units": 2,
        "constraints": (Constraint(attribute="net_weight", value=Quantity(magnitude=1,
            unit="kg", dimension=Dimension.MASS), channel=Channel.TOOL_ARGUMENT),)})
    session = Session(inventory, case, Arm.APPROV, RunConfig(surface="verify"))
    session.step(Action(type="search"))
    review = session.step(Action(type="select", product_id="a", units=2))["approv"]
    assert review["assessed_sale_units"] == 2
    assert all(f["support"] == "satisfied" for f in review["findings"])


def test_per_pack_quantity_is_not_multiplied(inventory, cases):
    from approv.types.core import Quantity, Dimension
    case = cases[0].model_copy(update={"constraints": (Constraint(attribute="net_weight",
        value=Quantity(magnitude=1, unit="kg", dimension=Dimension.MASS), channel=Channel.TOOL_ARGUMENT),)})
    session = Session(inventory, case, Arm.APPROV, RunConfig(surface="verify"))
    session.step(Action(type="search"))
    review = session.step(Action(type="select", product_id="a", units=2))["approv"]
    assert review["findings"][0]["support"] == "violated"


def test_snapshot_hash_is_stable_for_unordered_floor(inventory):
    from approv.harness.shopping import canonical, Inventory
    schema = inventory.category_schema.model_copy(update={"floor": frozenset({"brand", "net_weight"})})
    changed = inventory.model_copy(update={"category_schema": schema})
    assert digest(changed) == digest(Inventory.model_validate_json(canonical(changed)))


def test_browser_surface_does_not_expose_answer_key():
    from approv.harness.storefront import HTML
    assert "gold" not in HTML


def test_http_agent_roundtrip(monkeypatch):
    from approv.harness.adapters import HttpAgent
    monkeypatch.setattr("approv.harness.adapters.post_json", lambda *args: {"type": "abstain"})
    assert HttpAgent("http://127.0.0.1:9999")({}).action.type == "abstain"


def test_gemini_adapter_uses_header_auth_and_records_usage(monkeypatch):
    sent = []
    def post(*args):
        sent.append(args)
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"type":"abstain"}'}]}}],
                "usageMetadata": {"totalTokenCount": 12}, "modelVersion": "test-version"}
    monkeypatch.setattr("approv.harness.adapters.post_json", post)
    reply = ChatAgent("https://example.test/v1beta", "test", "secret", provider="gemini")({})
    assert sent[0][2] == {"x-goog-api-key": "secret"}
    assert "secret" not in sent[0][0]
    assert reply.metadata["usage"]["totalTokenCount"] == 12


def test_legacy_cache_separates_prompts_and_providers(tmp_path, monkeypatch):
    import scripts.run_benchmark as legacy
    first = legacy._cache_path(tmp_path, "m", "title", None, provider="one")
    assert first != legacy._cache_path(tmp_path, "m", "title", None, provider="two")
    monkeypatch.setattr(legacy, "PROMPT", "different")
    assert first != legacy._cache_path(tmp_path, "m", "title", None, provider="one")


@pytest.mark.parametrize("text", ["", "UNKNOWN", '{"type":"select"}', '```json\n{"type":"abstain"}\n```'])
def test_invalid_api_actions_remain_errors(text):
    with pytest.raises(AdapterError):
        parse_reply(text, {})


def test_chat_adapter_records_exact_request_and_usage(monkeypatch):
    sent = []
    def post(url, payload, headers, timeout):
        sent.append((url, payload, headers))
        return {"model": "resolved-model", "choices": [{"finish_reason": "stop",
            "message": {"content": '{"type":"abstain"}'}}], "usage": {"total_tokens": 9}}
    monkeypatch.setattr("approv.harness.adapters.post_json", post)
    agent = ChatAgent("http://127.0.0.1:9999/v1", "test", "secret", max_tokens=512)
    reply = agent({"request": "test"})
    assert reply.metadata["usage"]["total_tokens"] == 9
    assert "secret" not in json.dumps(reply.model_dump())
    assert sent[0][1]["max_tokens"] == 512
    assert reply.metadata["request_hash"] != agent({"request": "different"}).metadata["request_hash"]


def test_truncated_provider_response_is_error(monkeypatch):
    monkeypatch.setattr("approv.harness.adapters.post_json", lambda *args:
        {"choices": [{"finish_reason": "length", "message": {"content": '{"type":"abstain"}'}}]})
    with pytest.raises(AdapterError, match="incomplete_response"):
        ChatAgent("http://127.0.0.1:9999/v1", "test")({})


def test_command_adapter_uses_json_stdin():
    import sys
    agent = CommandAgent([sys.executable, "-c", 'import json,sys; x=json.load(sys.stdin); print(json.dumps({"type":"abstain","reason":x["request"]}))'])
    assert agent({"request": "test"}).action.reason == "test"


def test_local_http_storefront_completes_and_exports(inventory, cases, tmp_path):
    output = tmp_path / "external.json"
    store = Store(inventory, cases[:1], RunConfig(), output, "unit-test")
    server = make_server(store, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def post(path, payload):
        request = urllib.request.Request(base + path, json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(request))
    try:
        assert b"Test Store" in urllib.request.urlopen(base).read()
        for _ in Arm:
            task = post("/task", {})
            token = task["token"]
            post("/action", {"token": token, "action": {"type": "search"}})
            selected = post("/action", {"token": token, "action": {"type": "select", "product_id": "a"}})
            if selected["observation"]["status"] == "running":
                post("/action", {"token": token, "action": {"type": "select", "product_id": "a"}})
        assert post("/task", {})["done"]
        report(json.loads(output.read_text()), inventory, cases[:1])
        assert len(list(tmp_path.glob("*.session-*.json"))) == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_published_text_extraction_refuses_ambiguous_and_uncued_values():
    """Both vocabularies that were withdrawn after measurement stay withdrawn.

    Bare size codes matched "Charlotte's Web" on 1,212 products and "full refund" on
    219; a listing naming two genders states neither. A false evidence value produces a
    false verdict, which under §2.6 is the expensive direction of the error.
    """
    from approv.harness.casepacks import parse_published

    assert parse_published("Charlotte's Web") == {}
    assert parse_published("Full refund guaranteed") == {}
    assert parse_published("iPhone Xs Case Leopard Cheetah") == {}
    assert "gender_age" not in parse_published("Capezio girls Boys Cut Low Rise Short")
    assert parse_published("Available in size XL")["size"] == "xl"
    assert parse_published("Madison Park King Size Comforter")["size"] == "king"
    assert parse_published("BIRKENSTOCK Gizeh Black (US Women's 7-7.5)") == {
        "gender_age": "women", "color": "black"}


def test_declared_colour_is_widened_to_a_family_not_compared_verbatim():
    """"Polar White" against a parsed "white" is agreement, not a field conflict.

    Comparing the structured field verbatim manufactured 1,763 conflicts across 4,018
    products — over half of everything that stated a colour — and every one of them
    would have surfaced to the agent as an unresolved disagreement.
    """
    from approv.harness.casepacks import constrained_product

    product = constrained_product({
        "product_id": "X1", "product_title": "Nintendo DS Lite Polar White",
        "product_brand": "Nintendo", "product_color": "Polar White",
        "product_bullet_point": "White handheld console", "product_description": None})
    colours = {e.field_name: e.value.surface for e in product.evidence if e.attribute == "color"}
    assert colours == {"product_color": "white", "title": "white", "prose": "white"}

    # A colour the family vocabulary cannot place is not asserted at all.
    unplaceable = constrained_product({
        "product_id": "X2", "product_title": "Sofa", "product_brand": "Ikea",
        "product_color": "Cerulean", "product_bullet_point": None, "product_description": None})
    assert not [e for e in unplaceable.evidence if e.attribute == "color"]


def test_a_reviewed_session_still_accepts_the_select_tool_it_was_given():
    """Renaming select to confirm_selection after review made the natural next call fail.

    The provider rejects a call to a function that is not offered, so the whole turn dies
    with tool_use_failed rather than degrading. Baseline never reaches a second selection,
    so this fell only on the review arms — it removed two of nine Approv sessions on
    9 September while leaving baseline untouched, which biases the comparison it is meant
    to measure. Both names are offered now, and both mean select.
    """
    from approv.harness.adapters import ToolChatAgent

    agent = ToolChatAgent("https://example.invalid/v1", "m", "k")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(payload)
        return {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"function": {
            "name": "select", "arguments": '{"product_id":"P1","units":1}'}}]}}], "usage": {}}

    import approv.harness.adapters as adapters
    original = adapters.post_json
    adapters.post_json = fake_post
    try:
        reply = agent({"request": "x", "actions_remaining": 3, "history": [
            {"kind": "action", "payload": {"action": {"type": "select", "product_id": "P1", "units": 1}}},
            {"kind": "response", "payload": {"status": "review"}}]})
    finally:
        adapters.post_json = original

    offered = {t["function"]["name"] for t in captured["tools"]}
    assert {"select", "confirm_selection"} <= offered
    assert reply.action.type == "select" and reply.action.product_id == "P1"


def test_one_unusable_requirement_does_not_discard_the_others():
    """A malformed value must cost its own requirement and nothing else.

    Seven of nine failed interpretations on 9 September were budget requests whose money
    bound did not validate, and each took every other requirement in the same request down
    with it — so a request stating a size, a colour and a price ended up verifying none of
    them because of the price alone.
    """
    import approv.harness.intent as intent
    from approv.harness.casepacks import shopify_schema
    from approv.harness.shopping import ShoppingCase

    reading = {"requirements": [
        {"attribute": "price", "value": {"kind": "bound", "op": "lte", "limit": "sixty eight"},
         "quote": "under $68"},
        {"attribute": "size", "value": {"kind": "term", "surface": "Size 4"}, "quote": "size Size 4"}],
        "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit", "unverified": []}

    def fake_post(url, payload, headers, timeout):
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reading)}}],
                "usage": {}, "model": "m"}

    original = intent.post_json
    intent.post_json = fake_post
    try:
        interpreter = intent.RequestInterpreter("https://example.invalid/v1", "m", "k", version="v4")
        case, meta = interpreter(ShoppingCase(id="c", request="size Size 4 under $68",
                                              author="test", cluster="c"), shopify_schema())
    finally:
        intent.post_json = original

    assert meta["status"] == "parsed"
    assert [c.attribute for c in case.constraints] == ["size"]
    assert any("Malformed requirement" in n for n in case.interpretation_notes)
