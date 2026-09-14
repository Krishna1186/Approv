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

## Intake — one normaliser, many shapes (12 September)

`approv/intake.py`. Every shape agent traffic arrives in ends at the same input the engine
already took: `tuple[Constraint, ...]`, with an honest `Channel` and a locator saying which
part of which artifact each requirement came from.

| Path | Channel | `raw_text` | Source |
|---|---|---|---|
| (a) structured — ACP, AP2, storefront MCP, a feed | `TOOL_ARGUMENT`, or `MANDATE` if signed | **None, correctly** | `acp.color` |
| (b) search — query *and* filters, never merged | `TOOL_ARGUMENT` + `AGENT_MESSAGE` | filter none, query kept | `search.filters.size`, `search.query` |
| (c) free text — declared intent, or a user message | `AGENT_MESSAGE` | kept | `declared_intent` |
| absence — no recoverable stated request | — | — | out of coverage, stated |

**Invariant 9, written with the module rather than after it.** Adding a traffic shape never
touches `algebra/` or `evaluator/`; intake imports only `approv.types`, and the engine never
imports intake. Both directions are AST-asserted, and the test was checked against a
deliberate violation rather than assumed to have teeth. Free-text reading is injected as a
callable — `harness/intent.as_extractor` — which is what lets the layer that needs a model
stay outside the layer that may not import one.

**Path (a)'s `raw_text=None` is why the quote fix that broke 31 tests was load-bearing.** A
protocol field has no wording to quote, so the highest-fidelity channel produces the
quoteless constraint. `request_layer` floors any constraint that exists at BOUND; had it
returned no signal for a missing quote, §2.2's never-stated cap would have dropped every
path (a) requirement to SOFT — out of coverage. The best input we can get would have made
the weakest record in the system. Pinned by a test that names the path.

**`Reading` carries `unread` as well as constraints.** An extractor interface returning
constraints alone would have dropped the signal that the narrowing routing above depends
on, and the free-text paths are exactly where narrowing happens.

Nothing calls intake in the measured pipeline yet, and no number moved. It is exercised
end to end against the real interpreter, not only a stand-in.

## DR 0021 — `unread` had two definitions; now it has one (12 September)

Both fed the verification floor, which is the decision path, so a number produced by one
did not mean what a number produced by the other said. Measured before deciding.

| v3 pack, 1,244 pairs, strict floor | `all` notes | `dropped` only |
|---|---:|---:|
| False allow, of 1,142 | 0.1% [0.0, 0.5] | 0.1% [0.0, 0.5] |
| False refuse, of 102 | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] |
| Caught · escalated | 90.9% · 9.0% | 90.9% · 9.0% |
| **Nuisance, of 102** | **84.3% [76.0, 90.1]** | **75.5% [66.3, 82.8]** |
| Guaranteed false allow | 0 | 0 |
| Coverage: guaranteed / refused / out | 42.0 / 42.9 / 15.1% | 42.0 / 42.9 / 15.1% |

Under the lenient floor the two are identical in every cell — `strict_unread=False` never
reads `unread`, so the definition can only bite where the floor is enforced.

