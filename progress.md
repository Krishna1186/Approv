# progress.md

What is measured, what is built, what is not. Rewritten 10 September 2026.

## The number

**The gate, scored as a classifier.** 1,057 (request, product) pairs over 34 held-out
requests, fresh corpus, gpt-oss-20b extraction, no model call at evaluation time.
Requirements come from the extractor; the answer key is the generator's spec applied to
published merchant fields by code importing nothing from `approv.algebra`.

| | rate | 95% CI |
|---|---:|---|
| **False allow** — wrong product authorised | **0.0%** | [0.0, 0.4] |
| **False refuse** — right product blocked | **0.0%** | [0.0, 4.1] |
| Caught — wrong product refused | 96.5% | [95.1, 97.5] |
| Escalated — wrong product confirmed | 3.3% | [2.4, 4.6] |
| Nuisance — right product confirmed | 3.3% | [1.1, 9.2] |

False allow on near-misses (694 pairs, same product different variant — the failure this
exists for): **0.0%** [0.0, 0.6].

Reproduce: `python scripts/score_gate.py --pack data/cache/shopping-study/shopper-fresh.json
--constraints output/fresh-2026-09-10/constraints-recovered.json`

**`strict_unread` is a business parameter, not a constant** (§2.6). At `True` false allow
is 0.0% and nuisance 41.8%; at `False` both sit as above. Recovery removed the reason to
pay for strict.

## Extraction

Every gate number is conditional on this. 35 held-out cases, 148 stated requirements,
scored against the generator's spec (code) by the extractor's output (model) — independent
paths, no model call at evaluation time.

| | rate | 95% CI |
|---|---:|---|
| Recall — stated and recorded | 97.3% | [93.3, 98.9] |
| Fidelity — recorded with the stated value | 97.1% | [92.7, 98.9] |
| End to end | 94.3% | [89.1, 97.1] |
| **Invented** — recorded, never stated | **0** | — |

`python scripts/score_extraction.py --pack PACK --constraints WORK/constraints-recovered.json`

Four wrong values, four misses, one case each: `"size 6"` where the spec said `6` (the
model echoed the attribute name into the value); `"L || 2"` narrowed to `"L"`; a mojibake
colour split across colour and product_type; one whole case whose extraction failed.

## Retrieval

Agent's own text search reaches the answer on **43.8%** of fillable held-out cases (14/32).
Filtering the catalogue's published fields reaches **90.6%** (29/32); either, 96.9%.

Approv does not retrieve — it states the predicate and the catalogue executes it. The
filter withholds entirely when the request carries an unverified detail: measured cost 3 of
17 recoveries, measured benefit the only wrong fill removed.

## What is built

`types/` vocabulary · `algebra/` five operators + feedback renderer · `evaluator/` the
decision function, import boundary asserted by test · `receipts/` record assembly, Ed25519
signing, hash chain · `harness/` extraction, catalogue filter, sessions, storefront ·
`scripts/` study drivers, gate scoring, standalone verifier.

Three call sites: `mark`, `verify`, `gate`. Scored separately, never averaged (invariant 7).
Only `gate` has been scored for accuracy. A stranger verifies a receipt with a public key
and none of this code: `scripts/verify_receipt.py`, asserted by a test that parses its
imports.

**262 tests pass.** Software tests are not accuracy results.

On disk: 33,485 Shopify variants from 19 brands; 599 Open Food Facts India records; Amazon
ESCI examples and products; WebShop instructions and attribute map.

## Also measured

| Finding | Number |
|---|---|
| Detection signal on Amazon prose listings | +11.1 pp, CI [0.8, 23.2] |
| Size stated in description but never the title | 26.9% of 132,832 listings |
| Real queries carrying a checkable constraint | 25.6% of 97,346 US ESCI queries |
| Cost of a check | ~25 tokens per report |

## Never measured

Whether published merchant data is true. Underwriting, loss rates, pricing. Injection resistance against a hostile corpus. Any
surface other than a JSON API agent. `mark` and `verify` accuracy.

## Retracted — do not reuse

| Claim | Why it fell |
|---|---|
| Baseline 96.3%, and 38.5% | 94% of requests quoted the exact catalogue title. It measured string matching. |
| "Approv improves accuracy +24.6 pp" | A content-free retry beat it by 26 points on the same cases. |
| "Presentation causes the error rate" | The messier layout scored better, 100% vs 95%. |
| "Model choice moves accuracy 58 points" | Confounded; two families later scored identically. |
| **"+0.0 pp against control" as evidence about the product** | It measured persuasion, not the gate. See below. |
| Approv's constraints improve retrieval | Tested: 41.3% against the agent's own 58.7%. As search terms they are noise. |

## Why three studies returned +0.0 pp

They scored the wrong mechanism. The forked driver shows an agent a report and asks whether
its second answer changes — persuasion, bounded by model stubbornness and by n=46 with a
noise floor near ±8 pp. **It never calls `decide()`.** The product claim is a deterministic
classifier that refuses without asking the agent anything, and nothing scored it until
`scripts/score_gate.py`. That eval needs no model at evaluation time and no rate limit, so
the one measurement that validates the product was the one being throttled.

