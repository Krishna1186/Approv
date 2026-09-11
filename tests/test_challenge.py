"""CONFIRM as a bounded evidentiary challenge."""
import pytest

from approv.challenge import (
    Challenge, Citation, challenges_for, render, resolve,
)
from approv.algebra.runner import check_constraints
from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Channel, Constraint, Criticality, Decision,
    Dimension, Evidence, FieldProfile, Liability, ReasonCode, Support, Term,
)

SCHEMA = CategorySchema(
    category_id="t", version="1",
    attributes=(
        AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
    ),
    field_profiles=(
        FieldProfile(field_name="variant.size", attributes=("size",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="description", attributes=("size",),
                     certainty=Certainty.PARSED, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name="review", attributes=("size",),
                     certainty=Certainty.PARSED, liability=Liability.UNATTRIBUTED),
        FieldProfile(field_name="seller.note", attributes=("size",),
                     certainty=Certainty.PARSED, liability=Liability.SELLER_STATED,
                     is_advice=True),
    ),
)

WANT = (Constraint(attribute="size", value=Term(surface="9"), channel=Channel.AGENT_MESSAGE),)


def evidence(field, surface="9", certainty=Certainty.EXACT,
             liability=Liability.MERCHANT_GUARANTEED, advice=False, attribute="size"):
    return Evidence(attribute=attribute, value=Term(surface=surface), field_name=field,
                    certainty=certainty, liability=liability, is_advice=advice)


def findings_for(evidence_tuple):
    return check_constraints(WANT, evidence_tuple, SCHEMA)


def reader(mapping):
    return lambda citation: mapping.get(citation.field_name)


# --- raising the challenge ---------------------------------------------------------

def test_a_silent_listing_raises_a_challenge_naming_the_attribute_and_the_bar():
    challenges = challenges_for(findings_for(()), SCHEMA)

    assert [c.attribute for c in challenges] == ["size"]
    assert ReasonCode.PRODUCT_SILENT in challenges[0].reasons
    assert challenges[0].needs_liability is Liability.SELLER_STATED


def test_a_soft_attribute_is_never_challenged():
    """It never held the decision up, so a round spent on it changes nothing. Softness is
    now per transaction: the shopper hedged, so this purchase does not turn on it."""
    hedged = (Constraint(attribute="size", value=Term(surface="9"),
                         channel=Channel.AGENT_MESSAGE, raw_text="ideally a 9"),)
    assert challenges_for(check_constraints(hedged, (), SCHEMA), SCHEMA) == ()


def test_a_settled_attribute_is_not_challenged():
    assert challenges_for(findings_for((evidence("variant.size"),)), SCHEMA) == ()


def test_the_challenge_names_what_was_already_read():
    """So the agent cannot answer with the same weak source that raised it."""
    challenges = challenges_for(
        findings_for((evidence("description", certainty=Certainty.PARSED),)), SCHEMA)

    assert challenges[0].consulted == ("description",)
    assert challenges[0].needs_certainty is Certainty.EXACT


def test_the_rendered_challenge_asks_for_a_source_not_an_answer():
    text = render(challenges_for(findings_for(()), SCHEMA))
    assert "Do not state the value" in text
    assert "size" in text


# --- the safety property -----------------------------------------------------------

def test_a_citation_carries_no_value():
    """The whole design. An agent that could state the value could clear its own check."""
    assert "value" not in Citation.model_fields


def test_approv_reads_the_source_rather_than_trusting_the_agent():
    """The agent points at `variant.size`; what that field says is the merchant's to say.
    Here it says 8, so the citation is admitted and the answer is REFUSE, not ALLOW."""
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size", surface="8")}))

    assert outcome.decision is Decision.REFUSE
    assert outcome.admitted and not outcome.rejected


def test_a_citation_that_resolves_the_gap_allows():
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size")}))

    assert outcome.decision is Decision.ALLOW


def test_advice_can_never_settle_a_fact():
    """"runs small, size up" does not change what size the item is. If advice could clear
    a HARD attribute, one line of seller copy moves the decision."""
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="seller.note"),),
                      reader({"seller.note": evidence("seller.note", advice=True,
                                                      liability=Liability.SELLER_STATED)}))

    assert outcome.decision is Decision.REFUSE
    assert outcome.rejected[0][1] == "advice may lower confidence, never establish a fact"