**Not a trade-off, a defect.** The narrower definition costs 8.8 pp of nuisance and buys
nothing back. The notes it stops counting are the model's free-text `unverified` list
(*women's*, *casual*, *kid's shoes*), shipping chatter (*"My last order took forever to
arrive"*), and — the case that settles it — `Superseded, discarded: Black (color)`. That
last is the extractor reading a correction *perfectly* and logging what it discarded.
Under the old definition a shopper who changed their mind got escalated for it, and the
better the extractor reported what it did, the worse the gate behaved.

The vocabulary moved to `approv/types/core.py`, the one module every layer may import.
`harness/shopping.py` could not reach `dropped_requirement` without a cycle, and a producer
that cannot reach the definition invents one — that cycle is why the two existed. All three
producers now filter identically; `score_gate --unread all` keeps the losing definition
runnable so this table can be reproduced rather than trusted.

Nuisance at 75.5% is still far too high for any merchant to run the strict floor. DR 0021
does not fix that. It removes the part of it that was measuring the extractor's honesty
rather than the request's completeness.

## The merchant order verification object (12 September)

PRD §3's headline gap. The request half of the record was strong and the order half did
not exist — `product_id` plus an untyped `product_snapshot` dict, in which the right
numbers *could* live with nothing binding or validating them, which is the same as not
having them.

**`OrderLine` on the record**: `order_id`, `line_id`, `product_id`, `sku`, `variant_id`,
`quantity`, `unit_price` as typed `Money`, `availability`, `catalogue_version`,
`checkout_state`. Inside the digest with everything else, so a price cannot be adjusted
after the outcome is known — asserted by tampering with a sealed record and watching the
hash check fail. Optional on the record, because `mark` runs at shelf time before any order
exists: a record with an order is a verification of a purchase, one without is a comparison
about a product, and that difference is now in the record rather than in what the caller
meant.

Required is what the artifact cannot argue without — a refund is denominated in the price,
so a record that cannot say what was charged cannot contest one. `availability` and
`checkout_state` are the merchant's own terms, recorded verbatim; nothing decides on them,
and DR 0004's failure semantics stay open.

**Two bindings, both enforced.** `ComparisonRecord` rejects an order line naming a
different product from the comparison. That one cannot fire at the surface — `product_id`
is taken *from* the order — so the surface enforces the binding that can actually fail
there: a catalogue snapshot identifying itself as a different product from the order line.
Checked only when the snapshot carries an id, because many exports do not and rejecting
those would invent a requirement the format does not have.

**The entry point.** `approv/surface/verification.py` is the whole request path with no web
framework in it: intake normalises the stated request whatever shape it arrived in, the
schema's own `field_profiles` read the merchant's snapshot into evidence, `algebra`
compares, `evaluator.decide` decides, `receipts` assembles and signs. `approv/surface/api.py`
is the only module in the repo that imports FastAPI — `POST /v1/verify`, `GET /v1/health`,
an optional dependency, and the framework-free tests are skipped per test rather than per
module so they go on proving they need no server.

Three things that fell out and are worth keeping:

- **The product-side adapter needed no new vocabulary.** `FieldProfile` already names the
  field, the attributes it speaks to and both DR 0016 axes, and it was being authored per
  category anyway. `evidence_from_snapshot` is that mapping read in the other direction.
- **A value we cannot honestly read produces no evidence.** A float where a size belongs
  yields nothing, the attribute goes UNSTATED and the sale escalates. Coercing it to a Term
  would manufacture a comparison out of a value we did not understand, and a manufactured
  SATISFIED is a guarantee we cannot keep.
- **A refusal is a 200.** An error status invites a caller to treat it as a transport
  failure and retry until it goes away.

Schemas, the catalogue reader, the extractor, the signing key and the floor policy are
deployment configuration rather than request payload. A caller supplying their own schema
would let the party being defended define what counts as a match.

396 tests. Nothing measured moved: no study path calls the surface.

## DR 0022 — what an unread request does (13 September)

The nuisance question, measured three ways rather than argued. v3 pack, heldout, 46 cases,
1,244 pairs; nothing changes between columns but the policy.

| | ESCALATE | **WITHDRAW** | IGNORE |
|---|---:|---:|---:|
| False allow, of 1,142 | 4.3% [3.3, 5.6] | 7.3% [5.9, 8.9] | 7.3% [5.9, 8.9] |
| False refuse, of 102 | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] | 0.0% [0.0, 3.6] |
| Escalated (wrong product confirmed) | 4.8% [3.7, 6.2] | 1.8% [1.2, 2.8] | 1.8% |
| **Nuisance (right product confirmed)** | **58.8% [49.1, 67.9]** | **16.7% [10.7, 25.1]** | 16.7% |
| **Guaranteed false allow** | **0** | **0** | **0** |
| Payout rate per authorisation | 0.0% [0.0, 4.1] of 91 | 0.0% [0.0, 2.2] of 168 | 0.0% [0.0, 2.2] of 168 |
| Coverage — guaranteed | 18.8% [17.7, 19.9] | 18.8% | 42.0% [40.6, 43.4] |
| Coverage — out of coverage | 38.3% [37.0, 39.7] | 38.3% | 15.1% [14.1, 16.2] |

**Guaranteed false allow did not rise — it is zero under all three.** That was the cost to
watch for and it did not appear.

The table separates on two axes, which is what made it decidable. ESCALATE and WITHDRAW
have identical coverage and differ only in the decision: 3.0 pp less false allow for
42.1 pp more nuisance, and every one of those false allows is out of coverage, so the
3.0 pp is bought with a currency that has no measured price. WITHDRAW and IGNORE have
identical decisions and differ only in what is promised: 23.2 pp of findings that IGNORE
claims as guaranteed over words nobody read.