The persuasion study is kept and demoted: it scores `verify`, a real surface, and its null
result is itself the argument for a gate that does not ask permission.

## Defects found by running it, and fixed

- `compare_term` matched a narrowing qualifier only after the word it qualified: "Orange"
  vs "Orange chalk stripe" was UNVERIFIED, "blue" vs "Medium wash blue" was MISMATCH. Same
  relation, other adjective order. `not` and `fake` joined the negation set as a result.
- The vocabulary guard and the comparison operator held two notions of "the same value".
  The catalogue publishes `in_stock`, the model writes "in stock", and the availability
  requirement was dropped on 4 of 46 cases — the one attribute the key constrains on all 46.
- The shelf report had no way to say "select one of these" and closed on the count of
  ruled-out candidates. On five cases it named the answer and the agent abstained anyway.
- The driver appended a trailer after that report, so the fix reached no prompt.
- `ComparisonRecord` had no `request_text` and no `request_constraints`. The record whose
  purpose is holding the request together with the product did not contain the request.
- `completeness` conflated "the request was silent" with "we failed to read it", so an
  extraction failure of ours was recorded as nobody's fault. `unread` is now separate.
- The extractor filed stated requirements as unverified when it had no closed list to map
  onto. Recovering them collapsed a 45-point nuisance/false-allow trade-off.

## Direction

Reset 11 September, then inverted the same day (DR 0020). The morning's conclusion —
agent-side integration is architecturally necessary — was answering a question the product
does not have to ask. Proving *the agent erred* needs the human's raw request and is
unreachable. Proving *the merchant did not err* needs the agent's stated request and the
merchant's fulfilment record, both already merchant-side.

Approv is the **dispute artifact** for agent-authorised transactions: did the merchant
deliver what was asked for, and if they are compelled to refund anyway, Approv absorbs a
capped portion. The merchant pays, because the merchant holds the loss. Coverage attaches
per channel, never per order — nobody is at an agentic checkout to elect anything.
Agent-side integration is kept as a strictly easier input case, not a precondition.

`docs/direction-2026-09-11.md` has the request sources, the sequencing, revenue beyond the
merchant fee, and the full criticality design.

CONFIRM is now a bounded evidentiary challenge (`approv/challenge.py`), not repair advice:
Approv names the attribute and the bar, the agent gets one round to cite a source, Approv
reads it and resolves to ALLOW or REFUSE. A citation carries no value — an agent that could
state the value could clear its own check.

**The Shopify corpus cannot test it.** Of 70 CONFIRMs, 62 are one case failing the unread
floor and 30 are `claim_more_specific` on size from the `"size 6"` artifact.
`PRODUCT_SILENT` fires zero times: that catalogue publishes every attribute exactly, so
there is nothing to cite. The challenge loop needs the Amazon prose corpus.

## Extraction quotes, and a wrong conclusion corrected

Commit f96181f concluded the corpus carried "zero hedges, zero negations, zero
corrections" and that per-transaction criticality was therefore untestable. **That was a
measurement of post-extraction constraints, not of the corpus.** shopper-v2's held-out
requests carry emphasis in 26 of 42, a negation in 29, a hedge in 8.

`raw_text` was the *value* quote. "It has to be in stock" was stored as `in stock`, so the
words that made it hard were gone before `criticality.request_layer` ran — its regexes were
reading a field that structurally could not contain what they looked for. The tell was that
correction worked and emphasis, negation and hedging did not: correction reads the
extractor's supersession notes rather than the quote, and it was the one signal wired to a
field nothing truncated.

PROMPT_V6 widens the quote to the whole clause, still verbatim and contiguous so the
grounding guards hold. Same model, same pack, same split as the captured v5 run:

| | v5 | v6 |
|---|---:|---:|
| Median quote length | 2 words | **5 words** |
| Quotes of 1–2 words | 144/164 | **40/165** |
| Quotes carrying a Layer 1 marker | 7 (4.3%) | **31 (18.8%)** |
| Constraints resolving HARD | 9 (5%) | **28 (17%)** |
| Parsed / grounding failures | 42/42, 0 | 42/42, 0 |

The static table called everything but price HARD. Per transaction, 83% resolve BOUND —
plainly stated — and 17% HARD. Both block, so no decision moves; what moves is **coverage**
(property 6), which is where the distinction was always meant to land.

Two limits. 60 of 165 constraints share a quote with another attribute, though only 2 of
those shared quotes carry a marker, so contamination is 2 constraints rather than 60. And
hedging still resolves nowhere: shopper-v2's hedges attach to *"Not fussed about the
brand"* (a non-requirement) and *"eco-friendly packaging"* (outside the schema), so **no
hedged requirement on a schema attribute exists in this corpus**. That path remains
untested, for a corpus reason rather than a pipeline one.

## Coverage, and what a false allow actually costs

`coverage_of` reached nothing until now — it was called from its own test and no further,
so per-transaction criticality had no observable effect anywhere. It is now per-finding on
`ComparisonRecord` and reported with its denominator.

