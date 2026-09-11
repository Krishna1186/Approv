# Direction — 11 September 2026

Supersedes the merchant-side framing. Items 2–5 of the reset; item 1 is built
(`approv/challenge.py`, 18 tests).

## The position, and why it is forced

Three things diverge in an agent purchase: what the human wanted (1), what the agent
captured (2), what the merchant fulfilled (3). Approv compares one request representation
against merchant evidence — so it sees (2)-vs-(3) or (1)-vs-(3), never both, and which one
depends entirely on where it sits.

Checkout only ever receives the agent's paraphrase, so it can catch merchant execution
errors and structurally cannot catch the agent misreading the human. That failure has no
liable party today and is the one that hurts the consumer most. It is visible only next to
the agent's own reasoning, with something close to the raw request.

**So agent-side integration is architecturally necessary, not preferred.** Distribution is
therefore a business-development problem — an operator has to wire us in voluntarily — and
there is no technical route around that.

## 2. The integration surface

One call, inside the agent's flow, before it commits to a purchase.

```
check(request_text, proposed_product, catalogue_reader, *, prior_turns=(), locale)
  -> Decision + findings + challenges + a signed record
```

**What it must receive, in descending order of value:**

| | why |
|---|---|
| The user's raw words, verbatim | the only input from which (1)-vs-(2) is visible at all |
| Prior turns that amend the request | corrections are where agents lose constraints |
| The proposed product id | what is being bought |
| A reader for the merchant's catalogue | Approv reads evidence; it never takes the agent's word |

The raw request is the whole reason to be at this position. An operator that passes only a
structured paraphrase gets the narrower merchant-execution check, and the record should say
so — `Channel` already distinguishes `AGENT_MESSAGE` from `TOOL_ARGUMENT`, and the
attestation field already carries who signed what. Degrade explicitly; never silently.

**What it returns:** the decision, the per-attribute findings, and on CONFIRM the
challenges. One bounded round, then ALLOW or REFUSE.

**The reader is the operator's, pointed at the merchant, not at the agent.** Approv is safe
against a dishonest agent because it never reads anything the agent wrote; it is not safe
against a dishonest merchant and does not claim to be.

**Open:** whether the SDK ships the catalogue reader for common shapes (Shopify, ACP, MCP
`search`) or requires the operator to write one. Shipping it is the infrastructure-
convenience pitch; requiring it is faster to build.

## 3. The guarantee

**The claim, narrowed to kill moral hazard:** a field-level mismatch between what the
signed record verified and what the merchant's own fulfilment record shows shipped. Record
says size 9 verified against `variant.option_size`; the merchant's shipment record says
size 8 went out. Checkable against merchant systems, not against a customer's assertion.

A return-cost guarantee triggered by customer say-so is a chargeback guarantee with a new
name — same adverse selection, same moral hazard. Not building that.

**Caps, because one bad catalogue field produces many simultaneous claims:**

| Cap | Purpose |
|---|---|
| Per order | bounds a single loss |
| Per occurrence (one root cause, however many orders) | the correlated-risk cap that actually matters |
| Monthly aggregate | bounds the pool regardless of cause |

Per-occurrence is the one that stops a systemic catalogue error from draining the pool, and
it is the one a naive per-order cap misses entirely.

**Sequencing.** No carrier underwrites a category with no actuarial history.

1. Self-funded pilot. Hard caps, narrow claim class only, one operator, 6–12 months.
2. Real loss data: frequency, severity, root-cause clustering, how often the narrow claim
   is even provable from merchant records.
3. Fronting insurer / MGA with a measured book.

**Unit economics, as a planning number and not a fact.** A 0.5–1.5% fee on typical order
value covers expected payout with margin *if* the gate's false-allow rate holds. Measured:
0.0% [0.0, 0.4] on 966 non-satisfying pairs, one synthetic corpus, clean structured
catalogue, no adversarial input. The CI upper bound is the number to price against, and
even that is optimistic for messy real data.

**Unmeasured and load-bearing:** what fraction of false allows become claims at all, and
what fraction are provable from merchant fulfilment records. A false allow nobody notices
costs nothing; one that is real but unprovable costs a dispute and pays nothing.

## 4. GTM sequencing

**First segment: merchant-controlled agents, sold as infrastructure convenience.** They
already have the catalogue, already control both ends, and need no liability transfer to
say yes. They are not the big prize; they are the only segment where a first deal closes
without an actuarial history, and they generate the loss data that makes pitch (b)
possible.

**Second: protocol-compliant flows (AP2/ACP/MCP)**, where the integration point already
exists and the work is an adapter rather than a partnership.

**Third, and only with loss data in hand: liability transfer to a general-agent operator.**
One deal covers every merchant that operator's agent buys from, priced against total
transacted GMV. This is the whole business and it cannot be attempted first, because the
pitch is "we will pay for your agent's mistakes" and that requires a priced book.

**What a first deal looks like:** one merchant-controlled agent, `gate` on every purchase,
Approv self-funding a capped guarantee on the narrow claim class, both sides instrumented
for six months. We are buying loss data and paying for it with a capped guarantee.

## 5. Criticality without a per-category table

Three inputs, in precedence order.

**Request specificity drives per-transaction criticality.** An attribute the shopper stated
unambiguously is HARD for that transaction whatever the category — "size 9" is hard because
they said 9, not because footwear has a size table. This is mostly already there:
`Constraint` carries `raw_text`, and the extractor records what was stated. What is missing
is the grading — stated-with-a-quote versus inferred versus absent.

**Returns data calibrates the category level.** Which attribute mismatches actually caused
returns at this merchant. Merchants have this; nobody has to label anything.

**Everything else defaults SOFT.** A missed check costs nothing until it is tested; a
wrongly-hard check blocks a real sale immediately. That asymmetry resolves every default in
one direction, and it is the same argument §2.6 makes about the error ratio.

**Not built.** `AttributeSpec.criticality` is currently a static per-schema field. Making it
per-transaction means deriving it at comparison time from the constraint's own provenance,
which is a change to how the schema is applied rather than to the operators.

## What is now dead in this repo

- `Resolution.SELECT_FROM_SUPPORTED`, `DECLINE_NO_MATCH`, `PICK_DIFFERENT_PRODUCT` as an
  interaction — repair advice, replaced by `approv/challenge.py`. The enum members stay
  while `harness/review.py` still renders them for the demoted `verify` study.
- `harness/catalogue.py` as a product feature. It measured 43.8% → 90.6% reachability, but
  that is "search better", and it is not the interaction mode. It survives as a merchant-
  side tool if the infrastructure-convenience pitch is taken, not as the check.
- The merchant checkout plugin as a distribution route.
