"""Recovering a stated requirement the extractor filed as unverified."""
import pytest

from approv.harness.request_literals import recover_noted_values
from approv.harness.shopping import ShoppingCase
from approv.types.core import (
    AttributeSpec, CategorySchema, Channel, Constraint, Criticality, Dimension, Term,
)

SCHEMA = CategorySchema(
    category_id="t", version="1",
    attributes=(
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="availability", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
    ),
    field_profiles=(),
)
PUBLISHED = {"color": {"stone two tone", "pride", "black"},
             "size": {"king cali king", "m"},
             "availability": {"in stock", "out of stock"}}


def case(request, constraints=(), notes=()):
    return ShoppingCase(id="c", request=request, author="t", cluster="t",
                        constraints=constraints, interpretation_notes=notes)


def sized(surface="M"):
    return (Constraint(attribute="size", value=Term(surface=surface),
                       channel=Channel.AGENT_MESSAGE),)


def test_a_note_that_is_a_published_value_becomes_a_requirement():
    """fresh-42: the request said "Stone Two Tone", the extractor had no colour list to
    map onto and filed it as unverified, and the gate then cleared three comforters in the
    wrong colour. The value was sitting in the record the whole time."""
    fixed, changes = recover_noted_values(
        case("after a comforter - Stone Two Tone, size M", sized(), ("Stone Two Tone",)),
        SCHEMA, PUBLISHED)

    assert changes == [{"recovered": "color", "surface": "Stone Two Tone"}]
    assert {c.attribute for c in fixed.constraints} == {"size", "color"}
    # It stops being unread, which is the point: it no longer fails the floor.
    assert fixed.interpretation_notes == ()


def test_nothing_is_invented_from_outside_the_request():
    """The note must appear in the shopper's own words. A model that hallucinates a note
    must not have it promoted into a requirement."""
    fixed, changes = recover_noted_values(
        case("size M please", sized(), ("Pride",)), SCHEMA, PUBLISHED)

    assert changes == []
    assert fixed.interpretation_notes == ("Pride",)


def test_an_ambiguous_surface_is_left_alone():
    """A value published for two attributes cannot be assigned without guessing which,
    and guessing is exactly the inference this avoids."""
    published = {"color": {"black"}, "size": {"black"}}
    fixed, changes = recover_noted_values(
        case("I want black", notes=("black",)), SCHEMA, published)

    assert changes == []
    assert fixed.interpretation_notes == ("black",)


def test_recovery_never_overwrites_what_the_model_did_state():
    """Only an unconstrained attribute can be filled, so a recovery can never contradict
    or replace a requirement the extractor actually read."""
    stated = (Constraint(attribute="color", value=Term(surface="Black"),
                         channel=Channel.AGENT_MESSAGE),)
    fixed, changes = recover_noted_values(
        case("Pride, but make it Black", stated, ("Pride",)), SCHEMA, PUBLISHED)

    assert changes == []
    assert [c.value.surface for c in fixed.constraints] == ["Black"]


def test_a_note_that_is_not_a_published_value_stays_a_note():
    """"not backordered" means in stock and is not a value any field publishes. Reading it
    would be inference; it stays unread and still fails the floor."""
    fixed, changes = recover_noted_values(
        case("needs to be there, not backordered", sized(), ("not backordered",)),
        SCHEMA, PUBLISHED)

    assert changes == []
    assert fixed.interpretation_notes == ("not backordered",)


def test_matching_uses_the_comparison_identity_key():
    """Recovery is only safe because the match is the same key the operators use, so a
    recovered value compares exactly as it would have had the model emitted it."""
    fixed, changes = recover_noted_values(
        case("in-stock please", sized(), ("in-stock",)), SCHEMA, PUBLISHED)

    assert changes == [{"recovered": "availability", "surface": "in-stock"}]
    assert fixed.interpretation_notes == ()


def test_an_attribute_outside_the_schema_is_never_recovered():
    fixed, changes = recover_noted_values(
        case("a Rothy's please", sized(), ("Rothy's",)), SCHEMA, {"brand": {"rothy s"}})

    assert changes == []
