# DR 0012 — Loss data, and what makes an indemnity priceable

- **Status:** OPEN — **not actionable until there is live transaction volume.** Nothing here
  blocks Stage B, Stage C or Stage D. Recorded now so it is not discovered late; revisit
  when a guarantee is about to be quoted
- **Raised:** 2026-09-05, by the founder
- **Touches:** §2.2, §2.6, §4.6, DR 0010, DR 0013
- **Blocks:** nothing in Stage B; blocks any quoted guarantee

---

## The question

> Do you have any ideas on how we'll collect our loss data accurately, verify it's
> correct, and use this to calculate how we underwrite?

DR 0010 closed on a capped B2B indemnity to the agent operator, priced off a measured
false-allow rate, and quoted only after Stage C. This DR specifies what has to be
measured and why the obvious way of measuring it does not work.

---

## 1. The exposure is narrower than it looks

**Approv only ever underwrites the `allow` path.**

Per §2.2, a user who is shown the comparison and confirms carries the outcome. So every
`confirm` is a claim not written, and the confirmation surface (DR 0013) is a **hedge,
not a cost centre**. This inverts the usual read of friction: each `confirm` is revenue
foregone on the merchant side and exposure avoided on the underwriting side, and those
have to be traded against each other deliberately rather than tuned for one alone.

It also means §2.3's *"unknown never authorises"* is what keeps the loss ratio finite.
That rule was justified on liability grounds; it turns out to be the solvency constraint
as well.

## 2. Ground truth: where an outcome label comes from

| Source | Latency | Bias | Value |
|---|---|---|---|
| **Reject at the confirmation screen** | immediate | low | **Highest.** A free labelled negative *before* money moves. Costs nothing and is not censored. |
| Return / refund with a reason code | 7–30 days | conflates buyer's remorse with mismatch | High, but merchant- or operator-held; needs a data-sharing term in the contract |
| Re-search of the same intent within 24h | immediate | weak | Free. Leading indicator only, never a label |
| Post-delivery survey | days | response bias | Low |

Only the first two are labels. The others are signals that a label may exist.

**The reason code on a return is doing heavy lifting and will not be clean.** "Did not
fit" is a mismatch; "changed my mind" is not; "not as described" could be either. The
mapping from merchant reason codes to *our* fault attribution has to be authored, and it
should be authored before any return data is ingested, for exactly the reason
`data/guideline.md` is written before any label exists.

## 3. The censoring problem, which decides whether any of this works

**Outcomes are observable only for transactions that were allowed.**

Every `refuse`, and every `confirm` the user declined, produces no outcome at all. We
never learn whether we were right to block it. Measured naively, the false-allow rate is
computed over a sample that was selected *by the very mechanism being evaluated*.

This is the **selective-labels** problem, and it is the same one consumer lending has
had for decades: measure defaults only among approved loans and the model looks
excellent and the number means nothing.

**The standard remedy is a random holdout.** Allow a small, capped, deliberately chosen
fraction of would-be-refused transactions and observe what happens to them. The losses
are not accidents; they are **the price of calibration data**, and they are the only way
the false-allow rate becomes identifiable rather than assumed.

Constraints on the holdout, which the founder sets:

- **A value cap** — only low-basket transactions enter the holdout.
- **A rate cap** — a fixed small percentage, budgeted in advance as a line item.
- **Never at the floor** — a `FLOOR_NOT_MET` request has nothing to compare, so
  releasing it produces a loss with no information. Holdout applies to `refuse` and
  `confirm`, not to preconditions.
- **Recorded as a holdout in the receipt**, so it is never mistaken for a decision the
  engine made on the merits.

Without this, any quoted price is a guess with a decimal point on it.

## 4. Verifying a claim

A claim is admissible only if it **names a specific attribute that the signed record
marked `satisfied` and that was wrong in fact.**

That is a narrow, checkable assertion, and the `ComparisonRecord` already contains
everything needed to adjudicate it: the request, the product snapshot at decision time,
the per-attribute comparison, the reason codes, and the version pins.

Coverage follows §2.2 exactly, which already reads as policy language:

