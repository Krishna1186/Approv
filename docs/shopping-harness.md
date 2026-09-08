**Traceable shopping experiments**

The harness gives an agent a shopping request and a frozen inventory,
records its search/inspection/selection actions, and compares outcomes across three
isolated runs. It supports API models, local model endpoints, command-line agents,
operator gateways and a local browser storefront. It does not require a particular
agent framework.

**What was implemented and why**

`approv/harness/shopping.py` owns the merchant simulation. The agent can search,
inspect a product, select one SKU with a sale-unit count, or abstain. The inventory is
fixed; selection never places a real order. Search uses deterministic lexical ranking
and a stable product-ID tie-break, with pagination over the full inventory. This is a
controlled test search backend, not a replica of a particular merchant's ranking.

The original typed-case mode supplies the request and author-specified constraints
to every arm. The original-request study below hides those constraints: only Approv
interprets the request privately, and that interpretation is evaluated rather than
assumed correct. A typed case also declares `quantity_scope`:
`per_sale_unit` compares the amount in one SKU pack; `cart_total` multiplies net mass,
net volume, price and component count by the selected number of packs. `unit_weight`
and `unit_volume` always describe a component inside one pack. `requested_units`, when
supplied, checks the number of sale units separately. Search annotations assess that
requested count, or one sale unit when it was unspecified, and disclose that count.

The current task is **one selected SKU**, optionally several sale units. Multi-SKU
baskets, live stock changes, shipping/tax totals and substitutions after checkout are
not simulated. OFF does not supply reliable price or stock data for this experiment;
the importer does not invent either. A generic Inventory can carry trusted typed price
evidence, and the algebra supports currency-aware money equality and numeric bounds.

The arms are:

| Arm | Behavior |
|---|---|
| `baseline` | Original agent; first valid selection is final. |
| `blind_review` | Original agent gets a fixed number of generic review opportunities. |
| `approv` | Same review opportunities, with Approv at the selected surface. |

All arms have the same maximum number of actions, inventory, constraints and search
ordering. Actual calls/tokens can differ and are reported. Every run uses a fresh
adapter instance. Case/arm execution order is randomized with a recorded seed.
`--surface mark` annotates search and inspection results without reordering them;
selection review remains generic. `--surface verify` leaves search results untouched
and supplies Approv findings during selection review. Run these separately.

The report provides both Approv minus baseline and Approv minus blind review. The
second comparison controls for the generic review opportunity; it does not magically
remove every experimental bias. The experiment uses whole independent sessions,
rather than forking one shared initial answer, so stochastic variation remains.

**Prepare the public inventory**

Python 3.11+ and Pydantic 2 are required; pytest is used for validation. The repository
declares these in `pyproject.toml`.

From the repository root in PowerShell:

```powershell
python scripts/run_shopping.py import-off data/cache/off_india_raw.json --output data/cache/shopping-inventory.json --captured-at (Get-Date).ToUniversalTime().ToString('o')
python scripts/run_shopping.py schemas --directory data/cache/shopping-schemas
```

The timestamp above records when this cached inventory is frozen/exported. It does
not assert that OFF was freshly fetched. Preserve the original data source and capture
information when available. The importer records source attribution, the licence,
raw records, extracted evidence and exclusions. The existing 599-record snapshot
imports 548 products; 51 records lack an ID or title. No shopper requests, accepted
choices, prices or inventory availability are generated.

Evidence profiles are assigned by trusted loader code. OFF brand aliases remain
distinct complete names. A title is candidate prose evidence and does not count as a
resolved published brand for coverage. Multipacks preserve aggregate amount, per-unit
amount and count. Missing fields remain missing.

**Author requests and a separate answer key**

```powershell
python scripts/run_shopping.py author --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --gold data/cache/shopping-gold.json
```

