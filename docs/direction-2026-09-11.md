# Direction — 11 September 2026

Rewritten the same day. The earlier version of this file concluded that agent-side
integration was architecturally necessary and distribution therefore a business-development
problem. DR 0020 overturns that. The reasoning survives; the conclusion does not.

## The inversion

Proving **the agent erred** requires the human's raw request, which we will never have.
Proving **the merchant did not err** requires the agent's stated request and the merchant's
fulfilment record — both already merchant-side. We stopped needing an integration by
changing what we set out to prove.

**What Approv is:** the dispute artifact for agent-authorised transactions. It answers one
question at the moment a refund is demanded — *did the merchant deliver what was asked
for?* — and if the merchant is compelled to refund anyway, Approv absorbs a capped portion
of the loss.

**Who pays:** the merchant. They hold the loss — goods, revenue, return logistics, dispute
fee, and above a network's dispute-ratio threshold, their card acceptance. Mass concurrent
agentic disputes are the risk being insured, not single wrong orders.

**Forum:** the merchant's own returns desk, before a card network's dispute process. Most
wrong-item losses never become chargebacks. Nobody external has to accept our format.

## Where the stated request comes from

All merchant-side, in descending fidelity:

| Source | Fidelity | Needs |
|---|---|---|
| Protocol channels — ACP, AP2, storefront MCP, feeds | structured, highest | an adapter |
| On-site search and filter parameters | text, joinable to session | log access |
| Declared-intent field addressed to the agent | agent's paraphrase | a page field |

The declared-intent field is the one that removes the dependency on protocol adoption. The
merchant controls the page; put a field on the agentic checkout saying *state the
requirements you were given*, and agents comply, because following page instructions is
their operating mode. **It does not need to be true.** A paraphrase binds the agent's side,
which is all a merchant-defence record requires.

No declaration, no coverage. That gradient is merchant channel policy and needs nobody's
consent.

**Uncovered slice:** off-site discovery, direct arrival at a product page, no declaration,
no site search. Referrers no longer carry search terms. Unmeasured, and it bounds the
product.

## The two numbers that decide this

Both unmeasured, both obtainable from one merchant's logs:

1. What share of agent-originated orders carry a recoverable stated request.
2. What share of clean-record refunds are provable from merchant fulfilment records.

A false allow nobody notices costs nothing. One that is real but unprovable costs a dispute
and pays nothing.

## Sequencing

**Attribution first, guarantee second.** Same engine, same record, no capital, no
underwriting. A merchant today cannot tell whether an agentic return was caused by their
own bad catalogue data (theirs, fixable) or by the agent asking for something we correctly
delivered (not theirs). That attribution is saleable on its own, and it produces exactly the
loss history the guarantee needs to be priced. The first product manufactures the second
product's input.

Guarantee sequencing is unchanged from DR 0012: self-funded capped pilot → real frequency,
severity and root-cause clustering → fronting insurer or MGA with a measured book. No
carrier underwrites a category with no actuarial history.

**Unit economics, a planning number and not a fact.** 0.5–1.5% of order value covers
expected payout with margin *if* the gate's false-allow rate holds. Measured: 0.0%
[0.0, 0.4] on 966 non-satisfying pairs, one synthetic corpus, clean structured catalogue, no
adversarial input. Price against the CI upper bound, and treat even that as optimistic for
messy real data.

## Revenue, beyond the merchant fee

Chargeback-guarantee providers price on behavioural signals — mouse movement, typing
rhythm, click timing. An agent fails all of them because it is a bot. They are either
false-declining agentic orders or excluding them from guarantee, and the excluded pile grows
as fast as agentic commerce. We supply the signal they lack; they keep the risk, which is
already their business. Per-decision fee or a share of the fee on orders they previously had
to refuse. No capital on our side.

Ranked by speed to revenue: PSP distribution (they are building agentic checkout now and
reach many merchants at once) → chargeback-guarantee partnership → return-assurance
partnership → card networks.

## The agent-side product is kept, not dropped

