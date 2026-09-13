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

**Who we defend, and why that decides everything (DR 0020).** Proving *the agent erred*
needs the human's raw request, which we will never have. Proving *the merchant did not
err* needs the agent's stated request and the merchant's own fulfilment record — both
already merchant-side. Inverting the burden of proof removes the access problem, and it
is why the product is merchant-facing.

The merchant holds the loss: goods, revenue, return logistics, the per-dispute fee, and
above a network's dispute-ratio threshold, their card acceptance itself. A burst of
simultaneous agentic disputes is an existential event, not a cost line. So the merchant
pays, coverage attaches per channel rather than per order, and no consumer-facing surface
exists — nobody is at an agentic checkout to elect anything.

**What the record is.** The dispute artifact. Its forum is the merchant's returns desk
before any card network, because most wrong-item losses become returns, where the merchant
is judge and payer and nobody external has to accept our format. Its strength is
proportional to the specificity of the stated request — a vague request satisfies almost
anything, swells the completeness vector and proves little. That is correct behaviour
under §2.2 and it bounds coverage.

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
   sale. The threshold is a business parameter, not a constant. Under a guarantee the two
   land on different balance sheets — a false allow costs us a payout, a false refuse
   costs the merchant a sale — so criticality maps to **coverage**, not only to the
   decision: HARD satisfied is guaranteed, SOFT or unstated is out of coverage, and a soft
   mismatch is declined insurance rather than a blocked sale.
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
  intake.py     any agent traffic shape -> constraints. Imports only approv.types.
  surface/      verification.py (framework-free) and api.py (the only FastAPI import).
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
9. Adding a new agent traffic shape never touches `algebra/` or `evaluator/`. The intake
   layer imports only `approv.types`, and the engine never imports intake. A test asserts
   both directions. Without it, adapter pressure leaks into the engine within a month and
   "the engine barely changes" silently stops being true.
10. **No personal data in the record.** The signed object holds the stated request, the
   product and the order line — never a name, address, email, phone, payment instrument or
   account identifier. The join keys it does carry (`correlation_id`, `order_id`, `sku`,
   `merchant_id`, `agent_id`) identify transactions, not people. A test asserts the record
   declares no such field. The reason is the artifact's own job: it is handed to a returns
   desk, a PSP and possibly a court, and one that needs a redaction pass first is not
   evidence, it is a liability. `request_text` is the agent's words about a *product*; a
   surface whose field could carry a shopper's identity redacts before the call, because
   nothing downstream can tell the difference.

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

## 5. What is built, and what is next

**Built.** The decision path: `decide()` called from `receipts/record.py`, sessions gating
on it, Ed25519-signed hash-chained records, a standalone verifier that imports no engine
code, the `gate` call site, and `approv/challenge.py` — one bounded evidentiary round that
replaced repair advice. Per-transaction criticality (`approv/criticality.py`), coverage on
the record, and `approv/intake.py` — one normaliser taking every traffic shape to the one
input the engine already took, under invariant 9. The order half of the record
(`OrderLine`: order, SKU, variant, quantity, price, availability, catalogue version, bound
into the digest) and the verification entry point — `approv/surface/verification.py`, with
FastAPI confined to `approv/surface/api.py`.

**Next, in order (DR 0020).** Everything here serves the record as a dispute artifact.

| # | Deliverable |
|---|---|
| 1 | Per-transaction criticality: request-derived, schema-derived, returns-calibrated |
| 2 | Declared-intent intake — the field addressed to the agent, and its absence as a coverage gradient |
| 3 | Stated-request adapters: ACP / AP2 / storefront MCP, on-site search and filter parameters |
| 4 | The dispute artifact itself — what a merchant hands a returns desk, not a JSON dump |
| 5 | Coverage scoping on the record: which findings are guaranteed and which are out |

**Not in scope:** live underwriting, priced guarantees, payment execution, the preference
record, consumer-facing anything, a new accuracy claim.

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
