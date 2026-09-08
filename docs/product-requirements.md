# Approv: simple product requirements

Approved direction: 2026-09-08. This describes the product we are building, not a
claim that every feature exists today.

## Purpose

Make autonomous shopping safe enough for merchants and customers to adopt.
Check the customer's actual request, the agent's choice and the product evidence.
Explain errors so the agent can correct them. Improve Approv from verified outcomes.
Eventually offer financial protection for clearly defined mistakes.

## First customer

A D2C merchant, or an agent provider serving D2C merchants, that can supply the
original conversation, agent actions and product records. Start with one selected
SKU and a pack count. Later support baskets and general-purpose shopping agents.

## Features and implementation

| Feature | How it works | Benefit / practical limit |
|---|---|---|
| Original request checking | Preserve the conversation. Extract requirements with supporting text. Separate explicit requirements, preferences and unresolved questions. | Detect requirements lost or invented by the shopping agent. Extraction can be wrong and must be measured. |
| Product evidence | Adapters preserve source records, variant IDs, timestamps and field meanings. Display the evidence to the agent. | Catch wrong variants, quantities and unsupported claims. Missing evidence stays missing. |
| Repeatable comparisons | Typed rules compare supported requirements with product facts. Models may extract fields; the rules report findings. | Same inputs and rule version give the same comparison. This does not prove a catalogue is true. |
| Correction loop | Return all relevant discrepancies and missing information. The agent can inspect, search again, revise or abstain. | Improve the final choice without changing the underlying model. |
| Clarification | Identify unresolved requirements and ask the shopper when an integration supports replies. Never silently invent consent. | Preserve personal intent. First experiments record uncertainty/abstention; live clarification is a later integration. |
| Common integration contract | Original request, product snapshot and proposed selection enter one service. Findings and an evidence record leave it. Start with JSON API/command agents and the browser storefront. | Reuse the same core across websites, mobile apps and different agents. Each surface needs an adapter and access to evidence. |
| Protocol and payment independence | Keep verification separate from checkout/payment adapters. Add AP2, ACP, MCP and other adapters where needed. | No required payment rail. A protocol adapter cannot recover a conversation it never receives. |
| Audit record | Save inputs, model/rule versions, tool actions, evidence and findings. Hash and replay records; later add signed attestations. | Investigate what happened. Hashes detect changes; signatures establish attribution, not truth. |
| Approv improvement | Collect failures, correct choices and uncertainties. Resolve cases independently. Propose a change, run regression and held-out tests, then release a version. | Improvements benefit compatible clients. Raw agent feedback is not automatically a label. |
| Personal preferences | Store confirmed preferences with origin, scope, age and correction controls. Keep guesses separate. | Less repeated clarification without treating past behaviour as permission. Not implemented yet. |
| Financial protection | Define covered errors, evidence requirements, limits, funding and claims handling with a suitable partner. | Reduce adoption risk. No coverage or underwriting accuracy is promised by this prototype. |

## How we prove value

1. Run an unchanged shopping agent without Approv.
2. Add original-request interpretation and Approv feedback.
3. Compare baseline, generic review and Approv on cases excluded from development.
4. Improve Approv on development failures, freeze a new version, and compare versions.

Report correct choices, wrong choices, unnecessary abstentions, fixed mistakes,
introduced mistakes, actions, failures, latency and token usage. Keep all failed runs.
Same tasks, candidate inventory and action budgets across arms. Labels never enter
agent observations or Approv interpretation. Freeze the test set before improvement.
Report synthetic and human-labelled results separately. Repeated templates are not
independent real customers. A small gain is not automatically statistically reliable.

## Current experiment scope

Public ESCI queries and human relevance labels supply an external benchmark.
User-authorized synthetic requests add varied clarity, corrections, quantity and
near-miss stress cases. Preserve the authorship and answer-key method explicitly.
Production request extraction is evaluated output, not human ground truth.

First surfaces: API agent and local web storefront. The existing command/HTTP agent
adapters use the same actions. Mobile and third-party assistant integrations are
planned adapters, not completed integrations. No claim of equal coverage when an
integration withholds the original request or necessary product evidence.

## What this build delivered and where we are — 8 September 2026

