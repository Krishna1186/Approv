"""Catalogue coverage: what fraction of listings can be verified at all.

This is DR 0015 Route C. It needs no agent, no labelled data and no accuracy number —
only a catalogue and the verification floor. It answers a question a merchant genuinely
wants answered, which is what converts a cold ask into a warm one:

    "41% of your listings publish no net weight, so 41% of weight-sensitive agentic
     traffic cannot be verified on your store."

This measures coverage of the current adapter, not a universal verification ceiling. An engine cannot verify what a
catalogue does not publish, so this number bounds the best any verification layer could
ever achieve on this data — ours or anyone's.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from approv.harness.openfoodfacts import evidence_from, parse_quantity
from approv.types.core import Certainty


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. §4.6 requires an interval on every published number.

    Used instead of the textbook normal interval because that one misbehaves badly near
    0% and 100% — it can produce bounds below zero — and coverage numbers land near the
    extremes often.
    """
    if total < 0 or not 0 <= successes <= total or z <= 0:
        raise ValueError("invalid binomial counts or interval level")
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass(frozen=True)
class AttributeCoverage:
    attribute: str
    published: int
    total: int

    @property
    def rate(self) -> float:
        return self.published / self.total if self.total else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.published, self.total)


def coverage_report(records: list[dict]) -> dict[str, AttributeCoverage]:
    """How many listings publish each attribute in a form a comparison can use.

    "Publishes" means *parses into a typed value*, not "the field is non-empty". A
    quantity of `'1'` with no unit occupies the field and supports no comparison, so it
    is counted as absent. This is the distinction that makes the number honest.
    """
    total = len(records)
    counts: Counter[str] = Counter()

    for record in records:
        # Count *records*, not evidence items. One record yields two pieces of brand
        # evidence (the brands field and the title), and counting those separately would
        # report brand coverage above 100%.
        for attribute in {e.attribute for e in evidence_from(record) if e.certainty is Certainty.EXACT}:
            counts[attribute] += 1

    attributes = {"brand", "net_weight", "net_volume"} | set(counts)
    return {
        attribute: AttributeCoverage(attribute, counts.get(attribute, 0), total)
        for attribute in sorted(attributes)
    }


def field_occupied_but_unusable(records: list[dict]) -> tuple[int, int]:
    """Listings whose quantity field is filled in but does not parse.

    The gap between this and plain emptiness is the most actionable line in the report:
    the merchant believes these listings are complete and they are not.
    """
    filled = unusable = 0
    for record in records:
        raw = record.get("quantity")
        if raw in (None, "", []):
            continue
        filled += 1
        quantity, _ = parse_quantity(raw)
        if quantity is None:
            unusable += 1
    return unusable, filled
