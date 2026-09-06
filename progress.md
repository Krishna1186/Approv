# progress.md — Approv

Tracking document. Reflects actual state, not intended state. Updated at the end of every session.

Last updated: 2026-09-06

---

## Where we are

**Stage: B — reframed 2026-09-06. Blocked on `data/guideline.md`, now being written from
the founder's answers in session (founder supplies every answer; Claude transcribes).**

**The reframe, 2026-09-06.** The check is no longer "does this product match the user's
intent." It is **"did the agent read this product page correctly, and from which field."**
Ground truth moves onto the merchant's own page, so labelling stops being a judgement call
about whether a sandal is a shoe. Category for v1 changed from footwear to **quick commerce
(incl. groceries)**, then broader e-commerce. Needs DR 0016 before any decision-path code
(§4.8).

Stage A is resolved without an audit. The prior repo is
`Krishna1186/payment-agent-harness` (Python, ~30 KB, last pushed 2026-08-24). Founder's
call, 2026-09-03: it was a different idea — the shopping/search agent itself, with no
intent verification and no security layer, which is the core of Approv. It is **not**
the ancestor of this codebase and nothing is being carried across as code.

One artifact is worth salvaging as *input*, not as code: `docs/threat-model.md`
(~9.8 KB) already enumerates prompt-injection sub-cases against a payment-capable
agent. It is a skeleton by its own admission, but it is a head start on the §6
attack-surface taxonomy when that gets written. Everything else is scaffolding.

TRL 3 claim as of today: **nothing demonstrated.** No engine, no gold set, no number.

---

## Stage ledger

| Stage | Definition of done (§10) | State |
|---|---|---|
| A — Audit | Every surviving line explainable; every deletion justified | **Closed 2026-09-03** — no subject to audit; prior repo declared non-ancestral, nothing carried across |
| B — Category, guideline, gold set | Cohen's kappa computed and > 0.6 | **Active.** Category changed 2026-09-06 to **quick commerce / grocery**, locale `en-IN`. `data/guideline.md` being written from the founder's in-session answers. Corpus source materially easier under the reframe — a pair needs a public product page plus a real agent's claim about it, not a merchant's private catalogue |
| C — Semantic stage + first number | One number with denominator, category, model version, prompt version, date, Wilson interval | Not started — gated on B |
| D — Evaluator, receipts, harness, scale | Stranger verifies a receipt with a public key; CI fails on metric drop; behaviour distribution + metamorphic pass rate | Not started — gated on C |
| E — Surfaces | End-to-end block → check → confirm → debit in sandbox + 60s recording | Not started — gated on D |
| Merchant plugin | — | Not started — explicitly worthless until C produces a number |

---

## Artifacts that exist

| Artifact | Path | State |
|---|---|---|
| The contract | `CLAUDE.md` | Committed |
| This tracker | `progress.md` | Committed |
| Annotation guideline | `data/guideline.md` | **Being rewritten 2026-09-06 for the reframe.** The 12 intent-matching questions are largely obsolete; the new set is about *which field a claim was read from*. Every answer is still the founder's, given in session; Claude transcribes and invents nothing (§3, §5). Critical path |
| Attack-surface taxonomy | — | Does not exist. §6 says write it now; costs thinking, not build time |
| Decision records | `docs/decisions/` | **Closed:** 0001, 0002, 0003, 0007, 0010, 0011. **On hold:** 0006. **Open:** 0004, 0005, 0008, 0009, 0012 (holdout caps), 0013 (Stage E), **0014 (escalation ladder + kill thresholds)**, **0015 (corpus route)**. 0015 is the critical path |
| `learnings.md` | `learnings.md` | **Created 2026-09-05.** Claude writes the factual part of each entry and logs founder corrections; the three reflection lines per session are the founder's and are currently blank |
| Gold set | `data/labelled/` | Empty. Founder-labelled only, never AI-generated (§5) |

---

## Open questions blocking progress

