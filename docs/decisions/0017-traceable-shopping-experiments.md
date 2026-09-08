# DR 0017 — Traceable shopping experiments and comparison corrections

Status: implementation authorized by the founder's 2026-09-08 request.

The experiment models a merchant-owned shopping agent receiving a recorded request
and selecting from a frozen public inventory. API models, local models, external
operators and browsers must use the same task, inventory and trace contract.

We will repair the reviewed algebra, provenance, coverage and diagnostic benchmark
defects, and add a shopping-session harness. This is comparison and measurement code;
it does not implement the founder-owned payment evaluator or issue guarantees.

Decisions:

- A request's structured constraints are fixed by the case author, visible to every
  arm, and cannot be relaxed by the agent. Original request text is retained.
- Baseline, blind-review control and Approv runs use isolated sessions, identical
  inventory/search ordering and equal action budgets. Order is seeded and randomized.
  Approv annotates results without reordering them; review feedback is bounded.
- Agent adapters emit explicit search, inspect, select and abstain actions. The harness
  records arguments, actual responses, errors and final selections. External sessions
  use the same engine through a local HTTP storefront/API. No live merchant checkout.
- Evidence is constructed from the frozen inventory by trusted code. The agent cannot
  set evidence provenance. Field profiles cap certainty and advice never supplies a
  clean supporting fact. Ambiguous terms remain unresolved; token overlap is not identity.
- Gold labels live separately from agent-visible cases and inventory. Human-authored
  acceptable product/quantity outcomes are matched exactly, independently of Approv's
  operators. No AI-generated accuracy corpus or auto-labelled gold set is created.
- Unlabelled runs report behavior only. Scored runs report paired task success,
  abstention, operational errors, costs when supplied, action counts and uncertainty.
  Small public-data results are not evidence of a priced third-party guarantee.
- Replay artifacts bind configuration, cases, inventory and traces by content hashes.
  A retained manifest detects trace edits/truncation; it is not a signature or proof
  of authorship. Provider request metadata is retained without credentials.
- Existing title-to-brand runs remain an explicitly labelled diagnostic. They are not
  a substitute for the shopping task. Preserve concurrent work when applying fixes.

Validation will cover the reproduced algebra failures, provenance spoofing, pack scope,
trace tampering, equal-budget experiments, gold-label isolation, invalid agent actions,
provider failures, human-label validation and local HTTP integration. Test fixtures are
software tests, never reported as agent accuracy or customer performance.
