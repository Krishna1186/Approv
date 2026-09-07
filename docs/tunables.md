# Tunables

Every number in this system that was **chosen rather than measured**.

This file exists because a made-up constant that lives only in code becomes load-bearing
without anyone noticing. Listing them in one place means we always know exactly how much
of the engine's behaviour is currently a guess.

**Rules for this file**

1. A constant on the decision path that is not in this table is a bug.
2. Every row names how it will be calibrated. "We'll tune it later" is not a method.
3. Changing a value here changes published numbers, so §4.6 applies: any accuracy figure
   carries the version of this file it was produced under.
4. Nothing here is calibrated yet. **Every value below is a placeholder chosen by
   argument, not by data.** Until §4.6 can be satisfied they are a *ranking*, never a
   probability, and must not be described as one to anyone outside.

Last reviewed: 2026-09-07 · Calibration status: **none — no real data has been run**

---

## 1. Provenance ceilings

Where: `approv/algebra/quantity.py` → `_CEILING_BY_CERTAINTY`

The highest confidence a value is allowed, given where it was read from. This is what
stops planted or marketing text from clearing a hard constraint, so it is the most
safety-relevant table in the system.

| Certainty | Value | Why this number | How we calibrate it |
|---|---|---|---|
| `EXACT` | 1.0 | A dedicated structured field is unambiguous by construction | Should stay 1.0 unless we find feeds where structured fields are routinely wrong |
| `PARSED` | 0.9 | Read from a title or spec table — right nearly always, occasionally truncated or ambiguous | Per-attribute extraction precision on the gold set |
| `INFERRED` | 0.6 | Read from prose. Must sit **below** the allow threshold for a HARD attribute or the injection defence does not hold | Same, but the floor is a design constraint not a measurement: it can never rise above the HARD allow threshold |

**Invariant:** `INFERRED` ceiling < HARD allow threshold. Violating this silently removes
the injection defence. Worth an explicit test once the threshold exists.

## 2. Comparison tolerance

Where: `approv/types/core.py` → `AttributeSpec.tolerance`

| Name | Default | Why this number | How we calibrate it |
|---|---|---|---|
| Relative tolerance | `0.005` (0.5%) | Feeds publish 4.99 kg for a 5 kg pack; exact equality calls that a violation. 0.5% absorbs rounding and still rejects 4.5 vs 5.0 (10% off) | Measure the distribution of \|claimed − published\| on real catalogue data. The right value sits in the gap between the rounding cluster near zero and the genuine-mismatch cluster |

Set **per attribute**, and the default is deliberately loose because early baskets are
small. Attributes where precision is the product (dosage, purity, anything sold by exact
weight) must override it. Founder's call, 2026-09-07: a wide-ish default is acceptable
while transaction values are low.

## 3. Not yet chosen, and blocking

These do not exist in code yet. They are listed so they are not invented quietly later.

| Name | Where it will live | Blocks | Notes |
|---|---|---|---|
| `allow` threshold, per criticality | `evaluator/` | any verdict at all | Founder's, by hand (§4.2). HARD will need a high bar; COSMETIC may not gate anything |
| `confirm` band | `evaluator/` | same | The gap between allow and refuse. Its width *is* the confirm rate |
| Maximum acceptable confirm rate | DR 0014 | Stage C measurement | §5: "if confirm fires on 60% of traffic we have a nuisance, not a product." Must be fixed **before** measuring |
| Maximum acceptable false-allow rate | DR 0014 | any guarantee | The number the indemnity is priced off |
| Minimum badge rate | DR 0014 | commercial viability | A badge that fires on 8% of traffic is safe and worthless. Per-badge pricing (DR 0012) makes this a revenue floor as well as a product one |
| Holdout value cap and rate cap | DR 0012 | calibration of the above | Only relevant once there is live volume |
| Latency budget p95 | DR 0004 | deployment | §5: a check adding two seconds to a debit path is not deployable |

## 4. Fixed by definition, not tunable

Listed so nobody "tunes" them by mistake.

- **Unit conversion factors** (`_UNITS`). International definitions. 1 lb *is* 453.59237 g.
  Adding a unit is fine; changing a factor is a bug.
- **`unknown` never authorises** (§2.3). A rule, not a parameter.
- **Advice may only downgrade** (DR 0016 §5). A rule, not a parameter.
