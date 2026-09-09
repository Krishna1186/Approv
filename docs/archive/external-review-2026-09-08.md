**Approv external review — 8 September 2026**

Reviewed local commit `c76bd54ac4d808b6daa5e71d6df56ad4a1c05773`, including the external review prompt, core types, all three comparison operators, runner, feedback, OFF loader, coverage report, benchmark, provider adapters, tests, security register, and relevant decision records. The working tree was clean at initial inspection. Existing tests: `python -m pytest -q -p no:cacheprovider` → **79 passed**. Additional isolated, in-memory probes reproduced the failures below. These probes are software counterexamples, not labelled evaluation data or an accuracy measurement. This review ran no model benchmark and changed no product implementation. At final inspection, a concurrent change to scripts/run_benchmark.py added an HTTP User-Agent; it was left intact and does not resolve the benchmark findings below. File locations refer to the reviewed commit.

**Judgment**

The current evidence does not support a payments assurance company, a priced indemnity, or a moat based on independence. It supports a prototype of a commerce-specific checker whose commercial value remains unmeasured. The narrow product could be useful, but the pitch repeatedly promotes properties of representations into guarantees about the world: structured data becomes truth, authorship becomes liability, signed records become complete evidence, and deterministic comparison becomes a safe decision system. Those steps do not follow.

The strongest first customer is already identified in the amendment to DR 0016: a company operating its own shopping agent over its own inventory. That company can supply requests, cart actions, catalogue snapshots, and outcomes. It can also implement these checks itself. Approv must demonstrate that it saves that team enough work or prevents enough costly mistakes to justify buying. A signature is not a substitute for that result.

**1. Revenue: identify a budget owner and a measurable avoided cost**

Do not assume that agent operators escape all economic consequences because their terms disclaim liability. Support work, abandonment, repeated inference, lost repeat purchases, and engineering incident response can matter without indemnity. Conversely, a merchant processing returns does not automatically want to buy a verifier for an external agent it cannot instrument.

For the in-house-agent customer, sell a bounded investigation: identify size, quantity, brand, and substitution failures in recorded purchase sessions; attach the exact evidence and action to each finding; measure which findings the team accepts and fixes. The buyer hypothesis is the head of commerce engineering or the owner of the agent's conversion and support metrics. This is a hypothesis to test, not established demand.

Observability is a plausible delivery channel but an insufficient differentiation claim. Langfuse already supports deterministic code evaluation and custom scores on traces and sessions. An Approv finding can be a component inside an existing observability stack. Building another trace dashboard would require a separate reason to buy. [Langfuse evaluation documentation](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)

Use a customer-specific value calculation: accepted incidents prevented × avoidable cost per incident, plus investigation hours saved, minus verification cost, integration cost, and conversion lost to unnecessary intervention. Count the customer's avoidable cost, not the full retail value of every rejected basket. Measure false interventions explicitly. A checker that mostly requests confirmation can destroy its own savings.

My suggested commercial test: within a time-boxed discovery period, secure one in-house-agent partner willing to supply representative traces and pay for a bounded pilot. Agree on the success metric before analysing their data. If nobody will provide traces, identify an owner, or fund the result after seeing concrete incident examples, more operators and signatures will not resolve the demand problem. These are proposed decision criteria, not industry benchmarks.

**2. Grounding: useful, but the wrong headline for the selected first buyer**

Grounding proves support in an observed source under a specified interpretation. It does not prove that the physical product has that property, that the source applies to the purchased variant, or that the shopper wanted it. An agent can accurately describe the wrong product. It can also correct its wording to describe a bad substitution without correcting the purchase.

DR 0016's amendment already says the first customer's dominant failure is substitution and orders the checks CONSISTENCY → SATISFACTION → GROUNDING. The external prompt still leads with grounding. Resolve that contradiction before building the next demonstration. A demo that improves brand guesses from incomplete OFF titles is disconnected from the strongest proposed buyer.

The claim that intent is inherently unverifiable because every integration supplies only an agent paraphrase is too broad. A third-party tool often lacks the original request; an agent operator can instrument its own input and confirmation surface. Signed authorization can also bind explicit constraints without proving an entire person's mental state. Google's AP2 introduction describes signed intent and cart mandates. It is evidence that delegated authorization can be recorded, not that semantic correctness is solved. [Google AP2 introduction](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)

Likewise, a search for 5 kg followed by adding one 1 kg SKU is an observable change, not automatically an unauthorized purchase: the cart may contain five units, the user may have amended the request, or substitutions may be permitted. Consistency needs quantity scope, temporal ordering, supersession, and authorization context. Calling that check ambiguity-free merely moves the ambiguity into the adapter.