It could not be shown to do anything until SOFT existed, and SOFT occurred **zero times in
165** across both captured extractor runs. v2's `hedge` family hedges the speaker
(*"pretty sure I need…"*), which attaches to no attribute. `shopify_shopper_pack_v3` adds
three families that hedge an attribute — *"preferably in Tan"*, *"around size M or
similar"*. v2 is provably untouched: regenerated at the same seed, its tasks are
byte-identical to the committed pack.

**One deviation from the specified `max`, forced by measurement.** With plain `max` the
hedged families still produced zero SOFT: `request_layer` returned SOFT for every one, and
`max` raised them back to BOUND because colour and size are variant axes. Layers 2 and 3
are priors; Layer 1 is direct evidence about this transaction, and `max` cannot represent a
signal that points down. An explicit hedge now caps. After it: **hard 18%, bound 72%, soft
10%** of 176.

| v3 pack, heldout split, 46 cases, 1,244 pairs | before narrowing routed | after |
|---|---:|---:|
| False allow, of 1,142 non-satisfying pairs | 7.3% [5.9, 8.9] | 7.3% [5.9, 8.9] |
| **of which guaranteed — an actual payout** | **1** | **0** |
| of which out of coverage — authorised, nothing promised | 82 | 83 |
| Nuisance confirm, of 102 satisfying pairs | 16.7% [10.7, 25.1] | 16.7% [10.7, 25.1] |
| Coverage, of 4,828 findings — guaranteed | 44.0% [42.6, 45.4] | 42.0% [40.6, 43.4] |
| — refused | 42.9% [41.5, 44.3] | 42.9% [41.5, 44.3] |
| — out of coverage | 13.1% [12.2, 14.1] | 15.1% [14.1, 16.2] |
| **Payout rate, per authorised transaction** | 1 of 168, 0.6% [0.1, 3.3] | **0 of 168, 0.0% [0.0, 2.2]** |

Read without coverage, adding hedges looks like the gate got seven points worse. Read with
it, the gate declined to insure 83 things the shopper said it could. The denominator that
matters is **authorisations, not pairs**: a payout can only happen on a transaction we
allowed, and there were 168 of those. Quoting it per pair understates the price by an
order of magnitude. An earlier draft of this file said "1 in 1,244"; the correct before
figure is 1 in 168.

The one payout was an extraction defect, not a gate defect: the request said *"Tandem
Stripe in Frost"*, the extractor recorded colour as *"Frost"*, and that matched the
product's published *"Frost"* exactly. Same class as the earlier `"L || 2"` narrowed to
`"L"`. **Value narrowing in extraction was the only failure mode measured to cost money.**

**It is routed rather than blocked.** The detector already existed — `coverage_gap` emits
*"Text not explicitly accounted for: tandem stripe"* — and the only lever it had was
`strict_unread`, which chooses between failing the floor (0.0% false allow at 48.4%
nuisance) and guaranteeing the sale anyway (0.3% at 3.3%). Coverage is the third option
that choice did not contain: `criticality.narrowed_attributes` attributes the gap to the
constraint whose own quote carries the unaccounted tokens, and that attribute's finding
goes out of coverage. The sale proceeds and nothing we could not finish reading is
promised.

Attribution is set arithmetic, no model call: quote tokens minus value tokens minus layer-1
marker words, intersected with the gap tokens. It is possible only because v6 widened
`raw_text` from the value to the whole clause — before that the quote *was* the value and
the difference was empty by construction. A second, unplanned payoff from that change.

The decision path is untouched, and that is checked rather than asserted: all 1,244 pairs
carry the identical decision before and after, so nuisance cannot have moved. The cost is
visible in the coverage row — 98 findings, 2.0 pp, move from guaranteed to out of
coverage. That is the price of not promising what we did not finish reading.

## Open

- Extraction is scored against the generator's spec, not against hand labels. That
  measures recovery of a machine-written requirement from machine-written prose; a real
  shopper's wording is not in evidence anywhere.
- `mark` and `verify` unscored.
- Whether published merchant data is true. Nothing here tests that and nothing can.
- Value narrowing in extraction still happens; it is now routed out of coverage rather
  than repaired. Attribution is scoped to the constraint's own quote, and a v6 quote is
  a whole clause, so a gap belonging to no single attribute marks every attribute read
  from that clause. Conservative in the right direction, blunt.
- Layer 3 has never run on real returns data; the highest-fidelity channels will depend on it.
- Quote bleed: one clause serving several attributes, 60 of 165, 2 of them marker-bearing.
- The challenge loop is untested against any corpus. Next: build a prose-corpus pack from
  ESCI/Amazon where `PRODUCT_SILENT` and `LOW_CERTAINTY_SOURCE` actually fire, and measure
  what fraction of CONFIRMs a citation can resolve.
- Criticality is still static per schema, not per transaction.
- The agent-side SDK surface is specified, not built.
- The three-arm agent run prepared in `output/fresh-2026-09-10/` is unrun and now demoted:
  it measures persuasion, which is the interaction the reset killed.
