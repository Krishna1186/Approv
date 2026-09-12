"""Two deterministic guards added after the 10 September WebShop audit
(scripts/audit_webshop.py, real crowd-worker instructions, not generated):

- _implausible_value: a bare property descriptor ("non slip") must not stand in for a
  named attribute value.
- coverage_gap: request content that ended up in no constraint and no note must not
  silently vanish.

Both are pure functions — no model call — so they are tested directly, not only through
a mocked RequestInterpreter round trip. One end-to-end test replays the real captured
model output from the audit that exposed the "non slip" bug, so the regression is pinned
to the actual failure rather than a paraphrase of it.
"""
import json
from unittest.mock import patch

from approv.harness.intent import RequestInterpreter, _implausible_value, coverage_gap
from approv.harness.shopping import ShoppingCase
from approv.types.core import (
    AttributeSpec, CategorySchema, Channel, Constraint, Count, Criticality, Dimension,
    Money, Term,
)


def schema():
    return CategorySchema(category_id="test.probe", version="1", field_profiles=(), attributes=(
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="material", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="product_type", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
    ))


def response(reading):
    return {"model": "unit-fixture", "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(reading)}}]}


# --- _implausible_value -----------------------------------------------------------

def test_a_bare_property_descriptor_is_not_a_named_value():
    assert _implausible_value(Term(surface="non slip")) == "non slip"
    assert _implausible_value(Term(surface="water resistant")) == "water resistant"
    assert _implausible_value(Term(surface="easy to use")) == "easy to use"


def test_a_real_value_carrying_a_harmless_adjective_is_not_flagged():
    """'quality leather' keeps 'leather' as a real value; only a value that consists
    entirely of a property phrase is redirected, per the guard's own scoping note."""
    assert _implausible_value(Term(surface="quality leather")) is None
    assert _implausible_value(Term(surface="dark brown")) is None


def test_non_term_values_are_never_flagged():
    assert _implausible_value(Count(n=3)) is None


# --- coverage_gap -------------------------------------------------------------------

def test_fully_accounted_request_has_no_gap():
    constraints = (
        Constraint(attribute="color", value=Term(surface="blue"), channel=Channel.AGENT_MESSAGE),
        Constraint(attribute="product_type", value=Term(surface="jacket"), channel=Channel.AGENT_MESSAGE),
    )
    assert coverage_gap("I need a blue jacket.", constraints, (), schema()) is None


def test_content_in_no_constraint_and_no_note_is_named():
    """The exact failure the audit found: the quote grounding a constraint can span more
    text than the constraint's own value keeps, and that gap has to be named somewhere."""
    constraints = (Constraint(attribute="product_type", value=Term(surface="gummy candies"),
                              channel=Channel.AGENT_MESSAGE, raw_text="individually wrapped gummy candies"),)
    gap = coverage_gap("i am searching for individually wrapped gummy candies.", constraints, (), schema())
    assert gap == "Text not explicitly accounted for: individually wrapped"


def test_content_already_in_a_note_is_not_double_flagged():
    """Every word must actually be accounted for somewhere — a note covers only the
    words it contains, not the rest of the sentence around it."""
    constraints = (Constraint(attribute="product_type", value=Term(surface="candles"), channel=Channel.AGENT_MESSAGE),)
    assert coverage_gap("scented candles, gift wrapped please", constraints,
                        ("scented", "gift wrapped"), schema()) is None


def test_a_schema_attribute_name_used_as_a_plain_word_is_not_flagged():
    """'in color eleven' records color=eleven, which accounts for 'eleven' but not the
    frame word 'color' itself — that word names which attribute is being stated, not
    content the reading dropped. Measured on the WebShop audit replay."""
    constraints = (Constraint(attribute="color", value=Term(surface="eleven"), channel=Channel.AGENT_MESSAGE),)
    assert coverage_gap("get the one in color eleven", constraints, (), schema()) is None


def test_a_price_bound_is_accounted_for_by_its_limit():
    from approv.types.core import Bound, BoundOp
    constraints = (Constraint(attribute="price",
        value=Bound(op=BoundOp.LTE, limit=Money(amount="50", currency="USD")),
        channel=Channel.AGENT_MESSAGE),)
    assert coverage_gap("nothing over $50", constraints, (), schema()) is None


# --- End to end, replaying the real audit failure ------------------------------------

def test_the_real_non_slip_case_no_longer_records_a_property_as_a_material():
    """webshop-B07Q7NKCS7-9 from the 10 September audit: the model recorded
    material="non slip" on a request that named no material at all, and the gate would
    have had a real, checkable-looking finding for an attribute the shopper never stated
    one for. Replays the actual captured model output — not a paraphrase."""
    case = ShoppingCase(id="webshop-B07Q7NKCS7-9",
        request="i want pink and non slip luffymomo womens shower slippers.",
        author="test", cluster="test")
    reading = {"requirements": [
        {"attribute": "product_type", "value": {"kind": "term", "surface": "shower slippers"},
         "quote": "shower slippers"},
        {"attribute": "color", "value": {"kind": "term", "surface": "pink"}, "quote": "pink"},
        {"attribute": "material", "value": {"kind": "term", "surface": "non slip"}, "quote": "non slip"},
    ], "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
       "unverified": ["luffymomo", "womens"]}
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result, meta = RequestInterpreter("https://example.test", "fixture", "key", "v4")(case, schema())

    attributes = {c.attribute for c in result.constraints}
    assert "material" not in attributes
    assert any(n.startswith("Descriptive property, not a named value, left unverified: material=")
              for n in result.interpretation_notes)


def test_coverage_gap_note_is_recorded_in_metadata_and_is_a_dropped_requirement():
    from approv.harness.intent import dropped_requirement
    case = ShoppingCase(id="c", request="i am searching for individually wrapped gummy candies.",
                        author="test", cluster="test")
    reading = {"requirements": [{"attribute": "product_type",
               "value": {"kind": "term", "surface": "gummy candies"},
               "quote": "individually wrapped gummy candies"}],
               "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
               "unverified": []}
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result, meta = RequestInterpreter("https://example.test", "fixture", "key", "v4")(case, schema())

    assert meta["coverage_gap"] == "Text not explicitly accounted for: individually wrapped"
    assert any(dropped_requirement(n) for n in result.interpretation_notes)


def test_the_real_extractor_plugs_into_intake_path_c():
    """Path (c) with the actual interpreter behind it, not a stand-in.

    The bridge is the whole of what `approv.intake` needs to be more than a shape: one
    function in the layer that is allowed to call a model, handing back constraints and
    the extractor's own account of what it could not encode. Asserted end to end because
    a layer nothing real ever calls is a layer that is quietly wrong.
    """
    from approv.harness.intent import as_extractor
    from approv.intake import AgentPresence, FreeText, intake

    reading = {"requirements": [{"attribute": "product_type",
               "value": {"kind": "term", "surface": "gummy candies"},
               "quote": "individually wrapped gummy candies"}],
               "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
               "unverified": []}
    interpreter = RequestInterpreter("https://example.test", "fixture", "key", "v4")
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result = intake(FreeText(text="i am searching for individually wrapped gummy candies."),
                        schema(), extract=as_extractor(interpreter))

    assert [c.attribute for c in result.constraints] == ["product_type"]
    assert [c.source for c in result.constraints] == ["declared_intent"]
    assert result.unread == ("Text not explicitly accounted for: individually wrapped",)
    assert result.covered and result.agent is AgentPresence.DECLARED


# --- v5: naming what a correction discarded -----------------------------------------

def test_v5_prompt_is_selected_and_differs_from_v4():
    from approv.harness.intent import PROMPT_V4, PROMPT_V5
    assert PROMPT_V5 != PROMPT_V4
    assert PROMPT_V5.startswith(PROMPT_V4)
    interpreter = RequestInterpreter("https://example.test", "fixture", "key", "v5")
    assert interpreter.prompt == PROMPT_V5


def test_a_logged_supersession_is_not_a_coverage_gap_and_not_a_dropped_requirement():
    """The whole point of v5: once the model names what it discarded, coverage_gap
    already treats note text as accounted for (no change needed there), and the note
    must NOT read as a dropped requirement — naming a correctly-superseded value is the
    opposite of missing one, and should not withhold a confident recommendation."""
    from approv.harness.intent import dropped_requirement
    case = ShoppingCase(id="c", request="Get me the belt in Cognac — actually no, make that Dark brown.",
                        author="test", cluster="test")
    reading = {"requirements": [
        {"attribute": "color", "value": {"kind": "term", "surface": "Dark brown"}, "quote": "Dark brown"},
        {"attribute": "product_type", "value": {"kind": "term", "surface": "belt"}, "quote": "belt"},
    ], "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
       "unverified": ["Superseded, discarded: Cognac (color)"]}
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result, meta = RequestInterpreter("https://example.test", "fixture", "key", "v5")(case, schema())

    assert meta.get("coverage_gap") is None
    assert not any(dropped_requirement(n) for n in result.interpretation_notes)
    assert "Superseded, discarded: Cognac (color)" in result.interpretation_notes


# --- A live-model failure this session actually hit, replayed verbatim -------------

def test_a_compound_value_split_across_two_requirements_no_longer_discards_the_whole_reading():
    """Live against gemini-3.6-flash on 10 September (v5 validation run, real API call, not
    a paraphrase): the model split "Beige and blue mouliné" into two separate `color`
    requirements instead of one combined value. approv.harness.shopping.ShoppingCase's
    own uniqueness validator then rejected the whole reading — 4 of 5 correctly-extracted
    requirements discarded along with the one that was actually wrong, and the note left
    behind ("Request interpretation failed; check original request manually.") carried no
    information about why. First value wins; the second is named, not silently dropped;
    everything else in the reading survives."""
    case = ShoppingCase(id="c", request="Get me the crewneck sweater in Dove gray and brown "
                        "— actually no, make that Beige and blue mouliné. Size 44, "
                        "and it has to be in stock. Delivery speed doesn't matter, I'm not in a rush.",
                        author="test", cluster="test")
    reading = {"requirements": [
        {"attribute": "product_type", "value": {"kind": "term", "surface": "crewneck sweater"}, "quote": "crewneck sweater"},
        {"attribute": "color", "value": {"kind": "term", "surface": "Beige"}, "quote": "Beige"},
        {"attribute": "color", "value": {"kind": "term", "surface": "blue mouliné"}, "quote": "blue mouliné"},
        {"attribute": "size", "value": {"kind": "term", "surface": "44"}, "quote": "44"},
        {"attribute": "availability", "value": {"kind": "term", "surface": "in stock"}, "quote": "in stock"},
    ], "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
       "unverified": ["Superseded, discarded: Dove gray and brown (color)",
                      "Delivery speed doesn't matter, I'm not in a rush"]}
    from approv.harness.casepacks import shopify_schema
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result, meta = RequestInterpreter("https://example.test", "fixture", "key", "v5")(case, shopify_schema())

    assert meta["status"] == "parsed"
    attributes = {c.attribute: c.value.surface for c in result.constraints}
    assert attributes == {"product_type": "crewneck sweater", "color": "Beige",
                          "size": "44", "availability": "in stock"}
    assert any(n.startswith("Duplicate requirement for a stated attribute, second value discarded: color=")
              for n in result.interpretation_notes)


def test_unverified_entries_shaped_as_objects_no_longer_discard_the_whole_reading():
    """Live against gemini-3.5-flash-lite on 10 September (WebShop audit, real API call):
    on 3 of 28 real cases the model wrote `unverified` as a list of objects instead of
    strings — {"reason": "mens", "quote": "mens"} — which is not malformed, it answers a
    shape the prompt did not ask for. Before _normalize_note, interpretation_notes being
    typed tuple[str, ...] meant a dict there raised a ValidationError (a ValueError
    subclass) and discarded every correctly-extracted constraint beside it."""
    case = ShoppingCase(id="c",
        request="i am looking for mens shoes that are of realtree edge color and have rubber sole.",
        author="test", cluster="test")
    reading = {"requirements": [
        {"attribute": "color", "value": {"kind": "term", "surface": "realtree edge"}, "quote": "realtree edge color"},
        {"attribute": "material", "value": {"kind": "term", "surface": "rubber"}, "quote": "rubber sole"},
        {"attribute": "product_type", "value": {"kind": "term", "surface": "shoes"}, "quote": "shoes"},
    ], "requested_units": None, "units_quote": "", "quantity_scope": "per_sale_unit",
       "unverified": [{"reason": "mens", "quote": "mens"}]}
    with patch("approv.harness.intent.post_json", return_value=response(reading)):
        result, meta = RequestInterpreter("https://example.test", "fixture", "key", "v5")(case, schema())

    assert meta["status"] == "parsed"
    assert {c.attribute for c in result.constraints} == {"color", "material", "product_type"}
    assert "mens" in result.interpretation_notes