**WITHDRAW is the default.** Withdrawal is record-wide, not attribute-scoped, and that is
the argument rather than a detail: narrowing could be attributed to a constraint's own
quote, but a gap belonging to no constraint has no attribute to scope to. A guarantee
promises that *this order was as asked*, and a request we did not finish reading cannot
support that about any attribute, however cleanly the ones we did read compare.

**What this corpus cannot show.** WITHDRAW and IGNORE produce the same payout count here:
zero. The case for WITHDRAW rests on the coverage claim being true, not on a measured
payout difference. The reason is structural — the answer key is derived from published
fields, so it is bounded by the same schema the comparison is, and text the schema cannot
express (*"delivery speed doesn't matter"*) is exactly the text that goes unread and can
never make a product wrong by the key's own definition. Pricing that needs return
outcomes, not an answer key.

**The marker fix this forced.** Under a record-wide withdrawal the gap detector's false
positives stopped being cosmetic: 8 of the 28 cases carrying an unread note were hedge
families and nothing else, and would have surrendered a whole record's guarantee because
the shopper said *"preferably"*. `criticality.unread_requirements` subtracts layer-1 marker
words, read off the quotes rather than the note. Holding policy at ESCALATE it moved
nuisance 75.5% → 58.8%, false allow 0.1% → 4.3%, guaranteed coverage 12.1% → 18.8%. It runs
in `build_record`, so what the record stores in `unread` and what the decision acts on are
the same set — storing a hedge as unread would put in the dispute artifact a claim that we
failed to read something we read.

**The number this exposes, and it is the real finding.** 28 of 46 held-out requests carry
an unread note; 20 of 46 still do after the marker fix. So roughly **two in five orders are
authorised with no guarantee at all**, and guaranteed findings fall from 42.0% to 18.8%.
That is not a defect in the decision — under IGNORE those guarantees were being claimed
anyway; what changed is that the record now says which ones we can stand behind. It does
bound the product, and the larger of the two ways out is schema expressiveness rather than
extraction: most surviving gaps are requirements the category has no attribute for.

## DR 0004 — a verification that did not complete (13 September)

Closed. A provider timeout, a malformed response, an unreadable catalogue and a genuine
product mismatch collapsed into one refusal, and one of them was worse than collapsed.

**It was failing open.** `decide(())` returns ALLOW, so an extractor that failed and
yielded no constraints *authorised the purchase*. DR 0004's own attack section describes
that bypass as something an attacker induces with latency; it was reachable without one.

**A second axis, not a fourth state.** `Decision` is untouched — a fourth transaction state
has been proposed and killed before, and it would be wrong here anyway: a provider outage
is not a verdict about the purchase, it is a fact about us, and putting it in the same enum
forces every consumer to handle "the shop is on fire" inside a switch about whether the
duvet is the right colour. `ComparisonRecord.completion` is the axis that was missing:

| | whose problem |
|---|---|
| `completed` | — |
| `provider_unavailable` · `unreadable_response` · `budget_exceeded` | ours |
| `catalogue_unreadable` | **the merchant's** |
| `internal_error` | ours, named rather than hidden |

`catalogue_unreadable` earns its own value because *"your catalogue is wrong"* and *"our
vendor is down"* are the two sentences a merchant needs told apart. On the reader boundary
a parse failure and no answer at all are also told apart; on the catalogue boundary they
are not, because however the merchant's snapshot failed to read, it is the merchant's
snapshot.

**It routes through the floor, so nothing overrides the evaluator.** An incomplete check
sets `floor_met=False` — the clearest possible case of the preconditions not being there —
and `decide` cannot return ALLOW from that. The answer is `confirm` and deliberately not
`refuse`: a failed check is not evidence the product is wrong, and refusing on our own
outage bills the merchant for it.

**Coverage is withdrawn entirely**, and `incomplete` is its own parameter on `coverage_of`
rather than folded in with narrowing and DR 0022's unread request. Those two are readings
we can characterise; this is the absence of a reading. A dispute artifact that cannot say
which of the three happened is worse at its only job. `VerificationResult.covered` is
gated on completion too — intake's channel verdict knows nothing about whether the check
finished, and `covered: true` beside a provider outage is exactly the seam worth closing.

