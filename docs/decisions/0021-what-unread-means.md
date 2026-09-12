# DR 0021: What `unread` means

Date: 2026-09-12. Closed the same day. Required by invariant 8: `unread` feeds the
verification floor, and the floor is the decision path.

## The problem

Two definitions were live at once, both producing the field that `floor_is_met` reads:

- `harness/intent.as_extractor` filtered to `dropped_requirement(note)` — notes meaning a
  *checkable requirement went unchecked*.
- `scripts/score_gate.py` and `harness/shopping.py` passed **every** interpretation note.

So a number produced by one did not mean what a number produced by the other said it did.
That is the exact failure this repo's discipline exists to prevent, and it was introduced
by accident rather than decided.

The reason they could diverge is structural: `dropped_requirement` lived in
`harness/intent.py`, and `harness/shopping.py` cannot import that module without a cycle.
A producer that cannot reach the definition invents one.

## Measured, both ways

v3 pack, heldout split, 46 cases, 1,244 pairs, v6 extraction. Nothing changed but the
definition.

| Floor = strict | `all` notes | `dropped` only |
|---|---:|---:|
| False allow, of 1,142 | 0.1% [0.0, 0.5] | 0.1% [0.0, 0.5] |
| False refuse, of 102 | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] |
| Caught | 90.9% [89.1, 92.4] | 90.9% [89.1, 92.4] |
| Escalated (wrong product confirmed) | 9.0% [7.5, 10.8] | 9.0% [7.5, 10.8] |
| **Nuisance (right product confirmed)** | **84.3% [76.0, 90.1]** | **75.5% [66.3, 82.8]** |
| Clean allow | 15.7% [9.9, 24.0] | 24.5% [17.2, 33.7] |
| Guaranteed false allow (a payout) | 0 | 0 |
| Coverage: guaranteed / refused / out | 42.0 / 42.9 / 15.1% | 42.0 / 42.9 / 15.1% |

Under the lenient floor the two are **identical in every cell**, which is the expected
result and worth stating: `strict_unread=False` does not read `unread` at all, so the
definition can only bite where the floor is enforced.

Coverage is identical under both because `narrowed_attributes` keys on the coverage-gap
prefix, which is a dropped-requirement prefix under either reading.

## Decision

**`unread` is `dropped_requirement(note)`, and nothing else.** The narrower definition
wins outright: it costs **8.8 pp of nuisance** and buys nothing back — false allow, false
refuse, caught, escalated, guaranteed false allow and every coverage figure are unmoved to
the last decimal.

This is not a trade-off being taken, it is a defect being removed. The notes `all` counted
that `dropped` does not, on the six cases that separated them:

- `women's`, `casual`, `kid's shoes`, `double-pleated` — the model's free-text `unverified`
  list, naming a product property this schema has no attribute for. Unverifiable in
  principle against this catalogue, not a gap in the reading. True of 35 of 46 requests on
  the 10 September pack, which is why a floor keyed on it fires on almost everything.
- `My last order took forever to arrive, hopefully this one's faster.` ·
  `Delivery speed doesn't matter, I'm not in a rush` — shipping chatter. Never a
  requirement, so it cannot have gone unchecked.
- **`Superseded, discarded: Black (color)`** — the case that settles it. The extractor read
  the correction *perfectly* and logged what the shopper discarded. Under `all`, a shopper
  who changes their mind gets their order escalated for it, and the better the extractor
  reports what it did, the worse the gate behaves. A floor that punishes good extraction is
  not a floor.

## What changed

- The note vocabulary — `DESCRIPTOR_PREFIX`, `COVERAGE_GAP_PREFIX`, `DUPLICATE_PREFIX`,
  `DROPPED_REQUIREMENT_PREFIXES`, `dropped_requirement` — moved to `approv/types/core.py`,
  which is the one module every layer may import. The cycle that forced the divergence is
  gone rather than worked around.
- All three producers now filter identically: `harness/shopping.py` (the `gate` call site),
  `harness/intent.as_extractor` (intake path (c)), `scripts/score_gate.py`.
- `score_gate --unread {dropped,all}` keeps both measurable, defaulting to the decision.
  The losing definition stays runnable so this table can be reproduced rather than trusted.
- `tests/test_receipts.py` pins the four separating cases.

## What this does not settle

The strict/lenient floor choice itself is untouched and stays a business parameter (§2.6).
Both operating points are now measured under one definition rather than two, which is the
only thing that was wrong with them.

Nuisance at 75.5% under the strict floor is still high enough that no merchant would run
it, and DR 0021 does not fix that — it only removes the part of it that was measuring the
extractor's honesty instead of the request's completeness.
