# DR 0015 — Breaking the corpus deadlock

- **Status:** OPEN — founder decides which route
- **Raised:** 2026-09-05, by the founder
- **Touches:** §5, Stage B, DR 0007, DR 0010
- **Blocks:** Stage B — this is the critical path

---

## The founder's statement of the problem

> It's like I need a verified dataset, but I can't get access to a real vendor's data till
> I pilot with them, and for that I need the MVP with a decently good success rate.

```
gold set ──needs──► vendor catalogue ──needs──► pilot ──needs──► working MVP ──needs──► gold set
```

The loop is real **only under two assumptions**, and neither has to hold:

1. that the catalogue must come from a *large marketplace*, and
2. that the *first thing shipped* must be the payment gate.

Drop either and the cycle opens.

---

## Route A — the gold set does not need a vendor at all

The gold set is **300–500 pairs**. That is not a dataset; it is a few days of manual work.

Recording facts about publicly visible listings — *this shoe is white, size 9, ₹8,499* — is
categorically different from bulk-extracting a database. Facts are not copyrightable, the
volume is trivial, there is no automated collection, and **nothing is ever redistributed:
we publish the number, never the corpus.** That last point is the one that matters and it
removes most of the exposure, because the risk in dataset work is almost entirely in
redistribution.

- *For:* available immediately, no counterparty, no negotiation, fully under §5 provided
  the collection is manual and nothing is republished.
- *Against:* slow and boring; roughly 3–5 days of the founder's time; and it must be
  genuinely manual — the moment it is automated it becomes scraping and the argument fails.
- **Not legal advice.** If any published claim rests on this corpus, get the position
  reviewed before publishing.

## Route B — the first partner is small, not large

The deadlock assumes Myntra or Flipkart. It dissolves against a **single D2C footwear brand
on Shopify** — there are thousands in India. They have 200–2,000 SKUs, which is more than
enough, no legal department, and a founder who will answer a DM.

Some storefronts also expose a public product feed by design (Shopify's `/products.json`,
Google Merchant Center feeds). That is published deliberately, not scraped from behind
authentication — but each store's own terms still govern, and §5 requires checking rather
than assuming.

- *For:* a real catalogue with real attribute metadata and a real permission trail; a named
  partner is worth more in a pitch than a public dataset.
- *Against:* one brand's catalogue is narrow — a single brand's colour vocabulary and size
  conventions may not generalise, and the gold set inherits that bias. Must be recorded as
  a limitation on the Stage C number.

## Route C — invert the ask, so no MVP is required

**The strongest option, and it comes free from DR 0007.**

The verification floor produces a **catalogue coverage report** — *"41% of your footwear
listings publish no width, so 41% of width-sensitive traffic cannot be verified on your
store"* — and that report is computable **from their catalogue alone.** No verification
engine. No accuracy number. No pilot.

So the ask stops being *"let me test my unproven product on your customers"* and becomes:

> *"Send me your product feed and I will tell you where your listings are incomplete."*

That is a favour with a deliverable, not a request for trust. It is useful to them
independently of anything we build, it costs them one CSV, and **it hands us the corpus.**

- *For:* breaks the loop at its weakest link; genuinely valuable to the merchant; requires
  only the floor definition and a counting script; converts a cold ask into a warm one.
- *Against:* the report must actually be good, or it burns the relationship; and it commits
  us to defining `FLOOR(footwear)` before we have labelled anything — which `guideline.md`
  Q2 requires anyway.

## Route D — ship the thing that cannot fail

Per DR 0004, `mark` **fails open**: when uncertain it renders no badge. Worst case, nothing
happens and the page is exactly as it was.

So a merchant can deploy `mark` at genuinely zero risk, before any accuracy number exists.
Accuracy determines whether it is *valuable*, not whether it is *safe*. Deploy first,
measure in production, improve — the gate comes much later.

- *For:* removes "prove it works first" from the pilot conversation entirely.
- *Against:* a badge that rarely appears is unimpressive, so this needs Route A or C to have
  produced something decent first. It opens the door; it does not walk through it.

## What does **not** work

- **Agent-search-sourced products for the gold set** (founder's earlier suggestion).
  Snippets paraphrase attributes, and a wrong attribute produces a wrong gold label, which
  is worse than no gold set. Also biases the corpus toward *good* matches when §3 requires
  it built around near-misses, and contaminates any later benchmark of that same agent.
  **Acceptable for the large unlabelled corpus (Stage D)**, where no ground truth is needed.
- **Non-commercial research datasets** (ABO, UT-Zappos50K, DeepFashion). CC BY-NC forbids
  the commercial use this number is for.
- **Kaggle marketplace dumps.** Scrape-derived; republication does not launder the upstream
  terms.

## Recommendation

**Route C to get a catalogue, Route A in parallel so nothing is blocked on a reply.**

Route A guarantees Stage B starts this week regardless of whether anyone answers. Route C
is the one that scales and produces a named partner, and it is available *now* because the
coverage report needs only `FLOOR(footwear)` and a counting script — no engine, no number,
no pilot. Route D is how the first deployment happens once there is something worth
deploying.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