1. ~~**Does a previous codebase exist to audit?**~~ **Resolved 2026-09-03** — no. Standing start.
2. ~~**Which category gets the first gold set?**~~ **Resolved 2026-09-03, changed 2026-09-06** — now **quick commerce / grocery** first, per the reframe; footwear deferred. Founder's constraint is speed of onboarding new categories, not depth in one. The answer is that comparison operators are per *type* (quantity, enum, integer count, money, date), not per category, so a new category supplies a schema and a criticality table rather than new logic. Original 2026-09-03 rationale, now superseded: **footwear / apparel** first. Exercises directed taxonomy, colour lattice, price bound and the size-silence rule in a single query. Grocery second, for dimensional quantities. Engine is category-parameterised so the second vertical is data, not a rewrite.
2a. ~~**How is §8 handled?**~~ **Resolved 2026-09-03** — §8 amended in `CLAUDE.md`. Claude may write a component body only after the founder has written its signature and its test. §4.2, §5 and §0's no-build-ahead rule are untouched.
3. **Which catalogue source?** Researched 2026-09-05. **Narrowed, not closed — now blocks Stage B, not just Stage D.**

   | Candidate | Licence | Verdict |
   |---|---|---|
   | Amazon Berkeley Objects (147k listings, 18 metadata attributes) | **CC BY-NC 4.0** | **Rejected.** Non-commercial. A gold set that prices a commercial indemnity (DR 0010/0012) is commercial use, whatever it is called internally |
   | Kaggle Myntra / Flipkart product dumps | Kaggle licence field is meaningless here | **Rejected.** Derived from scraping those sites; the upstream ToS was violated before the file reached Kaggle, and that does not launder |
   | UT-Zappos50K, DeepFashion, like.com Shoes | research/non-commercial | **Rejected**, same reason as ABO |
   | Clothing16K | CC0 | Possible, but images plus labels — not catalogue listings with attribute metadata, which is what a comparison needs |
   | **ONDC protocol specs + retail taxonomy** | open source, github.com/ONDC-Official | **Use for the ontology.** India-native, government-backed, publicly published. Directly relevant to DR 0003/0011 node structure. Catalogue *data* over ONDC belongs to sellers and needs network participation |
   | **One merchant partner's catalogue, with written permission** | negotiated | **Recommended for the gold set** |

   **The reframing that resolves this:** the gold set is 300–500 pairs, not a dataset. It does not need a corpus — it needs 300–500 listings we may legally use. A single merchant partner supplying their own catalogue under a written data-use term is clean, needs no licence archaeology, and is a partner we need anyway for row 1 of DR 0010. The large unlabelled corpus (§5, Stage D) is a separate and later problem.

   *Founder action: secure one merchant catalogue permission, or confirm a CC0/ODbL source carrying real attribute metadata.*
4. **Who is the second annotator for the 10% kappa sample?** Kappa needs two humans. *Blocking Stage B's definition of done.*
5. **DR 0052 — confirmation-window timeout default per irreversibility class.** Referenced in §3 Stage E as already resolved, but the decision record is not in this repo. *Needs to be written down or restated.*

---

## Standing constraints (from CLAUDE.md — restated so this file stands alone)

- No code written by Claude unless the founder asks for code **in that message**.
- The evaluator is hand-written by the founder. Claude never writes evaluator logic (§4.2).
- Training and evaluation data is never AI-generated, augmented, or relabelled (§5).
- `evaluator/` imports nothing from `semantic/`; a test asserts it (§4.1).
- `unknown` and underspecified route to `confirm`, never `allow` (§4.4).
- Mark and verify are scored separately, never averaged (§4.7).
- No stage begins without explicit go-ahead (§3).

---

## Session log

### 2026-09-06 — Session 7 — REFRAME

**The product changed shape, for the better.** The check is now grounding rather than
intent matching: *did the agent read this page correctly, and from which field.* This
moves ground truth onto the merchant's own page, makes labelling objective, raises the
expected kappa, and demotes the taxonomy/ontology work (DR 0003, 0006, 0011) out of v1.
The provenance ladder becomes the main event rather than a caveat.

**Merchant-side reframe.** The old merchant pitch (human traffic, one-tap) is dead by the
founder's own call: on quick commerce people build carts, so per-product one-tap is
useless and often costlier. The new merchant pitch is *all agentic traffic to you is
verified*, sold on the returns and trust cost rather than on conversion.