**The baseline was built and run. Approv has not yet shown an overall accuracy
improvement.** This build produced a working comparison harness and exposed errors;
it did not establish the reliability needed to support a customer guarantee.

### What was done, how and why

| Work completed | How it works and why it was needed |
|---|---|
| Reviewed and repaired comparison rules | Fixed unit mismatches, decimal comparisons, pack counts versus total quantities, brand matching, conflicting claims and source scoping. These prevent incorrect checks from becoming misleading feedback. This did not replace the production payment evaluator. |
| Built the baseline and comparison runner | The agent searches a frozen inventory, inspects products, then selects a product/count or abstains. Separate runs add ordinary review or Approv feedback. Each uses the same inventory and action budget; answer keys stay hidden. No purchases occur. |
| Prepared public data and requests | Prepared 40 human-labelled Amazon ESCI queries and 120 fabricated requests against public Open Food Facts products. Requests include corrections, unclear sizes and quantity traps. These are 160 prepared cases, not 160 completed comparisons. Synthetic answers are kept separate from human labels. |
| Built original-request checks and revised them | Approv extracts requirements with supporting quotes, then compares supported fields with product evidence. Later versions tightened extraction and repaired narrow quantity/count cases. Changes were made manually from development failures; Approv does not yet learn automatically. |
| Added reusable agent connections | Implemented model API, native tool, command and HTTP adapters, plus a local browser storefront. Groq was tested live; other connections received local checks. This is a foundation for more surfaces, not completed integration with every assistant or protocol. |
| Added traces and independent scoring | Saved requests, tool calls, choices, errors, model versions, token usage and hashes. Separate scoring and replay scripts make results inspectable and retain failed runs. Hashes establish consistency, not that product information is true. |
| Tested and packaged the work | 153 software tests passed, and the local storefront was exercised in a browser. Saved reports, traces and code in an evidence bundle. Software tests check implementation behaviour; they are not customer accuracy results. |

### What the completed comparison found

One completed Groq GPT-OSS 120B study ran 10 held-out cases in four conditions:
**40 sessions total**. Each number below is correct final choices out of five;
failed sessions remain in the denominator.

| Cases | Without Approv | Ordinary review | Approv v1 | Revised Approv v3 |
|---|---|---|---|---|
| Synthetic product/quantity requests | 5/5 | 3/5 | 4/5 | 4/5 |
| Human-labelled product relevance | 2/5 | 2/5 | 2/5 | 1/5 |

Approv v1 helped correct one human-labelled choice after an uncertainty warning.
That isolated correction did not produce an overall gain. Revised extraction
produced more valid responses but did not improve shopping accuracy. Some failures
came from provider/tool errors or exhausted searches before Approv feedback.
The synthetic baseline was perfect on this small sample, leaving no room to show
improvement. Human relevance labels also do not establish complete customer intent.

### What remains unfinished

A later run using a repaired tool adapter saved 9 of 15 sessions before Groq's daily
quota stopped it; six remain. Another model's comparison was also interrupted.
Those incomplete groups cannot establish an improvement. Newer local fixes have
not all been evaluated in the completed four-condition study.

The next proof still needed is a sufficiently varied, completed comparison showing
fewer wrong choices than both the baseline and ordinary review. Meaningful intent
coverage, live clarification, automatic feedback-driven releases, production
mobile/general-assistant/protocol integrations and underwriting remain unfinished.
The current deliverable is measurement and debugging infrastructure, not validated
pilot readiness. Detailed evidence is in
[the study report](shopping-study-results-2026-09-08.md).

### What should have been handled better

I spent too long expanding and repairing the evaluation infrastructure and trying
provider/version combinations before delivering a small, useful comparison. I
should have bounded that work and reported the lack of demonstrated benefit sooner.
Groq quotas explain interrupted runs; they do not excuse the coding-assistant usage
or the failure to establish the requested accuracy improvement.

## What makes this worth buying

Measured improvement over an agent and its ordinary review process. Less integration
work. Specific corrections. An inspectable evidence trail. Over time, validated
failure knowledge and financial protection. Broad compatibility is a feature;
dependable verification and demonstrated improvements are the stronger advantage.

## Not promised now

Perfect understanding, absolute physical-world truth, automatic underwriting,
live purchases, full baskets, all product categories, or integrations with every
closed assistant. We expand only when the evidence supports the claim.
