# progress.md — Approv

Rewritten 10 September 2026 to replace everything before it. Earlier entries described a
design stage that measurement has since overtaken, and several numbers in them are now
known to be artifacts. Session history before this date lives in git history.

## What Approv is, in the narrowest claim the evidence supports

An agent proposes a purchase. Approv compares the customer's stated requirements against
what the merchant published about that exact variant, and returns per-attribute findings
plus one decision: allow, confirm, or refuse.

The wider framing in docs/product-requirements.md — "make autonomous shopping safe enough
to adopt" — is the ambition. **What is measured supports something narrower:** catch the
near-miss when the agent has the right shelf in front of it, and stop a substitute
purchase when it does not. Of 21 agent failures in the current study, 11 were the agent
never seeing the item at all. That is retrieval, and Approv does not retrieve.

## The current number

Three arms, 46 held-out cases, gpt-oss-120b, agent wrote its own search query against a
33,485-variant catalogue from 19 real Shopify D2C brands. Answer key computed from
published merchant fields by code importing nothing from approv.algebra.

| Arm | Correct | 95% CI |
|---|---:|---|
| Baseline — one pass, no help | 23/46 = **50.0%** | 36–64% |
| Control — "check again", no information | 24/46 = 52.2% | 38–66% |
| Approv — findings and repair advice | 24/46 = **52.2%** | 38–66% |

**Approv − control = +0.0 pp**, paired bootstrap 95% CI **[−6.5, +6.5]**. One case better,
one worse. Zero errors in every arm.

The control comparison is the only honest headline. Against the untouched baseline Approv
shows +2.2 pp, but a content-free retry gets +2.2 pp on its own, so that measures the retry.

### Why the effect is bounded — measured, not assumed

| Failure mode | Cases | Reachable by Approv? |
|---|---:|---|
| Search found the item, agent picked wrong | 7 | yes — the core case |
| Search missed it, agent bought anyway | 3 | yes — "nothing here matches" |
| Search missed it, agent declined | 11 | no — it never saw the item |

**Ceiling on this task is +21.7 pp.** The remaining 24% is retrieval.

### Run-to-run variance

Re-running an identical configuration at temperature zero moved the baseline 54.3% to
50.0%. At n=46 any effect below roughly ±8 pp is indistinguishable from noise.

## What else is measured and defensible

| Finding | Number |
|---|---|
| Detection signal on Amazon prose listings | flags 20.8% of non-exact vs 9.7% of exact, **+11.1 pp**, CI [0.8, 23.2] |
| Size stated in description but never the title | **26.9%** of 132,832 Amazon listings |
| Real queries carrying a checkable constraint | **25.6%** of 97,346 US ESCI queries |
| Decline advice precision | 17 right, 1 wrong, 5 missed |
| Cost of a check | ~25 tokens per report, down from 81 |
| Two model families on identical cases | both **54.3%** — the task is the difficulty |

## Retracted — do not reuse

| Claim | Why it fell |
|---|---|
| Baseline 96.3%, and 38.5% | The task gave the answer away: 94% of requests quoted the exact catalogue title, the answer sat in the candidate list 100% of the time, failed-retrieval cases were discarded. It measured string matching. |
| "Approv improves accuracy +24.6 pp" | A content-free retry beat it by 26 points on the same cases. |
| "Presentation causes the error rate" | Tested: the messier flat layout scored better, 100% vs 95%. |
| "Model choice moves accuracy 58 points" | Confounded — model and pack changed together. Two families later scored identically. |
| "Cheap agents do not make mistakes" | Refuted by the 50.0% baseline here. |
| "Approv was factually right on every Brother/myCartridge flag" | It read the brand field correctly. Whether the shopper meant Brother-made or Brother-compatible is a separate unanswered question — grounds to confirm, never refuse. |

## Never measured

Extraction precision against hand labels. Receipt integrity beyond hashes. Underwriting,
loss rates, pricing. Injection resistance against a hostile corpus. Any surface other than
a JSON API agent.

## What exists in the build

types/ shared vocabulary · algebra/ five deterministic operators plus the feedback
renderer · evaluator/ the decision function, with a test parsing its imports to enforce
the §4.1 boundary · harness/ catalogue adapters, case packs, sessions, storefront ·
scripts/ study drivers and the error register.

**170 tests pass.** Software tests are not accuracy results.

On disk: 74,858 Shopify variants from 19 brands; 599 Open Food Facts India records; Amazon
ESCI examples and products; WebShop's 500 human instructions and 1.18M-product attribute
map. WebShop per-product price and options are still missing — a 5.5 GB file needing a
streaming loader.

## Defects found and fixed this week, each from running the thing

- Repair advice told the agent to reword the customer's requirement until it matched the
  wrong product. Measured cost: that arm scored 26 points below a null control.
- A narrower listing value ("Black Multi" vs "Black") was reported as a contradiction. Now
  unknown — except where the extra word negates ("sugar free", "Brother Compatible").
- One malformed requirement discarded every other requirement in the same request.
- A malformed model reply was recorded as an abstention, so a broken call could score as a
  correct refusal. Found by external review.
- Follow-up arms rebuilt the candidate list instead of continuing from the baseline's.
- Session records written UTF-8 were read back with the platform default, corrupting any
  accented product name.

## Why the correction fix did not show up in the number

Correction was identified as the barrier on 9 September and fixed the same day: the advice
that told the agent to reword the customer's requirement was replaced, the advice now names
the attribute and value that would satisfy the request, a "buy nothing" resolution was
added, and satisfied lines were collapsed. All four changes are in the 10 September run.
The result was +0.0 pp against the control.

So correction is not an unfixed item. It was fixed and it did not move the number, and the
reason is structural rather than a matter of wording:

**Approv examines one product. The control makes the agent re-read all twenty-five.**

The control's instruction is not information-free in effect — "review your choice" sends
the agent back over the whole shelf, and on a task whose errors are attention slips, that
is exactly the repair needed. Approv checks only the variant the agent proposed, so its
information is narrower than the control's prompt even when it is more accurate.

The fix is not better wording. It is to check the shelf rather than the pick: score every
candidate the agent retrieved, and say which ones satisfy the request. Today that happens
only for the decline advice, which is the one place Approv beat the control in this run
(impossible cases, 7/8 against 6/8).


## What would actually move the number

1. **The gold set.** 300–500 hand-labelled pairs against a guideline written first.
   Nothing else calibrates PARSED = 0.9, and no accuracy claim survives without it.
   ~200 pairs bounds the false-alarm rate under 5%; ~1,200 is the floor for a guarantee.
2. **Check the shelf, not the pick.** This is the single largest gap. A control that says
   "look again" beats a correct report about one product, because re-reading twenty-five
   candidates carries more repair than a precise finding about one. Approv should return
   the satisfying candidates, not only a verdict on the proposal.
3. **A task where re-reading does not fix the error.** A control reaching 52% by saying
   "check again" means these are attention slips. Real value lives in substitution and
   prose-only facts — where the Amazon detection signal was.
4. **One real integration.** Merchant-owned agent over the existing HTTP contract, then a
   browser agent, then MCP. Each carrying request provenance, exact variant, evidence
   snapshot, findings and final action.

## Standing constraints

evaluator/ imports only approv.types, asserted by test. Gold set never AI-generated.
Public catalogue data only, ToS checked. Every accuracy figure carries denominator, model,
prompt version, date and interval. Mark and verify scored separately.

The §8 amendment of 2026-09-06 suspends founder-authored tests for the pitch window in
exchange for a full teach-back. §4.2 was waived explicitly on 2026-09-10 for the
evaluator, which is written and awaiting review.
