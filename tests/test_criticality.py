"""Per-transaction criticality: three layers, a cap, a floor, and a coverage mapping."""
import pytest

from approv.criticality import (
    COVERAGE_GAP_PREFIX, GUARANTEED, OUT_OF_COVERAGE, REFUSED, applied, calibrate_returns,
    coverage_of, narrowed_attributes, request_layer, resolve, returns_layer, schema_layer,
    superseded_attributes, unread_requirements,
)
from approv.types.core import (
    AttributeSpec, Bound, BoundOp, CategorySchema, Certainty, Channel, CheckKind,
    Constraint, Criticality, Dimension, FieldProfile, Finding, Liability, Money, Support,
    Term,
)

VARIANT = FieldProfile(field_name="variant.size", attributes=("size",), is_variant_axis=True,
                       certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED)
PROSE = FieldProfile(field_name="description", attributes=("material",),
                     certainty=Certainty.PARSED, liability=Liability.MERCHANT_GUARANTEED)


def want(attribute="size", surface="9", quote=None, value=None):
    return Constraint(attribute=attribute, value=value or Term(surface=surface),
                      channel=Channel.AGENT_MESSAGE, raw_text=quote)


# --- layer 1: the shopper's own phrasing --------------------------------------------

@pytest.mark.parametrize("quote", ["must be a 9", "exactly 9", "it needs to be 9",
                                   "only a 9 will do", "size 9 specifically"])
def test_emphasis_is_hard(quote):
    assert request_layer(want(quote=quote)) is Criticality.HARD


@pytest.mark.parametrize("quote", ["no nuts", "not leather", "without parabens",
                                   "nothing with nuts", "allergic to latex",
                                   "nut-free", "gluten free", "none of those"])
def test_negation_is_hard_whatever_the_category(quote):
    """Almost always allergy, safety or compatibility. Getting a negation wrong is the
    failure with a consequence outside the return window, and a static table cannot see
    it because the attribute is ordinary — it is the word "no" that is not."""
    assert request_layer(want(quote=quote)) is Criticality.HARD


def test_a_corrected_value_is_hard_because_the_effort_is_the_signal():
    """A shopper who bothers to supersede a value has demonstrated they care about it."""
    assert request_layer(want(quote="size 9"), superseded=True) is Criticality.HARD


@pytest.mark.parametrize("quote", ["preferably 9", "ideally a 9", "around 9",
                                   "a 9 or similar", "roughly 9", "open to 8 or 9"])
def test_a_hedge_is_soft(quote):
    assert request_layer(want(quote=quote)) is Criticality.SOFT


def test_a_hedge_beats_the_value_type():
    """"around 500 g" is still a hedge. The shopper saying "roughly" says more about their
    tolerance than the fact that they happened to reach for a number."""
    bound = want(attribute="price", quote="around £500",
                 value=Bound(op=BoundOp.LTE, limit=Money(amount="500.00", currency="GBP")))
    assert request_layer(bound) is Criticality.SOFT


def test_a_bound_is_a_bound():
    bound = want(attribute="price", quote="under £500",
                 value=Bound(op=BoundOp.LTE, limit=Money(amount="500.00", currency="GBP")))
    assert request_layer(bound) is Criticality.BOUND


def test_plainly_stated_is_bound():
    assert request_layer(want(quote="size 9")) is Criticality.BOUND


def test_stated_without_a_preserved_quote_still_floors_at_bound():
    """A channel that drops the wording must not also drop the requirement. Only "never
    stated" earns the 2.2 exemption, not "stated, and we failed to keep the words"."""
    assert request_layer(want(quote=None)) is Criticality.BOUND


def test_a_bare_free_is_not_a_negation():
    """"free shipping" is not "nut-free". The compound form needs a word in front of it,
    which is the whole difference."""
    assert request_layer(want(quote="free shipping included")) is Criticality.BOUND


def test_markers_are_matched_on_word_boundaries():
    """Substring matching fires "not" inside "notebook" and "only" inside "colonial", which
    turns ordinary requests hard at random."""
    assert request_layer(want(quote="a notebook in colonial blue")) is Criticality.BOUND


def test_supersession_notes_are_read_rather_than_re_derived():
    notes = ("Superseded, discarded: blue (color)", "chelsea boots",
             "Superseded, discarded: 8 (size)")
    assert superseded_attributes(notes) == frozenset({"color", "size"})
    assert superseded_attributes(()) == frozenset()


# --- layer 2: the merchant's own merchandising ---------------------------------------

def test_a_variant_axis_is_at_least_bound():
    """They carry a separate SKU per value. Nobody stocks twelve variants of something
    customers do not choose on, so the merchandising decision is the signal."""
    assert schema_layer("size", (VARIANT,)) is Criticality.BOUND