**Channel fact-check (founder asked; verified against sources):**

| Channel | What the merchant actually receives | Verdict |
|---|---|---|
| Open-web agent | Identifying user-agent (`ChatGPT-User`, `OAI-SearchBot`, `PerplexityBot`, `ClaudeBot`) + the URL. Site-search query only if the agent used the merchant's own search; a direct product-page fetch carries no query at all. UA is self-declared | Partly true |
| Session control (agent drives the user's browser) | A normal logged-in session, typically indistinguishable from a human. Site-search box query if used | Query yes, agent-detection no |
| **UAP (NPCI)** | **Founder's assumption corrected.** UAP registers, verifies and authorises *agents* over UPI Circle delegation. It carries **identity, not intent**. Pending RBI approval | Do not design assuming intent arrives here |
| **AP2 (Google)** | Better than expected. The Intent Mandate carries a **Prompt Playback** field — *"the Agent's understanding of the User's prompt in natural language"* — signed, shared with the merchant, usable as dispute evidence | This is Tier 2 (DR 0008), and it standardises the *agent's paraphrase* as the record of intent, which makes DR 0005's fabrication problem a rail-level issue |
| **MCP (the one that matters)** | Typed tool arguments (`search(query, brand, pack_size)`), the exact server response, and the full call sequence | **Best channel.** Constraints arrive already structured, and agent-said-vs-agent-did becomes checkable with no model and no ontology |

Net: no channel ever delivers the user's own words. Tier 0/1 of DR 0008 survives the
reframe unchanged.

**New attack surface, not in the §6 taxonomy and to be added:** MCP tool descriptions are
text the agent reads, so they are an injection vector; and a server can change a tool
description after the agent approved it (rug-pull). A proxy sitting in front of a
merchant's MCP server is exactly where description hashing would catch this.

**DR 0016 pending** — the reframe, the graded score, and the MCP channel all touch the
decision path, so §4.8 requires one record before any code. One record, not five.

**Founder corrections #11 and #12** logged in `learnings.md` (two-axis field ladder;
seller advice may only downgrade).

**Still no engine code.**

### 2026-09-05 — Session 6

- **DR 0014 opened — the escalation ladder.** Founder challenged whether `confirm` defeats
  the product: if every ambiguity asks the human, agentic purchasing has gained nothing.
  Correct, and it exposed a conflation — `confirm` is a decision *state*, not a *recipient*.
  It resolves at one of four rungs: deterministically in `algebra/` (free), from the
  preference record (free), by the **agent re-picking** (milliseconds), and only last by a
  human. Only the `gate` call site ever reaches a person; `mark` means "no badge" and
  `verify` means "agent, pick again". Every DR written so far exists to widen rung 1.
  Three separate kill thresholds to be set **before** Stage C measures anything.
- **DR 0015 opened — the corpus deadlock.** Founder: cannot get vendor data without a
  pilot, cannot pilot without an MVP, cannot build an MVP without data. The loop holds only
  if the first partner must be a large marketplace and the first shipped thing must be the
  gate. Four routes; recommendation is **C in parallel with A** — the DR 0007 coverage
  report is computable from a merchant's catalogue alone, with no engine and no accuracy
  number, which converts the ask from "trust my unproven product" into "send me your feed
  and I'll tell you where your listings are incomplete."
- Created `learnings.md` and the `data/guideline.md` skeleton (12 questions, no answers).
- Still no engine code.

### 2026-09-05 — Session 5 — DESIGN FREEZE

Eleven DRs, 2,162 lines of design, zero lines of code and zero labelled pairs. Every
commercial path now depends on one missing artifact: an accuracy number with a
denominator and an interval. Design is frozen at its current state.

**Founder decisions:**
- **Guarantee structure:** receipts and confirmation gate first; **no guarantee quoted,
  priced or described to anyone until Stage C produces a number.** Then a capped B2B
  indemnity to the *agent operator*, who makes their own user whole. Approv never faces a
  consumer, keeping it a commercial warranty rather than a regulated financial promise.
- **Sequencing:** freeze design, execute Stage B.