**An abort is a 200 with the record.** A 5xx hands the merchant nothing to keep, and their
integration's most likely response to one is to ship anyway — failing open through the
error handler rather than through the gate. Only the two *injected* boundaries are caught
this way; a bug in our own assembly still raises, because laundering a programming error
into a signed `confirm` would hide it behind a plausible-looking artifact.

**The budget is a mechanism, not a number.** `budget_seconds` guarantees the safety
property — we never authorise on a call that blew its budget — and explicitly not the
latency one: it does not cut the call short, because cancelling in flight needs cooperation
from the adapter that owns the HTTP client. The millisecond figures stay Stage E work
against a real page load. `mark` failing open is unchanged and unimplemented: there is no
`mark` surface yet, and writing one to satisfy a table would be building ahead.

562 tests. Nothing measured moved.

## Seams 1 and 4, sealing, and shadow mode (13 September)

**Seam 1 — the field path format.** `approv.schema` emits
`/variants/*/options/*/value#name=Colour`; the surface read dotted keys. A schema derived
from a catalogue read *zero* evidence from that same catalogue. The resolver now walks the
pointer, and the `#name=` selector must match a sibling of the value — load-bearing rather
than decorative, because Size and Colour share that path and reading it wrong crosses two
attributes. It costs one shape deliberately: `/variants/*/option1#name=Colour`, whose label
lives in a separate table, reads nothing here. Reading nothing is now caught; reading the
wrong attribute is not.

**The silence was the worse half.** A schema whose paths read nothing from a non-empty
snapshot looked identical to a cautious engine — no exception, no log, every attribute
UNSTATED, every order confirmed. A pilot partner would have seen a 100% confirm rate and no
error. It is now `CATALOGUE_UNREADABLE` with a detail naming the mismatch.

