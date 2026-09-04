# DR 0008 — What we actually receive, and what we can honestly claim from it

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-04, by the founder, invalidating part of DR 0005
- **Touches:** §1, §2.2, §2.5, §2.8, DR 0005, the entire commercial pitch
- **Blocks:** the `Request` type, therefore `types/`

---

## The founder's objection, which is correct

> When GPT queries for results, it's not going to mention where it got the data from —
> user profile, guess, etc. This labelling will not be provided to us. We will never get
> `PRIOR_CONVERSATION` as a tag, neither will we have the prior conversation to
> validate. So this solution is kind of useless.

And:

> Will we even have the actual user prompt, or just what the agent searches for? If
> someone chats in GPT, we only ever see their agent searching for them with no info
> about what the user truly asked.

DR 0005's attestation design assumed a cooperating agent that volunteers provenance.
**No agent does this today, and none will volunteer it unprompted.** The design was
correct about what to do with an attestation and wrong about how one arrives.

Worse, the deeper problem: if all we observe is a search string emitted by an agent,
then `request_text` — the field §2 stores verbatim and §2.2 attributes liability
against — **is not the user's request at all.** It is the agent's paraphrase of it.
The record would be signing the wrong object.

---

## The three tiers we can actually be in

The honest framing is that intent reaches us at one of three fidelities, and **what we
can claim differs at each.** Conflating them would be the credibility failure §5 warns
about, applied to the input side instead of the corpus side.

### Tier 0 — Observed query only

We see a search string and a product. No user text, no provenance, no identity.
This is the GPT-browses-a-marketplace case and the merchant-plugin case.

**What we can verify:** does the selected product match *the query that was issued*?
This catches the agent picking the wrong item out of its own result list — a real and
common failure, since selection is a separate step from search and gets no scrutiny.

**What we cannot verify:** whether the query faithfully represents what the human
wanted. An agent that mistranslates "something for my daughter's school shoes" into
"black formal shoes size 3" produces a perfectly consistent Tier 0 verification of the
wrong intent.

**The claim must therefore be narrow and stated narrowly:** *"the product matches the
stated query."* Never *"the product matches the user's intent."* Everything downstream
— badge copy, merchant contract, receipt wording — must use the narrow phrasing.

### Tier 1 — Query plus declared constraints

The agent operator integrates and sends structured constraints alongside the query,
with provenance as DR 0005 describes. Still no raw conversation, and we still cannot
verify the attestation.

**What we can verify:** everything in Tier 0, plus whether the agent's own declared
constraints are internally consistent and whether they contradict our preference record.

### Tier 2 — Mandate-anchored intent

Under UAP, the payment mandate carries a scope the human authorised. Intent arrives
through the rails, not through the agent's goodwill.

**What we can verify:** whether the purchase falls inside a scope a human actually
authorised — which is the only tier where §2.2's liability claim is fully true.

---

## The objection that dissolves "no agent will attest"

The founder is right that attestation cannot be *extracted*. But it does not need to be
— the incentive is already pointing the right way, and the founder identified this in
the same message:

> If the agent (example Astra) is making purchase decisions, it's the one liable, not
> the merchant or consumer.

**The party with the strongest reason to attest is the party that gets sued.** An agent
operator facing liability for autonomous purchases wants a signed third-party record
saying *"the user stated white; we did not invent it."* That record is their defence.
Without it, every wrong purchase is unattributable and therefore theirs by default.

So Tier 1 is not something we scrape out of an uncooperative agent. **It is a product we
sell to agent operators**, and the customer for the provenance API is the agent
operator, not the merchant. That is a different sales motion than the merchant plugin
and probably a better one, because their exposure is per-transaction and unbounded
while a merchant's is a return.

This does not make Tier 0 optional. Tier 0 is what we can do on day one with no
integration, it is how we get data, and it is how we demonstrate the thing that makes
anyone want Tier 1.

## The identity problem for §2.8

> If it's the agent, we can't exactly assign it to a human to keep preference data.

Correct at Tier 0, and it means **§2.8's preference record does not exist at Tier 0.**
It needs a stable human anchor, and the candidates are:

| Anchor | Available at | Stable? | Problem |
|---|---|---|---|
| Agent session id | Tier 0 | no | dies with the session; useless |
| Agent-operator user id | Tier 1 | yes | requires integration; is *their* identifier |
| **UPI mandate / payment instrument** | Tier 2 | **yes** | tied to a real accountholder by construction |
| Merchant account id | Tier 0, if merchant-side | yes | fragments per merchant, no cross-merchant view |

The mandate is the natural anchor — it is the one identifier in the chain that is bound
to a human by the rails themselves. Which means **§2.8's switching cost is a Tier 2
property**, not something we get for free at launch. This should be said plainly in any
pitch rather than implied to exist from day one.

## Consequences for the record

`request_text` must stop pretending to be one thing:

```
observed_query          verbatim, what we were actually given
observed_query_source   USER_TYPED | AGENT_ISSUED | UNKNOWN
declared_constraints    Tier 1+, with provenance per DR 0005
mandate_scope           Tier 2 only
intent_tier             0 | 1 | 2
```

`intent_tier` then pins into the receipt, and **accuracy numbers are reported per
tier** — a Tier 0 number and a Tier 2 number measure different things and averaging
them would be the §4.7 mark/verify error repeated on a new axis.

## Options

**Option 1 — assume Tier 1 and build for cooperating agents.**
- *For:* cleanest design.
- *Against:* nothing to sell until someone integrates; no data; no wedge.

**Option 2 — build Tier 0, state the narrow claim honestly, sell Tier 1 to agent
operators on their own liability exposure, treat Tier 2 as the UAP endgame.**
- *For:* deployable immediately; the narrow claim is still a real and unmet need;
  each tier is a distinct commercial conversation with a distinct buyer.
- *Against:* three input shapes to support; the honest Tier 0 claim is less impressive
  than the pitch people will assume we are making, and we must correct them every time.

**Option 3 — refuse to operate below Tier 1.**
- *For:* every claim is fully defensible.
- *Against:* no product until a large agent operator signs, which inverts the order of
  proof — they will ask for the number first.

## Recommendation

**Option 2.** Tier 0 is the only thing that can produce Stage C's number, and Stage C's
number is what makes Tier 1 sellable. The discipline this requires is verbal: never
once describe a Tier 0 result as intent verification.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
