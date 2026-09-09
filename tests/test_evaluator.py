"""The evaluator's rules, and the boundary that makes the company's claim checkable."""
import ast
import pathlib

import pytest

from approv.evaluator import HARD_CONFIDENCE_FLOOR, VERSION, decide
from approv.types.core import CheckKind, Criticality, Decision, Finding, Support


def finding(attribute, support, confidence, criticality=Criticality.HARD):
    return Finding(check=CheckKind.SATISFACTION, attribute=attribute, criticality=criticality,
                   support=support, confidence=confidence, ceiling=1.0)


def test_the_evaluator_imports_nothing_from_the_semantic_side():
    """CLAUDE.md §4.1, invariant 1. The claim is that a deterministic engine authorises
    and a model only describes. An import from algebra or harness would make that false
    silently, so it is asserted rather than trusted."""
    source = pathlib.Path("approv/evaluator/__init__.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    offending = {m for m in imported if m.startswith("approv.") and not m.startswith("approv.types")}
    assert not offending, f"evaluator must import only approv.types, found {offending}"


def test_a_contradicted_hard_attribute_refuses_and_names_itself():
    decision, reasons = decide((finding("size", Support.VIOLATED, 1.0),
                                finding("color", Support.SATISFIED, 1.0)))
    assert decision is Decision.REFUSE
    # An operator who cannot attribute a refusal to an attribute switches it off.
    assert reasons == ("size",)


@pytest.mark.parametrize("support,confidence", [(Support.UNSTATED, 0.0),
                                                (Support.SATISFIED, 0.9)])
def test_unknown_never_authorises(support, confidence):
    """§2.3. Silence and a source too weak to clear the bar are both unknown, and unknown
    routes to confirm. A value parsed out of prose reaches 0.9 at best, which is why the
    second case exists: it looks like agreement and is not established."""
    assert confidence < HARD_CONFIDENCE_FLOOR
    decision, reasons = decide((finding("size", support, confidence),))
    assert decision is Decision.CONFIRM and reasons == ("size",)


def test_soft_attributes_never_block():
    decision, reasons = decide((finding("color", Support.UNSTATED, 0.0, Criticality.SOFT),
                                finding("size", Support.SATISFIED, 1.0)))
    assert decision is Decision.ALLOW and reasons == ()


def test_a_violation_outranks_an_unknown():
    """Both fire; refuse wins. Confirming a listing that already contradicts the request
    asks the shopper to approve something we know is wrong."""
    decision, _ = decide((finding("size", Support.UNSTATED, 0.0),
                          finding("color", Support.VIOLATED, 1.0)))
    assert decision is Decision.REFUSE


def test_an_unmet_verification_floor_confirms_even_with_nothing_else_wrong():
    decision, reasons = decide((), floor_met=False)
    assert decision is Decision.CONFIRM and reasons == ("verification_floor",)


def test_the_version_is_stamped_so_a_receipt_can_be_replayed():
    assert VERSION and isinstance(VERSION, str)
