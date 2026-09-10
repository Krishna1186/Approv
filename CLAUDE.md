# CLAUDE.md — Approv

Rewritten 10 September 2026. The previous contract optimised for the founder's
understanding and said so: *"the codebase is a byproduct."* It got what it asked for —
50,880 words of prose against 1,482 lines of engine, and the decision function never
called once. This version optimises for a working, defensible MVP.

---

## 1. What the company is

Agents are about to select and pay for goods with no per-transaction human
authorisation. UAP, AP2 and ACP all carry **who paid**. None carries **what was asked
for**. The merchant has the order, the agent operator has the intent, nobody holds both.

**Approv holds the stated request and the chosen product together, decides, and emits a
signed record that survives a dispute.**

Not a shopping agent, not a payments product, not a fraud tool. The check between the
pick and the money, and the evidence that outlives it.

**Positioning, corrected by our own data:** we sell **attribution**, not accuracy. Three
studies showed +0.0 pp against a "look again" control, because on a task where the agent
can already see every candidate, we add no information — only re-ranked attention. As
agents get more reliable the value of a checker falls and the value of an attributor
rises: failures become rare, autonomous, and at scale, and the live question stops being
"was this right" and becomes "who pays".

**Where we do add information, measured:** facts published only in prose (size in the
description but never the title — 26.9% of 132,832 listings), giving +11.1 pp detection
signal, CI [0.8, 23.2], excluding zero. That is the accuracy story. The shelf-picking
task is retired.

**Non-negotiable:** no model in the decision path. A model *describes*. A deterministic
function *authorises*.

---

## 2. The eight properties

1. **Output is a structured comparison, not a score or a verdict.** Per attribute:
   `satisfied` / `violated` / `unstated`.
2. **`unstated` is load-bearing.** The completeness vector — which attributes the request
   was silent on — is what makes fault attributable. Named and violated → agent's fault.
   Silent → nobody's. Shown and confirmed → the user's.
3. **Underspecification routes to `confirm`, never `allow`.** Unknown never authorises.
4. **Two stages, enforced.** `semantic/` emits fields and never a decision. `evaluator/`
   is pure functions and never calls a model. A test asserts the import boundary.
5. **One function, three call sites, never averaged.** `mark` (score N results, never
   reorder) · `verify` (score one pick) · `gate` (refuse before the debit).
6. **Errors are asymmetric.** A false allow is a wrong purchase; a false refuse is a lost
   sale. The threshold is a business parameter, not a constant.
7. **The signed object is the comparison, not the payment.** UAP signs payments. We sign
   a comparison between a stated request and a product. Never conflate them.
8. **The preference record.** Confirmed purchases accrue constraints the shopper holds
   but does not type, shrinking `unstated` over time. Same field attributes liability and
   builds switching cost.

### The record

```
ComparisonRecord
  request_text, request_constraints, completeness
  product_id, product_snapshot, snapshot_hash     at decision time
  findings         per attribute: satisfied | violated | unstated
  decision         allow | confirm | refuse
  reasons          fields, never prose
  model_version, evaluator_version, prompt_version, timestamp
  prev_hash, hash, signature
```

### Layout

```
approv/
  types/        shared vocabulary. Imports nothing from approv.
  algebra/      typed comparison operators -> findings.
  evaluator/    pure functions. findings -> allow|confirm|refuse.
  receipts/     record assembly, Ed25519 signing, hash chain.
  harness/      extraction (intent.py), catalogue filter, sessions, storefront, metrics.

Extraction lives in `harness/intent.py` and the storefront in `harness/storefront.py`.
Earlier drafts named `semantic/` and `surfaces/` packages; they were never created and
the names are dropped rather than carried as aspiration. The boundary that matters is
enforced and tested: `evaluator/` imports only `approv.types`.
```

---

## 3. Invariants

Violating one is a stop-work event.

1. `evaluator/` imports only `approv.types`. A test asserts it.
2. The evaluator is pure functions, no I/O, under 500 lines.
3. The semantic stage returns fields — never a verdict, never a score standing in for one.
4. `unknown` and underspecified both route to `confirm`. Never `allow`.
5. Product text is untrusted, first-party catalogues included.
6. Every published number carries denominator, category, model version, prompt version,
   date and interval.
7. `mark`, `verify` and `gate` are scored separately and never combined.
8. A change to the decision path, coverage language, or a number that will be published
   needs a decision record first. Nothing else does.

---

## 4. Ground truth — amended, and this is the change that unblocks the build

The old rule demanded 300–500 pairs hand-labelled by the founder and banned all AI
involvement. That rule was written for the question *"does this product match the user's
intent"*, which is subjective and needs human judgement. **DR 0016 replaced that question
on 6 September** with *"did the agent read this page correctly, and from which field"* —
and for that question ground truth is **on the page**, so hand-labelling is the wrong
instrument, not merely a slow one.

