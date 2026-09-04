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


---

## Amendment 2026-09-04 — the agent that legitimately knows more than the query

**The founder's case.** A shopper spends an hour talking to their agent about shoes and
mentions liking white. Later they say "find shoes under 3k, size 9." The agent adds
`colour = white`. That constraint is **true, useful, and ungroundable in the query
text** — and we will never see the conversation it came from.

Under this DR as originally written the constraint is `AGENT_INFERRED` and cannot
authorise, which makes the agent's genuine knowledge useless. That is too strict, and
the fix is not to loosen the rule but to notice what the rule was actually for.

### We do not need to know whether the agent is right

We need the claim to be **attributable**. That is the same move the whole company makes
— §1 does not promise to detect a bad purchase, it promises to hold the stated request
and the chosen product together in a record that survives a dispute.

So the agent **attests**. `AGENT_INFERRED` gains a declared source:

| `claimed_source` | Meaning |
|---|---|
| `PRIOR_CONVERSATION` | the user told the agent, outside this query |
| `USER_PROFILE` | standing preference the agent holds |
| `AGENT_GUESS` | the agent inferred it from nothing the user said |

Optionally with an evidence span — the fragment of prior conversation relied on. **We do
not verify it.** We record it, and the record is signed.

This converts an unverifiable epistemic problem into a verifiable accountability one.
If the agent attests `PRIOR_CONVERSATION` and no such conversation happened, the agent
operator has made a false signed attestation, and §2.2's fault attribution has exactly
what it needs. Representations and warranties work this way in every commercial
contract: the counterparty asserts, and bears the consequence of asserting falsely.

### Which constraints an agent may supply at all

The direction of harm is not symmetric across attribute classes, so the permission
should not be either. Using the criticality classes:

| Class | Example | May the agent supply it? |
|---|---|---|
| `SOFT` / `COSMETIC` | colour, style | **Yes.** Worst case is a narrowed search and a lost sale. |
| `HARD` | size, allergen, variant | **No.** Getting these wrong is the returned-parcel case, and they are precisely the attributes §2.2 needs the *user* on record for. |
| `BOUND` | price ceiling | **Never in the relaxing direction.** |

That last row is the one that matters. A user says "under 3k" and the agent supplies
"under 5k" — that is not a hallucination, it is an unauthorised increase in the
mandate, and it must be `refuse`, not `confirm`. **An agent may narrow a bound. It may
never widen one.** This is the rule that connects this DR to the mandate-cap work.

The founder's colour case sits in the first row and is therefore permitted, recorded as
agent-attested, and can contribute to `satisfied`.

### The preference record is the cross-check

§2.8 accrues the shopper's unstated constraints from confirmed purchases. That is
*our* copy of the knowledge the agent is claiming to have.

- Agent attests `colour = white`, our preference record agrees → **corroborated.**
  Treat as authorising and stop asking.
- Agent attests something our record **contradicts** → surface it. The agent may be
  working from newer information than we have, or it may be fabricating. Either way
  a human should see it before money moves.
- Agent attests something we have no view on → record as attested, no corroboration.

This gives §2.8 a second job. It was described as a switching-cost mechanism; it is
also the only independent check we have on agent attestations, and it gets stronger
with every purchase. The same field again: liability attribution, switching cost, and
now agent verification.


---

## Amendment 2026-09-04 (second) — the attestation channel does not exist yet

The founder's objection, which is correct:

> When GPT queries for results it is not going to mention where it got the data from.
> This labelling will not be provided to us. We will never get `PRIOR_CONVERSATION` as a
> tag, neither will we have the prior conversation to validate.

The amendment above assumed a cooperating agent volunteering provenance. **No agent does
this today.** The design was right about what to do with an attestation and wrong about
how one arrives, and everything in this DR is therefore **inapplicable at Tier 0**.

What survives: the incentive is not ours to create. The agent operator is the liable
party for autonomous purchases, so a signed third-party record stating what the user did
and did not specify is *their* defence, not our imposition. Attestation is a product sold
to agent operators rather than a field scraped from them.

The tiering, the identity anchor for §2.8, and what may honestly be claimed at each tier
are moved to **DR 0008**, which supersedes the applicability of this DR. This DR remains
correct as the specification of Tier 1 behaviour and is dormant until Tier 1 exists.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