Use a bounded promise: “Approv checks selected cart attributes against recorded constraints and source fields, and preserves the evidence for each discrepancy.” Demonstrate fewer actionable errors on real sessions before expanding the promise.

**3. Independence and competition: there is no automatic external-auditor moat**

An independent company can produce a poor measurement; an internal team can produce a replayable, externally inspectable one. Independent assurance becomes valuable when someone relies on a recognized method, scope, governance process, contractual undertaking, or accepted evidence format. No customer, bank, regulator, or insurer requirement for Approv's particular assurance has been demonstrated here. The analogy to statutory financial audits does not establish one.

The claim that nobody else joins authorization and execution evidence is particularly vulnerable. Mastercard and Google announced Verifiable Intent on 5 March 2026, including cryptographic records of delegated authorization. Its open specification defines a layered credential format for delegated authority. That overlaps the signed-evidence story directly; it does not establish that they solve Approv's product-field comparison problem. [Mastercard announcement](https://www.mastercard.com/us/en/news-and-trends/stories/2026/verifiable-intent.html), [Verifiable Intent specification](https://www.verifiableintent.dev/spec/)

Visa's Trusted Agent Protocol addresses agent recognition and signed interactions, rather than establishing item-level semantic correctness. Treat it as adjacent infrastructure with distribution, not proof of either complete competition or complete non-overlap. [Visa developer documentation](https://developer.visa.com/capabilities/trusted-agent-protocol/docs)

The assumption that agent operators cannot receive post-purchase outcomes is also not universal. UCP's April 2026 order specification includes order events and adjustments such as returns, refunds, and disputes. Whether a particular merchant supplies useful reason codes remains an integration question. [UCP order specification](https://ucp.dev/2026-04-08/specification/order/)

Potential defensibility is faster integration across actual merchant schemas, a human-adjudicated catalogue of failure modes, and evidence that those failures predict customer costs. Cross-customer data only compounds if contracts permit its use and the labels describe real outcomes. A rule firing is not automatically a labelled example of manipulation. None of those advantages exists merely because the company is separate from the agent vendor.

**4. Benchmark: C − B does not rescue this design**

The current experiment should not produce a headline product-improvement claim. Its problems are causal, semantic, and mechanical:

| Problem | Evidence and implication | Required correction |
|---|---|---|
| Feedback and scoring share a reference | `_findings_for` reads OFF `brands`; scoring reads the same field. The comment in `_is_correct` says identical scoring prevents contamination of C − B. It does not: C alone receives information derived from the potentially wrong reference. | Score against independent human adjudication. Preserve OFF as an observed source, not unquestioned truth. |
| Probe mode still reveals information | A SATISFIED/MISMATCH response is an answer-dependent oracle. It need not spell out the correct value to reveal information about the scored answer. | Describe C as reference-informed feedback. That can be a legitimate treatment, but distinguish it from unaided reading and measure the reference's errors. |
| The task instruction and success metric disagree | `PROMPT` says to answer UNKNOWN if the title does not identify the brand. The scorer rewards naming the hidden OFF brand and counts UNKNOWN as unsuccessful overall. | Decide whether the task is grounded extraction or brand identification using additional evidence. Annotate abstention correctness against that task. |
| “Blind retry” lacks the first answer | B gets the title and generic retry text in a fresh request. C's finding normally includes A's claimed answer. B is not revising the same visible answer. | Fork the same initial transcript into B and C; preserve A in both and vary only the feedback intervention. |
| Scorer relation is reversed | `compare_term` accepts claim tokens contained in evidence. `_is_correct` accepts reference tokens contained in the answer. These are different predicates. | Use an independent, task-specific scoring rubric rather than reversing a token heuristic. |
| Over-answering can earn credit | Executed: `_is_correct('not Amul', 'Amul')` and `_is_correct('Amul Britannia Nestle', 'Amul')` both return `True`. Conversely, `Amul` versus `Amul Gold` is SATISFIED by the checker but incorrect by the scorer. | Score unique entity assertions and contradictions; reject hedged lists when the task requires one brand. |
| Conditional accuracy changes denominators | C can improve accuracy among answered cases by abstaining on difficult cases. B and C then cover different samples. | Report correct, incorrect, and abstained counts over all eligible sessions; also report risk at matched coverage and completed correct purchases. |
| No uncertainty on the treatment effect | Per-arm Wilson intervals do not estimate the paired C − B effect. | Retain paired outcomes; estimate uncertainty on the paired difference. Account for SKU/brand clusters and repeated sessions. |
| Cached runs are not fresh replications | `_cache_path` hashes model, title, and feedback, omitting the full prompt, endpoint/provider and generation settings. A prompt change can reuse an old response. | Version the full request configuration, source snapshot, comparator, scorer, and response metadata. Separate cached replay from new sampling. |
| Operational failures become abstentions | Provider adapters turn some malformed/missing responses into UNKNOWN. This mixes infrastructure failure with deliberate abstention. | Record provider errors, parsing failures, truncation and genuine abstention separately. |

