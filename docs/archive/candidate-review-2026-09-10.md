# Approv engineering assessment — 10 September 2026

The intended product is an independent check between an agent's choice and a purchase:
preserve the original request, compare the exact variant with attributable product
evidence, help the agent correct mistakes, and retain a record. Financial protection
is a later ambition. The current build is a comparison engine and experimental
shopping environment; the latest completed study has not established an advantage
over ordinary review. See [the current study](../progress.md).

## What the code actually does

`intent.py` extracts typed requirements with supporting request quotes. Vocabulary
and type guards reject some bad interpretations, but do not prove completeness or
that a quoted value expresses the right relationship. `runner.py` dispatches typed
comparisons and enforces configured source profiles. `feedback.py` explains findings.
`shopping.py` provides search/inspect/select/review sessions with replayable traces.
The separate `evaluator/` contains a decision function, but the shopping feedback path
does not invoke it or gate purchases. Its presence does not make the harness a payment
authorization service.

The narrow study driver presents an ID-only choice among frozen listings. It is a
useful feedback experiment, but does not exercise the entire tool-using agent loop,
count corrections, live clarification, fresh merchant inventory or payment binding.

## Why further improvement is needed

1. **Diagnosis does not finish the correction.** The old forked report explains one
   product and checks the shelf only to issue decline advice. It never names the
   candidates whose required fields are supported. A useful correction should reduce
   the work the agent has to repeat. Whether this improves outcomes is an experiment,
   not something established by the previous tie with control.
2. **Extracted fields are an incomplete account of the request.** A matching size and
   stock status can coexist with the wrong product, use case or compatibility. The
   old follow-up drops extraction notes, and conflates an abstained proposal with an
   extraction failure. More deterministic comparisons cannot recover omitted intent.
3. **Unknown and impossible need separate treatment.** No contradiction is not proof
   of satisfaction. Missing or conflicting colour evidence does not establish that
   no suitable product exists. A failed search is not proof of catalogue-wide absence.
4. **The proof is narrower than the vision.** Software tests establish behaviour;
   catalogue-derived answer rules measure a particular shopping task. Neither measures
   request-extraction precision, physical product truth, live losses or insurability.
   The generic-review control must remain the commercial comparison.

## Implemented change and teach-back

`review.py` owns the product check formerly embedded in `Session._findings`, so cart
scaling, sale counts and schema floors are shared by session and candidate review.
It runs that check over the supplied candidates without changing their order. Each
candidate retains findings, source fields, contradicted attributes and unresolved
attributes. The compact report names supported alternatives and unresolved evidence.

“Supported” means the recorded required fields have supporting evidence. It is not
an allow decision or a claim that the complete original request was understood.
Weak supporting sources remain unresolved. Soft preferences do not rule products out.
The report retains extraction notes and explicitly asks the agent to check product
identity and remaining requirements. An empty comparison is unassessed.

The shelf is scoped to the sale count actually assessed. Sessions can assess the
requested count when the proposal uses the wrong one. The ID-only forked driver
rejects explicit multi-unit/cart-total tasks, because its answer format cannot express
a count correction. This avoids claiming coverage that the action space cannot test.

The forked driver offers a separate `shelf` arm and retains full assessments outside
the compact model prompt. Both feedback paths use the actual baseline shelf; a missing
baseline shelf now stops preparation instead of silently reconstructing retrieval.
Answer checkpoints bind to the stage, model and driver. Calls retain usage, timing and
hashes; truncated replies and IDs outside the supplied shelf remain errors.

These choices keep the experiment inspectable. A model-written recommendation would
introduce another unmeasured decision maker. Automatically picking the first candidate
would assume the extracted fields cover the whole request. Checking unseen inventory
would mix retrieval changes with feedback changes. None is needed to test this step.

## Running it

For the shared tool/HTTP/browser harness, add `--surface verify --candidate-review`
to `scripts/run_shopping.py run` or `serve`. The original behaviour remains available
without the flag so versions can be compared explicitly. Verification reviews only
candidates seen through search or inspect. Mark results keep their existing behaviour.

For a forked study, use a new work directory containing the frozen
`stage1-baseline.json`, `answers-baseline.json` and `constraints.json`:

```powershell
python scripts/run_forked_study.py followup --pack PACK --work NEW_WORK --review-scope shelf
python scripts/run_forked_study.py pick --pack PACK --work NEW_WORK --file 2-shelf --model MODEL
python scripts/run_forked_study.py score --pack PACK --work NEW_WORK
```

Retain or run blind-review answers for the same cases. Use `--review-scope product`
to prepare the previous report. Do not overwrite old study evidence. A changed stage
or model requires a new output suffix/directory rather than reuse of old answers.

## Second pass — 10 September, from replaying the study rather than reasoning about it

The change above was shipped and the 46-case study was then replayed against its own
frozen shelves and frozen extraction. The check was already right more often than the
outcome suggested: on five held-out cases it named the answer-key product as the only
candidate satisfying every required field, and the agent abstained on all five. That
located the remaining defect on the reporting side, not the checking side.

Four repairs followed, each recorded with its measured checker-side effect in
[progress.md](../progress.md). In summary: the resolution vocabulary had a member for
declining and none for proceeding; the report closed on the count of ruled-out candidates,
so isolating one right answer out of twenty-five read as a failure statistic; the identity
caveat trailed the supported list and so read as doubt about the candidate just cleared;
the report never said when the agent's standing answer was already among the supported
set; the narrowing rule matched a qualifier only after the word it qualified; and the
vocabulary guard and the comparison operator held two different notions of when two values
are the same, which dropped the availability requirement on four cases.

`SELECT_FROM_SUPPORTED` is deliberately narrower than "supported". It requires that
nothing in the request went unread, because an imperative resting on a partial reading of
the request is a worse failure than a buried one — on the one unfillable case where the
extractor had silently dropped a constraint, the old buried wording produced a correct
decline and an imperative would not have. Where the reading is incomplete the supported
candidates are still named and the imperative is withheld. It remains feedback to an
agent: no `Decision` is produced on this path, and `evaluator/` is still not invoked here.

One hypothesis was tested and refuted rather than adopted: extracted constraint values
retrieve worse than the agent's own free-text query (41.3% against 58.7%), so the
retrieval ceiling is not reachable by handing the ranker what Approv already knows.

## Validation and remaining work

210 software tests pass. New counterexamples cover alternative IDs, source evidence,
missing/conflicting/weak fields, preferences, empty checks, uncertainty notes, cart
counts, unseen products, trace replay, label isolation and invalid model replies.
They are artificial software fixtures, not accuracy labels.

The saved 46-case study was replayed as a development diagnostic: 1,150 candidate
assessments, 25 shelves containing at least one candidate with supported required
fields, and uncertainty notes retained in 20 requests. These counts describe the
checker, not the correctness of its findings or the agent's eventual choice.

The next product work should address request coverage and evidence acquisition:
retain each requirement's relation to product identity, compatibility, variant and
quantity; identify which missing fact another source could resolve; and measure the
result against independently reviewed examples. Each release needs fixed starting
choices and a generic-review control, with introduced errors, extra abstentions,
extraction failures and total cost retained. Already inspected cases are development
material; a fresh held-out result is still needed before claiming improvement.
