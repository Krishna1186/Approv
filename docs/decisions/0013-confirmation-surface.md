# DR 0013 — The confirmation surface

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-05, by the founder
- **Touches:** §2.2, §2.7, §3 Stage E, DR 0004, DR 0012
- **Blocks:** Stage E; nothing earlier

---

## The founder's proposal

> Let the payment go through, if wrong we refund the user, the merchant gets the pay,
> but before this we send a verification popup notice to the user — a UPI payment
> confirmation page has payment details etc, so we have a custom invoice with the agent
> selection, verification reasoning and score, and a verify or reject option.

The instinct is right and the surface is the correct one. A UPI confirmation page is
already a moment where the user has stopped, is already reading, and expects to make a
decision. Adding the comparison there costs almost no new attention — which is rare, and
is worth more than a purpose-built screen elsewhere in the flow.

Four corrections.

---

## 1. It must sit before the debit

The proposal contains both orderings — *"let the payment go through"* and *"before this
we send a verification popup"* — and they are different products.

**Pre-debit.** The user sees the comparison and confirms. Per §2.2, they now carry the
outcome. Exposure transferred, nothing to refund, and the confirmation cost us one tap.

**Post-debit.** The user sees a notice about a purchase already made. No consent was
obtained because nothing was pending. We have given away the liability transfer for
free and are now refunding out of our own funds for a decision the user never got to
make. Per DR 0012 this converts a hedge into a pure cost.

The whole value of the surface is that it happens while the answer can still change.

## 2. Show attributes, not a score

The proposal says "verification reasoning and score." §2.1 forbids a score standing in
for a verdict, and there is a practical reason beyond the contract: **a score invites a
rubber stamp, a list invites reading.** A user shown `94%` learns nothing actionable and
clicks through. A user shown:

```
✓  white
✓  under ₹3,000
⚠  size not specified
```

reads three lines and notices the third. That is the same repair-signal argument that
DR 0010 makes for agents, aimed at a human instead.

It also matters for the record. A confirmation is only evidence of informed consent if
we can show *what the user was informed of*. "They were shown 94%" is not a defence.
"They were shown that size was unspecified and confirmed anyway" is.

**The confirmation screen's contents are therefore part of the signed record**, not
merely a rendering of it.

## 3. No dark patterns, and the timeout must not confirm

DR 0004 already requires this; here it becomes load-bearing rather than principled.

- No pre-selected default.
- No leading copy ("Looks great! Continue?").
- **A timeout must never auto-confirm.** §3 Stage E already says auto-proceed
  manufactures consent nobody gave.

If the surface nudges, the informed-consent claim fails, the liability transfer in §2.2
does not occur, and we have paid the full UX cost of a confirmation while retaining the
full exposure. **A nudged confirmation is strictly worse than no confirmation**, because
it costs conversion and buys nothing.

## 4. The refund is second-loss, not first

The proposal has Approv refunding the user directly. Two problems.

**Economically:** the ordinary merchant return path already recovers most of the value of
a wrong item. Refunding first-loss means subsidising ordinary returns that had nothing to
do with a verification error. Exposure is the *irrecoverable residue* after the normal
return completes — restocking fees, shipping, an item that cannot be returned — not the
basket value.

**Structurally:** per DR 0010, Approv pays the **agent operator** under a capped
contractual indemnity, and the operator makes their own user whole. Approv never faces a
consumer. A consumer-facing refund promise is the version most likely to be treated as a
financial product regardless of what it is called.

So on the screen the user sees a comparison and a choice. They do not see a guarantee
from Approv, because our counterparty is not them.

---

## What the surface produces beyond consent

Each rejection is a **free labelled negative, before money moves, uncensored** — the
single most valuable outcome label available per DR 0012. The surface is simultaneously
the consent mechanism, the liability transfer, and the primary ground-truth collector.

This is worth stating plainly because it changes how the `confirm` rate should be read.
A high `confirm` rate is a nuisance for conversion (§5) *and* a hedge against exposure
*and* the data source that makes pricing possible. Those pull in different directions and
the operating point is a business decision, not a tuning constant — which is exactly what
§2.6 says.

## Options

**Option 1 — post-debit notice with a refund promise**, as first described.
- *Against:* no consent, no liability transfer, first-loss exposure, consumer-facing
  promise. Strictly the weakest version.

**Option 2 — pre-debit gate on the UPI confirmation page: attribute list, neutral
presentation, no auto-confirm, contents included in the signed record; indemnity is
second-loss and paid to the operator.**
- *For:* transfers exposure, produces the best ground-truth labels, uses attention that
  is already being spent.
- *Against:* adds a step to a payment flow, which merchants and operators will resist;
  the conversion cost is real and must be measured, not assumed away.

**Option 3 — pre-debit gate shown only above a value threshold or only on `confirm`.**
- *For:* limits the conversion cost to where exposure is material.
- *Against:* the threshold is another parameter to defend, and low-value transactions are
  exactly where the DR 0012 holdout wants observations.

## Recommendation

**Option 2 now; revisit Option 3 once conversion cost is measured rather than guessed.**
Thresholds should come out of data, and there is no data yet.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
