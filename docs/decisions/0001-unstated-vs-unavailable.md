# DR 0001 — Does the ternary need a fourth value?

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-03
- **Touches:** the decision path and the record. §4.8 requires this to close before code.
- **Blocks:** the `ComparisonRecord` schema, therefore every component

---

## The question

`CLAUDE.md` §2.1 fixes the per-attribute comparison as a ternary:

```
satisfied | violated | unstated
```

`unstated` is currently carrying two situations that are not the same situation.

**Situation A — the request was silent.** The shopper said "white shoes under 9k" and
never mentioned size. The product publishes `size: 9`. We know the product's size
perfectly well. What we do not have is a constraint to compare it against.

**Situation B — the product has no data.** The shopper said "size 9 white shoes" and
the listing publishes no size field, nothing parseable in the title, nothing in the
description. We have the constraint. What we do not have is an attribute.

Both currently record as `unstated`. Both route to `confirm` under §4.4, so **the
decision is identical either way**. That is not what is at stake.

## Why it matters even though the decision is the same

The record is the evidence (§2.7). §2.2 says the completeness vector is *"what makes
liability attributable."* These two situations attribute to different parties:

| Situation | Missing thing | Who carries the exposure | The sentence in a dispute |
|---|---|---|---|
| A | the constraint | the shopper | "You never specified a size." |
| B | the attribute | the merchant | "The listing never published a size." |

Collapsed into one field, the record cannot tell an adjudicator which sentence applies.
The field §2.2 calls load-bearing is load-bearing precisely because it assigns fault,
and in its current form it assigns fault to two different parties with one symbol.

There is a second-order cost. §2.8's preference record learns from Situation A —
every confirmed purchase where the shopper was silent teaches us a constraint they
hold but do not type. Situation B teaches us nothing about the shopper; it is a data
quality signal about the merchant. Mixed into one field, the preference record trains
on merchant catalogue gaps as if they were shopper preferences.

## Options

**Option 1 — keep the ternary as written.**
Three values. `unstated` means "no comparison was possible" for any reason.
- *For:* §2 says the record was designed in week 2 and should change as little as
  possible. Simplest schema. The decision genuinely does not change.
- *Against:* the liability claim in §2.2 is weaker than the pitch says it is, and a
  technical evaluator will find this in about four minutes.

**Option 2 — split into four values.**
```
satisfied | violated | unstated | unavailable
```
`unstated` = request silent. `unavailable` = product silent. Both route to `confirm`.
- *For:* the record now attributes correctly. Also gives a free merchant-facing
  metric — catalogue coverage per attribute — which is a plausible second product and
  a reason for a merchant to talk to us.
- *Against:* one more value in every schema, every test, every profile. Adds an
  extraction burden: the semantic stage must now distinguish "not present" from
  "not extracted", which is a real and non-trivial distinction.

**Option 3 — keep three values, add an orthogonal reason code.**
Ternary stays. A separate `reason` field on each comparison records *why* it was not
`satisfied`/`violated` — `REQUEST_SILENT`, `PRODUCT_SILENT`, `INCOMMENSURABLE`,
`LOW_PROVENANCE`, `EXTRACTION_FAILED`.
- *For:* §2.1's ternary survives untouched, so §2 does not need rewriting. The reason
  space is extensible without touching the decision logic — and there are already more
  than two reasons (dimensional incommensurability and provenance-gating both produce
  a non-comparison that is neither A nor B).
- *Against:* two fields where one might do. Risk that the reason code becomes the real
  field and the ternary becomes decoration.

## Recommendation

**Option 3.** The trigger is that Situations A and B are not the only two. A `250g`
request against a `250ml` product is a non-comparison for a third reason
(incommensurable dimensions), and an `INFERRED`-provenance attribute against a hard
constraint is a non-comparison for a fourth (evidence too weak to authorise). Option 2
solves the case in front of us and will need extending twice more. Option 3 sizes the
field to the actual shape of the problem, and leaves §2.1 as written.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