| Record said | Reality | Covered? |
|---|---|---|
| `satisfied` | wrong | **yes** — this is the insured event |
| `violated` | — | n/a, we refused |
| `unstated` / any reason code | wrong | **no** — named perils only |
| holdout release | wrong | **no**, and recorded as a calibration cost, not a claim |

The last two rows are what make the exposure bounded. Nothing we declined to assert is
covered.

## 5. What has to be measured before a price exists

- **False-allow rate**, with a Wilson interval, per §4.6's full metadata set.
- **Attachment rate** — what fraction of transactions receive an `allow` at all.
- **Loss given false allow** — basket value distribution, net of what the ordinary
  merchant return path recovers. The indemnity is **second-loss** (DR 0013), so the
  recoverable portion is not exposure.
- **Claim rate** — not every false allow is noticed or claimed. This is a discount on
  expected payout and it is empirical, not assumable.
- **IBNR reserve** — returns report over 7–30 days, so at any moment losses have been
  incurred that have not been reported. A quote without a reserve is understated by
  construction.
- **Per-operator re-measurement** — DR 0010 flagged adverse selection. A single blended
  rate prices the good operators out and the bad ones in.

## Options for the holdout

**Option 1 — no holdout.** Measure only allowed transactions.
- *Against:* the rate is unidentifiable. Not viable for pricing, though fine for Stage C's
  gold-set number, which is measured against labels rather than outcomes.

**Option 2 — capped random holdout on `refuse` and declined `confirm`, value- and
rate-limited, recorded as such.**
- *For:* the only construction that makes the false-allow rate estimable.
- *Against:* deliberately permits some known-risky purchases; requires a budget and an
  explicit decision that this is acceptable.

**Option 3 — synthetic holdout via the offline harness only.**
- *For:* no real losses.
- *Against:* measures the engine against our own corpus, not against the world. Useful
  and much cheaper, but it does not remove the censoring in production.

## Recommendation

**Option 2, with Option 3 running alongside.** The harness gives a continuous cheap
signal; the production holdout is what makes it trustworthy. Both are needed and they
measure different things — which is the same two-corpora distinction §5 already draws.

---

## Amendment, 2026-09-06 — the badge is the unit of both revenue and exposure

Founder's commercial model, which is tighter than anything above and should be treated as
the working structure:

- **We are only ever liable for what we badged.** No badge, no promise, no payout. This is
  §2.2's named-perils rule expressed commercially, and it bounds exposure by construction.
- **On a disputed return, the hash-chained receipt is the adjudicator.** Fault is decided
  by a mapping written into the commercial contract, not negotiated per incident.
- **If it is our fault, the refund routes through our account.** The partner is not out of
  pocket. We are standing behind our own output, not covering their business risk.
- **Pricing is per badge**, discounted in volume. Revenue and exposure therefore move
  together.
- **A second revenue line that needs no guarantee:** cross-company QA. Measuring agents
  against a common corpus, including outside a partner's own catalogue, gives them an
  independent quality number and gives us the cross-company failure data that is the
  actual moat. Sells before Stage C produces a guarantee.

### Three things to get right

**1. The wording, not the label.** "Just a refund, not insurance" is the right *structure*
but the distinction that matters is what the contract says we are standing behind. *"We
refund when our own badge was wrong"* is a warranty on our own performance, like an SLA
credit. *"We cover your losses"* is risk transfer and reads as insurance. Same money, very
different regulatory posture. **Get this reviewed by a lawyer before it appears in a
contract — not by Claude.**

**2. Per-badge pricing makes the badge rate the whole business, in both directions.** A
badge that fires on 8% of traffic is perfectly safe and commercially worthless. Being paid
per badge means we are paid to take risk, so the pressure to badge more is structural
rather than occasional. The kill thresholds in DR 0014 must be set before this is priced,
not after.

**3. The fault mapping is the hard part and it is unchanged from §2 above.** Merchant
return reason codes are "did not fit" and "changed my mind"; neither maps cleanly to our
fault. That mapping must be authored **before** any return data is ingested.

## Decision

*(founder — set the holdout value cap and rate cap, then close)*
