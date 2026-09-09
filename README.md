# Approv

Approv compares recorded shopping constraints with product evidence and produces
field-level findings. Its shopping harness tests whether those findings improve a
traceable agent's selection from a frozen inventory.

Start with [the shopping harness guide](docs/shopping-harness.md). It covers public-data
import, human case authoring, API/local/command adapters, the browser storefront,
paired experiments, independent scoring and audit replay.

Product direction and implementation: [simple PRD](docs/product-requirements.md).
Latest measured outcomes and limitations: [current state](progress.md).
Current engineering assessment: [candidate review and remaining gaps](docs/candidate-review.md).
For original customer requests, frozen human-labelled and synthetic cases, and
version comparisons, use the study commands in the harness guide.

```powershell
python scripts/run_shopping.py --help
python -m pytest -q -p no:cacheprovider
```

The legacy `scripts/run_benchmark.py` measures OFF brand-field agreement only.
It is not the shopping experiment or an independent accuracy measurement.

Design changes: [DR 0017](docs/decisions/0017-traceable-shopping-experiments.md).
Current defenses and limits: [security register](docs/security.md).
Review evidence: [archived external review](docs/archive/external-review-2026-09-08.md).

No production payment evaluator, priced guarantee, or certification is implemented.
