# DR 0009 — Can Approv itself be an agent? The monotone safety rule

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-04, by the founder
- **Touches:** §1 (the non-negotiable), §2.4, DR 0002, DR 0004
- **Blocks:** nothing yet; decides whether a model may appear anywhere outside `semantic/`

---

## The founder's question

> Why don't we wrap Approv as a lightweight, fast and reliable agent? Even though we
> have deterministic policies there are a lot of surfaces, and when it interacts with an
> agent even more so. Why not build the full deterministic layer but then on a
> lightweight model (still running under budget time) it can help improve security and
> validity through internal checks. Is it technically possible to have the agent run a
> "mini-sandbox" for tests that improve our intent score in real time, under budget?

Also asked: what technically differentiates a more capable agent from a less capable one
on the same base model?

---

## The answer to the second question first, because it constrains the first

Agentic capability on a fixed base model comes almost entirely from scaffolding:

- **Tool design** — narrow, well-typed tools with unambiguous failure modes beat broad
  ones. Most agent failure is tool ambiguity, not reasoning failure.
- **Structured output under a schema** rather than free text that gets parsed.
- **Verification loops** — the agent checks its own output against something external
  and retries. This is the single largest contributor.
- **Context management** — what is kept, what is summarised, what is dropped.
- **Error recovery** — distinguishing retryable from terminal failures.
- **Bounded planning horizon** — fewer, larger, checkable steps.

Note what dominates that list: **an external, non-model source of truth to check
against.** That is precisely what Approv is. So the honest framing is not that Approv
should become an agent — it is that **Approv is the missing verification loop that makes
other agents better**, which is a stronger position than being one more agent.

The founder's own observation supports this: an agent "can't use its own thinking as
proof." An agent that self-verifies is marking its own homework. The value of an
external verifier is that it is external.

---

## Where a model may and may not go

§1 is non-negotiable: *no model in the decision path.* But "the decision path" needs a
sharper definition than it currently has, because the founder's proposal is not
obviously a violation and the current wording cannot tell.

**Proposed rule — monotone safety:**

> A model may participate anywhere its worst-case behaviour degrades the outcome toward
> `confirm` or `refuse`, and can never move an outcome toward `allow`.

Under this rule, a model can be wrong, adversarial, injected, or completely broken, and
the failure is a nuisance rather than a wrong purchase. §2.6's asymmetry says exactly
this: a false `refuse` is a lost sale, a false `allow` is a wrong purchase, and they do
not cost the same. Monotone safety is that asymmetry expressed as an architectural
permission.

### What this permits

**A model that selects which deterministic checks to run.** Given a request, a
lightweight model proposes which of a fixed, hand-written set of checks are relevant.
Every check is deterministic. The decision is deterministic over check results. If the
model chooses badly, fewer checks run, less evidence exists, and the evaluator sees more
`unknown` — which routes to `confirm`. **It cannot manufacture an `allow`.** Safe.

**A model that proposes hypotheses to be tested deterministically.** "This might be a
pack-size mismatch" is a suggestion; the deterministic operator decides. Safe.

**A model that generates clarification question wording.** No authority over outcomes.
Safe — subject to the DR 0004 rule that a clarification must not lead the user.

### What this forbids

- A model that produces or adjusts the final decision. Obviously.
- A model that resolves an `unknown` into a `satisfied`. This is the subtle one, and it
  is where a well-meaning implementation will drift: "the model is confident the colour
  matches, so let's not bother the user." That is a model authorising a purchase.
- **A model that adds a category or lexicon entry at runtime.** Forbidden already by
  DR 0003 — the pending queue exists to prevent exactly this.
- A model that widens a bound, per DR 0005.

---

## The mini-sandbox: yes, and it does not need a model

The founder asked whether real-time self-tests are feasible under budget. They are, and
the cheapest and most valuable version uses no model at all.

§5 already lists **metamorphic invariants** — properties that must hold without knowing
the right answer. Run a handful of them at request time against the deterministic
operators:

| Invariant | Perturbation | Must hold |
|---|---|---|
| Monotonicity | tighten a constraint | the allow set can only shrink |
| Order independence | reorder attributes in the request | comparison unchanged |
| Violation stability | add an attribute the product violates | never moves `refuse` → `allow` |
| Unit sensitivity | swap pack size | the size attribute must flip |

These are deterministic re-runs of code that already executes in microseconds. Running
four of them costs roughly four times almost nothing, which is well inside any budget
that permits one model call.

**What they detect:** not whether the answer is right, but whether *our own extraction
was self-consistent on this specific request*. An invariant failure means the semantic
stage produced something incoherent for this input, which is a defect regardless of
correctness (§5 says exactly this about self-consistency). An invariant failure
downgrades the outcome to `confirm` and is recorded with its own reason code.

This is a genuinely strong feature and it is worth stating plainly: **a per-request
self-check that can only ever downgrade confidence.** It is monotone-safe by
construction, it needs no model, and it produces a live metamorphic pass rate — which
§10-D already requires as a definition-of-done metric, here available in production
rather than only in the harness.

## Options

**Option 1 — no model anywhere outside `semantic/`.**
- *For:* §1 needs no interpretation; simplest thing to defend.
- *Against:* forbids check selection and hypothesis generation, which are safe by the
  argument above; leaves capability on the table for no risk reduction.

**Option 2 — monotone safety rule, plus a deterministic per-request metamorphic
self-check.**
- *For:* §1 preserved and made precise rather than merely asserted; permits the
  founder's proposal in the form that is actually safe; the self-check is cheap,
  model-free and produces a live metric.
- *Against:* the rule must be enforced, not just written — every model-touching
  component needs an argument for why its failure mode is downward, and that argument
  needs a test.

**Option 3 — full agent wrapper around the deterministic core.**
- *For:* maximum flexibility on messy surfaces.
- *Against:* the moment a model can influence an outcome upward, §1's central claim is
  false and the product is one more agent claiming to check itself. This is the failure
  the whole contract was written to prevent.

## Recommendation

**Option 2.** It gives the founder what the question was actually after — a model
improving robustness on messy agent-facing surfaces — without the property that would
make the company's central claim untrue. Option 3 is the one that looks like progress
and is not.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