**Closed:** 0001 (superseded by 0007) · 0002 (three stages + `types/`) · 0007 (floor as
precondition) · 0010 (agent operator is the buyer) · 0011 (facets independently optional).

**Opened:** 0012 loss data and underwriting basis · 0013 confirmation surface.

**The point in 0012 that decides whether underwriting is possible at all:** outcomes are
observable only for transactions we allowed, so the false-allow rate measured naively is
computed over a sample selected by the mechanism being evaluated. This is the
selective-labels problem from consumer lending. It requires a **capped random holdout** —
deliberately releasing a small, value-limited fraction of would-be-refused transactions
and eating the losses as the price of calibration data. Without it no quoted price is
defensible.

**On the confirmation surface (0013):** the founder's UPI-invoice concept is the right
surface, corrected on four points — it must sit *before* the debit or no consent is
obtained and the liability transfer is given away free; it must show attributes rather
than a score, because a score invites a rubber stamp and "they were shown 94%" is not a
defence; a nudged or auto-confirming screen is strictly worse than no screen at all; and
the indemnity is second-loss, after the ordinary merchant return recovers what it can.

**Still no engine code, and correctly so** — §3 gates Stage C behind Stage B.

**Catalogue source researched (Step 4).** Every standard footwear/apparel research
dataset is non-commercial or scrape-derived and therefore unusable under §5 — ABO is
CC BY-NC 4.0, and the Indian Kaggle dumps are Myntra/Flipkart scrapes. See open question
3 for the full table. The resolution is that a 300–500 pair gold set is not a dataset
problem: one merchant partner's own catalogue under a written data-use term is clean, and
that partner is needed for DR 0010 row 1 regardless. ONDC's published retail taxonomy is
separately useful as input to the ontology.

**Next action is the founder's:** answer Q1–Q12 in `data/guideline.md`; pick a route in
DR 0015; set the three kill thresholds in DR 0014.

**Agent-search sourcing (founder question, 2026-09-05):** usable for *discovery* of
candidate products, not for *ground truth*. A search snippet may paraphrase or omit
attributes, and a wrong attribute in the gold set poisons the only asset that can produce
an accuracy number. It also biases the corpus toward products agents pick, which is the
opposite of the near-miss construction §3 requires, and it circularly contaminates any
later benchmark of that same agent. Attributes must be verified against the real listing.
The distinction maps onto §5's two corpora: agent-sourced data is acceptable for the large
*unlabelled* corpus (behaviour, self-consistency, metamorphic invariants — no ground truth
needed) and not for the gold set.

### 2026-09-04 — Session 4
- **DR 0007 opened — the verification floor.** Founder's concept: some fields are *preconditions*, not optional attributes. Footwear cannot be verified without a size. A request lacking one was never verifiable rather than uncertain, and that is a different heading from the merchant failing to publish data. Checkable before any model call. Closes DR 0001 toward reason codes and adds `FLOOR_NOT_MET`.
- **DR 0008 opened — and it invalidates part of DR 0005.** Founder: agents will not label provenance, we will never receive `PRIOR_CONVERSATION`, and we may never see the user's actual words — only the query the agent composed. Correct. Response is to tier what we honestly receive (0: observed query · 1: declared constraints · 2: mandate-anchored) and to fix the claim at each tier. Tier 0 verifies *the product against the stated query*, never "the user's intent". §2.8's preference record needs a human anchor that does not exist below Tier 2.
- **DR 0009 opened — monotone safety.** Founder asked whether Approv should be a lightweight agent. Rule proposed: a model may participate anywhere its worst case degrades toward `confirm` and can never move an outcome toward `allow`. Permits model-driven check selection; forbids a model resolving `unknown` into `satisfied`. The requested "mini-sandbox" is real and needs no model — per-request metamorphic self-checks are deterministic, cost microseconds, and can only downgrade confidence.
- **DR 0003 addendum, two more founder corrections.**
  - *Facet ordering:* asking whether form or use-case sits higher reveals a modelling error, not a missing answer. They are orthogonal facets; forcing them into one hierarchy is what manufactures the diamonds. Taxonomy is one DAG per facet.
  - *Cycles:* a visited set gives **termination, not cycle detection** — seeing a node twice is a diamond, not a cycle. Cycle detection needs the current DFS path (grey/black), and belongs in the build-time validator, not the payment path.
