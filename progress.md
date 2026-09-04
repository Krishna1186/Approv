# progress.md — Approv

Tracking document. Reflects actual state, not intended state. Updated at the end of every session.

Last updated: 2026-09-04

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
| B — Category, guideline, gold set | Cohen's kappa computed and > 0.6 | **In progress.** Category fixed: footwear / apparel. `data/guideline.md` not yet written — it must exist before any label does |
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
| Decision records | `docs/decisions/` | **0003 CLOSED.** Open: **0001** ternary vs reason codes · **0002** where comparison lives · **0004** latency + failure direction (amended) · **0005** request-side provenance (amended) · **0006** one ontology, many lexicons. 0001, 0002, 0005 and 0006 block code (§4.8) |
| `learnings.md` | — | Does not exist. §7 step 8 writes into it every session |
| Gold set | `data/labelled/` | Empty. Founder-labelled only, never AI-generated (§5) |

---

## Open questions blocking progress

1. ~~**Does a previous codebase exist to audit?**~~ **Resolved 2026-09-03** — no. Standing start.
2. ~~**Which category gets the first gold set?**~~ **Resolved 2026-09-03** — **footwear / apparel** first. Exercises directed taxonomy, colour lattice, price bound and the size-silence rule in a single query. Grocery second, for dimensional quantities. Engine is category-parameterised so the second vertical is data, not a rewrite.
2a. ~~**How is §8 handled?**~~ **Resolved 2026-09-03** — §8 amended in `CLAUDE.md`. Claude may write a component body only after the founder has written its signature and its test. §4.2, §5 and §0's no-build-ahead rule are untouched.
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

### 2026-09-04 — Session 3
- **DR 0003 CLOSED.** DAG + multi-assignment + entity linking as a separate scored step. Taxonomy never self-edits: unrecognised terms go to a **pending queue**, approved **manually in batches**, each batch cutting a new taxonomy version.
- **DR 0004 amended** — the clarification/latency conflict resolved four ways: `mark` never asks (no badge is a valid output); precompute all ambiguity branches and only ask when they disagree; ask once per shopper rather than per purchase (§2.8); precompute merchant top-N offline so we are not in their render path at all. Option 3 upgraded from defer to recommended-for-`mark` once the cache key includes `snapshot_hash`.
- **DR 0005 amended** — founder raised the agent that legitimately knows more than the query (colour learned in a prior chat we cannot see). Resolved by attestation rather than verification: the agent declares `claimed_source`, we record and sign it, and a false attestation becomes the agent operator's liability. Plus: agents may supply SOFT attributes, never HARD ones, and may narrow a bound but never widen one. The §2.8 preference record doubles as the corroboration check.
- **DR 0006 opened** — one universal ontology, N per-locale lexicons with per-term readings. Answers the India "shoes means footwear" problem without forking the DAG. Adds `locale` to the §4.6 metadata every accuracy number must carry.
- Still no engine code.

### 2026-09-03 — Session 2
- Founder identified the prior repo (`payment-agent-harness`) and ruled it non-ancestral. Stage A closed.
- Target verticals fixed: **quick commerce and e-commerce**, in that priority order for the product, category for the first gold set still open.
- Founder asked for the intent verifier to be built. **Refused pending an explicit contract amendment** — §8 and §4.2. Named the rules per §0.
- Architecture for the verifier taught in-session (typed constraint algebra, dimensional quantities, directed taxonomic subsumption, provenance-weighted attributes, per-category criticality profiles, closed-vocabulary injection containment). No code written.
- Raised a design question for a decision record per §4.8: `unstated` (request was silent) and `unavailable` (product has no data) are currently collapsed into one field, but they attribute liability to different parties.
- **§8 amended** with founder's approval: Claude writes a body only against a founder-written signature and test. §4.2 (evaluator), §5 (data) and §0 (no build-ahead) untouched.
- **Category fixed: footwear / apparel** for the first gold set and the first criticality profile.
- Wrote **DR 0001** and **DR 0002**, both OPEN. §4.8 blocks decision-path code until they close.
- Still no engine code. Next action is the founder's: close the DRs, then §7 step 4 on the first operator.

**Founder corrections to Claude, same session — these are the December-test entries (§7):**
- **Taxonomies are DAGs, not trees.** A bulb sits under Lighting, Electronics, Decor and Interiors at once. Claude asserted a tree and claimed cycle-safety followed from it. Both wrong. Subsumption is reachability over a multi-parent DAG, acyclicity must be explicitly validated, and a visited set is still required at read time. → DR 0003.
- **Fail-open on timeout, because the marketplace will not wait.** Correct, and the constraint most verification layers learn only after a merchant rips them out. Claude added the asymmetry the founder had not separated: fail-open is right for `mark`, and a complete bypass at `gate`, where latency becomes an off-switch. → DR 0004.
- **Agents fabricate constraints the user never stated, and that is a security surface.** Independently derived the mirror of product-side provenance. Without it, §2.2 cannot attribute fault to the agent, because an invention and an instruction are byte-identical in the record. → DR 0005.
- Claude's counter, accepted: the "user types shoes but means sneakers" case is **not** a false negative — `subsumes(shoes, sneakers)` is satisfied, breadth in the request is permissive by construction. The real failure is surface terms that do not resolve at all ("joggers", "chappals"), which is entity linking, a different component. → DR 0003 §3.

### 2026-09-02 — Session 1
- Committed `CLAUDE.md` to the repo root.
- Created this tracker.
- Confirmed the repo was empty at start, so Stage A has no audit subject.
- **Did not write any engine code.** §0 — the founder has not asked for code.
- Next: founder answers open question 1.
