# DR 0005 — Constraints carry provenance too

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-03, by the founder
- **Touches:** §2.1, §2.2, the record, §6, and the liability claim in §1
- **Blocks:** the `Constraint` type, therefore `types/`

---

## The founder's position

> If the user prompted white shoes under 3k but the agent on clarification mentions
> some design or brand or something that wasn't mentioned — basically if it
> hallucinates or gives wrong info — we verify this as a security layer.

An agent standing between the shopper and the check can introduce constraints the
shopper never expressed. It does not need to be adversarial to do this; it is what
helpful agents do when asked to be specific. The check as currently designed cannot
tell an agent's invention from a shopper's instruction.

---

## Why this is not just a safety feature

§4.5 already treats **product** text as untrusted. The design answer to that was
attribute provenance: `STRUCTURED` / `TITLE` / `DESCRIPTION` / `INFERRED`, with the
rule that an `INFERRED` attribute may never produce `satisfied` against a hard
constraint.

The founder's point is the mirror image, and it exposes a gap: **the request side has
been treated as trusted, and in an agent-mediated flow it is not.** The intent arrives
via the agent, not the shopper. Symmetry is required.

**The liability argument is the stronger one.** §2.2 attributes fault by asking whether
the request named an attribute. If an agent invents "Nike" and the shoes are wrong,
§2.2 must be able to say *agent fault, coverable* — and it can only say that if the
record proves the constraint originated with the agent rather than the shopper. Without
request-side provenance, a fabrication and an instruction are byte-identical in the
evidence trail, and the fault attribution that §1 calls the company collapses in
precisely the dispute it was built to survive.

## Proposed values

| Provenance | Origin | May authorise? |
|---|---|---|
| `USER_STATED` | present in the shopper's verbatim text | yes |
| `CLARIFICATION_ANSWER` | shopper answered a targeted question | yes |
| `PREFERENCE_RECORD` | learned from past confirmed purchases (§2.8) | yes, recorded as inferred |
| `AGENT_INFERRED` | supplied by the agent, not traceable to the shopper | **no** |

The verification is mechanical and does not need a model: every constraint the agent
supplies must be **groundable in `request_text`**, which the record already stores
verbatim. Ungroundable constraints are not rejected — they are *labelled*.

## The asymmetry worth noticing

An `AGENT_INFERRED` constraint is not dangerous in the direction one first assumes.

- **Agent invents a constraint the product violates** → `refuse`. Safe. A lost sale, not
  a wrong purchase.
- **Agent invents a constraint the product satisfies** → looks like a clean match. This
  is the harmful case. The agent has silently narrowed the shopper's intent without
  authority: the shopper asked for white shoes under 3k and got a specific brand they
  never requested, possibly at a worse price, and the record shows a perfect match.

So the rule is not "reject agent-inferred constraints." It is **"an agent-inferred
constraint may never be the reason a comparison reads as `satisfied`."** It records,
and it may trigger `confirm`, but it cannot contribute to authorisation.

## Relationship to injection

This mechanism also absorbs part of §6. An injection that reaches the agent and alters
the constraints it supplies produces exactly the same signature as a hallucination —
constraints not groundable in `request_text`. One check, two threat classes. The
difference between the two is intent, which we cannot observe and do not need to.

## Options

**Option 1 — trust the request side.**
- *For:* nothing to build; matches the current §2 record.
- *Against:* false in any agent-mediated flow, which is the entire premise in §1.

**Option 2 — provenance enum on every constraint, groundability checked against
`request_text`, recorded in the `ComparisonRecord`.**
- *For:* closes the fault-attribution gap; symmetric with product-side provenance;
  absorbs an injection class for free.
- *Against:* the `Constraint` type grows a required field; groundability checking on
  paraphrase is fuzzier than exact-match ("under 3k" vs "cheaper than three thousand"),
  so the check itself has a false-positive rate that needs measuring.

**Option 3 — Option 2, plus refusing to proceed on any `AGENT_INFERRED` constraint.**
- *For:* strictest.
- *Against:* breaks legitimate agent behaviour and, worse, breaks §2.8 — the preference
  record's whole purpose is to supply constraints the shopper did not type. This would
  forbid the mechanism that builds the switching cost.

## Recommendation

**Option 2.** Option 3 conflates *inferred* with *illegitimate*; §2.8 depends on
inferred constraints being usable. The distinction that matters is not whether a
constraint was inferred but whether it is **attributable** — and provenance is exactly
the field that makes it so.

## Open sub-question

Is `PREFERENCE_RECORD` provenance strong enough to authorise on its own? It is inferred,
but inferred from the shopper's own confirmed history rather than from an agent's
guess. Arguably it authorises for `SOFT` constraints and only prompts `confirm` for
`HARD` ones. Not settled here.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
