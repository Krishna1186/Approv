"""Legacy title-to-brand diagnostic. OFF field agreement is not accuracy.

Use the shopping harness and separate human labels for task improvement experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from approv.algebra.feedback import explain_all
from approv.algebra.runner import run_checks
from approv.harness.coverage import wilson
from approv.harness.openfoodfacts import evidence_from, OFF_FIELD_PROFILES
from approv.types.core import (
    AttributeSpec,
    CategorySchema,
    Channel,
    Claim,
    Criticality,
    Dimension,
    Finding,
    Support,
    Term,
)

BRAND_SCHEMA = CategorySchema(
    category_id="grocery.any",
    version="v1",
    attributes=(
        AttributeSpec(
            name="brand", dimension=Dimension.NOMINAL, criticality=Criticality.HARD
        ),
    ),
    field_profiles=OFF_FIELD_PROFILES,
)


class Agent(Protocol):
    """Anything that can answer a question about a product, optionally after feedback.

    Deliberately tiny. The point is that a real Claude, GPT or Gemini call slots in here
    without the harness knowing which, so the same measurement runs across vendors and
    the number is not secretly a statement about one of them.
    """

    def __call__(self, title: str, feedback: str | None = None) -> str: ...


@dataclass
class ArmResult:
    name: str
    correct: int = 0
    total: int = 0
    abstained: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def abstention_rate(self) -> float:
        return self.abstained / self.total if self.total else 0.0

    @property
    def accuracy_when_answered(self) -> float:
        """Accuracy over attempts where the agent actually committed to a brand.

        Reported separately because an abstention is not an error. Approv's signal is
        "the listing does not support this", so an agent that responds by admitting it
        does not know has done the *right* thing — and scoring that as a failure would
        systematically punish arm C for making the agent more honest. Judging the two
        together would have produced a misleading negative result.
        """
        answered = self.total - self.abstained
        return self.correct / answered if answered else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.correct, self.total)


@dataclass
class BenchmarkResult:
    arms: dict[str, ArmResult] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)

    def improvement(self) -> tuple[float, str]:
        """C minus B field agreement diagnostic; not an independent accuracy estimate."""
        control = self.arms.get("B_blind_retry")
        treatment = self.arms.get("C_approv_feedback")
        if not control or not treatment:
            return 0.0, "incomplete — both arms B and C are required"
        delta = treatment.accuracy - control.accuracy
        return delta, (
            f"C {treatment.accuracy:.1%} - B {control.accuracy:.1%} = {delta:+.1%} "
            f"(n={treatment.total})"
        )


def _claim_from(answer: str) -> Claim:
    return Claim(
        attribute="brand",
        value=Term(surface=answer.strip()),
        channel=Channel.AGENT_MESSAGE,
    )


_ABSTENTIONS = frozenset({"unknown", "unsure", "unclear", "none", "na"})


def is_abstention(answer: str) -> bool:
    """Did the agent decline to name a brand rather than guess one?

    An **empty** answer is not an abstention. It is a broken call, and treating it as
    one let 29 failed API responses be recorded as "the agent honestly declined" in the
    first full run — a measurement reporting model behaviour that never happened. The
    caller must raise on empty rather than pass it here.
    """
    from approv.algebra.term import _tokens

    if not answer.strip():
        raise ValueError("empty agent response is a failed call, not an abstention")
    return answer.strip().casefold() in _ABSTENTIONS


def _is_correct(answer: str, truth: str) -> bool:
    """Exact normalized field agreement, not independent accuracy or grounding gold."""
    import re
    import unicodedata
    def key(value):
        return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", value).casefold()).split())
    if is_abstention(answer):
        return False
    return any(key(answer) == key(candidate) for candidate in truth.split(",") if candidate.strip())


def brand_in_title(record: dict) -> bool:
    """Is the brand literally present in the product title?

    Splits the corpus into a trivial subset (the agent need only copy) and a real one
    (the agent must know that Good Day is a Britannia product). Reporting only the
    combined number would hide the effect inside a pile of copy jobs.
    """
    from approv.algebra.term import _tokens

    title = _tokens(record.get("product_name") or "")
    for candidate in (record.get("brands") or "").split(","):
        expected = _tokens(candidate)
        if expected and expected <= title:
            return True
    return False


def subset(result: "BenchmarkResult", *, brand_in_title_value: bool) -> dict[str, ArmResult]:
    """Recompute arm results over only the rows matching the subset flag."""
    arms = {name: ArmResult(name) for name in result.arms}
    for row in result.transcript:
        if row["brand_in_title"] is not brand_in_title_value:
            continue
        for key, name in (("A", "A_baseline"), ("B", "B_blind_retry"),
                          ("C", "C_approv_feedback")):
            entry = arms[name]
            entry.total += 1
            if row["abstained"][key]:
                entry.abstained += 1
            elif row["correct"][key]:
                entry.correct += 1
    return arms


def _findings_for(answer: str, record: dict) -> tuple[Finding, ...]:
    evidence = tuple(e for e in evidence_from(record) if e.attribute == "brand")
    # An abstention is not a claim. Passing "UNKNOWN" through as a brand produced
    # `MISMATCH brand: claimed UNKNOWN`, which compares the word "UNKNOWN" against the
    # catalogue as though the agent had asserted it. Withholding an answer should yield
    # NO_CLAIM, which is what the runner emits when there is nothing to check.
    claims = () if is_abstention(answer) else (_claim_from(answer),)
    return run_checks(claims, evidence, BRAND_SCHEMA)


def run_benchmark(
    records: list[dict],
    agent: Agent,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> BenchmarkResult:
    """Run all three arms over the given records.

    Only records carrying both a title and a brand are used; everything else has no
    ground truth. That filter is on data availability, never on difficulty — filtering
    on difficulty is how benchmarks get quietly rigged.
    """
    usable = [
        r for r in records
        if (r.get("product_name") or "").strip() and (r.get("brands") or "").strip()
    ]

    result = BenchmarkResult(
        arms={
            "A_baseline": ArmResult("A_baseline"),
            "B_blind_retry": ArmResult("B_blind_retry"),
            "C_approv_feedback": ArmResult("C_approv_feedback"),
        }
    )

    for index, record in enumerate(usable, start=1):
        title = record["product_name"].strip()
        truth = record["brands"].strip()

        first = agent(title)
        findings = _findings_for(first, record)

        blind = agent(title, f"Your first answer was: {first!r}. Some of your answer may be wrong. Answer again.")
        guided = agent(title, f"Your first answer was: {first!r}. " + explain_all(findings, reveal=False))

        for arm, answer in (
            ("A_baseline", first),
            ("B_blind_retry", blind),
            ("C_approv_feedback", guided),
        ):
            entry = result.arms[arm]
            entry.total += 1
            if is_abstention(answer):
                entry.abstained += 1
            elif _is_correct(answer, truth):
                entry.correct += 1

        result.transcript.append(
            {
                "code": record.get("code"),
                "title": title,
                "truth": truth,
                "A": first,
                "B": blind,
                "C": guided,
                "approv_said": explain_all(findings, reveal=False),
                "approv_support": [f.support.value for f in findings],
                "correct": {k: _is_correct(v, truth) for k, v in
                            (("A", first), ("B", blind), ("C", guided))},
                "abstained": {k: is_abstention(v) for k, v in
                              (("A", first), ("B", blind), ("C", guided))},
                # The interesting subset. Where the brand is already sitting in the
                # title, all three arms are doing a copy job and will converge, diluting
                # any real effect. Tagged here so results can be split.
                "brand_in_title": brand_in_title(record),
            }
        )

        if on_progress:
            on_progress(index, len(usable))

    return result