Filtering on complete fields also changes the population. Availability can correlate with catalogue quality and difficulty, even if the filter does not explicitly reference difficulty. Fixed B-then-C order and repeated cached titles add further dependencies. Randomize execution order where appropriate and group repeated products when estimating uncertainty.

The abandoned extraction experiment was not inherently circular merely because two source fields were derived from one another. A model can be evaluated on extracting a field against independently verified annotations of that same field. The issue is using an unvalidated parser output as gold. The current hidden-brand experiment changes the task without fixing that problem.

Run two separately named measurements: (a) checker correctness on human-adjudicated claims and source snapshots, and (b) customer task outcomes after interventions. For (b), compare the existing agent, an equal-context retry, a simple direct-field/constraint checker, and Approv, with equivalent source access. Production feedback can reveal a correct source value if that is the deployed behavior; it must then earn its advantage against a baseline that can access the same source. Score final carts against held-out human labels or subsequently adjudicated outcomes, not the very value Approv supplied.

Freeze the hypothesis, scorer, exclusions, sample, primary metric, and stopping rule before looking at the held-out results. Debug on a development set. Repeatedly redesigning the experiment on the same corpus can overfit even if every rejected design is documented.

**5. Provenance: the axes are distinct, but their current interpretation overclaims**

Authorship and extraction certainty are meaningfully different. Liability is not simply an ordered authorship enum. A merchant description, a seller statement, and a platform-derived field do not by themselves establish an enforceable remedy or who ultimately pays. “The person who injected this inherits liability” confuses attribution, contractual responsibility, and collectability. Compromised accounts, copied listings, authorized third-party sellers, and unknown attackers break that inference. Treat legal attribution as unresolved until supported by the relevant contracts and jurisdiction, rather than emitting a guarantee from a field label.

Keep separate records of observed origin, authenticated publisher, acquisition method, extraction method, applicable SKU/variant, freshness, and any contractual attestation. Two trusted-looking fields derived from the same source are not independent evidence. The repository already recognizes that for OFF quantities; the same reasoning must apply elsewhere.

An EXACT reading of a false structured field is still exact extraction. `Finding.confidence` is documented as confidence in the product fact, but the operators set it from extraction certainty alone. Although the code also disclaims calibrated probabilities, `1.0` cannot support the stated interpretation. Name it an assurance tier or extraction score until outcome calibration supports a stronger meaning.

The injection defense is not established. `Evidence` accepts caller-supplied `certainty`, `field_name`, `liability`, and `is_advice`; `run_checks` does not enforce `schema.field_profiles`. A caller can mark description-derived content EXACT. This is a confirmed missing boundary in the current runner, not a demonstrated remote exploit: there is no deployed ingestion path here. Trusted adapters must assign and verify those properties outside model control.

Closed-vocabulary prompts do not remove a channel: an attacker can ask for exactly an allowed but false value. Likewise, a deterministic evaluator remains causally dependent on model extraction if a model chooses values, category, attributes, or which constraints survive. DR 0009's assertion that selecting fewer checks only creates more unknowns needs a fixed, independently established required-check set. Otherwise omitted checks can simply disappear, as the runner's unknown-attribute behavior illustrates.

The security register must distinguish algebra guarantees from future evaluator guarantees. “No algebra failure returns allow” is not evidence of safe authorization when the algebra never returns authorization decisions at all. The existing prose-ceiling test verifies a supplied enum mapping; it does not prove that hostile prose cannot be promoted into a stronger tier.

**Executed implementation findings for Claude Code**

Priorities below are review priorities before relying on findings in a purchase gate; they are not claims of exploitable production vulnerabilities. Fixtures use matching claim/evidence attributes and EXACT evidence unless otherwise stated.