This interactive command asks the human for a request, typed constraints, quantity
scope, accepted product-ID/unit-count pairs, and evidence notes. It records those
answers; it does not infer or generate them. It backs up existing files before adding
a validated case. Inspect the inventory and the source evidence before labelling.
The JSON schemas describe all supported types. Repeat to add cases, or author the
JSON files directly using those schemas.

For direct authoring, cases are an array of `ShoppingCase` objects. Each contains
`id`, `request`, `constraints`, `author`, `cluster`, and optional quantity settings.
Use a shared cluster ID for related requests/products. GoldSet is a separate object
with `inventory_hash`, `label_method: "human"`, provenance, and annotations. Each
annotation binds to a `case_hash` and identifies exact accepted `(product_id, units)`
outcomes, whether abstention is correct, the annotator, and evidence notes. The
`validate` command prints the hashes needed when authoring directly.

```powershell
python scripts/run_shopping.py validate --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json
python scripts/run_shopping.py validate --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --gold data/cache/shopping-gold.json
```

Write the rubric before the held-out labels. Separate development cases from held-out
cases; an experiment's gold must cover exactly its cases. Include valid choices,
near-misses, unavailable requirements and genuinely correct abstentions. Have another
human inspect disagreements and critical labels. A public field is evidence to inspect,
not automatically physical-product truth. The software can validate label structure
and snapshot binding; it cannot authenticate the declared human authorship.

Gold is never a parameter to the execution engine and never appears in observations
or browser endpoints. Keep it outside an external agent's accessible workspace.
Command/gateway adapters are trusted integration code: this harness does not sandbox
their filesystem or prevent a malicious adapter from independently reading an answer
key. API models receive only the serialized observation.

**Run an API or local model**

Use the endpoint and model available to your account. No model or provider is assumed
to be free. Keys are read from the named environment variable, not CLI literals or
trace files. Live Groq runs use the configured test credential; results and limitations
must be assessed separately from local transport tests.

```powershell
python scripts/run_shopping.py run --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --gold data/cache/shopping-gold.json --transport compatible --endpoint http://127.0.0.1:11434/v1 --model YOUR_LOCAL_MODEL --max-actions 12 --surface mark --output data/cache/shopping-run.json
```

