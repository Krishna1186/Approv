# DR 0018: Original requests and disclosed synthetic experiments

Date: 2026-09-08. Authorized by the user's current instruction to write the PRD,
run baseline and Approv experiments, fabricate varied requests if needed, and work
autonomously. This supersedes the local no-synthetic-data restriction for this task.
It does not authorize disguising generated labels as human labels.

The product checks original customer requests, not only agent-supplied fields.
The experiment must keep typed answer constraints out of the agent's input.
Approv may extract supported requirements from the request using its own versioned
model/prompt. Store extraction, provenance and costs separately; no answer labels
or accepted SKU lists may enter extraction. Unsupported intent remains unverified.

Expose public product detail fields through the shared session contract so API and
browser agents can inspect the same source evidence. Keep internal raw records and
answer labels separate. Preserve existing manually-typed-constraint experiments.

Use two distinct sources: original ESCI queries with original human relevance labels;
and explicitly synthetic stress requests with separately recorded answer construction.
Do not merge their accuracy claims. Candidate pools contain only judged ESCI products.
An E/S/C/I label measures relevance, not subjective satisfaction or pack-count intent.

Freeze development and held-out splits before tuning. Retain unsuccessful runs and
negative effects. v2 changes come from development errors only. The end condition is
an honest measured comparison, not a predetermined positive result. If provider quota
blocks progress, retain checkpoints and do not repeatedly spend on rejected requests.

Development findings: v1 emitted unsupported fields and sometimes exhausted its
output budget. v2 uses JSON mode and lower extractor reasoning effort but incorrectly
mapped a total amount to per-pack weight. v3 adds conservative literal checks for
explicit per-pack/total wording, corrected sale counts and exact published product
names. The name resolver may use public catalogue vocabulary, never relevance labels
or accepted-choice lists. This clarifies the earlier products restriction: the model
still receives only the request and supported attribute names; a deterministic name
resolver uses public titles. Synthetic template performance must not be presented as
proof that these rules generalize to all customer language.

The GPT-OSS run reached a provider quota pause. A separately reported Qwen 3.6 27B
study is permitted under the same test credential and frozen task rules. Its initial
development preflight rejected extractor JSON. Qwen's documented non-thinking mode
is therefore used for every extractor version; the shopping agent keeps the same
native tool settings across all arms. The model change is not pooled with GPT-OSS
results. `qwen-plan.json` records case selection before Qwen held-out outcomes.

The account's actual Qwen input limit was only 1,000 tokens/minute; its 1,226-token
initial request was rejected, so that model did not reach held-out evaluation.
GPT-OSS 120B passed the same credential's capacity check. `gpt120b-plan.json` records
a separate study on the reserved cases. Its results are also kept separate from 20B.

An outstanding development transport failure persisted with ordinary second-select
instructions. A distinct native `confirm_selection` function now maps to the shared
select action after review. One retained failed development continuation passed with
this change. It is a separately identified adapter revision, not a modification to
ongoing frozen held-out runs. The current studies do not prove its general reliability.
