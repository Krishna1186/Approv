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

## Open

- Extraction is scored against the generator's spec, not against hand labels. That
  measures recovery of a machine-written requirement from machine-written prose; a real
  shopper's wording is not in evidence anywhere.
- `mark` and `verify` unscored.
- Whether published merchant data is true. Nothing here tests that and nothing can.
- The challenge loop is untested against any corpus. Next: build a prose-corpus pack from
  ESCI/Amazon where `PRODUCT_SILENT` and `LOW_CERTAINTY_SOURCE` actually fire, and measure
  what fraction of CONFIRMs a citation can resolve.
- Criticality is still static per schema, not per transaction.
- The agent-side SDK surface is specified, not built.
- The three-arm agent run prepared in `output/fresh-2026-09-10/` is unrun and now demoted:
  it measures persuasion, which is the interaction the reset killed.
