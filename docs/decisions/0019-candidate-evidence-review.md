# DR 0019: Review the retrieved shelf with explicit evidence limits

Date: 2026-09-10.

The latest completed comparison shows no gain over generic review. Checking the
retrieved shelf is a testable improvement hypothesis, not an established explanation
for that result. A size match alone does not establish product identity or complete
request interpretation.

Use one product-check implementation for session feedback and forked-study review.
Review only candidates actually shown to the agent, in their original order. Return
per-candidate findings and compact lists of supported required fields, unresolved
evidence, and contradicted requirements. Preserve source fields, quantity scope,
assessed sale count, extraction notes and the original request. Do not rank candidates,
silently relax requirements, or treat missing evidence as a contradiction.

These are evidence summaries, not purchase decisions. Soft preferences cannot rule
out a candidate. Parsed/inferred support for a required field remains unresolved.
Empty checks are unassessed. Even supported required fields do not certify product
identity or cover requirements the extractor missed. An all-contradicted shelf means
no supported purchase at the assessed count from these results, not global absence
from the merchant's catalogue. Other counts are not exhaustively searched.

Keep the previous single-product study arm available for comparisons. Candidate
review is an explicit mode with separate stage/answer files and retained structured
assessments. Refuse to rebuild a missing baseline shelf during follow-up. The forked
ID-only study cannot test cart-count corrections; reject explicit multi-unit or
cart-total interpretations there instead of silently scoring the wrong action space.

Verify missing/conflicting/weak evidence, empty extraction, preferences, quantity
scope, original candidate order, baseline/control isolation and trace replay using
software fixtures. Replays of already-inspected study cases are development diagnostics.
Any customer-accuracy claim still requires fresh independently scored comparisons,
including extraction and feedback cost. No gold labels or evaluator logic change.
