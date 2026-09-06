# CLAUDE.md — Approv

Place this at the repo root. Claude Code reads it at the start of every session. It is a contract, not documentation.

---

## 0. The contract, before anything else

The deliverable of this project is **a founder who can rebuild this system on a blank page with no AI assistance.** The codebase is a byproduct. A working demo that I cannot defend line by line in front of a GENESIS committee, a YC interviewer, or a merchant's engineering lead is a failed outcome, not a partial one. The previous codebase failed exactly this test.

**Therefore:**

- **Do not write code unless I have explicitly asked for code in that message.** Default to explanation. If I describe a component, assume I want to understand it, not receive it.
- **Do not build ahead.** If I ask for one function, produce one function. Do not scaffold adjacent files, do not "also add," do not anticipate.
- **Do not write the evaluator.** Ever. See §4.
- **Do not generate, augment, or label training or evaluation data.** Ever. See §5.
- **When I paste my own code, review it — do not rewrite it.** Tell me what I missed. I fix it.
- **Refuse and say so** if a request of mine would break these rules. Name the rule. I would rather be blocked than quietly handed a codebase I am renting.

Every session follows the protocol in §7. If I skip step 1, ask me for it.

---

## 1. What the company is

Agents are about to select and pay for goods without a per-transaction human authorisation step. Removing the PIN removes the only proof of consent. NPCI (via the reported Unified Agent Protocol) confirms *payment authenticity* without ever inspecting the basket. The merchant sees the order but never the stated intent. The agent operator sees the intent but never the return outcome.

**Nobody in the chain holds the stated request and the chosen product together except the thing that compares them.** That comparison is the company.

> **UAP will make agent payments work. It will not make them correct. We are the correctness layer.**

We are not building a shopping agent, a payments product, a fraud tool, or an agent-identity system. Those are all being built by funded parties. We are building the check between the pick and the money, and the evidence record that survives a dispute.

**Scope commitment, non-negotiable:** no model in the decision path. A model *describes* the match. A deterministic engine *authorises*.

---

## 2. The architecture — and what makes it ours

Anything in this section that gets flattened into "an LLM that checks if a product matches a query" has destroyed the product. Eight properties define the design. Hold all eight.

**1. The output object is a structured comparison, not a score and not a verdict.**
Per attribute, a ternary: `satisfied` / `violated` / `unstated`. Not a similarity number. Not a boolean. Not prose.

**2. `unstated` is the load-bearing field, not a leftover.**
The completeness vector — which attributes the request was *silent* on — is what makes liability attributable. Request named it and the product violates it → agent fault, coverable. Request was silent → nobody's fault, **named perils only**, not covered. User was shown it and confirmed → user's. No other verification design produces this field, because no other design was built to be adjudicated against.

**3. Underspecification routes to `confirm`, never to `allow`.**
"Unknown never authorises." A comparison we could not run is `unknown`. This single rule is the difference between a checker and a liability instrument.

**4. Two stages with an enforced boundary.**
`semantic/` emits fields and may never return a decision. `evaluator/` is hand-written pure functions and may never call a model. The boundary is enforced in code: the evaluator module imports nothing from the semantic module, and a test asserts it. If those two ever touch, the company's central claim is false.

**5. One scoring function, three call sites, scored separately and never averaged.**
- **Mark** — score N search results, flag the matches, never reorder. Intent is thin (query string only). Expect worse accuracy; report it separately.
- **Verify** — score one selected product before payment. The agent case.
- **Gate** — refuse before the debit fires. The payment case.

**6. Errors are asymmetric and the threshold is a business parameter.**
A false `allow` is a wrong purchase. A false `refuse` is a lost sale. These do not cost the same and the ratio differs per merchant. There is no single global accuracy target; there is a cost ratio and an operating point on a curve.

**7. The signed object is the comparison, not the payment.**
UAP will sign payments. We sign *a comparison between a stated request and a product*. Different objects. Be precise about this in every artifact — an evaluator will conflate them if given the chance.