- Still no engine code.

### 2026-09-04 — Session 3
- **DR 0003 CLOSED.** DAG + multi-assignment + entity linking as a separate scored step. Taxonomy never self-edits: unrecognised terms go to a **pending queue**, approved **manually in batches**, each batch cutting a new taxonomy version.
- **DR 0004 amended** — the clarification/latency conflict resolved four ways: `mark` never asks (no badge is a valid output); precompute all ambiguity branches and only ask when they disagree; ask once per shopper rather than per purchase (§2.8); precompute merchant top-N offline so we are not in their render path at all. Option 3 upgraded from defer to recommended-for-`mark` once the cache key includes `snapshot_hash`.
- **DR 0005 amended** — founder raised the agent that legitimately knows more than the query (colour learned in a prior chat we cannot see). Resolved by attestation rather than verification: the agent declares `claimed_source`, we record and sign it, and a false attestation becomes the agent operator's liability. Plus: agents may supply SOFT attributes, never HARD ones, and may narrow a bound but never widen one. The §2.8 preference record doubles as the corroboration check.
- **DR 0006 opened** — one universal ontology, N per-locale lexicons with per-term readings. Answers the India "shoes means footwear" problem without forking the DAG. Adds `locale` to the §4.6 metadata every accuracy number must carry.
- Still no engine code.

### 2026-09-03 — Session 2
- Founder identified the prior repo (`payment-agent-harness`) and ruled it non-ancestral. Stage A closed.
- Target verticals fixed: **quick commerce and e-commerce**, in that priority order for the product, category for the first gold set still open.
- Founder asked for the intent verifier to be built. **Refused pending an explicit contract amendment** — §8 and §4.2. Named the rules per §0.
- Architecture for the verifier taught in-session (typed constraint algebra, dimensional quantities, directed taxonomic subsumption, provenance-weighted attributes, per-category criticality profiles, closed-vocabulary injection containment). No code written.
- Raised a design question for a decision record per §4.8: `unstated` (request was silent) and `unavailable` (product has no data) are currently collapsed into one field, but they attribute liability to different parties.
- **§8 amended** with founder's approval: Claude writes a body only against a founder-written signature and test. §4.2 (evaluator), §5 (data) and §0 (no build-ahead) untouched.
- **Category fixed: footwear / apparel** for the first gold set and the first criticality profile.
- Wrote **DR 0001** and **DR 0002**, both OPEN. §4.8 blocks decision-path code until they close.
- Still no engine code. Next action is the founder's: close the DRs, then §7 step 4 on the first operator.

**Founder corrections to Claude, same session — these are the December-test entries (§7):**
- **Taxonomies are DAGs, not trees.** A bulb sits under Lighting, Electronics, Decor and Interiors at once. Claude asserted a tree and claimed cycle-safety followed from it. Both wrong. Subsumption is reachability over a multi-parent DAG, acyclicity must be explicitly validated, and a visited set is still required at read time. → DR 0003.
- **Fail-open on timeout, because the marketplace will not wait.** Correct, and the constraint most verification layers learn only after a merchant rips them out. Claude added the asymmetry the founder had not separated: fail-open is right for `mark`, and a complete bypass at `gate`, where latency becomes an off-switch. → DR 0004.
- **Agents fabricate constraints the user never stated, and that is a security surface.** Independently derived the mirror of product-side provenance. Without it, §2.2 cannot attribute fault to the agent, because an invention and an instruction are byte-identical in the record. → DR 0005.
- Claude's counter, accepted: the "user types shoes but means sneakers" case is **not** a false negative — `subsumes(shoes, sneakers)` is satisfied, breadth in the request is permissive by construction. The real failure is surface terms that do not resolve at all ("joggers", "chappals"), which is entity linking, a different component. → DR 0003 §3.

### 2026-09-02 — Session 1
- Committed `CLAUDE.md` to the repo root.
- Created this tracker.
- Confirmed the repo was empty at start, so Stage A has no audit subject.
- **Did not write any engine code.** §0 — the founder has not asked for code.
- Next: founder answers open question 1.