**The rule now:**

- **Answer keys are derived from published merchant fields by code that imports nothing
  from `approv.algebra`.** Deterministic, reproducible, and it scales to the full
  catalogue instead of 500 rows. This is already how the current studies work.
- **A model may never label its own output, and never grade a run it participated in.**
  This is the part of the old §5 that was always right and it stands unchanged.
- **Human audit, not human labelling:** ~50 cases spot-checked to confirm the key
  *generator* is not systematically wrong. Hours, not weeks. Disagreement indicts the
  generator and is fixed in code, where the fix applies to every row at once.
- Public catalogue data only. ToS checked. No scraping behind auth. No personal data.

Two corpora, and the distinction still holds: the **keyed set** measures accuracy; the
**large unlabelled corpus** measures behaviour — the allow/confirm/refuse distribution,
self-consistency across repeats, metamorphic invariants, schema failures, p95 latency and
cost. Never state a behaviour number as an accuracy number.

---

## 5. The MVP — done by Sunday

The decision path is built: `decide()` is called from `receipts/record.py`, sessions
gate on it, and records are signed and chained. What was missing after that is an
*evaluation* of it — see §6.

| # | Deliverable | Rough size |
|---|---|---|
| 1 | `completeness` — schema attributes the request never constrained | ~10 lines |
| 2 | Call `decide()` on the verify path, carrying the floor | ~20 lines |
| 3 | Build `ComparisonRecord` from a real session | ~40 lines |
| 4 | `receipts/` — Ed25519 signing, hash chain, append-only store | ~120 lines |
| 5 | `scripts/verify_receipt.py` — standalone, no engine import | ~40 lines |
| 6 | `gate` call site — refuse before the debit fires | ~30 lines |
| 7 | 60-second demo: request → decision → receipt → independent verification | — |

**Definition of done:** a stranger verifies a receipt with a public key and none of our
code; `gate` refuses a wrong purchase and the refusal is a first-class record; the
allow/confirm/refuse distribution over the large corpus is reported with its denominator.

**Not in scope this weekend:** underwriting, pricing, live payments, the preference
record, the merchant plugin, a new accuracy claim.

---

## 6. How the gate is measured

Every accuracy number published before 10 September measured a different mechanism from
the one being sold. The forked study shows an agent a report and asks whether its second
answer changes — that is persuasion, it never calls `decide()`, and it is bounded by how
stubborn the model is and by an n of 46 with a noise floor near ±8 pp. Three such studies
returned +0.0 pp, which is the expected result from testing whether text changes a
model's mind.

The gate is a classifier and is scored as one, by `scripts/score_gate.py`: no agent, no
model call at evaluation time, thousands of pairs, on every commit. Requirements come
from the extractor and never from the answer key — feeding the key's own spec back in
would make the gate and the key the same computation over the same fields and the matrix
would come back perfect having measured nothing.

Report three outcomes against two truths, split by population, because `confirm` is not a
third error but a different cost, and near-misses are the failure this exists for while
unrelated products are the easy half. Never average the call sites (invariant 7).

The persuasion study is kept, demoted: it scores `verify`, which is a real surface, and
its null result is itself the argument for a gate that does not ask permission.

## 7. Attack surface

Written as a catalogue — attack, entry point, absorbing component, proving test. Priority
order is deliberate: near-miss substitution first (wrong variant, pack size, quantity —
no attacker required and it dominates first-party catalogues), then catalogue-text
injection, schema-level tricks (homoglyphs, unit ambiguity), intent-side
underspecification, record-integrity attacks (snapshot skew, replay, chain truncation),
and confirmation-window timing. Adversarial gating waits for third-party marketplace
listings.

Structural defence worth remembering: merchant-authored text is merchant-liable, so
injecting into a description is self-incriminating. Residual risk concentrates in text
nobody is answerable for — reviews, Q&A, third-party seller copy.

---

## 8. How we work now

- **Write code when asked.** Explanation on request, not by default.
- **Teach-back on anything non-obvious:** what it does, why, what was rejected. Short.
- **Do not build ahead.** Finish the item in front of you.
- **Report failures as failures.** A study that shows nothing shows nothing; say so and
  say why the design could not have shown it.
- **Every claim carries its denominator.** Retracted claims stay listed in `progress.md`.
- **Prose is a cost.** A decision record earns its place only for §3.8 changes.

## 9. Stack

Python · Pydantic · pytest · Ed25519 via `cryptography` · SQLite before Postgres ·
FastAPI only at the surface layer · no agent framework in the engine · small commits.
