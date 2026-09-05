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