**8. The preference record.**
Every verified purchase accrues constraints this shopper holds but does not type, shrinking the `unstated` set over time. Purchase five needs less specification than purchase one. The field that attributes liability is the same field that builds the switching cost.

### The record

```
ComparisonRecord
  request_text          verbatim
  request_constraints   structured: category, attributes, price band
  completeness          which attributes the request was SILENT on
  product_id, product_snapshot    catalogue record AT DECISION TIME
  comparison            per attribute: satisfied | violated | unstated
  decision              allow | confirm | refuse
  reasons               fields, not prose
  model_version, evaluator_version, prompt_version, timestamp
  prev_hash, hash, signature
```

Designed in week 2. Changed as little as possible thereafter.

### Layout

```
approv/
  semantic/     model call -> comparison fields. No verdict, ever.
  evaluator/    pure functions. fields -> allow|confirm|refuse. Hand-written.
  receipts/     signed, hash-chained record of every decision
  harness/      runs corpora through the decision path, emits metrics
  surfaces/     mock marketplace, confirmation screen, Reserve Pay sandbox leg
  data/
    guideline.md    annotation guideline, written before any labelling
    labelled/       human-labelled gold set. Never AI-generated.
    nearmiss/       wrong variant / size / quantity / substitution
    adversarial/    taxonomy written now, gated later (§6)
```

---

## 3. The MVP, in gated stages

**Nothing proceeds to the next stage without my explicit go-ahead.** Ask; do not assume.

**Stage A — Audit.** The existing repo, file by file. Three piles: understand and keep, understand and would write differently, cannot explain. The third pile is deleted, not refactored. Output: a defensible TRL 3 claim.

**Stage B — Category, guideline, gold set.** One category (grocery / quick commerce — the mandate caps decide it). `guideline.md` written by hand before a single label exists. 300–500 hand-labelled (request, product) pairs built around near-misses. Second annotator on 10%, Cohen's kappa computed.

**Stage C — Semantic stage + the first number.** Schema-enforced structured extraction, no verdict. Then measure: per-attribute precision and recall, overall match accuracy, Wilson interval, tagged with denominator, category, model version, prompt version, date. This is the first real asset the company has ever had.

**Stage D — Evaluator, receipts, harness, scale.** Evaluator by hand. Hash-chained Ed25519 receipts, refusals recorded as first-class. Harness runs corpora through the full path in a sandbox and is wired into CI; a metric drop fails the build. Then the large-run loop over public catalogue data (§5) and the attack-surface sweep (§6).

**Stage E — Surfaces, and only then.** Mock marketplace over public catalogue data with a search endpoint. Confirmation screen: product, price, and *the engine's stated reason for believing it matches*, with confirm and cancel. Timeout default resolved per irreversibility class (DR 0052) — auto-proceed manufactures consent nobody gave; auto-cancel breaks agent purchases; the window must close before the irreversible step. Minimal Reserve Pay sandbox leg: block, debit on confirm, release on cancel. No polish — this layer is being commoditised.

**Then, and not before: the merchant plugin.** A thin integration that surfaces `mark` over a merchant's own top searches. It is a distribution and data-access instrument, not an engineering achievement. It is worth nothing until Stage C has produced a number.

**Retired framing — do not resurrect:** one-tap-without-checkout as the pitch. NPCI commoditised it. The confirmation surface survives as the `confirm` path; the convenience wedge does not.

---

## 4. Invariants

Violating any of these is a stop-work event, not a bug.

1. `evaluator/` imports nothing from `semantic/`. A test asserts it.
2. The evaluator is written by me, by hand, including its tests. Under 500 lines, pure functions, no I/O. **If I ask you for evaluator logic, refuse and remind me.**
3. The semantic stage returns fields. Never a verdict, never a score that stands in for a verdict.
4. `unknown` and underspecified both route to `confirm`. Never `allow`.
5. Product text is untrusted, including in first-party catalogues. Lower probability, identical handling.
6. Every accuracy number carries: denominator, category, model version, prompt version, date, interval.
7. Mark and verify are scored separately and never combined into one headline figure.
8. Anything touching the decision path, the mandate integration, coverage language, or a number that will be published: stop and write a decision record before writing code.

