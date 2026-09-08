# DR 0010 — The agent is the customer, and the badge is an underwriting instrument

- **Status:** CLOSED 2026-09-05 — Option 2, agent operator is the buyer
- **Raised:** 2026-09-04, by the founder
- **Touches:** §1, §2.2, §2.5, §2.7, §2.8, §3, DR 0008
- **Supersedes:** the merchant-first reading of DR 0008 Option 2

---

## The founder's correction

> In the west many merchants use protocols like ACP that give structured merchant data.
> The agent directly submits an entire CART of products, no query texts, nothing. It has
> MADE its decision already. This implies that as a merchant integration it doesn't make
> sense unless there's a workaround.

This is a harder version of DR 0008 and it is correct. DR 0008 assumed Tier 0 gives us
an observed query. Under a cart-submission protocol **there is no query at all** —
neither the user's words nor the agent's paraphrase. The merchant receives a decided
basket.

So the merchant-side integration does not degrade to a narrower claim. **It has nothing
to verify against.** A product with no stated request is not a weak comparison; it is
not a comparison. This kills merchant-side intent verification outright wherever
cart-submission protocols are used, and that is the direction the West is moving.

The founder's second observation closes it:

> If an agent is giving a cart, a merchant doesn't care if it's what matches — that's
> the agent's responsibility.

Correct, and it explains why merchant-side was always the weaker sale. **The merchant's
liability ends at "I shipped what was ordered."** Intent mismatch is not their exposure,
so intent verification is not their purchase. We were trying to sell a hedge to the one
party in the chain that is not exposed.

## What this leaves

| Setting | Do we get intent? | Is there a product? |
|---|---|---|
| Human searching a marketplace, merchant-integrated | yes — a real typed query | **yes** — this is what we build now |
| Agent submitting a cart via ACP-style protocol, merchant-integrated | **no** | **no** |
| Agent integrated with us directly | yes — whatever they choose to send | **yes, and it is the larger one** |
| UAP mandate, post-launch | scope authorised by a human | yes, and the strongest |

India today is mostly row 1: few merchants on these protocols, and UAP's data structures
are not published. So **row 1 is correctly what we are building**, and it is the only
row that can produce Stage C's number. But it is a starting position, not the business.
Rows 3 and 4 are where this goes.

---

## The reframe: what an agent operator actually buys

The founder's proposal:

> We sign the record for them with all our logs as backup, AND the future idea is to
> underwrite their agent by guaranteeing that if it has a badge from us, we bear the cost
> if it's a false purchase.

This changes what the company is, and it is the first framing where every existing
design decision pays for itself.

**Two things are being sold, to the same buyer, on one integration:**

**1. A capability upgrade.** Not a compliance tax. The check returns a *structured
repair signal* — which attribute failed and why — that the agent can act on before it
buys. An agent that receives `colour: violated (requested white, product black)` can
correct in one step. An agent that receives `0.42` can do nothing. This makes the
operator's agent measurably better on unchanged model weights, which is a thing they
are already spending heavily to achieve.

**2. A liability shield, and eventually a warranty.** The agent operator is the exposed
party for autonomous purchases. A signed, hash-chained, third-party record stating what
was requested, what was compared, and on what basis, is their defence. And the badge
graduates from *evidence* to *guarantee*: if we said allow and it was wrong, we bear it.

### Why the whole architecture was already built for this

Underwriting is not a bolt-on. Read backwards, the design already assumes it:

- **§2.2's completeness vector is the exposure calculation.** "Request named it and the
  product violates it → agent fault, coverable. Request was silent → **named perils
  only, not covered**." That is policy language. The `unstated` field *is* the coverage
  boundary.
- **§2.6's asymmetric error cost is a loss ratio.** A false `allow` is a claim. Its rate
  times average basket value is the expected payout, and the operating point on the
  curve is a **pricing decision**, not a tuning decision.
- **§4.6's requirement that every accuracy number carry a denominator and an interval**
  stops being methodological hygiene and becomes the actuarial basis. You cannot price a
  guarantee off a number without a confidence interval.
- **§2.7's signed comparison** is the claims-adjudication artifact.
- **DR 0007's verification floor** is the underwriting questionnaire: below the floor,
  no cover, stated in advance.
- **"Unknown never authorises" (§2.3)** is what keeps the loss ratio finite. Every
  `confirm` is a claim not written.

**This is why the accuracy number is the whole company and not a demo statistic.** It is
not a marketing claim, it is a price.

### What has to be true before underwriting is real

Flagged honestly rather than assumed away:

- **Capital and regulatory posture.** A guarantee to bear third-party financial loss is
  plausibly a regulated activity. In India that is IRDAI territory, and "we will pay if
  we are wrong" may be an insurance product regardless of what it is called. **The early
  form should be a capped commercial indemnity inside the contract** — a normal
  warranty, priced off the measured false-allow rate — not a policy. Real underwriting
  comes later, with a partner carrier.
- **Adverse selection.** Operators with the *worst* agents want the badge most. Pricing
  has to be per-operator and re-measured, not a flat rate.
- **Moral hazard.** If we cover the loss, the operator under-invests in their own checks.
  Mitigated by a deductible, and by pricing on their observed `confirm` rate.
- **A number first.** Nothing above is quotable until Stage C exists. §3 already says the
  merchant plugin is worth nothing before Stage C; the same is true of this, more so.

