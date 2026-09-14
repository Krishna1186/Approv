"""The intake layer: many traffic shapes, one engine, and the boundary that keeps it one."""
import ast
import pathlib

from approv.algebra.runner import check_constraints
from approv.criticality import resolve
from approv.intake import (
    AgentPresence, FreeText, Reading, Search, Shape, Structured, Surface, Undeclared,
    intake,
)
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Dimension,
    Evidence, FieldProfile, Liability, Money, Support, Term,
)

SCHEMA = CategorySchema(
    category_id="apparel", version="1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
        AttributeSpec(name="price", dimension=Dimension.MONEY, criticality=Criticality.BOUND),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ),
)


def reader(text, schema):
    """A stand-in extractor. The real one needs a model and lives two layers up."""
    return Reading(constraints=(Constraint(attribute="color", value=Term(surface="Frost"),
                                           channel=Channel.AGENT_MESSAGE, raw_text=text),),
                   unread=("Text not explicitly accounted for: duvet",))


# --- the invariant -------------------------------------------------------------------

def approv_imports(path):
    imported = set()
    for node in ast.walk(ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return {m for m in imported if m.startswith("approv.")}


def intake_sources():
    module, package = pathlib.Path("approv/intake.py"), pathlib.Path("approv/intake")
    return [module] if module.exists() else sorted(package.rglob("*.py"))


def test_adding_a_traffic_shape_never_touches_the_engine():
    """The new invariant, mirroring invariant 1, and asserted for the same reason.

    The claim of the whole layer is that a new agent traffic shape is an adapter and not
    an engine change. Nothing enforces that by itself: an adapter needs one comparison
    helper, imports `algebra`, and six months later the engine has a per-protocol branch
    in it and nobody decided that. Written with the module rather than after it, because
    a boundary added later is a boundary already crossed.
    """
    for path in intake_sources():
        offending = {m for m in approv_imports(path) if not m.startswith("approv.types")}
        assert not offending, f"{path} must import only approv.types, found {offending}"


def test_the_engine_never_learns_about_intake():
    """The other direction, and the one that actually rots. A one-line import of a shape
    enum into an operator is how "the engine barely changes" stops being true."""
    for directory in ("approv/algebra", "approv/evaluator"):
        for path in sorted(pathlib.Path(directory).rglob("*.py")):
            assert "approv.intake" not in approv_imports(path), path


# --- path (a): structured -------------------------------------------------------------

def test_path_a_is_a_tool_argument_with_no_quote_and_a_locator():
    """A protocol call has no wording. The agent filled a slot, so `raw_text=None` is the
    truthful record of it rather than a lost quote, and the locator is what a returns desk
    points at: which of the protocol's fields carried this."""
    result = intake(Structured(protocol="acp", fields={"color": "Frost", "size": "M"}), SCHEMA)

    assert [c.channel for c in result.constraints] == [Channel.TOOL_ARGUMENT] * 2
    assert all(c.raw_text is None for c in result.constraints)
    assert sorted(c.source for c in result.constraints) == ["acp.color", "acp.size"]
    assert result.covered and result.agent is AgentPresence.DECLARED


def test_a_missing_quote_is_still_a_stated_requirement_and_path_a_depends_on_it():
    """**Load-bearing for path (a), not an edge case.**

    `request_layer` floors any constraint that exists at BOUND, whether or not a quote
    survived. Returning None for a quoteless constraint instead would collapse "stated
    through a channel that carries no wording" into "never stated" — and §2.2's cap would
    then drop every path (a) requirement to SOFT, which is to say out of coverage. The
    highest-fidelity channel we have would produce the weakest record in the system.

    Pinned against a genuinely never-stated attribute so the distinction is the assertion
    rather than the absolute level: `brand` here has no profile and no return history, so
    the only thing separating the two is whether the shopper said it at all.
    """
    result = intake(Structured(protocol="acp", fields={"brand": "Quince"}), SCHEMA)
    stated = result.constraints[0]

    assert stated.raw_text is None
    assert resolve("brand", constraint=stated, profiles=SCHEMA.field_profiles) is Criticality.BOUND
    assert resolve("brand", constraint=None, profiles=SCHEMA.field_profiles) is Criticality.SOFT


def test_a_signed_mandate_outranks_a_plain_tool_argument():
    """The agent committed in advance and cannot later say the call was malformed."""
    result = intake(Structured(protocol="ap2", fields={"size": "M"}, signed_mandate=True), SCHEMA)
    assert result.constraints[0].channel is Channel.MANDATE


def test_a_typed_protocol_value_passes_through_untouched():
    """Nothing here parses a string into a quantity. A protocol that already typed its
    value keeps it; one that did not gets a Term and no invented structure."""
    budget = Money(amount="40.00", currency="USD")
    result = intake(Structured(protocol="acp", fields={"price": budget}), SCHEMA)
    assert result.constraints[0].value == budget


def test_a_field_this_category_cannot_express_is_reported_not_dropped():
    result = intake(Structured(protocol="acp", fields={"size": "M", "gift_wrap": "yes"}), SCHEMA)

    assert result.unmapped == ("gift_wrap",)
    assert any("gift_wrap" in note for note in result.notes)
    assert [c.attribute for c in result.constraints] == ["size"]


def test_an_unmappable_field_is_a_requirement_nobody_checked():
    """DR 0026's easier half. The agent asked for gift wrapping, this category has no
    attribute for it, and nothing checked it — which is exactly DR 0022's unread
    requirement, and the prefix for it already existed."""
    result = intake(Structured(protocol="acp", fields={"size": "M", "gift_wrap": "yes"}),
                    SCHEMA)

    assert result.unread == ("Unsupported requirement: gift_wrap",)


def test_a_protocol_name_can_withdraw_the_agent_inference():
    """`protocol` is a free string we do not control, and `form` is a checkout POST
    wearing the shape of a protocol call: a person filling slots."""
    form = intake(Structured(protocol="form", fields={"size": "M"}), SCHEMA)
    versioned = intake(Structured(protocol="checkout-form-v2", fields={"size": "M"}), SCHEMA)

    assert form.agent is AgentPresence.UNKNOWN and not form.covered
    assert versioned.agent is AgentPresence.UNKNOWN


def test_a_protocol_name_can_never_grant_one():
    """The asymmetry is the point. Believing a name that costs coverage is safe;
    believing one that earns it puts a fabricated basis on a dispute record — so a name is
    read as a disclaimer and never as proof, and `webhook` is not a form."""
    assert intake(Structured(protocol="acp", fields={"size": "M"}), SCHEMA).agent \
        is AgentPresence.DECLARED
    assert intake(Structured(protocol="webhook", fields={"size": "M"}), SCHEMA).agent \
        is AgentPresence.DECLARED
    declared = intake(Structured(protocol="form", fields={"size": "M"}), SCHEMA,
                      agent=AgentPresence.DECLARED)
    assert declared.agent is AgentPresence.DECLARED and declared.covered


def test_an_adapter_is_a_field_name_mapping_and_nothing_more():
    """Many adapters, each a few lines of data, none of them code the engine knows about."""
    result = intake(Structured(protocol="mcp", fields={"variant_size": "M"}), SCHEMA,
                    adapter={"variant_size": "size"})
    assert result.constraints[0].attribute == "size"
    assert result.constraints[0].source == "mcp.variant_size"


# --- DR 0026: request text nothing read -------------------------------------------------

def test_a_query_nobody_read_is_named_rather_than_passed_over():
    """The filters were read and the prose was not. Recording only what we managed to read
    is how a guarantee ends up standing on a request that contradicted it."""
    result = intake(Search(query="actually make it the Ash one", filters={"size": "M"}),
                    SCHEMA, agent=AgentPresence.DECLARED)

    assert result.unprocessed == ("search.query",)
    assert [c.attribute for c in result.constraints] == ["size"]


def test_an_extractor_that_returned_nothing_at_all_read_nothing():
    """Indistinguishable from having no extractor, from where the record sits. An empty
    reading of a non-empty request is unknown, not agreement."""
    result = intake(Search(query="something about it", filters={"size": "M"}), SCHEMA,
                    extract=lambda text, schema: Reading())

    assert result.unprocessed == ("search.query",)


def test_an_extractor_that_read_something_is_dr_0022_and_not_this():
    """It told us what it missed, which is the whole difference: we can name the gap."""
    result = intake(Search(query="a frost duvet", filters={"size": "M"}), SCHEMA,
                    extract=reader)

    assert result.unprocessed == ()
    assert result.unread == ("Text not explicitly accounted for: duvet",)


def test_an_empty_query_is_not_unprocessed():
    """Nothing to read is not a failure to read. Silence has always been out of coverage
    on its own terms and does not need a second mechanism."""
    assert intake(Search(filters={"size": "M"}), SCHEMA).unprocessed == ()
    assert intake(FreeText(text="   "), SCHEMA).unprocessed == ()
    assert intake(Undeclared(why="direct arrival"), SCHEMA).unprocessed == ()


def test_declared_intent_nobody_read_is_named_by_its_own_field():
    result = intake(FreeText(text="a king duvet in frost"), SCHEMA)

    assert result.unprocessed == ("declared_intent",)


# --- path (b): search query plus filters ----------------------------------------------

def test_path_b_keeps_structure_and_prose_apart():
    """A filter is a slot the agent filled; a query is prose somebody had to read. Merging
    them into one channel would launder the weaker half up to the stronger, which is the
    one thing a dispute artifact must never do."""
    result = intake(Search(query="something in frost", filters={"size": "M"}), SCHEMA,
                    extract=reader, agent=AgentPresence.INFERRED)

    by_attribute = {c.attribute: c for c in result.constraints}
    assert by_attribute["size"].channel is Channel.TOOL_ARGUMENT
    assert by_attribute["size"].raw_text is None
    assert by_attribute["color"].channel is Channel.AGENT_MESSAGE
    assert by_attribute["color"].raw_text == "something in frost"
    assert by_attribute["size"].source == "search.filters.size"
    assert by_attribute["color"].source == "search.query"


def test_a_query_nobody_read_is_said_so_rather_than_silently_dropped():
    result = intake(Search(query="something in frost", filters={"size": "M"}), SCHEMA,
                    agent=AgentPresence.INFERRED)

    assert [c.attribute for c in result.constraints] == ["size"]
    assert any("was not read" in note for note in result.notes)


# --- path (c): free text ---------------------------------------------------------------

def test_path_c_keeps_the_wording_and_names_the_field_it_came_from():
    """On the merchant surface this is the agent's paraphrase, and it does not need to be
    true — a paraphrase binds the agent's side, which is all a merchant-defence record
    requires."""
    result = intake(FreeText(text="a Frost duvet, size M"), SCHEMA, extract=reader)
    constraint = result.constraints[0]

    assert constraint.channel is Channel.AGENT_MESSAGE
    assert constraint.raw_text == "a Frost duvet, size M"
    assert constraint.source == "declared_intent"
    assert result.agent is AgentPresence.DECLARED


def test_what_the_extractor_could_not_read_is_carried_rather_than_dropped():
    """`unread` is what stops a requirement read too narrowly from being guaranteed, and
    the free-text paths are exactly where narrowing happens. An intake that returned
    constraints alone would drop it silently — kept separate from intake's own notes,
    because they answer different questions."""
    result = intake(FreeText(text="a Frost duvet, size M"), SCHEMA, extract=reader)

    assert result.unread == ("Text not explicitly accounted for: duvet",)
    assert result.unread[0] not in result.notes


def test_a_structured_order_has_nothing_unread_by_construction():
    """There was no prose, so there is no part of it we failed to read. Path (a) is the
    one shape where an empty `unread` is a fact rather than an absence of checking."""
    assert intake(Structured(protocol="acp", fields={"size": "M"}), SCHEMA).unread == ()


def test_an_empty_declared_intent_field_is_out_of_coverage_and_says_why():
    result = intake(FreeText(text="   "), SCHEMA, extract=reader)

    assert not result.covered
    assert any("present and empty" in note for note in result.notes)


# --- the absence, which is not a shape --------------------------------------------------

def test_an_order_carrying_no_stated_request_is_counted_rather_than_ignored():
    """DR 0020's uncovered slice: off-site discovery, direct arrival, no declaration. It
    bounds the product, so it is returned explicitly — "we read nothing" and "there was
    nothing to read" attribute differently."""
    result = intake(Undeclared(), SCHEMA)

    assert result.shape is Shape.UNDECLARED
    assert not result.covered and result.constraints == ()
    assert "no stated request accompanied this order" in result.notes


def test_an_unclassifiable_order_is_out_of_coverage_and_states_that():
    """A bare search query establishes nothing: humans use those too. Coverage attaches
    per channel, so an order we cannot place in a channel is outside it."""
    result = intake(Search(query="frost duvet"), SCHEMA, extract=reader)

    assert result.agent is AgentPresence.UNKNOWN
    assert not result.covered
    assert any("could not be classified" in note for note in result.notes)


def test_a_merchants_own_agent_signal_is_taken_but_never_invented():
    """A merchant whose checkout detects agents does so with their own data. Guessing on
    their behalf would put a fabricated basis on a dispute record."""
    artifact = Search(query="frost duvet", filters={"size": "M"})
    assert not intake(artifact, SCHEMA).covered
    assert intake(artifact, SCHEMA, agent=AgentPresence.INFERRED).covered


# --- one engine --------------------------------------------------------------------------

def test_every_shape_ends_at_the_same_input_the_engine_already_took():
    """The point of the layer. Two artifacts of different fidelity produce constraints the
    operators consume identically — no branch anywhere downstream knows which arrived."""
    evidence = (Evidence(attribute="size", value=Term(surface="M"), field_name="variant.size",
                         certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),)
    structured = intake(Structured(protocol="acp", fields={"size": "M"}), SCHEMA)
    typed = (Constraint(attribute="size", value=Term(surface="M"),
                        channel=Channel.AGENT_MESSAGE, raw_text="size M"),)

    from_intake = check_constraints(structured.constraints, evidence, SCHEMA)
    direct = check_constraints(typed, evidence, SCHEMA)

    assert [f.support for f in from_intake] == [f.support for f in direct]
    assert from_intake[0].support is Support.SATISFIED


def test_both_surfaces_use_the_same_normaliser():
    """Two surfaces, one engine. The surface is recorded on the row and changes nothing
    about how the request is read — it is the agent surface's *input* that is easier (the
    human's words rather than a paraphrase), not its machinery."""
    artifact = FreeText(text="a Frost duvet")
    merchant = intake(artifact, SCHEMA, extract=reader, surface=Surface.MERCHANT)
    agent = intake(artifact, SCHEMA, extract=reader, surface=Surface.AGENT)

    assert merchant.surface is Surface.MERCHANT and agent.surface is Surface.AGENT
    assert merchant.constraints == agent.constraints


def test_the_row_is_serialisable_and_keyed_by_merchant():
    """Durable and queryable on purpose: the distribution over shapes per merchant is the
    first of DR 0020's two unmeasured numbers. Keeping it is not building the analytics
    product; throwing it away would be the only thing that forecloses one."""
    result = intake(Structured(protocol="acp", fields={"size": "M"}), SCHEMA,
                    merchant_id="m-1")
    assert result.merchant_id == "m-1"
    assert json_roundtrips(result)


def json_roundtrips(result):
    return type(result).model_validate_json(result.model_dump_json()) == result