| ID / priority | Location | Reproduced result | Expected contract to establish |
|---|---|---|---|
| R1 / high | `approv/algebra/quantity.py:81,150`; `approv/types/core.py:185` | Claim 500 g MASS versus evidence 500 ml incorrectly declared MASS → SATISFIED, confidence 1.0, no reasons. `_to_base` discards the unit table's dimension. | Validate canonical unit dimension against the supplied dimension and attribute specification; malformed inputs must not produce a clean match. |
| R2 / high | `approv/algebra/term.py:110,118` | `Amul` versus `not Amul` → SATISFIED at 1.0. `sugar` versus `sugar free` also matches. `Amul Gold` versus `Amul Taaza` → UNSTATED, “claim more specific.” | Token overlap does not establish identity, negation or mutually exclusive variants. Use verified entity/attribute semantics; unsupported prose must not become an exact identity assertion. `Term.node_id` currently has no effect. |
| R3 / high | `approv/algebra/runner.py:138` | Claims `[Amul, Britannia]` against Amul evidence produce only one clean SATISFIED finding. | Explicitly reject, disambiguate or report contradictory duplicate claims. Do not silently take the first. |
| R4 / high | `approv/algebra/runner.py:154,177`; `approv/algebra/feedback.py` | Equal-certainty evidence `[Amul, Britannia]` yields SATISFIED + FIELD_CONFLICT + “No action needed.” Reverse it and the result is VIOLATED + FIELD_CONFLICT + “Choose a different product.” | Establish order-independent conflict handling and a repair that resolves the conflict. Do not leave action selection tied to arrival order. |
| R5 / high | `approv/algebra/runner.py`; `approv/types/core.py:280,288,326` | Matching `is_advice=True` evidence gives clean SATISFIED at 1.0. Field profiles are unused. | Enforce trusted field profiles and advice treatment before operators can elevate evidence. Liability policy may be separate, but cannot be implied by the current result. |
| R6 / medium | `approv/algebra/runner.py:177` | Claim Amul; fields Britannia and Nestle: no FIELD_CONFLICT because both comparisons return VIOLATED. Claims outside the schema produce zero findings. | Distinguish disagreement between evidence items from disagreement with the claim. Report or reject unsupported attributes explicitly. |
| R7 / medium | `approv/harness/openfoodfacts.py:113,160` | `parse_quantity('2 x 500 g')` returns 1000 g and count 2; `evidence_from` emits only net_weight=1000 g. | Preserve per-unit amount, pack count and total semantics where relevant. Two packs and one bulk pack are not generally interchangeable. |
| R8 / medium | `approv/harness/coverage.py:55`; `approv/harness/openfoodfacts.py:118` | A record containing only title `plain flour` counts as published brand coverage. | Distinguish candidate evidence from a resolved brand value and from evidence sufficient for a hard check. |

Additional inspection concerns: `AttributeSpec.tolerance` has no semantic bounds; operators do not validate the full attribute-spec/value contract. `fl_oz` encodes one convention without explicit locale. Nominal comparison strips combining marks beyond Latin accents, so multilingual identity needs review. These are inspection findings, not separately executed failures in this review.

**6. Corpus: the deadlock is partly self-imposed, and the coverage claim is overstated**

I reproduced the quantity counts from the existing cached 599-record corpus:

| Measure | Numerator / denominator | Result |
|---|---|---|
| No quantity parseable by the current loader | 263 / 599 records | 43.9% |
| Occupied quantity field that does not parse | 75 / 411 occupied fields | 18.2% |
| Same occupied-but-unparseable cases as share of all records | 75 / 599 records | 12.5% |

The prompt omits the denominator switch. The 75 unparseable records are included in the 263 without a parseable quantity; these percentages are not additive. Corpus SHA-256: `85c084a076a5fe714533677559adcf13e312ac93115b196703516be63ceb93a5`.

This is a current-adapter coverage result on a convenience sample. It is not a universal bound on what any verifier can determine: the loader supports limited units and syntax, and does not inspect product images, alternate descriptions, or every potentially useful source field. A parse failure is not proof that the listing contains no usable size. Nor does an OFF product's sold-in-India tag establish coverage of Indian shopping traffic. Report source, snapshot, parser version, attribute, eligibility rule, and denominator. Weight production estimates by relevant customer sessions once those exist. A Wilson interval does not cure nonrandom sampling.

A merchant partner is not required to label whether a claim follows from a captured public listing. A human can annotate a frozen title, structured fields, variant selection, and packaging image against a written rubric. Keep “what the source says” separate from “what the delivered product is.” The latter, and real customer impact, require stronger evidence such as packaging inspection or partner outcomes.

Start with a small human-labelled development set to repair the rubric and these obvious counterexamples. Then collect a separately held-out set sized for the error bounds you intend to claim. Include missing fields, contradictory sources, multipacks, and correct cases; do not select only examples the checker detects. Double-annotate disagreements and critical cases, report class-specific agreement and adjudication, and do not treat one kappa threshold as sufficient evidence of validity. No labels were generated during this review.