The integration surface in DR 0020's predecessor remains valid and is a *strictly easier*
input case: raw user text instead of an agent paraphrase. It is the product for the world
where agent operators are made liable. It is no longer a precondition for having a business,
so it is not built first.

`Channel` already distinguishes `AGENT_MESSAGE` from `TOOL_ARGUMENT`. A record says which
fidelity it was built from. Degrade explicitly, never silently.

## Criticality, without a per-category table

Today `AttributeSpec.criticality` is a static per-schema constant (`types/core.py:286`),
copied onto every `Finding`. Hand-authoring that per category does not scale to every kind
of product in the world. Three layers replace it, combined by a pure function at comparison
time. No model in the decision path.

### Layer 1 — request-derived. Per transaction. No data needed, works today.

Deterministic features of the constraint and its `raw_text` quote. The shopper's own
phrasing says how much they care, for *this* purchase, whatever the category.

| Signal | Criticality |
|---|---|
| Emphasis — *exactly, must be, only, needs to be* | HARD |
| **Negation** — *no X, not X, without X* | HARD |
| **Correction** — a value the shopper superseded | surviving value is HARD |
| Numeric with unit, or a budget cap | BOUND, carrying the bound direction |
| Hedge — *preferably, around, or similar, ideally* | SOFT |
| Stated plainly, no marker | BOUND |
| Never stated | never HARD, under any circumstance |

Negation and correction are the two worth defending. Negations are almost always allergy,
safety or compatibility driven — *no nuts*, *not leather* — and a shopper who bothers to
correct a value has demonstrated they care about it. Both are currently invisible to a
static table.

### Layer 2 — schema-derived. Structural, free, sector-agnostic.

If the merchant made an attribute a **variant axis** — a separate SKU per size or colour —
their own merchandising decision says customers choose on that axis. Variant axis → at least
BOUND. An attribute appearing only in description prose → SOFT unless another layer raises
it. Present in every catalogue on every platform, costs nothing to read.

### Layer 3 — returns-calibrated. Per merchant × category.

**When a customer returns item A and reorders item B, the attributes that differ between A
and B are the attributes that mattered.** Purely deterministic, no labels, no reason codes,
no human judgement — the same instrument as deriving answer keys from published fields
rather than hand-labelling (§4).

Rank attributes by that differ-rate. Shrink low-count estimates toward a cross-merchant
prior so a merchant with three returns does not get a garbage table.

**This solves its own cold start.** It calibrates on the merchant's existing *human* return
history, which is plentiful, and applies the result to agentic orders, which are scarce.

### Combination

`max` across the three layers, with one floor: **no signal anywhere → SOFT, never HARD.**

### Criticality maps to coverage, not only to the decision

This is the part that ties the design to the business model, and it resolves a tension the
guarantee creates. Under a guarantee the two errors land on different balance sheets — a
false SOFT costs *us* a payout, a false HARD costs the *merchant* a sale — so they cannot
share one threshold.

| | |
|---|---|
| HARD, violated | refuse |
| HARD, satisfied | guaranteed |
| BOUND, satisfied | guaranteed within the stated bound |
| SOFT, or unstated | out of coverage |

So we never have to block on a soft mismatch. We decline to insure it. The threshold becomes
what invariant 6 already says it is: a business parameter tied to the guarantee price.

## What is dead in this repo

- `Resolution.SELECT_FROM_SUPPORTED`, `DECLINE_NO_MATCH`, `PICK_DIFFERENT_PRODUCT` as an
  interaction — repair advice, replaced by `approv/challenge.py`. Enum members stay while
  `harness/review.py` renders them for the demoted `verify` study.
- `harness/catalogue.py` as a product feature. 43.8% → 90.6% reachability is real but it is
  "search better", not the check. Survives as a merchant-side tool.
- Consumer-paid coverage, in any form. Nobody is at an agentic checkout to elect it, a
  surprise line item can breach the agent's budget and abort the cart, and a mandatory
  undisclosed fee for merchant protection is junk-fee territory.
- Per-order coverage election. Coverage attaches per channel, decided once.