def test_a_source_nobody_is_answerable_for_is_inadmissible():
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="review"),),
                      reader({"review": evidence("review", liability=Liability.UNATTRIBUTED,
                                                 certainty=Certainty.PARSED)}))

    assert outcome.decision is Decision.REFUSE
    assert "answerable" in outcome.rejected[0][1]


def test_re_offering_the_source_that_raised_the_challenge_is_rejected():
    """Otherwise a bounded round is trivially made unbounded."""
    weak = evidence("description", certainty=Certainty.PARSED)
    challenges = challenges_for(findings_for((weak,)), SCHEMA)
    outcome = resolve(WANT, (weak,), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="description"),),
                      reader({"description": weak}))

    assert outcome.decision is Decision.REFUSE
    assert "already read" in outcome.rejected[0][1]


def test_an_unreadable_source_is_not_a_resolution():
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="nowhere"),),
                      reader({}))

    assert outcome.decision is Decision.REFUSE
    assert "could not be read" in outcome.rejected[0][1]


def test_a_citation_for_an_unchallenged_attribute_is_ignored():
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="color", field_name="variant.color"),),
                      reader({}))

    assert outcome.rejected[0][1] == "no challenge was raised for that attribute"


def test_two_exact_sources_that_disagree_stay_unresolved_and_so_refuse():
    """Conflict handling is the runner's and needs no special case here. Two sources of
    equal standing that disagree leave the attribute unresolved, and unresolved after the
    round refuses rather than confirming again."""
    schema = SCHEMA.model_copy(update={"field_profiles": SCHEMA.field_profiles + (
        FieldProfile(field_name="spec.table", attributes=("size",),
                     certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),)})
    known = evidence("spec.table", surface="8")
    challenges = challenges_for(check_constraints(WANT, (), schema), schema)
    outcome = resolve(WANT, (known,), schema, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size", surface="9")}))

    assert outcome.decision is Decision.REFUSE
    assert ReasonCode.FIELD_CONFLICT in outcome.findings[0].reasons


def test_an_exact_field_outranks_a_prose_mention_that_disagrees():
    """The certainty ladder, at the point where it pays for itself. A description saying
    "8" against a variant field saying "9" is not a conflict — DR 0016 puts a description
    at high liability and low certainty, so the structured field settles it. Treating this
    as a conflict would make every listing whose prose is loosely worded unverifiable."""
    known = evidence("description", surface="8", certainty=Certainty.PARSED)
    challenges = challenges_for(findings_for((known,)), SCHEMA)
    outcome = resolve(WANT, (known,), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size", surface="9")}))

    assert outcome.decision is Decision.ALLOW


# --- boundedness -------------------------------------------------------------------

def test_the_round_never_returns_confirm():
    """A state that can recur is a negotiation, and a checker that can be negotiated with
    is not a checker. Silence is not a yes."""
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges, (), reader({}))

    assert outcome.decision is Decision.REFUSE
    assert outcome.decision is not Decision.CONFIRM


def test_an_unmet_floor_still_refuses_after_the_round():
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size")}), floor_met=False)

    assert outcome.decision is Decision.REFUSE


def test_resolution_reuses_the_ordinary_comparison():
    """No second notion of satisfaction. The cited evidence is appended and the same
    check_constraints runs, so certainty ceilings, conflict and liability all behave as
    they do everywhere else."""
    challenges = challenges_for(findings_for(()), SCHEMA)
    outcome = resolve(WANT, (), SCHEMA, challenges,
                      (Citation(attribute="size", field_name="variant.size"),),
                      reader({"variant.size": evidence("variant.size")}))
    direct = check_constraints(WANT, (evidence("variant.size"),), SCHEMA)

    assert [f.support for f in outcome.findings] == [f.support for f in direct]
