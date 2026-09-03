# progress.md — Approv

Tracking document. Reflects actual state, not intended state. Updated at the end of every session.

Last updated: 2026-09-03

---

## Where we are

**Stage: A — closed. Building from a standing start. No engine code yet.**

Stage A is resolved without an audit. The prior repo is
`Krishna1186/payment-agent-harness` (Python, ~30 KB, last pushed 2026-08-24). Founder's
call, 2026-09-03: it was a different idea — the shopping/search agent itself, with no
intent verification and no security layer, which is the core of Approv. It is **not**
the ancestor of this codebase and nothing is being carried across as code.

One artifact is worth salvaging as *input*, not as code: `docs/threat-model.md`
(~9.8 KB) already enumerates prompt-injection sub-cases against a payment-capable
agent. It is a skeleton by its own admission, but it is a head start on the §6
attack-surface taxonomy when that gets written. Everything else is scaffolding.

TRL 3 claim as of today: **nothing demonstrated.** No engine, no gold set, no number.

---

## Stage ledger

| Stage | Definition of done (§10) | State |
|---|---|---|
| A — Audit | Every surviving line explainable; every deletion justified | **Closed 2026-09-03** — no subject to audit; prior repo declared non-ancestral, nothing carried across |
| B — Category, guideline, gold set | Cohen's kappa computed and > 0.6 | **Next.** Target verticals fixed: quick commerce + e-commerce. Which one gets the *first* gold set is undecided |
| C — Semantic stage + first number | One number with denominator, category, model version, prompt version, date, Wilson interval | Not started — gated on B |
| D — Evaluator, receipts, harness, scale | Stranger verifies a receipt with a public key; CI fails on metric drop; behaviour distribution + metamorphic pass rate | Not started — gated on C |
| E — Surfaces | End-to-end block → check → confirm → debit in sandbox + 60s recording | Not started — gated on D |
| Merchant plugin | — | Not started — explicitly worthless until C produces a number |

---

## Artifacts that exist

| Artifact | Path | State |
|---|---|---|
| The contract | `CLAUDE.md` | Committed |
| This tracker | `progress.md` | Committed |
| Annotation guideline | `data/guideline.md` | Does not exist. Must be hand-written **before** any label exists (§3 Stage B) |
| Attack-surface taxonomy | — | Does not exist. §6 says write it now; costs thinking, not build time |
| Decision records | — | None. §4.8 requires one before any decision-path code |
| `learnings.md` | — | Does not exist. §7 step 8 writes into it every session |
| Gold set | `data/labelled/` | Empty. Founder-labelled only, never AI-generated (§5) |

---

## Open questions blocking progress

1. ~~**Does a previous codebase exist to audit?**~~ **Resolved 2026-09-03** — no. Standing start.
2. **Which category gets the first gold set?** Verticals are fixed (quick commerce + e-commerce), but §3 Stage B says *one* category and each vertical needs its own 300–500 pairs and its own criticality profile. Footwear/apparel exercises taxonomy + attribute lattice + price bound + the size-silence rule; grocery exercises dimensional quantities and pack-size hardest. *Blocking Stage B.*
2a. **How is §8 handled?** Founder asked for the intent verifier to be built. §8 lists "Build the semantic stage" as a refuse-on-sight prompt and §4.2 reserves the evaluator for the founder by hand. The contract needs an explicit amendment or an explicit split of who writes what. *Blocking all engine work.*
3. **Which public catalogue source, and is its ToS clean?** §5 requires ToS checked before any collection, no auth-walled scraping, no personal data. *Blocking the large corpus, i.e. Stage D.*
4. **Who is the second annotator for the 10% kappa sample?** Kappa needs two humans. *Blocking Stage B's definition of done.*
5. **DR 0052 — confirmation-window timeout default per irreversibility class.** Referenced in §3 Stage E as already resolved, but the decision record is not in this repo. *Needs to be written down or restated.*

---

## Standing constraints (from CLAUDE.md — restated so this file stands alone)

- No code written by Claude unless the founder asks for code **in that message**.
- The evaluator is hand-written by the founder. Claude never writes evaluator logic (§4.2).
- Training and evaluation data is never AI-generated, augmented, or relabelled (§5).
- `evaluator/` imports nothing from `semantic/`; a test asserts it (§4.1).
- `unknown` and underspecified route to `confirm`, never `allow` (§4.4).
- Mark and verify are scored separately, never averaged (§4.7).
- No stage begins without explicit go-ahead (§3).

---

## Session log

### 2026-09-03 — Session 2
- Founder identified the prior repo (`payment-agent-harness`) and ruled it non-ancestral. Stage A closed.
- Target verticals fixed: **quick commerce and e-commerce**, in that priority order for the product, category for the first gold set still open.
- Founder asked for the intent verifier to be built. **Refused pending an explicit contract amendment** — §8 and §4.2. Named the rules per §0.
- Architecture for the verifier taught in-session (typed constraint algebra, dimensional quantities, directed taxonomic subsumption, provenance-weighted attributes, per-category criticality profiles, closed-vocabulary injection containment). No code written.
- Raised a design question for a decision record per §4.8: `unstated` (request was silent) and `unavailable` (product has no data) are currently collapsed into one field, but they attribute liability to different parties.

### 2026-09-02 — Session 1
- Committed `CLAUDE.md` to the repo root.
- Created this tracker.
- Confirmed the repo was empty at start, so Stage A has no audit subject.
- **Did not write any engine code.** §0 — the founder has not asked for code.
- Next: founder answers open question 1.