**Seam 4 — DR 0023.** `covered` and `coverage_notes` moved onto the record, inside the
digest. My original reasoning (*"policy about the channel rather than a fact about the
comparison"*) was wrong against a renderer that reads the record and nothing else, and two
agents hit it from opposite sides within a day. `covered=False` now withdraws every
guarantee, which makes four withdrawal reasons — narrowed attribute, unread request,
incomplete verification, uncovered channel — each with its own field on the record.
Coverage still never gates a decision.

**Sealing has one owner.** The surface no longer signs: only the store knows the chain
head, and a signature over `prev_hash=None` is a receipt appendable exactly once per
ledger. `verify_order` returns an unsealed record.

**Shadow mode.** `Mode.SHADOW | ENFORCE` on the record and inside the digest. It is
deployment configuration, never request payload — a caller who could send `enforce` could
defeat sandbox isolation with one JSON field — and it defaults to SHADOW everywhere,
because the two mistakes are not symmetric: a shadow record mislabelled `enforce` is a
false claim in a dispute, an enforce record mislabelled `shadow` under-claims and is
recoverable. Only the second is reachable by forgetting.

**Outcome ingestion.** `OrderOutcome` joins a verification by `correlation_id`: shipped /
returned / disputed / refunded, with the merchant's reason text kept verbatim and read by
nothing. That last part is asserted the way the other import boundaries are — `evaluator/`,
`algebra/` and `criticality` may not import the outcome types — because it is the field
most likely to be quietly promoted into a signal. `POST /v1/outcomes` refuses an outcome
carrying the other mode (409) and refuses to accept one at all when the deployment has
nowhere to put it (501): an ingestion endpoint that silently discards is worse than none,
because it reports success.

Storage and the separate sandbox chain are the store's, not this fence's. What is enforced
here is that a shadow record cannot be produced by an enforce deployment or relabelled
afterwards, and that an outcome cannot cross modes through this surface.

**Invariant 10** — no personal data in the record, approved by the founder. A field-name
test catches the day someone adds `customer_email`, which is how personal data actually
arrives: as a convenience field, not as an attack.

## Seams 5 and 6, and the outcome fields (14 September)

**Seam 6 — the ordered variant.** The catalogue reader was handed a product record and
read *every variant in it*. On an apparel catalogue that is not a partial answer: a duvet
in six colours publishes six colours, and a reader that pools them finds Frost in a record
whose ordered line is Ash — then states it with the same confidence as a correct reading,
names a field path that really exists, and signs it into the same record. Nothing
downstream can tell the two apart. `verify_order` now projects the snapshot to the ordered
SKU before the reader sees it, so a merchant's own `Reader` cannot read the wrong variant
either. The record keeps the snapshot as sent; the projection is reproducible from the
order line it already carries. DR 0024.

A multi-SKU snapshot that does not hold the ordered line raises, the same way posting
product A's snapshot with product B's order line already raises. Two identifiers that
disagree are a contradiction rather than a match — a stale `variant_id` beside a good
`sku` would otherwise read var-9 and sign it against a SKU never sold.

**The resolver is now the producer's own walk.** The surface stopped walking locators
itself and calls `approv.schema.catalogue.flatten`, the code that emitted them. A second
walk would have to reproduce the option table, the currency inheritance, the pair
detection, the labelled-clause extraction and the child-over-parent rule *exactly*, and
the day one drifted we would read a merchant's catalogue differently from the schema
derived out of it — seam 1 again, silently. Producer and consumer agree by construction;
the contract test is a regression on the agreement rather than the only thing holding it
together. It also answers the flat Shopify export: the option-name table resolves, so
`/variants/*/option1#name=Size` reads.

One thing the reader knows that the walk does not is what the attribute **settled as**
across the catalogue. Size `3XL` reads as an unrecognised unit in isolation and `13.5` as
a unitless decimal; both are labels once the schema says NOMINAL. Everywhere else the
dimensions must agree.

All 19 of codex2's contract checks pass, and the seven strict-xfail markers came off.

**Seam 5 — corroboration.** `algebra.runner` raised DUPLICATE_CLAIM for any two claims on
one attribute *without comparing their values*. A shopper who ticks the King filter and
types "king duvet" gave us the strongest evidence in the record that they meant King and
got the weakest outcome available: both findings UNSTATED, the attribute unresolved, the
order escalated — 20 of 24 on-site-search orders, and on-site search is DR 0020's second
fidelity tier.

*Which one they meant* is only a question when the two answers differ. The values are now
compared with the attribute's own operator — the same treatment two fields of evidence
have always had — run **both directions**, because half a comparison is containment rather
than agreement and a $150 ceiling "satisfied" by a $120 claim one way round would silently
drop the tighter limit the shopper set. Both statements stay in `request_constraints`;
only the comparison collapses, to the strongest channel's. DR 0025.

Measured on the v3 pack: **all 1,244 rows byte-identical**, decisions and coverage both.
That corpus is single free-text requests and has zero cases stating an attribute twice, so
it cannot show this either way — the published numbers are unchanged, not confirmed. The
measurement that matters is claude2's on-site-search week, which is not ours to re-run.

**Outcome ingestion grew four optional fields.** Without a ship date and a window length,
*kept* is not observable: a return is known the day it happens, a keep only by a window
expiring, so a feed of shipped and returned events has a denominator containing every
return and no keeps — precision 100% by construction, which `report.outcomes` correctly
refuses to print. `ship_date` + `return_window_days` make it derivable, and
`return_window_closes_at` lets a partner send the date outright.

`reason_code` is the returns desk's own coding, verbatim, beside their free text rather
than read out of it. A string and deliberately not an enum of ours: classifying
`merchant_reason` into an Approv taxonomy would mean grading our own work against
categories we chose — we decide what counts as a wrong item, then report how often we got
wrong items right. Their code is evidence because they chose it, before knowing what we
would do with it. All four optional, because partners arrive at different tiers and a
required field turns "cannot answer that yet" into "cannot be onboarded".

## The three blockers: a request nobody read, cart-only traffic, form submissions (14 September)

**An unprocessed search query permitted a guarantee.** Measured on the shape that shows it
worst — filters `{size: M, color: Frost}`, query *"actually make it the Ash one, and it
must be organic"*, no extractor configured:

```
decision=allow  covered=True  coverage=[guaranteed, guaranteed]
notes: ["search query was not read: no extractor was supplied"]
```

The request contradicted the filters in its first four words and we guaranteed both
attributes. The note was there; nothing acted on it.

`REQUEST_UNPROCESSED` joins DR 0004's `Completion` axis rather than becoming a fifth
coverage flag, because it is the same fact those codes record and that axis already does
both things this needs: the floor is not met so `allow` is unreachable, and `coverage_of`
withdraws every guarantee. A refusal still refuses. It is the first completion that keeps
its findings — the comparison really did run, against a request we had half of, and
discarding them would hand the merchant a record saying less than we know. DR 0026.

Two shapes, treated alike: nothing was available to read the prose, or something ran and
returned an entirely empty reading from non-empty text. An extractor that read something
and could not encode part of it is DR 0022's case and stays there — it told us what it
missed.

**The same hole, one door along.** A protocol field this category has no attribute for was
noted, allowed and guaranteed. That is a requirement we can *name* and did not check,
which is DR 0022's definition of unread, so it now uses the `"Unsupported requirement: "`
prefix that already existed and takes DR 0022's answer: withdraw, do not block. The line
between the two is what we know — unread prose can contradict everything we did read, and
in the measurement above it did.

**Cart-only traffic is a different product.** An adapter receiving only a final cart knows
what was bought and nothing about what was asked for, and it used to issue the usual
record anyway: headed like a verification, holding a decision, findings about a request
nobody made, and `covered: false` some distance below. A returns desk reads the heading and
a billing system reads the kind.

`OrderEvidenceRecord` is a separate object and the product is chosen **before** the
comparison rather than described after one. No `decision`, because nothing was authorised
on the strength of a request we never received; no `findings` and no `coverage`, because
there is nothing to have found. `eligible` is hard-wired false and is a field anyway, so a
reader does not have to know that a missing coverage block means what it means. `kind` is
on both records and inside both digests.

**A protocol name can withdraw the agent inference and never grant one.**
`Structured(protocol="form")` is a checkout POST wearing the shape of a protocol call. We
will not read a name as proof of an agent — that is the fabricated basis intake refuses
everywhere else — and we will take one as a disclaimer, because a merchant who calls it a
form has told us it is one. `agent` remains the only mechanism that grants.

All three verified against the v3 pack: 1,244 rows byte-identical. That corpus reaches
`check_constraints` directly and never enters intake, so it cannot show these either way.

## Parked

**`approv/challenge.py` — built, tested, unwired, and staying that way for now.** One
bounded evidentiary round: Approv names the attribute it could not establish, the agent
answers with a *citation* rather than a value, Approv reads that source itself. The design
is sound and the safety property (`Citation` has no `value` field) is the good part.

It is parked because there is nobody to challenge. Under DR 0020 the record is a merchant
defence assembled from merchant-side data, and a shadow run has no live agent in the loop
to answer a question — the order has already been placed by the time we see it. Wiring it
would mean inventing a round-trip that the surface does not have and the merchant did not
ask for. It waits for the agent-side product, which DR 0020 keeps and does not build first.

Do not wire it. Its tests keep passing, which is the whole cost of keeping it.

## Open

- Extraction is scored against the generator's spec, not against hand labels. That
  measures recovery of a machine-written requirement from machine-written prose; a real
  shopper's wording is not in evidence anywhere.
- `mark` and `verify` unscored.
- Whether published merchant data is true. Nothing here tests that and nothing can.
- A merchant whose multi-SKU export carries no identifier the order line can name now gets
  a hard mismatch on every order rather than a wrong reading. That is the right direction
  and it is loud, but it is an onboarding requirement nothing states up front: the order
  line must carry a `sku` or `variant_id` that appears in the snapshot.
- The surface now imports `approv.schema.catalogue`, so the request path depends on
  onboarding. Deliberate — it is what makes producer and consumer agree by construction —
  but it is a coupling that did not exist before, and an onboarding change can now move a
  production read.
- **The store cannot seal an `OrderEvidenceRecord`.** `receipts/chain.py` tests
  `isinstance(record, ComparisonRecord)` in both `require_unsealed` and `record_json`, so
  cart-only traffic produces a record nothing can append. Two lines, codex1's fence, and
  it blocks the offline backtest which routes cart-only rows straight into
  `store.append_many`.
- A deployment with no extractor now confirms every search order that carried a query,
  because it cannot read one (DR 0026). Correct, and expensive: the repair is on our side
  and it is to read the query.
- The protocol-name disclaimer matches whole words — `form`, `checkout`, `cart`,
  `browser`, `manual`, `human`, `storefront`, `page`. A merchant whose human channel is
  named something else is still inferred as an agent unless they pass `agent`, which is
  the mechanism that was always right and is now the only one that grants.
- Coverage is bounded by schema expressiveness: 43% of held-out requests still carry an
  unread note after the marker fix, and most of those name something this category has no
  attribute for. Selling a guarantee on under half of traffic is a product limit, not a
  tuning one, and nothing here measures which categories are worse.
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
