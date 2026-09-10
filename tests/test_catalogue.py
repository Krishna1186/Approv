"""The retrieval repair: predicates over published fields, not more search terms."""
from datetime import datetime, timezone

from approv.harness.catalogue import build_index, describe, satisfying
from approv.harness.shopping import Inventory, Product
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Dimension,
    Evidence, FieldProfile, Liability, Term,
)

SCHEMA = CategorySchema(
    category_id="t", version="1",
    attributes=(
        AttributeSpec(name="product_type", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
    ),
    field_profiles=(
        FieldProfile(field_name="product.product_type", attributes=("product_type",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="variant.size", attributes=("size",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ),
)


def item(pid, kind, size):
    return Product(id=pid, title=pid, details={"title": pid}, evidence=(
        Evidence(attribute="product_type", value=Term(surface=kind),
                 field_name="product.product_type", certainty=Certainty.EXACT,
                 liability=Liability.MERCHANT_GUARANTEED),
        Evidence(attribute="size", value=Term(surface=size), field_name="variant.size",
                 certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ))


CATALOGUE = (item("boot-9", "Chelsea Boots", "9"), item("boot-8", "Chelsea Boots", "8"),
             item("shirt-9", "Dress Shirt", "9"))


def want(**kw):
    return tuple(Constraint(attribute=a, value=Term(surface=v), channel=Channel.AGENT_MESSAGE)
                 for a, v in kw.items())


def test_it_finds_what_search_over_a_text_blob_would_have_to_stumble_on():
    result = satisfying(want(product_type="Chelsea Boots", size="9"), CATALOGUE, SCHEMA)
    assert result["matches"] == ["boot-9"]
    assert result["checked"] == ["product_type", "size"]


def test_identity_is_a_predicate_not_a_search_term():
    """The measured reason product_type had to become a schema attribute: a filter on
    size alone returns the shirt too, and "no chelsea boot exists in size 13" is not a
    statement about size."""
    without = satisfying(want(size="9"), CATALOGUE, SCHEMA)
    with_kind = satisfying(want(product_type="Chelsea Boots", size="9"), CATALOGUE, SCHEMA)
    assert set(without["matches"]) == {"boot-9", "shirt-9"}
    assert with_kind["matches"] == ["boot-9"]


def test_an_unfillable_request_returns_nothing():
    assert satisfying(want(product_type="Chelsea Boots", size="13"), CATALOGUE, SCHEMA)["matches"] == []


def test_silence_is_not_satisfaction():
    """Section 2.3 in the optimistic half. A variant that publishes nothing for a required
    attribute is not offered, because an UNSTATED field means the catalogue is silent."""
    quiet = Product(id="quiet", title="q", details={"title": "q"}, evidence=())
    assert satisfying(want(size="9"), CATALOGUE + (quiet,), SCHEMA)["matches"] == ["boot-9", "shirt-9"]


def test_a_soft_attribute_does_not_filter():
    """Only HARD and BOUND requirements select. A preference is not a predicate."""
    result = satisfying(want(size="9", color="Purple"), CATALOGUE, SCHEMA)
    assert "color" not in result["checked"]
    assert set(result["matches"]) == {"boot-9", "shirt-9"}


def test_an_unencoded_detail_withholds_the_whole_filter():
    """Stricter than the shelf report on purpose. These variants were never retrieved by
    the agent, so they carry no other context: if part of the request went unencoded they
    were selected against an incomplete requirement set and nothing will catch it.

    Measured on the fresh corpus: gating costs 3 of 17 recoveries and removes the only
    wrong fill, a request for size "L || 2" that the extractor narrowed to "L"."""
    result = satisfying(want(product_type="Chelsea Boots", size="9"), CATALOGUE, SCHEMA,
                        unverified=("|| 2",))
    assert result["matches"] == []
    assert result["withheld"] == ["|| 2"]
    assert "not encoded" in describe(result, {})


def test_no_required_attribute_means_nothing_to_filter_on():
    assert satisfying((), CATALOGUE, SCHEMA)["matches"] == []
    assert satisfying(want(color="Purple"), CATALOGUE, SCHEMA)["matches"] == []


def test_the_index_agrees_with_the_unindexed_path():
    """The index is an optimisation. A second, faster notion of satisfaction that
    disagreed with the first would be worse than no filter at all."""
    constraints = want(product_type="Chelsea Boots", size="9")
    indexed = satisfying(constraints, CATALOGUE, SCHEMA, index=build_index(CATALOGUE, SCHEMA))
    plain = satisfying(constraints, CATALOGUE, SCHEMA)
    assert indexed["matches"] == plain["matches"]


def test_describe_names_variants_rather_than_the_predicate():
    """An agent handed `option_color == "Dark blue"` has to turn it back into a search.
    An agent handed an id can select it."""
    result = satisfying(want(product_type="Chelsea Boots", size="9"), CATALOGUE, SCHEMA)
    text = describe(result, {p.id: p for p in CATALOGUE})
    assert "boot-9" in text and "product_type, size" in text
    empty = satisfying(want(product_type="Chelsea Boots", size="13"), CATALOGUE, SCHEMA)
    assert "cannot be filled" in describe(empty, {})
