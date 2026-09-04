# DR 0004 — Latency budget, and which way we fail when it runs out

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-03, by the founder
- **Touches:** all three call sites in §2.5, the record, §6
- **Blocks:** nothing yet, but it constrains every operator's implementation

---

## The founder's position

> The marketplace won't wait a millisecond longer for our check, hence we need to
> provide the results on the fly before the actual marketplace loads the product. If
> the marketplace takes 500 ms to load, we need to keep a threshold below which our
> search is ready. If that exceeds the result display time of the marketplace, we abort
> the verification and don't give false negatives, just let the product recommendations
> by the marketplace be as it is.

Correct, and it is the constraint most verification layers discover only after a
merchant removes them. §5 already requires cost and latency at p95 to be measured, on
the grounds that *"a check that adds two seconds to a debit path is not deployable."*
This is that requirement stated as a runtime policy rather than a metric.

---

## Where it needs qualifying

**"Abort and let the marketplace results stand" is correct for one call site and a
complete product bypass at another.**

§2.5 names three call sites, and they do not share a failure direction:

| Call site | On timeout | Why |
|---|---|---|
| **Mark** — badge N search results | **Fail open.** Render unbadged. | We add nothing and remove nothing. The shopper browses exactly as they would have without us. Genuinely harmless. |
| **Verify** — check one selected product | **Fail closed → `confirm`.** | Nothing irreversible has happened yet, and a confirmation costs a tap. |
| **Gate** — before the debit fires | **Fail closed → `confirm`. Never open.** | Failing open means the debit fires unverified. That is the one event the entire product exists to prevent. |

### The attack this closes

If the gate fails open on timeout, then **anyone who can add latency can disable the
gate.** Slow the service by 300 ms — via load, a slow catalogue fetch, an oversized
product payload, a deliberately expensive query — and verification silently stops
happening while every surface still reports itself as protected.

That is a total bypass, cheap to execute, and it produces no error anyone sees. It
belongs in §6 under *timing attacks on the confirmation window*, which currently only
contemplates running the clock toward the confirmation timeout, not toward the
verification timeout. §6 needs the second case added.

### Aborts are a recorded outcome, not a silent skip

§3 Stage D already requires refusals to be recorded as first-class. A timeout is the
same class of event: it is a comparison that did not happen, on a purchase that did.
An unrecorded abort is indistinguishable from a successful `allow` in the receipt
chain, which makes the chain useless for exactly the dispute it exists to survive.

So every abort writes a record carrying the call site, the elapsed budget, and which
stage was still outstanding. The abort rate then becomes a headline operational metric
alongside the §5 behaviour distribution — if the gate aborts on 20% of traffic, the
product does not work, and no accuracy number will reveal that.

### The tension with clarification

Targeted clarification questions and a sub-500 ms budget are in direct conflict on the
same request. They cannot both be honoured. The likely resolution is that clarification
is asynchronous relative to the check — the check completes, returns `confirm` with the
specific unresolved attribute named, and the surface decides whether to ask — but that
is a design question this DR raises rather than settles.

---

## Options

**Option 1 — one global budget, fail open everywhere.**
- *For:* simplest; never slows a merchant down; never blocks a sale.
- *Against:* the gate becomes bypassable by anyone who can add latency. Not viable.

**Option 2 — per-call-site budget, per-call-site failure direction.**
Mark fails open. Verify and gate fail closed to `confirm`. Every abort is recorded.
- *For:* preserves the founder's requirement exactly where it applies, and refuses it
  where it would void the product.
- *Against:* three budgets and three policies to keep straight; the gate can be made to
  ask for confirmation more often under load, which is a nuisance vector rather than a
  bypass — an acceptable trade, but a real one.

**Option 3 — Option 2, plus a precomputed-verdict cache on the mark path.**
Popular query/product pairs verified ahead of time; the live path is a cache lookup.
- *For:* makes the mark budget trivially achievable at scale.
- *Against:* a cached verdict is a verdict computed against a *previous* product
  snapshot, and §2's record is explicit that the snapshot is taken **at decision time**.
  Cache invalidation on catalogue edits becomes a correctness requirement, and stale
  entries are exactly the snapshot/decision-time skew already listed in §6. Defer.

## Recommendation

**Option 2 now, Option 3 revisited only after Stage C produces a number.** Option 3 is
a scaling answer to a problem we do not yet have, and it collides with the snapshot
guarantee that makes the receipt meaningful.

Budgets themselves (the actual millisecond figures) should not be guessed here. They
come from a measurement against a real marketplace page load, which is Stage E work.


---

## Amendment 2026-09-04 — resolving the clarification/latency conflict

The original text flagged that targeted clarification and a sub-500 ms budget cannot
both be honoured on the same request, and left it open. Four mechanisms resolve it, in
descending order of how much they buy.

### 1. `mark` never asks. It just does not badge.

The tight budget applies to search-results rendering. But `mark`'s output is a badge,
and **the absence of a badge is a perfectly good output.** Uncertain → no badge → the
shopper browses as normal. No question, no latency, no false negative.

Clarification is therefore only ever needed at `verify` and `gate` — where the shopper
has already clicked and *stopped*, the page is already in a transition, and the budget
is an order of magnitude looser. The conflict was an artefact of applying one budget to
three call sites.

### 2. Precompute every branch; ask only when branches disagree.

When entity linking returns 2–3 candidate nodes, or a locale lexicon offers a broadened
reading (DR 0006), **evaluate all of them.** Comparison is deterministic and cheap;
three subsumption walks cost microseconds against a model call.

- All branches agree → answer, no clarification. **Ambiguity that does not change the
  outcome is not ambiguity worth surfacing.**
- Branches disagree → *now* ask, and the question is precise because we know exactly
  which distinction flips the verdict.

This removes the large majority of would-be clarifications. Most ambiguity is
irrelevant to the answer, and the naive design asks about all of it.

### 3. Ask once per shopper, not once per purchase.

The `HARD` unstated attributes in apparel — size, width — are **stable facts about a
person**, not about a purchase. Asked once and retained via §2.8, the clarification
burden decays toward zero after the first transaction, which is the same curve §2.8
already promises for the `unstated` set. Purchase five needs no questions.

### 4. For the merchant: get out of the render path entirely.

Merchant top-N search queries follow a power law and are stable over days.
`mark` verdicts for them can be **precomputed offline** and served from cache. The live
path becomes a lookup, well under a millisecond, with zero integration into their
latency-critical code. Cache miss → no badge → fail open. This is exactly what §3's
merchant plugin is for, and it is the honest answer to "how do we avoid hampering their
existing process": we are mostly not in it.

This revises Option 3 above, which was deferred over stale-snapshot risk. Keying the
cache on `(query, product_id, snapshot_hash, taxonomy_version, lexicon_version,
model_version, prompt_version)` resolves that: if the merchant edits the product, the
snapshot hash changes, the key misses, and we fail open rather than serving a verdict
computed against a listing that no longer exists. The §2 snapshot guarantee is
preserved because a cache hit *proves* the snapshot is unchanged.

**Option 3 is therefore upgraded from "defer" to "recommended for `mark`, still
forbidden for `gate`"** — the gate must always compute live, because at the gate the
thing being authorised is this debit, now.

### The actual millisecond figures

Still to be measured, as the founder said, against real marketplace page loads rather
than guessed. Stage E work. What this amendment fixes is the *shape* of the policy, not
its constants.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