The OFF loader's licensing sentence is too categorical. ODbL 4.4(c) and 4.6 discuss public use of produced works from derivative databases as well as redistribution; 4.3 covers attribution for produced works. “Publish the number, never the corpus” is not a universal legal safe harbor. Whether a specific report or pipeline triggers those provisions depends on what was created and used; review that concrete use before relying on the assertion. [ODbL license text](https://opendatacommons.org/licenses/odbl/1-0/)

**7. Other things that can kill this**

**Binding the check to the purchased thing.** A correct check of a product page can be invalidated by variant selection, cart quantity, seller change, shipping charges, substitution, or a changed checkout. An asynchronous observer also cannot guarantee it saw every relevant event. Define the exact action being checked and bind evidence to that cart version before any future gate claims to protect a debit.

**Hash chaining does not prove completeness.** A chain truncated after an earlier valid record still has valid internal links. Detecting a missing suffix requires an independently retained expected head/checkpoint, witness, or equivalent completeness mechanism. Signatures also require identity/key binding, revocation policy, canonical serialization and replay scope. These are missing design work, not reasons to implement a signature module ahead of customer validation. Pydantic `frozen=True` does not deeply freeze the dictionaries in `AgentTurn` and `ComparisonRecord`.

**Two signatures still require two contributors.** Joining halves asynchronously removes a proxy requirement; it does not cause a nonparticipating merchant to sign. A one-sided observability product can work, but DR 0016's rule that an unattested half forces confirmation limits its autonomous gating value. The in-house-agent case avoids organizational adoption friction because one company owns both sides; it does not create independent corroboration of the facts.

**Repairs can optimize the statement instead of the purchase.** `PICK_DIFFERENT_PRODUCT` can be inappropriate for a pure grounding error: correcting a mistaken description may suffice. `RESTATE_CLAIM` can make a result cleaner while abandoning the original constraint. Establish the objective and immutable constraints before measuring a repair as success. A listing that is silent also does not prove “Nothing can fix this” if another admissible source is available.

**Type reuse does not eliminate category engineering.** Mass arithmetic is reusable; net mass versus drained mass, per-pack versus aggregate quantity, dosage, dimensions with different roles, compatibility, bundles, and mutually exclusive variants require relationships and policies. The same-dimension check cannot establish that two values measure the same property. Six operator families may be sufficient for an initial representation; they do not demonstrate that thousands of categories cost only schema entry. The current code has three comparators and no date value in its discriminated union.

**A learning preference record can reinforce a mistake.** Purchase history does not establish consent to a permanent hard constraint: gifts, stockouts and bad substitutions also produce purchases. Inferred preferences need distinct status from explicitly confirmed constraints. Otherwise the supposed switching cost becomes a source of persistent incorrect decisions.

**Protocol and regulatory assertions need evidence.** I did not find a primary NPCI specification for the exact “Unified Agent Protocol” name in the searches performed. This is not proof it does not exist. Do not use a reported roadmap, per-transaction cap, or assumed authorization requirement as a binding requirement without an authoritative source and version. Similarly, the repository has not established that a bank or regulator requires an independent Approv-style verifier. A concrete indemnity offer would need defined covered errors, exclusions, payout duties, contracting parties and jurisdiction-specific legal review before it can become a product claim.

**Recommended next work, in order**

1. Reconcile the prompt and DR 0016 around the actual first customer: an in-house commerce agent with access to recorded constraints and cart outcomes. Remove the unsupported consent-disappears, automatic-liability, and independence-as-moat assertions from pitch material.
2. Have Claude reproduce R1–R6 and the scoring counterexamples, then address the contracts in small reviewed changes. Preserve the founder-owned evaluator boundary. Add regression tests for these failures, not more happy-path examples. Do not spend quota on a headline benchmark until its task and scorer are corrected.
3. Establish trusted ingestion and the scope of quantities, required attributes, advice, and conflicts. This is where the safety argument currently fails; adding numeric thresholds downstream will not repair it.
4. Freeze a human annotation rubric and held-out evaluation design. Use the existing OFF corpus for adapter diagnostics, clearly labelled as such.
5. Obtain a bounded pilot and measure accepted error findings, investigation effort, correct task completion, and unnecessary interventions. Compare against direct field checks. Expand the product only when the measured advantage justifies the integration.

This review deliberately leaves the evaluator and all human evaluation labels to the founder. Its deliverable is the set of concrete failures, corrected claims, and decision criteria above.
