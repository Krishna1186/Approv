# Shopping study: 8 September 2026

Approv has a working, traceable original-request experiment. The completed 40-session
120B study has **not demonstrated an overall shopping accuracy improvement**. It
contains one real human-labelled correction, alongside misses and operational
failures. V3 did not improve on v1. The earlier 20B held-out study remains incomplete
because of provider limits. A separate check of the latest adapter stopped at the
120B daily quota after nine of fifteen sessions.

Product requirements and implementation scope: [simple PRD](product-requirements.md).
Reproduction and integration commands: [harness guide](shopping-harness.md).

## What was tested

Initial runs used Groq `openai/gpt-oss-20b`; the separately reported 120B studies
used `openai/gpt-oss-120b`. Within each comparison the shopping model and its settings
stay fixed. The model searches frozen inventory, inspects
product details, proposes a product and chooses a sale-unit count. It can abstain.
It receives the original request, not a pre-solved list of constraints. No purchases
occur. Each session starts without another session's answers or model context.

Baseline accepts the first valid selection. Generic review asks the agent to check
its choice. Approv review also supplies findings from independently extracted
request requirements and typed comparisons against product evidence. Each arm has
six actions, four products per search page and at most one review. Actual token
usage differs. Approv adds an interpretation call; generic review does not control
for all of that additional compute.

Search uses the same lexical ranking in every arm. Inventory records, tool results,
provider responses, errors and implementation hashes are recorded. API requests
contain no answer labels. Independent scoring happens after the session ends.

## Data prepared, not all executed

| Source | Prepared | What the answer key establishes |
|---|---:|---|
| Amazon ESCI | 40 original queries: 10 development, 30 held out | Original human E/S/C/I relevance judgements for the query's candidate pool. E counts as exact relevance. Quantity and correct abstention are unlabelled. |
| Open Food Facts with synthetic requests | 120 requests: 40 development, 80 held out; 548 products | Separately constructed rules for exact published product name, literal pack quantity, sale count and deliberately unavailable size. These are synthetic answers, not human shopping judgements. |