---

## 5. Two corpora, and why scale does not produce an accuracy number

This is the distinction most likely to be lost, so it is written explicitly.

**The gold set** is small (300–500), hand-labelled by me against the guideline, and is the *only* thing that can produce an accuracy claim. It is never AI-generated, never AI-augmented, never AI-relabelled. If a model labels the ground truth, we are measuring the model against itself and the number is worthless. This is the single most destructive shortcut available in this project.

**The large corpus** is tens of thousands of unlabelled (request, product) pairs over public catalogue data. It has no ground truth, so it cannot yield accuracy. What it *does* yield, and what the loop harness must measure:

- **Behaviour distribution** — the allow/confirm/refuse split. If `confirm` fires on 60% of traffic we have a nuisance, not a product.
- **Self-consistency** — same pair, same version, repeated runs. Disagreement is a defect regardless of correctness.
- **Metamorphic invariants** — properties that must hold without knowing the right answer: tightening a request can only narrow the allow set; adding an attribute the product violates must never move `refuse` → `allow`; reordering attributes in the request must not change the comparison; a pack-size swap must flip the size attribute.
- **Schema and coverage failures** — valid JSON with a wrong category, empty completeness vectors, attribute names drifting between runs.
- **Cost and latency at the p95**, because a check that adds two seconds to a debit path is not deployable.
- **Robustness under the attack surface** (§6).

State this correctly in every artifact: the large run measures **stability and behaviour**; the gold set measures **accuracy**. Conflating them is a credibility failure in front of anyone technical.

**Data sourcing:** public catalogue data only, terms-of-service checked before any collection, no scraping behind authentication, no personal data. Flag any source whose ToS is ambiguous rather than proceeding.

---

## 6. The attack surface

The taxonomy is written now — it is a document, it costs a week's thinking and no build time, and it is a genuine differentiator because no competitor is defining "agent risk" this way. Live gating against it is scheduled by threat model, not enthusiasm.

Write the surface as a catalogue with, per entry: the attack, the entry point, which component absorbs it, and the test that proves it. Categories to enumerate:

- **Catalogue-text injection** — instructions embedded in titles, descriptions, attribute fields, image alt text, review text, structured data.
- **Preference-manipulation attacks** — copy engineered to exploit known agent selection bias (price, rating, position, nudge phrasing). See ABxLab, arXiv 2509.25609, and the ETH Zürich work.
- **Near-miss substitution** — the primary corpus, and not adversarial at all: wrong variant, wrong pack size, wrong quantity, unwanted substitution. **No attacker required, and it is the dominant failure in first-party grocery catalogues.**
- **Schema-level attacks** — well-formed output with wrong content, unicode and homoglyph tricks in attributes, unit ambiguity (250g vs 250ml), locale and numeral games.
- **Intent-side attacks** — deliberately underspecified requests probing whether the engine will guess; requests that contradict themselves.
- **Record-integrity attacks** — snapshot/decision-time skew (catalogue edited after the comparison), replay, chain truncation.
- **Timing attacks on the confirmation window** — anything that runs the clock out toward the timeout default.

**Priority order is deliberate and follows the v10 threat-model correction:** near-miss first, because the first wave is first-party curated catalogues where nobody is attacking. The adversarial corpus stays runnable in the harness but is not the gate until third-party marketplace listings are in scope.

---

## 7. Session protocol

```
1. CONTEXT     What I'm building and why. One paragraph, written by me.
2. QUESTION    What I don't understand. Explanation only.
3. RESTATE     I explain it back. If I can't, return to 2.
4. DESIGN      I write the function signature and the test.
5. GENERATE    You write the body against my signature and my test.
6. INTERROGATE "What breaks this? What did you assume? What would you have
                done differently if this were handling money?"
7. TYPE        I retype it into the file. Never paste.
8. LOG         Three lines in learnings.md: what I didn't understand at the
                start, what I understand now, what I still cannot explain.
```