def test_description_prose_only_is_soft():
    assert schema_layer("material", (PROSE,)) is Criticality.SOFT


def test_an_attribute_with_no_profile_gives_no_signal():
    assert schema_layer("unknown", (VARIANT, PROSE)) is None


def test_the_verification_floor_survives_the_per_transaction_layers():
    """The floor says the category cannot be checked at all without the attribute — about
    whether a comparison is possible, not about how much the shopper cares. Letting it
    fall to SOFT is "unknown authorises" by a side door."""
    assert schema_layer("size", (), in_floor=True) is Criticality.BOUND


# --- layer 3: the merchant's own return history --------------------------------------

def test_returns_calibration_reads_what_customers_did_not_what_they_typed():
    """Return item A, reorder item B: the attributes that differ are the ones that
    mattered. No labels, no reason codes, no human judgement."""
    pairs = [({"size": "8", "color": "navy"}, {"size": "9", "color": "navy"}),
             ({"size": "7", "color": "navy"}, {"size": "8", "color": "navy"}),
             ({"size": "10", "color": "red"}, {"size": "11", "color": "red"})]
    rates = calibrate_returns(pairs, prior_weight=0.0)

    assert rates["size"] == 1.0
    assert rates["color"] == 0.0


def test_low_counts_are_shrunk_toward_the_prior():
    """A merchant with three returns should get the prior, not a table of 0.0 and 1.0."""
    pairs = [({"size": "8"}, {"size": "9"})]
    alone = calibrate_returns(pairs, prior_weight=0.0)
    shrunk = calibrate_returns(pairs, prior={"size": 0.3}, prior_weight=5.0)

    assert alone["size"] == 1.0
    assert 0.3 < shrunk["size"] < 1.0


def test_differ_rate_ranks_into_criticality():
    rates = {"size": 0.8, "color": 0.3, "material": 0.01}
    assert returns_layer("size", rates) is Criticality.HARD
    assert returns_layer("color", rates) is Criticality.BOUND
    assert returns_layer("material", rates) is None
    assert returns_layer("absent", rates) is None


def test_no_returns_data_is_no_signal_rather_than_evidence_of_unimportance():
    assert returns_layer("size", None) is None
    assert returns_layer("size", {}) is None


# --- combination ----------------------------------------------------------------------

def test_the_strongest_layer_wins_when_they_point_up():
    """`max` across the layers, for the raising direction."""
    level = resolve("size", constraint=want(quote="size 9"), profiles=(VARIANT,),
                    returns={"size": 0.9})
    assert level is Criticality.HARD


def test_an_explicit_hedge_caps_rather_than_contributing():
    """The deviation from plain `max`, and it was forced by measurement.

    Layers 2 and 3 are priors — customers in general choose on this axis, this attribute
    in general drives returns. Layer 1 is direct evidence about this transaction. `max`
    treats all three as equally authoritative, so a signal pointing *down* cannot survive
    it. On the v3 pack every hedged request produced "preferably in Tan" and "around size
    M or similar" in the quote, `request_layer` returned SOFT for each, and `max` raised
    all of them back to BOUND because colour and size are variant axes. SOFT stayed at
    zero of 176 — the exact outcome the hedged families were added to prevent.

    A merchant's merchandising cannot outrank this shopper saying "preferably" about the
    thing being merchandised. Under the guarantee the result is coherent: we neither block
    the sale nor insure the attribute, which is what the shopper asked for by hedging."""
    level = resolve("size", constraint=want(quote="ideally a 9"), profiles=(VARIANT,),
                    returns={"size": 0.9})
    assert level is Criticality.SOFT


def test_only_a_hedge_caps_not_every_low_signal():
    """`request_layer` returns SOFT for a hedge and nothing else, so the cap tests exactly
    that case. A plainly stated value still takes the strongest layer."""
    assert request_layer(want(quote="size 9")) is not Criticality.SOFT
    assert resolve("size", constraint=want(quote="size 9"), returns={"size": 0.9}) is Criticality.HARD


def test_an_attribute_the_shopper_never_mentioned_is_never_hard():
    """2.2 in force. Silence is nobody's fault, so refusing a sale over it would attribute
    a failure to a party that did not fail — however the merchant merchandises it and
    however often it drives returns."""
    level = resolve("size", constraint=None, profiles=(VARIANT,), returns={"size": 0.99})
    assert level is Criticality.BOUND


def test_no_signal_anywhere_floors_to_soft():
    """A missed check costs nothing until it is tested; a wrongly-hard check blocks a real
    sale immediately. Every ambiguity resolves toward not blocking."""
    assert resolve("mystery", constraint=None) is Criticality.SOFT


