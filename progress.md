# progress.md — Approv

Tracking document. Reflects actual state, not intended state. Updated at the end of every session.

Last updated: 2026-09-02

---

## Where we are

**Stage: A — blocked on a scope decision. Nothing built.**

The repository is empty. `CLAUDE.md` is the first and only commit.

Stage A as written in `CLAUDE.md` §3 is *"the existing repo, file by file — three piles"*. There is no existing repo here to audit. Either (a) the previous codebase lives somewhere else and needs to be brought in before Stage A can run, or (b) the previous codebase was already abandoned and Stage A collapses to writing down the TRL 3 claim from scratch. **This is the open question blocking everything. Founder decides.**

---

## Stage ledger

| Stage | Definition of done (§10) | State |
|---|---|---|
| A — Audit | Every surviving line explainable; every deletion justified | **Not started** — no subject to audit (see above) |
| B — Category, guideline, gold set | Cohen's kappa computed and > 0.6 | Not started — gated on A |
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

1. **Does a previous codebase exist to audit?** Determines whether Stage A is an audit or a standing start. *Blocking Stage A.*
2. **Which category?** §3 Stage B says grocery / quick commerce, "the mandate caps decide it". The caps have not been written down here. *Blocking Stage B.*
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

### 2026-09-02 — Session 1
- Committed `CLAUDE.md` to the repo root.
- Created this tracker.
- Confirmed the repo was empty at start, so Stage A has no audit subject.
- **Did not write any engine code.** §0 — the founder has not asked for code.
- Next: founder answers open question 1.