ESCI source files are pinned to repository revision
`7916cdf6ab75a462e77f20ab40428a10923998d5`, with local download hashes and licence
files. Sampling uses seed `20260908` and does not select queries by agent performance.
See [Amazon's dataset repository](https://github.com/amazon-science/esci-data) and
[the local source review](public-shopping-datasets.md).

The synthetic pack has five templates: clear request, corrected count, total amount
using a specified pack size, unspecified size, and unavailable exact size. Development
and held-out requests use separate product-name groups. Templates overlap across
splits, so this tests new products within familiar language patterns. It does not
test broad language generalization. Decimal near-misses are deliberately artificial;
names such as "bourbon" may be ambiguous outside the catalogue's context. The public
catalogue is not an assurance of current stock, physical contents or merchant accuracy.
"Held out" means excluded from this project's development work. Public benchmark
material may have appeared in model training; this study cannot rule that out.

## Completed development comparison

Five synthetic requests across two product-name groups were run in all three arms.
IDs: `off-0-clear`, `off-0-correction`, `off-0-total`, `off-1-vague_size`,
`off-1-impossible`. The later v2 run reused these development cases for Approv only.

| Condition | Correct outcomes | Wrong completed selections | Operational failures | Recorded agent tokens | Extra interpretation tokens |
|---|---:|---:|---:|---:|---:|
| Baseline | 5/5 | 0 | 0 | 11,351 | 0 |
| Generic review | 4/5 | 0 | 1 | 18,597 | 0 |
| Approv v1 | 4/5 | 0 | 1 | 17,689 | 10,035 |
| Approv v2, development rerun | 4/5 | 0 | 1 | 18,958 | 4,032 |

Both v1 review-arm failures were HTTP 400 tool failures. Relative to baseline,
Approv's observed outcome rate was 20 percentage points lower. Relative to generic
review it was unchanged, with one case succeeding where review failed and one doing
the reverse. This is operational variation, not evidence of better product reasoning.
Five related requests are far too few for an assurance claim.

V1 produced valid interpretations in two of five cases. V2 produced valid JSON and
supported field types in all five, using fewer extraction tokens. **Validity was not
semantic correctness:** for a request for 150 g total using 50 g packs, v2 incorrectly
checked 150 g per pack, despite choosing three packs. The shopping agent still chose
the correct product/count. This is a concrete example of Approv giving bad feedback
to an agent that already understood the request.

V3 adds literal checks grounded in the original text and public product-name
vocabulary. Offline replay of that development interpretation now gives 50 g per
pack and three packs, with the named product retained. This proves that particular
repair works; it is not a new shopping accuracy result. V3 was frozen before the
held-out comparison.

## Held-out comparison in progress

Five cases from five previously unused product-name groups were selected before
their outcomes: `off-8-correction`, `off-9-total`, `off-10-impossible`,
`off-11-vague_size`, `off-12-clear`.

The shopping agent uses native assistant/tool conversation history in all these
conditions, correcting a transport issue observed during development. Therefore
these runs must not be pooled with the older development transport as repeated
trials of the same agent configuration.

At the first long provider pause, 10 of 15 v1 sessions were saved: baseline 3/4,
generic review 3/4, Approv 2/2. These unequal denominators must not be interpreted
as a comparative accuracy table. Only two cases had both Approv and baseline results;
both succeeded in both conditions. One generic-review run failed with HTTP 400.
One baseline run failed with HTTP 429 and a `retry-after` value of 477 seconds.
The failed sessions remain in the denominator. The run will not silently retry a
completed failure or substitute a different model.

A subsequent development diagnostic confirmed the 20B account's daily token limit:
200,000 allowed, 199,089 used, and 1,414 requested, with another 218-second wait.
That long-window limit prevents running the complete corpus continuously on this
model under the present quota.

## Completed 120B synthetic comparison

This is a separate model study, using five fresh product-name groups selected before
their 120B outcomes: `off-13-correction`, `off-14-total`, `off-15-impossible`,
`off-16-vague_size`, `off-17-clear`. All 20 planned sessions completed and replayed.

| Condition | Correct outcomes | Wrong completed selections | Failure | Agent tokens | Interpretation tokens |
|---|---:|---:|---|---:|---:|
| Baseline | 5/5 | 0 | None | 17,286 | 0 |
| Generic review | 3/5 | 0 | One HTTP 400, one search budget exhausted | 22,658 | 0 |
| Approv v1 | 4/5 | 0 | One search budget exhausted | 22,995 | 5,413 |
| Approv v3 | 4/5 | 0 | One HTTP 400 | 24,425 | 4,615 |

Both Approv versions were 20 percentage points below baseline and 20 points above
generic review in this tiny sample. V3 did not improve the aggregate result over v1:
one case improved and another regressed. Total recorded tokens increased slightly.
The uncertainty ranges are broad and cannot support a reliable positive-effect claim.

Every first proposed selection in these sessions was already correct. There were
**zero incorrect proposals corrected into successful outcomes**. The unavailable-size
case illustrates why separate model sessions need care: identical initial request
hashes led to different searches and outcomes even at temperature zero. In the
exhausted runs, neither review nor Approv feedback was ever reached. V3's successful
abstention in another run is therefore not evidence that its feedback corrected v1.

For a stronger causal test, also fork continuations from a shared initial proposal,
then compare generic review and Approv from that same starting point. The current
study uses independent sessions and reports the resulting variation openly.

## Earlier human-labelled exploratory runs

Seven of nine planned native-tool development sessions completed before a rate-limit
stop. Baseline selected an E-labelled product in 2/2 recorded sessions; generic
review in 3/3; Approv in 1/2, with one provider failure. All six completed selections
were E-labelled. Approv's two interpretations failed validation. This incomplete,
tiny development sample establishes neither improvement nor human shopping accuracy.

Earlier JSON-transport setup attempts are retained separately: four initial baseline
records and nine further failed sessions. Some provider calls during early crashes
were not checkpointed. They are not silently included as a complete experiment, and
recorded token totals are a lower bound on total provider consumption. The API setup
failures are not evidence that the model cannot perform the shopping tasks.

## Completed 120B human-labelled comparison

Five original held-out ESCI queries were selected before their outcomes: `enema hose`,
`this is water david foster wallace book`, `buffalo bills womens winter hat`, `v`,
and `funny shirts for men`. Their candidate pools contain 15–22 judged products.
All 20 planned sessions completed and replayed. These queries are original search
queries, not full customer conversations or independent purchase-satisfaction labels.

| Condition | Exact matches | Non-exact final selections | Other outcomes | Agent tokens | Interpretation tokens |
|---|---:|---:|---|---:|---:|
| Baseline | 2/5 | 2: one S, one I | One HTTP 400 | 13,635 | 0 |
| Generic review | 2/5 | 2 S | One HTTP 400 | 24,468 | 0 |
| Approv v1 | 2/5 | 1 S | One HTTP 400, one budget exhausted | 33,388 | 3,377 |
| Approv v3 | 1/5 | 2 S, one I | One HTTP 400 | 21,355 | 3,430 |

V1's winter-hat run initially proposed `B0824RTCDQ` (human label S), then changed to
`B0723C8R3F` (E). Baseline and generic review ended with a substitute. This is one
observed correction during an Approv-assisted session. However, v1's interpretation
failed validation: its useful intervention was the explicit uncertainty warning and
request to recheck. It was not successful verification of women's winter-hat features.

All five v1 interpretations failed validation. V3 parsed all five, yet scored worse
and made no incorrect-to-correct proposal changes. Its winter-hat selection stayed S.
This is why successful parsing cannot be used as the release criterion for Approv.
The catalogue schema supports brand and colour; most of these queries require other
semantics. Unsupported requirements and uncertainty need explicit handling, and the
present rules are not a complete personal-intent verifier.

V1's net effect versus each control was zero: one better case and one worse case.
Its exploratory interval spanned -60 to +60 percentage points. V3's observed effect
was -20 points. These small, noisy samples do not establish population effects.
The query `v` is especially ambiguous; failure to select an E-labelled product is
not proof that buying any particular product was the right real-customer action.

## Four milestones

| Milestone | Result |
|---|---|
| Baseline agent | Executed on public human-labelled and separately synthetic tasks. |
| Original-request Approv loop | Implemented and exercised; interpretation remains fallible and coverage limited. |
| Held-out comparison | Completed for 120B: ten cases, four conditions, 40 sessions. The earlier 20B run is incomplete. |
| Approv version comparison | Completed for v1 and v3; no release-worthy accuracy improvement demonstrated. |

The latest working-tree adapter and parser safeguards are subsequent changes. Their
new comparison uses five unused ESCI queries and a fresh runtime archive. Its results
must remain separate from the 40-session study above.

The new run stopped after nine sessions: baseline 3/3 exact matches, generic review
3/4 and Approv 1/2. One review session was rejected by the daily quota before any
action, and one Approv session exhausted its budget searching before reaching review.
All seven completed selections were E-labelled; no HTTP 400 appeared in these saved
sessions. These unequal, incomplete samples are not an accuracy comparison or proof
that tool failures have been eliminated. All nine sessions replayed successfully.

The blocking provider response reported a daily limit of 200,000 tokens, 199,798
used, 816 requested, and a 266-second wait. Short waits restore enough capacity for
individual calls; finishing larger studies continuously needs renewed or higher quota.

## Reliability and audit checks

153 software tests pass. They cover independent scoring, original-request isolation,
typed quantities, malformed extraction, native tools, adapters and trace replay.
The 15 v1 development sessions, five v2 development sessions and first ten held-out
sessions replayed against their archived implementation and original inventory.
The browser storefront displayed product details and literal untrusted script text
without executing it; the browser console had no errors or warnings.

Replay establishes consistency of the recorded tool actions and findings. It does
not prove that a provider is deterministic, that a public source is true or that a
record's author is authentic. Production signatures and independent retention remain
future work. No underwriting decision, claim payout or live payment was tested.

A development-only transport repair now exposes a distinct `confirm_selection`
function after review. Repeating the failed 20B development continuation then produced
a valid confirmation for three 50 g packs. An extra instruction alone had still failed.
This single check supports the repair but does not prove all tool failures are gone.
The completed 40-session 120B comparison used the frozen `native_messages_v2` adapter;
its results are not validation of this newer `native_messages_v4` adapter.
Additional working-tree regression checks prevent literal repairs from reading
`1,050 g` as `50 g`, or treating the excluded count in "three packs, not two packs"
as the requested count. These later safeguards are also outside the frozen study.
A further check makes empty-but-valid extraction explicitly unverified rather than
silently presenting an empty set of requirements. None of these working-tree fixes
has been promoted as a validated accuracy release.

## Remaining work

Finish the fresh comparison of the repaired adapter. Preserve the earlier incomplete
20B schedule for resumption when its quota permits. Expand the customer-language and
evidence challenges before making a pilot accuracy claim: the synthetic baseline is
too easy, while the original human queries expose major gaps in semantic coverage.
Keep both introduced errors and corrected errors when judging a new Approv release.
Do not promote v3 as an accuracy improvement on the evidence in this report.

Groq enforces both short and longer quota windows; the account's actual responses
govern pacing. A long retry is a provider-capacity block, not a model accuracy result.
See [Groq's rate-limit documentation](https://console.groq.com/docs/rate-limits).
No billing settings or additional credentials were applied. Qwen 3.6 27B was checked
as a separate fallback, but the account rejected the 1,226-token initial observation
against a 1,000-token/minute limit. It did not reach held-out testing. A separate
GPT-OSS 120B capacity check succeeded; its completed comparison has its own model
manifest and must not replace missing 20B outcomes.

Local evidence lives under `data/cache/shopping-study/`: frozen packs, archived
`runtime-*` code, per-session JSON records, interpretation records and generated
reports. These files are ignored by Git. Preserve them separately for reproduction;
this document alone is not the complete audit artifact.

To resume the latest interrupted schedule with its original code and settings:

```powershell
python data/cache/shopping-study/runtime-confirmation-v4/run_study.py --pack data/cache/shopping-study/esci.json --output data/cache/shopping-study/gpt120b-confirmation-v4 --split heldout --arm all --version v3 --model openai/gpt-oss-120b --case-ids esci-87001,esci-91618,esci-39975,esci-45798,esci-86068
```

This preserves the recorded quota failure and finishes only the six missing sessions.
It does not rerun failed outcomes until they become successful.
