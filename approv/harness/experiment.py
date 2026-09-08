"""Paired experiments and independent, human-authored outcome scoring."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import random
from pathlib import Path
from typing import Callable

from pydantic import Field, model_validator

from approv.harness.coverage import wilson
from approv.harness.shopping import (
    Agent, Arm, Frozen, Inventory, RunConfig, Session, ShoppingCase, canonical,
    digest, replay, run_session,
)


class AcceptedSelection(Frozen):
    product_id: str = Field(min_length=1)
    units: int = Field(ge=1, strict=True)


class Annotation(Frozen):
    case_id: str
    case_hash: str
    accepted: tuple[AcceptedSelection, ...] = ()
    abstention_correct: bool = False
    annotator: str = Field(min_length=1)
    evidence_notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def outcome_exists(self):
        if not self.accepted and not self.abstention_correct:
            raise ValueError("label must specify an accepted selection or correct abstention")
        return self


class GoldSet(Frozen):
    inventory_hash: str
    provenance: str = Field(min_length=1)
    label_method: str = "human"
    annotations: tuple[Annotation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def human_and_unique(self):
        if self.label_method != "human":
            raise ValueError("accuracy scoring requires independently human-authored labels")
        if len({a.case_id for a in self.annotations}) != len(self.annotations):
            raise ValueError("duplicate annotations")
        return self


def validate_cases(cases: list[ShoppingCase]) -> None:
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("cases must be nonempty with unique IDs")


def validate_gold(gold: GoldSet, inventory: Inventory, cases: list[ShoppingCase]):
    if gold.inventory_hash != digest(inventory):
        raise ValueError("gold belongs to a different inventory snapshot")
    by_id = {c.id: c for c in cases}
    if {a.case_id for a in gold.annotations} != set(by_id):
        raise ValueError("gold must cover exactly the experiment cases")
    products = {p.id for p in inventory.products}
    for annotation in gold.annotations:
        if annotation.case_hash != digest(by_id[annotation.case_id]):
            raise ValueError("case changed since annotation")
        if any(s.product_id not in products for s in annotation.accepted):
            raise ValueError("accepted product is outside inventory")


def run_experiment(inventory: Inventory, cases: list[ShoppingCase], config: RunConfig,
                   agent_factory: Callable[[], Agent], *, agent_metadata: dict,
                   on_result=None) -> dict:
    validate_cases(cases)
    # No gold parameter: the execution layer cannot leak answer keys to an adapter.
    tasks = [(case, arm) for case in cases for arm in Arm]
    random.Random(config.seed).shuffle(tasks)
    results = []
    for case, arm in tasks:
        result = run_session(Session(inventory, case, arm, config), agent_factory())
        results.append(result)
        if on_result:
            on_result(result)
    manifest = {"version": "experiment-v1", "date": datetime.now(timezone.utc).isoformat(),
        "inventory_hash": digest(inventory), "cases_hash": digest([c.model_dump(mode="json") for c in cases]),
        "config": config.model_dump(mode="json"), "agent": agent_metadata,
        "schedule": [{"case_id": c.id, "arm": a.value} for c, a in tasks],
        "results_hash": digest(results)}
    return {"manifest": manifest, "results": results}


def verify_experiment(experiment: dict, inventory: Inventory, cases: list[ShoppingCase]):
    validate_cases(cases)
    manifest, results = experiment["manifest"], experiment["results"]
    if (manifest["inventory_hash"] != digest(inventory)
            or manifest["cases_hash"] != digest([c.model_dump(mode="json") for c in cases])
            or manifest["results_hash"] != digest(results)):
        raise ValueError("experiment manifest mismatch")
    by_id = {c.id: c for c in cases}
    expected = {(c.id, a.value) for c in cases for a in Arm}
    pairs = [(r["case_id"], r["binding"]["arm"]) for r in results]
    if set(pairs) != expected or len(pairs) != len(expected):
        raise ValueError("missing or duplicated experiment arm")
    if manifest["schedule"] != [{"case_id": c, "arm": a} for c, a in pairs]:
        raise ValueError("schedule mismatch")
    for result in results:
        if result["binding"]["config"] != manifest["config"]:
            raise ValueError("arm configuration mismatch")
        if result["cluster"] != by_id[result["case_id"]].cluster:
            raise ValueError("cluster mismatch")
        replay(result, inventory, by_id[result["case_id"]])


def _correct(result: dict, label: Annotation) -> bool:
    # No algebra import: labels are matched by exact SKU and sale-unit count.
    if result["status"] == "abstained":
        return label.abstention_correct
    if result["status"] != "selected":
        return False
    return any(result["selection"] == item.model_dump() for item in label.accepted)


def paired_effect(results: list[dict], labels: dict, control: str, seed: int) -> dict:
    by_case = defaultdict(dict)
    clusters = defaultdict(list)
    for result in results:
        by_case[result["case_id"]][result["binding"]["arm"]] = int(_correct(result, labels[result["case_id"]]))
    case_cluster = {r["case_id"]: r["cluster"] for r in results}
    differences = []
    for case_id, arms in by_case.items():
        difference = arms[Arm.APPROV.value] - arms[control]
        differences.append(difference)
        clusters[case_cluster[case_id]].append(difference)
    point = sum(differences) / len(differences)
    # Cluster bootstrap. Suppress a degenerate interval rather than claiming
    # certainty when a small sample has no observed variation.
    interval = None
    if len(clusters) >= 2:
        groups = list(clusters.values())
        rng = random.Random(seed)
        samples = []
        for _ in range(2000):
            values = [v for group in rng.choices(groups, k=len(groups)) for v in group]
            samples.append(sum(values) / len(values))
        samples.sort()
        interval = [samples[49], samples[1949]]
        if interval[0] == interval[1]:
            interval = None
    return {"control": control, "difference": point, "paired_cases": len(differences),
            "clusters": len(clusters), "improved": differences.count(1),
            "regressed": differences.count(-1), "unchanged": differences.count(0),
            "cluster_bootstrap_95_interval": interval,
            "interval_note": "Exploratory cluster bootstrap; null when too little variation. "
                             "Not a population guarantee; publish sample construction."}


def report(experiment: dict, inventory: Inventory, cases: list[ShoppingCase], gold: GoldSet | None = None) -> dict:
    verify_experiment(experiment, inventory, cases)
    if gold:
        validate_gold(gold, inventory, cases)
    labels = {a.case_id: a for a in gold.annotations} if gold else {}
    arms = {}
    for arm in Arm:
        rows = [r for r in experiment["results"] if r["binding"]["arm"] == arm.value]
        counts = Counter(r["status"] for r in rows)
        latency = sorted(r["elapsed_seconds"] for r in rows)
        entry = {"sessions": len(rows), "status_counts": dict(counts),
            "mean_actions": sum(r["actions"] for r in rows) / len(rows),
            "p95_session_seconds": latency[min(len(latency) - 1, int(.95 * len(latency)))],
            "abstention_rate": counts["abstained"] / len(rows),
            "operational_failure_rate": (counts["agent_error"] + counts["budget_exhausted"]) / len(rows)}
        metadata = [e["payload"].get("metadata", {}) for r in rows for e in r["events"]
                    if e["kind"] in ("action", "error")]
        usage = [m["usage"] for m in metadata if isinstance(m.get("usage"), dict)]
        entry["provider_usage"] = {
            "calls_with_usage": len(usage),
            "total_tokens": sum(u.get("total_tokens", u.get("totalTokenCount", 0)) or 0 for u in usage) if usage else None,
            "monetary_cost": None,
            "cost_note": "Not priced; free-tier eligibility and monetary cost are provider/account specific.",
        }
        if gold:
            correct = sum(_correct(r, labels[r["case_id"]]) for r in rows)
            entry.update({"correct": correct, "task_success_rate": correct / len(rows),
                          "descriptive_wilson_95_interval": wilson(correct, len(rows)),
                          "wrong_selections": sum(r["status"] == "selected" and not _correct(r, labels[r["case_id"]]) for r in rows)})
        arms[arm.value] = entry
    return {"measurement": "human-labelled task outcomes" if gold else "unlabelled behavior only",
        "manifest": experiment["manifest"], "gold_hash": digest(gold) if gold else None,
        "arms": arms, "effects": [paired_effect(experiment["results"], labels, a.value,
                      experiment["manifest"]["config"]["seed"]) for a in (Arm.BASELINE, Arm.BLIND)] if gold else [],
        "limitations": ["Public inventory and authored requests need not represent customer traffic.",
            "Human authorship is declared provenance, not cryptographically established identity.",
            "Wilson intervals are descriptive; repeated/related cases are not independent.",
            "No payment authorization, indemnity pricing, or independent certification is inferred."]}


def save_experiment(path: Path, experiment: dict):
    # Exclusive write prevents an accidental rerun from destroying an audit artifact.
    with path.open("x", encoding="utf-8") as file:
        file.write(canonical(experiment) + "\n")