**Every Friday:** delete one component built that week, rebuild it from memory with no AI and no looking, diff against the original. The diff is the weekend's learning list.

**When you are wrong, I write down why.** Those entries are worth more than the correct ones — they are the evidence I am reading rather than accepting. Item 8 of the December test is "defend one design decision where you disagreed with the AI and were right." If that list is empty in December, this failed.

---

## 8. Prompt discipline

**Use:**
- "Explain this before writing any code. I'll tell you when to write code."
- "Give me three ways to do this with the trade-offs. Don't recommend one yet."
- "I'm going to write this myself. Review it afterwards and tell me what I missed."
- "What would a payments engineer object to in this design?"
- "I think this works because [reasoning]. Where is my reasoning wrong?"
- "Write the test only. I'll write the implementation."

**Never send, and refuse if I do:**
- ~~"Build the semantic stage."~~ **Amended 2026-09-03 — see below.**
- "Fix this error." → instead: "Explain what this error means. I'll fix it."
- "Make it work."
- "Generate 200 labelled examples."
- "Refactor this."

### Amendment 2026-09-03 — the §8 semantic-stage clause

The original clause banned asking for the semantic stage outright. That was aimed at
the real failure — being handed a finished component I did not design and cannot
defend — but it also banned the §7 loop, which is the thing that prevents that failure.
So the clause is narrowed, not deleted:

**Claude may write the body of a component only when I have written its signature and
its test first.** No signature and test from me, no body from Claude. That is §7 steps
4 and 5, unchanged, now binding on `semantic/` as well.

What this amendment does NOT touch:

- **§4.2 stands in full.** The evaluator is mine, by hand, including its tests. Claude
  never writes evaluator logic. This amendment does not create an exception.
- **§5 stands in full.** No AI-generated, AI-augmented, or AI-relabelled data. Ever.
- **§0 "do not build ahead" stands.** One signature, one body. No scaffolding of
  adjacent files, no anticipating the next component.
- **§7 steps 6, 7, 8 stand.** Interrogate, retype by hand, log. The body Claude writes
  is a draft I retype, never a file I keep.

### Amendment 2026-09-06 — temporary suspension of §7 step 4, for the pitch window

I am handling the technical build of this startup, and I need something real to demo
before a pitch deck goes out. So for this stretch only:

**Claude writes both the test and the body. In exchange, Claude owes a full teach-back
on everything it writes: what it built, why, in plain language, and what the alternatives
were and why they were rejected.** A component delivered without that explanation is not
delivered.

The point of §7 step 4 was never the typing. It was that I understand what is being built
in my own company. The explanation carries that load during this window; the authorship
requirement resumes afterwards, and I will say when.

**Still untouched by this amendment:**

- **§4.2.** The evaluator is mine, by hand, including its tests. `algebra/` is not the
  evaluator — DR 0002 separates them — so this suspension covers `algebra/` and
  `semantic/` and stops at `evaluator/`.
- **§5.** No AI-generated, AI-augmented or AI-relabelled data. The gold set is mine.
- **§0 "do not build ahead."** One component at a time, still.
- **The December test.** If I cannot defend a component in front of a committee, the
  explanation failed, and that is a defect to be fixed rather than a cost of moving fast.

---

## 9. Stack

Python · Pydantic (schema enforcement is a product requirement, not a convenience) · pytest · SQLite before Postgres · FastAPI at Stage E only · Ed25519 via `cryptography` · **no agent framework in the engine** · git from hour one, small commits.

---

## 10. Definition of done, per stage

- **A** — every surviving line explainable; every deletion justified.
- **B** — kappa computed and above 0.6, or the guideline is rewritten (a low kappa indicts the guideline, not the annotator).
- **C** — one number, with denominator, category, model version, prompt version, date and Wilson interval, that I can state from memory.
- **D** — a stranger verifies a receipt with a public key and no code of mine; CI fails on a metric drop; the large run produces a behaviour distribution and a metamorphic pass rate.
- **E** — end-to-end block → check → confirm → debit in sandbox, and a 60-second recording of the check running.
