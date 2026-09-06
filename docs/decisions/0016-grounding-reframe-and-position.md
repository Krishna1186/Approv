# DR 0016 — The grounding reframe, the graded score, and where Approv sits on the wire

- **Status:** OPEN — recommendation stated; founder closes
- **Raised:** 2026-09-06, by the founder
- **Touches:** §1, §2.1, §2.3, §4.3, §4.8, DR 0003, DR 0008, DR 0009, DR 0010, DR 0015
- **Blocks:** all decision-path code. §4.8 requires this record to exist first.

---

## 1. What changed

The check is no longer *"does this product match the user's intent."* It is:

> **"Did the agent read this product correctly, and from which field?"**

Consequences, in order of size:

- **Ground truth moves onto the merchant's own page.** Labelling stops being a judgement
  call ("is a sandal a shoe") and becomes a lookup ("does the variant field say 5kg").
  Expected kappa rises; Stage B stops being the wall.
- **The provenance ladder becomes the verdict**, not a caveat on it. "The agent said 5kg
  and got it from marketing prose, not the weight field" *is* the finding.
- **DR 0003, 0006 and 0011 leave v1.** Subsumption over a DAG is needed only when the
  agent's claim is a *category* claim. Most claims are attribute claims. Not wrong — not
  v1.
- **Category for v1 changes to quick commerce / grocery.** Its dominant failure mode is
  substitution and pack-size confusion, which is exactly what a grounding check catches.

## 2. Three comparisons, not one

Naming these separately is the whole design. They have different inputs, different
failure modes, and different evidentiary value.

| Check | Compares | Needs | Fails when |
|---|---|---|---|
| **CONSISTENCY** | what the agent *asked for* vs what it *claims about the pick* | nothing but the agent's own trace | agent searched `pack_size=5kg`, added 1kg |
| **GROUNDING** | what the agent *claims* vs what the merchant's data *says* | the merchant's product record | agent said 5kg, the page says 1kg |
| **SATISFACTION** | what the agent asked for vs the merchant's data | both sides | the classic intent check |

**CONSISTENCY is free, deterministic, and needs no catalogue understanding at all.** It is
the agent contradicting itself inside one session, in its own structured arguments. There
is no ontology, no extraction, no ambiguity, and no model. It is also, on MCP, always
available. This is the cheapest real product in the system and it should ship first.

## 3. The field ladder has two axes (founder correction #11)

The original ladder ranked fields by how confidently we can read them. That is only half.

- **Liability** — who owes a remedy if this text is wrong. A merchant's own published
  description is a guarantee they are answerable for; a customer review is not.
- **Certainty** — how sure we are we read it correctly. A dedicated weight field is
  unambiguous; prose is not.

These are independent. A variant field is high on both. A description is **high liability,
low certainty**. A review is low on both. Liability decides whether a claim is *coverable*;
certainty decides whether it is *confident*.

**Corollary the founder surfaced and Claude had not:** because merchant-authored text is
merchant-liable, **injecting into a description is self-incriminating** — whoever plants
the text inherits liability for it. Residual injection risk therefore concentrates in text
nobody is liable for: reviews, Q&A, third-party seller copy. That is a structural defence
and it is stronger than a technical filter.

## 4. The graded score — shape corrected

The founder asked for a distribution over `satisfied / unsure / refuse`. Rejected as
written: **`unsure` is a state of our knowledge, not a state of the world.** Nothing can be
65% likely to be unsure. Probability ranges over facts.

Adopted instead:

- **One number over the fact** — `P(this product really is 5kg)`.
- **A ceiling on that number, set by provenance.** A claim read only from prose caps below
  the `allow` threshold for a HARD attribute, no matter how confident the extractor is.
  Source beats confidence. This is what keeps the injection defence alive once a score
  exists.
- **The verdict is derived from founder-set thresholds plus criticality**, never from the
  score alone. Score inside, verdict outside — §4.3 intact.
- **Not a calibrated probability at v1.** Calibration needs thousands of observed
  outcomes, not 300–500 pairs. v1 ships the number as a *ranking* (which claims deserve
  scrutiny). Publishing it as a probability before calibration is what §4.6 exists to
  prevent.

## 5. Seller advice may only downgrade (founder correction #12)

