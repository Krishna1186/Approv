# DR 0007 — The verification floor: minimum data per category

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-04, by the founder
- **Touches:** §2.1, §2.2, the record, the criticality profiles, the merchant pitch
- **Blocks:** the `CategoryProfile` type; closes out DR 0001

---

## The founder's position

> Some basic data about the purchase is NECESSARY, below this it can't be verified.
> Shoe size for shoes is one such criterion, maybe brand or laces length isn't. So
> effectively we must EXPECT certain minimum data for a certain category, and without
> that, uncertain means the minimum isn't fulfilled. The tag of not having data from
> the vendor is not the same, it's a different heading, so don't combine.

This introduces a concept the design did not have, and it is not a variant of
`unstated`. It is a **precondition on whether verification is possible at all.**

---

## What is new here

DR 0001 treated every missing field as one of several kinds of *non-comparison*, all
discovered while comparing. The founder's point is that some fields are not optional
inputs at all: **without them there is no verification to run.**

For footwear, `size` is not an attribute that happens to be missing. It is a required
input. A comparison that cannot see a size is not a comparison that came out uncertain
— it is a comparison that never had enough to start.

Three distinct states, which the founder is explicit must not be merged:

| State | Meaning | Whose gap |
|---|---|---|
| `FLOOR_NOT_MET` | a category-required field is absent from the request | the requester's |
| `PRODUCT_SILENT` | the listing does not publish a field we needed | the merchant's |
| `UNSTATED` | request was silent on an optional field; comparison ran fine | nobody's |

## Why this is structurally better than treating it as another reason code

**1. It is checkable before any work happens.** The floor is a set membership test
against the category profile. It runs in microseconds, before entity linking, before
any model call, before any DAG walk. A request that cannot clear the floor is known to
be unverifiable *immediately* — which matters directly for the DR 0004 budget, because
the cheapest possible outcome is discovering early that there is nothing to compute.

**2. It makes the decision basis explicit, which is the founder's stated requirement.**

> We need an extraneous validator of harness reasoning and intent matching, we need all
> the decisions made, based on what, to be explicit. This becomes the key failure data
> or success and the defence for the merchant.

`FLOOR_NOT_MET` states *which* required field was absent and *which category profile
required it*. That is a complete, self-contained explanation of a non-decision, and it
is the same artifact in both directions: the shopper sees "we need your size", the
merchant sees "this request could not be verified because size was absent."

**3. It produces a merchant-facing metric that is a product on its own.** Aggregate
`PRODUCT_SILENT` across a catalogue and you can tell a merchant: *"41% of your footwear
listings publish no width, so 41% of width-sensitive traffic is unverifiable on your
store."* That is a coverage report they cannot generate themselves, derived as a
by-product of verification, and it is a reason for a merchant to take a meeting before
we have an accuracy number.

## The floor is per category, and it is authored

`FLOOR(footwear) = {size, category}`. `FLOOR(grocery) = {quantity, variant}`.
`FLOOR(electronics) = {model_or_variant, region}`.

These are hand-authored judgements about what a purchase in this category cannot be
correct without. They sit in the same `CategoryProfile` as the HARD / BOUND / SOFT /
COSMETIC criticality classes, and they are a strict subset of HARD: every floor field
is critical, but not every critical field is a floor field.

**The floor is a claim about the world, not about our capability**, so it belongs in
`data/guideline.md` before labelling. An annotator shown *(request: "white shoes under
9k", product: a size-9 white sneaker at ₹8,499)* must know whether the gold label is
`satisfied` or `floor not met`. Without that written down, two annotators will split
and kappa will not say why.

## Relationship to DR 0001

This **closes DR 0001 in favour of Option 3** (reason codes rather than a fourth
ternary value), and adds a term that Option 3's list did not have:

```
REASON ::= FLOOR_NOT_MET        category profile required a field the request lacks
         | PRODUCT_SILENT       listing does not publish a field we needed
         | REQUEST_SILENT       request was silent on an optional field
         | INCOMMENSURABLE      dimensions do not compare (250g vs 250ml)
         | LOW_PROVENANCE       evidence too weak to authorise (DR 0005)
         | UNRESOLVED_TERM      entity linking produced no node (DR 0003)
         | BRANCH_DISAGREEMENT  candidate readings disagree (DR 0006)
```

Every one of these routes to `confirm` under §4.4, and every one of them is a
*different sentence* in a dispute. That is the founder's requirement — the decision and
its basis are recorded separately, and the basis is what gets defended.

## Options

**Option 1 — treat the floor as another reason code, checked during comparison.**
- *For:* no new concept; one code path.
- *Against:* wastes the whole pipeline discovering something knowable up front, and
  buries a precondition inside a result.

**Option 2 — the floor is a precondition, evaluated before the pipeline runs, with its
own outcome state and its own metric.**
- *For:* cheapest possible failure; explicit basis; generates the merchant coverage
  report; the floor becomes a reviewable per-category artifact.
- *Against:* two places where a request can terminate instead of one; the profile
  becomes a required input to every call.

## Recommendation

**Option 2**, as the founder described it. The floor is a different kind of thing from
a comparison outcome and collapsing it into one loses exactly the explicitness that
makes the record a defence.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
