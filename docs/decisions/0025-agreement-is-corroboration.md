# DR 0025: Two statements of one attribute that agree are corroboration

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes the decision
path.

## What was wrong

`algebra.runner` raised `DUPLICATE_CLAIM` for any two claims on one attribute **without
comparing their values**. Both claims became `UNSTATED`, and unstated routes to `confirm`.

On-site search states the same attribute twice by design. A shopper who filters to Size:
King and types "king duvet in frost" has told the merchant the same thing through two
channels — `search.filters.size` as a TOOL_ARGUMENT and `search.query` as an
AGENT_MESSAGE. The engine read that as an unresolved disambiguation problem and escalated
the order.

**Measured on a synthetic week: 20 of 24 on-site-search orders confirmed for this reason
alone.** Not a rare shape — it is what a search box *is*, and DR 0020's second fidelity
tier is on-site search. The tier was unusable.

The rule was not wrong when it was written. Two claims on one attribute genuinely can be
a disambiguation problem, and refusing to guess which one the shopper meant is the right
instinct. What was missing is that *which one they meant* is only a question when the two
answers differ.

## The decision

**Compare the values. Agreement collapses to one claim; disagreement keeps the existing
conflict path.**

Agreement is decided by the attribute's own operator, run in **both directions**, not by
model equality. Half a comparison is containment rather than agreement: a price ceiling of
$150 is satisfied by a claim of $120 one way round and violated the other, and collapsing
those two would silently drop the tighter limit the shopper actually set. Requiring both
directions makes "agree" mean the same thing for a Term, a Quantity and a Count, and puts
two different limits on the conflict path where they belong.

This is the rule the evidence side has had all along. Two fields that both speak to one
attribute are compared to each other pairwise and only a VIOLATED result is a
`FIELD_CONFLICT`. Claims now get the same treatment, using the same operators.

When several statements agree, the surviving claim is the one from the **strongest
channel** — TOOL_ARGUMENT over MANDATE over AGENT_MESSAGE over IMPLIED_BY_SELECTION, DR
0008's tiers. A structured filter and a paraphrase of the same request are not equally
disputable, and the record should attribute the constraint to the half that needs no
extraction step to defend.

## What stays

**Both statements stay in the record.** `request_constraints` carries every constraint the
agent made, each with its own channel and source locator. Only the *comparison* collapses.
A dispute turns on what was said and where, and dropping the corroborating statement
because it agreed would throw away the strongest thing about this class of order: the
shopper said it twice.

**Disagreement is unchanged.** Two claims that differ are still `DUPLICATE_CLAIM`, still
`UNSTATED` for both, still an escalation. That case is a real disambiguation problem and
guessing which one the shopper meant would be exactly the wrong repair.

**Incommensurable pairs go to the conflict path, not the collapse.** Two values of
different types, or two bounds, never compare SATISFIED, so they take the existing route
without a special case. A limit is not a value: two limits are the same request only when
they are the same limit, and tightening is a different request.

## Why this is worth a decision record

It moves orders from `confirm` to `allow`, which is the direction that costs money when it
is wrong (§2.6: a false allow is a wrong purchase). The safety argument is that no
*comparison* is weakened. A collapsed claim is compared against the catalogue exactly as a
single claim would have been, and the evidence side's conflict checks run unchanged. What
changes is only that we stop treating a shopper saying the same thing twice as a reason to
know less than if they had said it once.

And it unblocks the data plan. On-site search is how we reach 10,000 observed orders in
six weeks rather than four years (DR 0015), and a tier that escalates five orders in six
for a defect of ours is not a tier.