## The identity anchor, revisited

The founder proposed mapping to the account an agent is registered to, or a payment id
hash. At Tier 0 we get neither. But under this DR the buyer is the agent operator, and
an integrated operator can supply a **stable opaque per-user identifier** — they already
have one, and it costs them nothing to hash and send.

So §2.8's preference record becomes available at Tier 1 rather than only Tier 2. It must
be a pseudonymous operator-scoped id, never an email, and never joined across operators —
both because India's DPDP framework constrains it and because a cross-operator identity
graph is a liability nobody asked us to hold.

## Options

**Option 1 — merchant-first, as DR 0008 Option 2 implied.**
- *Against:* the founder's ACP correction. No query, no product, and the merchant is not
  the exposed party.

**Option 2 — build row 1 (human search) to produce the number; sell rows 3 and 4 to
agent operators as capability-plus-indemnity.**
- *For:* row 1 is buildable now and is the only source of a number; the number prices the
  indemnity; the indemnity is what an exposed buyer actually wants.
- *Against:* two audiences; the row 1 surface may look like a demo to an agent operator
  and must be positioned as the measurement rig it is.

**Option 3 — go straight to agent operators.**
- *For:* correct end state.
- *Against:* they will ask for the number first, and the number requires row 1. Inverts
  the order of proof.

## Recommendation

**Option 2.** Unchanged build order, changed story. What we are building this quarter is
the same code either way; what it is *for* is producing the number that prices a
guarantee to an agent operator, rather than a badge sold to a merchant who is not
exposed.

## Amendment, 2026-09-08 — nobody may be liable, so stop selling liability

Founder's observation, and it undercuts the pitch this DR was built on: **the agent
operator probably does not carry the loss.** Their terms disclaim it, the payment
provider authorised a valid transaction, and neither is the party out of pocket.

Follow the money on a wrong agentic purchase and it lands in two places: the **consumer**
(hassle, and time), and the **merchant** (return logistics, restocking, refund cost). The
agent operator's exposure is churn, which is real but soft, deferred, and not something a
procurement team writes a cheque against.

So an indemnity sold to the agent operator is an insurance policy against a risk they do
not hold. That is not a hard sell; it is an incoherent one.

### Where revenue can actually come from, ranked by how soon it works

**1. Observability — the strongest near-term product.**
An agent operator cannot see *why* its agent picked the wrong item. Approv can: which
attribute, which field, whether the agent read it or invented it. That is error
monitoring, and error monitoring is bought by engineering teams with existing budget for
exactly one reason — you cannot debug what you cannot see. Nobody buys Sentry for
liability reasons.
- Buyer: the team that owns the agent. Budget line already exists.
- Needs: the engine and a dashboard. **No liability, no guarantee, no regulator.**
- This is the pitch that survives the founder's observation intact.

**2. Conversion uplift — the strongest once there is a number.**
If verification raises the completed-purchase rate, the benefit is revenue rather than
avoided loss, and it accrues to *both* sides. "We make you money" outsells "we protect
you from a risk you did not think you had." Blocked on the benchmark producing a real
delta, which is precisely what `docs/benchmark-design.md` measures.

**3. Merchant-side return reduction.** The merchant *is* the party with the loss, so the
merchant is a coherent buyer even for traffic from external agents. This is narrower than
the withdrawn "audit someone else's agent" pitch: it is "cut your return rate on agentic
traffic, and get proof of fault when it was not you."

**4. Trust registry — the long game.** Merchants will eventually decide which agents may
transact on their platform. Whoever scores agents sits in the middle of that. Real
network position, needs scale first, cannot be sold today.

**5. Indemnity — last, and conditional.** Only coherent where agent and inventory sit in
one company (DR 0016 amendment), because there the loss is internal and genuinely theirs.
Keep it for that customer; stop leading with it everywhere else.

### Consequences

- **Geography opens up.** Sitting at the agent layer rather than the payment rail means
  nothing here is India-specific. UAP is a reason to be *ready* in India, not a
  constraint on where this sells. The regulatory posture also softens: an observability
  product touches no financial regulation at all.
- **DR 0012's badge-priced refund does not disappear**, but it stops being the wedge and
  becomes an upsell for customers who want it.
- **Benchmark targets widen** — browser agents and agentic browsers (Comet, Atlas,
  browser-use, Claude in Chrome) are a growing surface and belong in the corpus. They are
  also the channel where the merchant sees an ordinary session and cannot tell an agent
  from a human, which makes independent verification more valuable rather than less.

## Decision

**2026-09-05 — Option 2 adopted.** Build row 1 (human search on an integrated merchant)
as the measurement rig that produces Stage C's number. Sell rows 3 and 4 to agent
operators as capability-plus-indemnity.

Founder decision on the guarantee structure, same date:

- Receipts and the confirmation gate ship first. **No guarantee is quoted, priced, or
  described to any counterparty until Stage C produces a number with a confidence
  interval.**
- The guarantee, when it exists, is a **capped commercial indemnity to the agent
  operator**, who pays their own user. Approv never faces a consumer. This keeps it a
  B2B contractual warranty rather than a consumer-facing financial promise, which is the
  form most likely to attract IRDAI attention.
- Pricing is per-operator and re-measured, because adverse selection is real: the
  operators with the weakest agents want the badge most.

Mechanics of loss measurement move to **DR 0012**; the confirmation surface to **DR 0013**.

