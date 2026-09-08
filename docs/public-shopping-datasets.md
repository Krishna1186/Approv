# Public shopping evaluation sources

Inspected 2026-09-08. This is a source assessment, not an accuracy result.

**First choice: Amazon ESCI.** The authors describe manually annotated customer
query/product relevance judgments: Exact, Substitute, Complement and Irrelevant.
The release includes the corresponding product catalogue and query-separated
train/test splits. Its repository declares Apache-2.0.
[Source and download instructions](https://github.com/amazon-science/esci-data).

The original examples Parquet, README, LICENSE and NOTICE are cached unchanged in
`data/cache/public-shopping/esci/`. `manifest.json` records upstream revision
`7916cdf6ab75a462e77f20ab40428a10923998d5`, URLs, retrieval time and SHA-256 hashes.
The Parquet hash matches the upstream Git LFS object ID. Local inspection finds
2,621,288 judgments; the reduced English test partition contains 8,956 queries and
181,701 judgments. These are measured file counts; the README prose has a different
overall judgment count. `inspection.json` preserves these checks.

The separate product catalogue is also cached unchanged (1,108,857,465 bytes), with
its SHA-256 checked against the upstream Git LFS object ID. No source records have
been converted into harness cases or gold labels.

Local join validation finds 1,814,924 catalogue rows. All 164,900 distinct products
referenced by the reduced English test partition exist with nonempty titles and
unique `(product_locale, product_id)` catalogue keys. That partition has no duplicate
query/product judgments or conflicting labels. One query has no Exact-labelled
candidate; this alone does not label abstention as correct. Counts are recorded in
`inspection.json`.

For Approv, this supports a **search relevance experiment**, with these necessary
adaptations:

- Preserve original query text, IDs, split and labels. Keep labels outside agent
  observations and Approv evidence. Do not use accepted products to infer intent.
- Use the matching ESCI catalogue. The existing Open Food Facts inventory has
  different products, so its IDs cannot inherit these judgments.
- Restrict each query to its judged candidate pool, or report unjudged selections
  separately. An absent label does not mean an irrelevant product.
- Keep E/S/C/I outcomes distinct. A substitute is not automatically a wrong purchase
  or an acceptable fulfillment; that depends on the task being measured.
- Define and freeze request extraction independently of labels. ESCI does not give
  the typed request constraints our current shopping session expects. Empty
  constraints would not exercise Approv meaningfully, and deriving constraints
  from the answer key would leak gold information.
- Preserve the official test split and declare any category or constraint filtering
  before running models. Broad public search performance does not establish a
  particular merchant's purchase correctness or third-party guarantee.

**Browser workflow source: WebShop.** Its authors provide 12,087 crowdsourced
instructions, a simulated storefront and human demonstration downloads.
[Repository](https://github.com/princeton-nlp/WebShop).
The environment's reward uses fuzzy attribute/option matching and category/title
heuristics; its human-goal loader also appends generated price limits. Treat those
rewards as benchmark-specific diagnostics. They are not independent human verdicts
on every possible purchase. Preserve the original instructions if using them as
human-authored cases.
[Goal and reward implementation](https://github.com/princeton-nlp/WebShop/blob/master/web_agent_site/engine/goal.py).

**Further research source: ShoppingComp.** The English ground-truth file has 97
records; direct inspection finds 42 labelled Expert Questions and 55 Synthesized
User Questions. Another file contains 48 safety tasks. The dataset declares MIT.
[Dataset card and files](https://huggingface.co/datasets/huaixiao/ShoppingComp).
Its paper describes human verification of product lists, but also LLM-assisted
rubric creation and model-based scoring. Even the expert-question subset therefore
does not establish wholly human authorship of every rubric. Keep it outside the
project's strictly non-AI-augmented gold set. It may inform a separately disclosed
benchmark later; do not copy its judge scores into Approv accuracy claims.
[Collection and evaluation methods](https://arxiv.org/html/2511.22978v2).

**Agent connection.** The current compatible ChatAgent can use Groq with
`--endpoint https://api.groq.com/openai/v1` (the adapter appends `/chat/completions`)
and a `GROQ_API_KEY` environment
variable. A Groq account key is required for that provider, not for the harness
itself. Local, command, HTTP and browser agents remain alternatives. Verify the
account's available model and limits before selecting the pilot configuration.
[Groq compatibility documentation](https://console.groq.com/docs/openai).

Once connected, first run a bounded connectivity test, then a frozen experiment
with baseline, generic review and Approv arms. Record actual model identity,
failures, actions, token usage and traces. No real-agent accuracy run has been
performed against these sources yet.

**Groq preflight, 2026-09-08.** The user configured a test key in the Windows user
environment. The models endpoint authenticated successfully. One model request
through the existing ChatAgent using `openai/gpt-oss-20b` returned a schema-valid
search action for an unchanged ESCI training query. Provider usage was 307 prompt
tokens and 107 completion tokens (414 total). This checks authentication and action
serialization only; it does not measure completed shopping or Approv improvement.
The credential was not printed or written to the trace. The local trace is
`data/cache/provider-preflight/groq-20260908T133245Z.json`.