def test_applied_resolves_the_whole_schema_without_touching_the_operators():
    schema = CategorySchema(
        category_id="t", version="1",
        attributes=(
            AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
            AttributeSpec(name="material", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        ),
        field_profiles=(VARIANT, PROSE))
    specs = applied(schema, (want(quote="must be a 9"),))

    # The static table said size was soft and material hard. This transaction says the
    # opposite, and the transaction is what the shopper actually asked for.
    assert specs["size"].criticality is Criticality.HARD
    assert specs["material"].criticality is Criticality.SOFT
    assert specs["size"].dimension is Dimension.NOMINAL


# --- coverage ---------------------------------------------------------------------------

def finding(criticality, support):
    return Finding(check=CheckKind.SATISFACTION, attribute="size", criticality=criticality,
                   support=support, confidence=1.0, ceiling=1.0)


def test_criticality_maps_to_coverage_not_only_to_the_decision():
    """Property 6. Under a guarantee a false SOFT costs us a payout and a false HARD costs
    the merchant a sale, so the two land on different balance sheets."""
    assert coverage_of(finding(Criticality.HARD, Support.SATISFIED)) == GUARANTEED
    assert coverage_of(finding(Criticality.BOUND, Support.SATISFIED)) == GUARANTEED
    assert coverage_of(finding(Criticality.HARD, Support.VIOLATED)) == REFUSED


def test_a_soft_mismatch_is_declined_insurance_not_a_blocked_sale():
    """We never block on a soft mismatch. The merchant keeps the order and keeps the risk
    on that attribute, which is right when we have no evidence the shopper cared."""
    assert coverage_of(finding(Criticality.SOFT, Support.VIOLATED)) == OUT_OF_COVERAGE
    assert coverage_of(finding(Criticality.SOFT, Support.SATISFIED)) == OUT_OF_COVERAGE


def test_an_unstated_attribute_is_out_of_coverage_even_when_satisfied():
    """The record cannot claim to have honoured a requirement nobody made."""
    assert coverage_of(finding(Criticality.HARD, Support.UNSTATED)) == OUT_OF_COVERAGE


# --- narrowing: a value read from more words than it kept ------------------------------

def gap(text):
    return (COVERAGE_GAP_PREFIX + text,)


def test_a_value_narrower_than_its_own_quote_is_detected():
    """The one measured failure mode that costs money, and the case it was measured on.

    `shopper2-78-plain` asked for "a Tandem Stripe in Frost", the extractor recorded
    colour as "Frost", the catalogue publishes colour "Frost", so the comparison was
    SATISFIED and the record guaranteed it. The product was the wrong line. Set
    arithmetic on the quote finds it with no model call:

        {a, tandem, stripe, in, frost} - {frost} intersects {tandem, stripe}
    """
    constraint = want("color", "Frost", quote="a Tandem Stripe in Frost")
    assert narrowed_attributes((constraint,), gap("tandem stripe")) == {"color"}


def test_a_hedge_in_the_gap_is_not_a_narrowing():
    """Six of the twenty-four gap notes on the v3 pack were nothing but hedge words.
    "preferably" carries no value, so it reaches no constraint and the gap names it — but
    it was read, by `request_layer`, and it is the reason the finding is SOFT. Counting it
    as dropped text would put every hedged attribute out of coverage for the wrong
    reason."""
    constraint = want("color", "Tan", quote="preferably in Tan")
    assert narrowed_attributes((constraint,), gap("preferably")) == frozenset()


def test_a_split_marker_phrase_is_still_a_marker():
    """The gap residual is a bag of words with stopwords stripped, so "or similar" arrives
    as "similar". The quote still has the phrase intact, which is why markers are read off
    the quote rather than off the note."""
    constraint = want("size", "M", quote="around size M or similar")
    assert narrowed_attributes((constraint,), gap("around similar")) == frozenset()


def test_a_gap_belonging_to_another_clause_marks_nothing():
    """Scoping to the constraint's own quote is what keeps this from being global. "no
    rush" is genuinely dropped and genuinely uncoverable, but it says nothing about
    whether the colour was read correctly."""
    constraint = want("color", "Tan", quote="a Tan jacket")
    assert narrowed_attributes((constraint,), gap("delivery speed rush")) == frozenset()


def test_a_constraint_with_no_quote_is_not_narrowed():
    """A structured channel that carries no wording cannot have narrowed the wording.
    Absent evidence of a gap is not evidence of one."""
    assert narrowed_attributes((want("color", "Frost"),), gap("tandem stripe")) == frozenset()


def test_a_gap_that_is_nothing_but_the_shoppers_hedge_names_nothing_unread():
    """DR 0022. "preferably" carries no value, so it reaches no constraint and the gap
    detector names it — but it was read, by `request_layer`, and it is why the finding is
    SOFT. Under a record-level withdrawal this would surrender the whole record's guarantee
    because the shopper hedged, which is the opposite of what a hedge means. 8 of the 28 v3
    cases carrying a note were exactly this."""
    hedged = (want("color", "Tan", quote="preferably in Tan"),)
    assert unread_requirements(hedged, gap("preferably")) == ()


def test_a_split_marker_phrase_still_names_nothing_unread():
    """Read off the quote, not the note: the residual is a bag of words with stopwords
    stripped, so "or similar" arrives as "similar" and the note alone cannot tell."""
    hedged = (want("size", "M", quote="around size M or similar"),)
    assert unread_requirements(hedged, gap("around similar")) == ()


def test_a_real_gap_survives_the_marker_filter():
    stated = (want("color", "Frost", quote="a Tandem Stripe in Frost"),)
    assert unread_requirements(stated, gap("tandem stripe")) == (
        COVERAGE_GAP_PREFIX + "tandem stripe",)


def test_a_gap_that_is_part_marker_and_part_content_survives():
    """Only a residual that is *entirely* marker words names nothing. "ideally Oxford
    Stripe" dropped a pattern the record cannot claim to have checked."""
    stated = (want("color", "Fresh Moss", quote="ideally Oxford Stripe in Fresh Moss"),)
    assert unread_requirements(stated, gap("ideally oxford stripe")) != ()


def test_a_dropped_requirement_that_is_not_a_gap_is_untouched():
    """The marker rule is about the gap detector's own false positives. An unsupported
    requirement is unread whatever words are in the quotes."""
    notes = ("Unsupported requirement: gift_wrap",)
    assert unread_requirements((want("color", "Tan", quote="preferably in Tan"),),
                               notes) == notes


def test_a_note_that_is_not_a_dropped_requirement_never_reaches_here():
    """DR 0021 still governs what counts at all; this only narrows it further."""
    assert unread_requirements((), ("Superseded, discarded: Black (color)",)) == ()


def test_an_unread_request_withdraws_the_guarantee_from_the_whole_record():
    """DR 0022, and the reason it is not attribute-scoped: a gap belonging to no
    constraint has no attribute to scope to. A guarantee promises that this order was as
    asked, and a request we did not finish reading cannot support that about any
    attribute, however cleanly the ones we did read compare."""
    assert coverage_of(finding(Criticality.HARD, Support.SATISFIED),
                       request_unread=True) == OUT_OF_COVERAGE
    assert coverage_of(finding(Criticality.HARD, Support.VIOLATED),
                       request_unread=True) == REFUSED


def test_a_verification_that_did_not_complete_carries_no_guarantee(): 
    """DR 0004, and it is not the same fact as the other two. Narrowing and an unread
    request are readings we can characterise; this is the absence of a reading. Whatever
    the findings say, they came from a check that did not finish."""
    assert coverage_of(finding(Criticality.HARD, Support.SATISFIED),
                       incomplete=True) == OUT_OF_COVERAGE
    assert coverage_of(finding(Criticality.HARD, Support.VIOLATED),
                       incomplete=True) == REFUSED


def test_narrowing_withdraws_the_guarantee_and_nothing_else():
    """It changes what the record promises, never what it decides. Relabelling a REFUSED
    finding would report that we made no claim when in fact we blocked the sale."""
    assert coverage_of(finding(Criticality.HARD, Support.SATISFIED),
                       narrowed=True) == OUT_OF_COVERAGE
    assert coverage_of(finding(Criticality.HARD, Support.VIOLATED),
                       narrowed=True) == REFUSED


def test_a_budget_cap_is_a_bound_even_though_it_is_phrased_as_a_negation():
    """"Nothing over $305" is price <= 305. The word that makes it a negation is the same
    word that makes it a cap, and the operator has already consumed it — reading it as a
    safety exclusion turns a budget into an allergy. It fired on 7 of 34 held-out cases
    the first time the negation lexicon was widened."""
    cap = want(attribute="price", quote="Nothing over $305",
               value=Bound(op=BoundOp.LTE, limit=Money(amount="305.00", currency="USD")))
    assert request_layer(cap) is Criticality.BOUND


def test_a_genuine_exclusion_still_escalates_because_it_carries_a_term():
    assert request_layer(want(quote="no nuts")) is Criticality.HARD


def test_emphasis_still_outranks_a_bound():
    firm = want(attribute="price", quote="it must be under $305",
                value=Bound(op=BoundOp.LTE, limit=Money(amount="305.00", currency="USD")))
    assert request_layer(firm) is Criticality.HARD
