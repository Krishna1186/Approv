# DR 0022: What an unread request does to the answer

Date: 2026-09-13. Closed the same day. Required by invariant 8: this is the decision path.

## The problem

An unread requirement had two options and both were bad.

- **Escalate** — fail the verification floor, confirm rather than authorise. Measured at
  **75.5% nuisance** on the v3 pack. No merchant runs that.
- **Ignore** — proceed as though the request had been read in full, and guarantee it.

The second is not merely a looser setting, it is a false statement: it sells a promise over
words nobody read. The first is not obviously better, because **an unread requirement is
our defect, not the merchant's.** Escalating makes the merchant pause their own checkout
over our extraction miss, which charges them for it.

Coverage created a third option that did not exist when that trade-off was measured — the
same third option that fixed hedges (DR 0020, property 6) and fixed narrowing.

## The decision

**`UnreadPolicy.WITHDRAW` is the default.** The sale proceeds, and the guarantee is
withdrawn from every finding on the record.

Withdrawal is at the **record** level, not the attribute level, and that is the whole
argument. Narrowing could be attributed to a constraint's own quote, so it withdraws one
attribute. A gap that belongs to no constraint has no attribute to scope to — the
requirement was never represented anywhere. What a guarantee promises is not "colour was
right", it is "this order was as asked", and a request we did not finish reading cannot
support that promise about any attribute, however cleanly the attributes we did read
compare.

`ESCALATE` and `IGNORE` remain selectable. `ESCALATE` is a legitimate merchant preference.
`IGNORE` is kept only so this table reproduces.

## Measured, three ways

v3 pack, heldout split, 46 cases, 1,244 pairs, v6 extraction, `unread` as DR 0021 defines
it. Nothing changes between columns but the policy.

| | ESCALATE | **WITHDRAW** | IGNORE |
|---|---:|---:|---:|
| False allow, of 1,142 | 4.3% [3.3, 5.6] | 7.3% [5.9, 8.9] | 7.3% [5.9, 8.9] |
| False refuse, of 102 | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] |
| Caught | 90.9% [89.1, 92.4] | 90.9% | 90.9% |
| Escalated (wrong product confirmed) | 4.8% [3.7, 6.2] | 1.8% [1.2, 2.8] | 1.8% |
| **Nuisance (right product confirmed)** | **58.8% [49.1, 67.9]** | **16.7% [10.7, 25.1]** | 16.7% |
| Clean allow | 41.2% [32.1, 50.9] | 83.3% [74.9, 89.3] | 83.3% |
| **Guaranteed false allow (a payout)** | **0** | **0** | **0** |
| Payout rate per authorisation | 0.0% [0.0, 4.1] of 91 | 0.0% [0.0, 2.2] of 168 | 0.0% [0.0, 2.2] of 168 |
| Coverage — guaranteed | 18.8% [17.7, 19.9] | 18.8% | 42.0% [40.6, 43.4] |
| Coverage — refused | 42.9% [41.5, 44.3] | 42.9% | 42.9% |
| Coverage — out of coverage | 38.3% [37.0, 39.7] | 38.3% | 15.1% [14.1, 16.2] |

**Guaranteed false allow did not rise. It is zero under all three.** That was the cost to
watch for and it did not appear on this corpus.

The table separates cleanly along two axes, which is what makes it decidable:

- ESCALATE and WITHDRAW have **identical coverage** and differ only in the decision.
  ESCALATE buys 3.0 pp less false allow for 42.1 pp more nuisance. All 49 of its false
  allows and all 83 of WITHDRAW's are out of coverage, so neither costs a payout — the
  3.0 pp is bought with a currency that has no measured price.
- WITHDRAW and IGNORE have **identical decisions** and differ only in what is promised.
  IGNORE claims 42.0% of findings as guaranteed against WITHDRAW's 18.8%. That 23.2 pp is
  the promise IGNORE makes over words nobody read.

## What this corpus cannot show, and why

**WITHDRAW and IGNORE produce the same payout count here: zero.** The case for WITHDRAW
therefore rests on the coverage claim being true, not on a measured payout difference, and
saying otherwise would overstate it.

The reason is structural rather than a shortage of data. The answer key is derived from
published merchant fields, so it is bounded by the same schema the comparison is. Text the
schema cannot express — *"delivery speed doesn't matter"*, *"whatever's easiest to return"*
— is exactly the text that goes unread, and it can never make a product wrong *by the
key's own definition*. A corpus keyed on the schema cannot price a promise about what the
schema does not contain. Measuring that needs return outcomes, not an answer key.

## The marker fix, which this decision forced

Under a record-level withdrawal a single bad gap note costs the whole record's guarantee,
so the gap detector's false positives stopped being cosmetic.

`coverage_gap` names any request word carried by no constraint value and no note — which
includes the shopper's own hedge words, because "preferably" and "or similar" carry no
value and so reach no constraint. **8 of the 28 v3 cases carrying an unread note were
hedge families and nothing else.** Those records would have surrendered their guarantee
because the shopper said *"preferably"*, which is the opposite of what a hedge means: the
word was read, by `request_layer`, and it is why the finding is SOFT.

`criticality.unread_requirements` subtracts layer-1 marker words before deciding a gap
names anything unread, reading them off the **quotes** rather than the note because the
residual is a bag of words with stopwords stripped and "or similar" arrives as "similar".
Its effect, holding the policy fixed:

| Holding policy = ESCALATE | before | after |
|---|---:|---:|
| Nuisance | 75.5% [66.3, 82.8] | 58.8% [49.1, 67.9] |
| False allow | 0.1% [0.0, 0.5] | 4.3% [3.3, 5.6] |
| Coverage — guaranteed | 12.1% [11.2, 13.0] | 18.8% [17.7, 19.9] |

Under WITHDRAW it moves coverage (12.1% → 18.8% guaranteed) and no decision at all.

The filter runs in `build_record`, so what the record **stores** in `unread` and what the
decision **acts on** are the same set. Storing a hedge as an unread requirement would put
in the dispute artifact a statement that we failed to read something we read.

## The number this exposes, and it is the real finding

**28 of 46 held-out requests (61%) carry a note saying part of the request went unread; 20
of 46 (43%) still do after the marker fix.** So under WITHDRAW roughly two in five orders
are authorised with no guarantee at all, and guaranteed findings fall from 42.0% to 18.8%.

That is not a defect in this decision — it is this decision making an existing fact
visible. Under IGNORE those guarantees were being claimed anyway. What has changed is that
the record now says which ones we can stand behind.

It does bound the product: the guarantee is what a merchant pays for, and on this corpus
we could sell it on well under half of traffic. Two ways out, neither decided here and both
measurable: read more of the request (extraction), or express more of it (schema). The
second is the larger one — most surviving gaps are requirements this category has no
attribute for, not requirements the model missed.

## What is not decided here

The strict/lenient trade in `receipts/record.py`'s docstring was measured on the fresh
corpus under the pre-DR-0021 definition of `unread` and has not been re-run. It stands as
measured rather than as corrected.

DR 0004's failure semantics are separate and still open: a verification that did not
complete is a different event from one that completed and found a gap, and nothing here
touches it.