An `others` bucket (seller recommendations, reviews) is accepted as evidence, with a hard
direction constraint. *"Runs small, order a size up"* is **advice, not an attribute claim.**
It does not change that the item is a size 9; it changes whether a size 9 suits this
buyer's foot, which is unverifiable.

**Advice may only lower confidence or force a `confirm`. It may never raise a verdict or
flip a fact.** If advice can upgrade, one planted line of copy moves the decision, which
reopens the exact injection channel §3 just closed. DR 0009's monotone rule, applied to
advice.

## 6. Where Approv sits — the founder's escrow question

> *"If we sit inside or after the Swiggy cart, we don't read the agent's trace. We'll have
> one-sided info."*

**The premise is wrong for MCP specifically, and that is load-bearing.** On MCP the agent's
request *is* its trace. A merchant-side observer receives the tool call with typed
arguments — `search_products(brand="Aashirvaad", pack_size="5kg")` — the exact response
served, and the whole call sequence. That is both sides for that merchant.

The genuinely one-sided position is the opposite one:

**Option A — agent-side (Approv is a server the agent calls before checkout).**
- Sees only what the agent chooses to send, including the agent's own *report* of the
  product — which is the thing under test. You are asking the defendant for the evidence.
- *For:* one party to sell to, no merchant integration, matches DR 0010's buyer.
- *Against:* GROUNDING is unverifiable here. Only CONSISTENCY survives.

**Option B — merchant-side proxy (Approv sits in front of the merchant's MCP server).**
- Sees the agent's typed arguments, the merchant's authoritative response, and the cart.
  All three checks are available.
- *For:* one party adopts, both sides observed, no dependency on agent cooperation.
- *Against:* the user's original words are still absent (they are absent everywhere), and
  we see nothing the agent did at other merchants.

**Option C — true escrow, both parties connect through Approv.**
- *For:* complete visibility.
- *Against:* **requires simultaneous adoption by both a marketplace and an agent
  operator**, which doubles the DR 0015 deadlock rather than solving it. Puts us in the
  latency path of every call, not just checkout. Makes us hold both parties' data, which
  is a compliance burden and the highest-value target in the chain. Not viable as a first
  product.

### The resolution: escrow the evidence, not the traffic

The property the founder wants from escrow is **neither party can later rewrite its half.**
That comes from *signing*, not from *position*. It does not require being the wire.

```
correlation id  ──┬── agent's half:    stated constraints, signed by the agent
                  │                    (AP2 Intent Mandate where one exists)
                  └── merchant's half: product snapshot as served, signed by the merchant

Approv joins the two by id, compares, hash-chains the result.
```

Each side submits a signed half. Approv joins them. Neither side has to route its live
traffic through us, and neither can repudiate its own submission later. That is the escrow
guarantee without the escrow topology.

**And it degrades cleanly, which is what makes incremental adoption possible.** Whichever
side integrates first produces a signed half; the other half is `UNATTESTED` and, per
§2.3, an unattested half routes to `confirm` and never to `allow`. The system works
one-sided — it simply verifies less and says so.

### In-path vs off-path

Observe on every call, **off** the latency path, asynchronously. Decide on **one** call —
cart submission or checkout — in path. This is DR 0004's `mark` / `verify` / `gate` split
expressed as a wire position: being in the path of every search would make us the
merchant's uptime problem, and that is how verification layers get removed.

## 7. New attack surface entries (§6 additions)

Not in the current taxonomy and now required:

- **Tool-description injection.** An MCP tool's description is text the agent reads before
  calling it. It is an instruction channel.
- **Tool-definition rug-pull.** A server may change a tool's description after the agent
  has approved it. Absorbed by hashing tool definitions at the proxy and alerting on
  change.
- **Correlation-id forgery.** If the join key is guessable, a half can be attached to
  someone else's session. The id must be unguessable and bound into each signed half.
- **Half-submission withholding.** A party that expects to lose a dispute simply does not
  submit its half. Absorbed by treating a missing half as `UNATTESTED`, never as absent
  evidence in that party's favour.

## Recommendation

**Option B, with the signed-halves construction from §6, shipping CONSISTENCY first.**

Consistency needs no catalogue permission, no ontology, no labelled data and no model —
which means it is the only part of this system that can be demonstrated before Stage B
finishes. It is also the check that most directly answers "is this agent trustworthy",
which is what DR 0010's buyer is paying for.

## Decision

*(founder — close this before any decision-path code beyond `types/`)*