For a hosted compatible endpoint, replace `--endpoint` and supply, for example,
`--api-key-env GROQ_API_KEY` with the appropriate variable for your configured
provider. The adapter supports `--token-parameter max_completion_tokens` for models
requiring that field; other compatible endpoints may require `max_tokens`. Temperature
is omitted unless explicitly supplied. Compatibility is a transport contract, not a
claim that every model supports identical parameters. The schema is included in the
prompt and returned JSON is validated locally. [Official Chat Completions reference](https://platform.openai.com/docs/api-reference/chat/create)

For Gemini use `--transport gemini --endpoint
https://generativelanguage.googleapis.com/v1beta --model YOUR_MODEL --api-key-env
GEMINI_API_KEY`. The adapter uses header authentication and records the returned model
version and usage. [Gemini generation API reference](https://ai.google.dev/api/generate-content).
Use `--transport compatible_tools` for native function calls. The adapter preserves
tool-call IDs and reconstructs assistant/tool turns for review loops.
The latest adapter exposes `confirm_selection` after review and maps it back to the
common `select` action. This makes the outstanding confirmation explicit. Historical
study archives keep their original tool names; their results do not validate later
adapter revisions.
The Gemini and compatible adapters have local transport tests; run
a small real preflight on the chosen account before a full experiment.

The general runner has no implicit retries, budget escalation or response cache.
The study runner below permits two recorded retries for HTTP 429 only when the
provider supplies a wait of at most 60 seconds. Empty, malformed, truncated, timed-out
and exhausted rate-limited calls become explicit
operational failures. The default request timeout is 45 seconds; maximum configurable
timeout is 60 seconds. Use `--max-tokens` and `--max-actions` to bound the run. Failed
actions do not become fabricated UNKNOWN answers. The legacy brand diagnostic retains
its existing token escalation, with corrected cache identity and response validation.

**Connect any operator through an adapter**

For a local executable:

```powershell
python scripts/run_shopping.py run --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --transport command --command-json '["python","C:/path/to/your_agent_bridge.py"]' --output data/cache/command-run.json
```

One JSON observation arrives on stdin; return one Action JSON on stdout. Diagnostics
belong on stderr. The command is launched as explicit arguments with `shell=False` and
a timeout. The full observable history is included in every request, so the bridge
need not retain state. Do not let it retain hidden context across experiment sessions.

For a user-managed gateway, use `--transport http --endpoint
http://127.0.0.1:PORT/action`. It accepts the same observation as a JSON POST and returns
one Action. HTTPS is required for non-loopback endpoints. New operators need only
translate their native tools/actions into this protocol; no engine changes are needed.

Actions are `search` (query and offset), `inspect` (product_id), `select` (product_id,
units), or `abstain` (optional reason). Unknown keys are rejected. Evidence, certainty,
source profiles, labels and relaxed constraints cannot be submitted as action fields.
An agent must have seen a product through search/inspection before selecting it.

**Run an agentic browser**

```powershell
python scripts/run_shopping.py serve --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --agent-name YOUR_BROWSER_AGENT --surface verify --output data/cache/browser-run.json
```

Open `http://127.0.0.1:8765/`. The storefront presents each task, searchable products,
source fields, sale-unit input, selection and abstention. The same session engine
records browser actions. Browsers need no access to the gold file. There is no native
MCP/ACP/AP2 integration in this change; bridges can call the HTTP protocol.

For a programmatic browser/operator bridge, `POST /task` with `{}` returns an opaque
session token and observation. `POST /action` with `{token, action}` returns the tool
response and updated observation. Repeat until terminal, reset the agent context,
then request the next task. A selection review is not terminal; the agent must select
again or abstain. `/task` returns the active task while it is unfinished. Old tokens
cannot act on another session. After all arms complete, the experiment is written to
disk. There is no endpoint for other arms' results or gold labels.

The external operator must reset memory/context between tasks. The server cannot
enforce that inside an opaque browser agent. Record the browser model/version and
isolation procedure alongside the artifact before treating the run as comparable.
The server binds only to loopback, checks Host/Origin, limits request bodies, and
renders product text with textContent. It is a local research surface, not a hosted
multi-user service. Stop it with Ctrl+C.

**Read and verify the result**

```powershell
python scripts/run_shopping.py report --inventory data/cache/shopping-inventory.json --cases data/cache/shopping-cases.json --gold data/cache/shopping-gold.json --experiment data/cache/browser-run.json --output data/cache/browser-report.json
```

API/command runs write this report automatically as `<output>.report.json`. Without
gold, the report contains behavior only: selected/abstained/error/exhausted counts,
action counts, session latency, and provider token usage when available. Unknown
monetary cost is null, never silently treated as zero.

With gold, success is exact membership in the human's accepted product-ID/unit pairs,
or an explicitly correct abstention. This scorer imports no Approv comparison operator.
Every case stays in the denominator, including agent errors and exhausted budgets.
The report includes wrong selections, task success, descriptive Wilson intervals,
paired improved/regressed counts, and an exploratory cluster-bootstrap interval for
the effect. Degenerate/insufficient-variation intervals are null. These are small-sample
diagnostics, not population assurance. The public sample and authored request mix still
limit generalization, and the declared cluster IDs need human care.

Each action and actual response is snapshotted and hash-chained. Source-file hashes,
Python and Pydantic versions are bound to each session. Replay requires the recorded
implementation/runtime, so preserve that checkout and dependency versions. The retained manifest
binds inventory, cases, configuration, schedule and complete result contents. Report
generation replays every tool response and terminal outcome against those inputs.
Editing a result or truncating a trace without matching the retained manifest is
detected. A separate session checkpoint is written as each session completes. Output
files are exclusive-created so reruns cannot overwrite evidence accidentally.

These hashes establish consistency against a retained manifest, not signer identity.
Someone able to rewrite both the data and its manifest can manufacture another valid
artifact. Retain an independent manifest/checkpoint for an audit. Cryptographic signing,
third-party witnessing and a payment evaluator remain separate work.

**Validation and limitations**

Run `python -m pytest -q -p no:cacheprovider`. The tests include the review
counterexamples, independent scorer behavior, all transports, public-loader behavior,
quantity scope, equal action limits, label isolation, malformed responses, replay and
a complete external HTTP run. Their artificial fixtures are software tests, not an
agent accuracy corpus or a product-improvement claim.

The implementation uses deterministic comparison because reproducible arithmetic and
identity rules are inspectable. It keeps uncertain prose unresolved because a token
overlap would otherwise invent support. It uses a protocol rather than an agent
framework so the transport can change without changing the task or scorer. It uses
separate human labels rather than Approv's own findings as the answer key to avoid
measuring agreement with itself. These choices improve the experiment's validity;
only actual independent runs can establish whether Approv improves an agent.

**Original-request study and Approv versions**

Install optional dataset support with `python -m pip install -e ".[study]"`.
`scripts/prepare_study.py --help` describes the source paths. It freezes sampled ESCI
human relevance queries and, separately, 120 synthetic requests over the cached OFF
inventory. Synthetic generation is explicitly authorized for this experiment; see
[DR 0018](decisions/0018-original-requests-and-synthetic-experiments.md).
Source records are public evidence, not independently verified physical stock.

The study sends the shopping agent only the original request and observed tool
results. Approv's interpreter receives the request and supported field schema, never
the answer key. Version v3 additionally checks literal product names and quantity
phrases against the public catalogue vocabulary. Scoring happens after each session
using separate source labels or explicitly documented synthetic answer rules.

```powershell
python scripts/freeze_study.py --help
python scripts/run_study.py --help
python scripts/analyse_study.py --help
python scripts/replay_study.py --help
```

Freeze a runtime before a run so concurrent source edits cannot change its replay
identity. Point the archived `run_study.py` at a frozen pack, choose `--split dev` or
`heldout`, and set `--arm all` to compare baseline, generic review and Approv. Select
case IDs before looking at their outcomes. Use a new output directory for each
version. Resume only with the identical command; completed results remain retained.
The runner reads `GROQ_API_KEY` from the process environment, falling back to the
Windows user environment. Never put the credential in a command or result file.

For a version comparison, keep the same archived shopping agent, pack and action
budget; rerun only `--arm approv --version v3` into another directory. Then run
`python scripts/analyse_study.py BASE_DIRECTORY --approv-folder V3_DIRECTORY`.
The report rejects mismatched agent/configuration manifests. Replay with
`python scripts/replay_study.py --pack PACK --runs DIRECTORY --archives ARCHIVE_PARENT`.
Add `--pack PACK` to the analysis command to verify saved scores against the answer
key and compare first proposals with final outcomes. Export local evidence with
`python scripts/export_study.py output/study-evidence.zip`; retain the separate
manifest outside the writable run directory. New study manifests also bind the
observation driver file hash. Earlier archived runs predate that additional binding.

The current versions are manually reviewed Approv releases: v1 extracts requirements;
v2 constrains supported fields and extraction format; v3 repairs narrowly supported
literal product/count/quantity interpretations. They do not train the shopping model.
There is no automatic production learning or release pipeline yet. A useful release
must improve independently scored outcomes, not merely reduce parsing errors.

Prepared task counts are not executed sample sizes. Report incomplete schedules,
provider failures, extra interpretation tokens and synthetic template limitations.
Human ESCI labels judge relevance, not quantities or purchase satisfaction. Five
synthetic templates cannot establish broad customer accuracy or an underwriting rate.
