# DR 0011 — Partial facet coverage: a node exists, its other facets do not

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-04, by the founder
- **Touches:** DR 0003, DR 0007, the pending queue, the taxonomy artifact format
- **Blocks:** the taxonomy file format, therefore the first operator

---

## The founder's question

> If there are many DAGs, how does this update from traffic in every new version? We may
> have discovered a new category but not its use case, then what?

DR 0003's addendum split the taxonomy into one DAG per facet — form, use-case, and so on.
DR 0003's decision put new categories through a manually-approved pending queue. The two
together leave a gap: traffic reveals a node's position in **one** facet and says nothing
about the others.

Concretely: `huaraches` shows up in queries. Review establishes it is a kind of sandal, so
`form` is settled. Nothing observed tells us whether it is casual, athletic or formal.

---

## The resolution

**Facets are independently optional, and an unassigned facet is `unknown` — never
`satisfied`, never `violated`.**

A node may be complete in `form` and absent from `use`. That is a legal, expected,
publishable state, not a broken taxonomy. What it must never do is silently pass.

Three rules follow:

**1. Absence is `unknown`, and `unknown` never authorises.** If a request constrains
`use: athletic` and the product's node has no `use` assignment, the comparison is
`unknown` with reason `FACET_UNASSIGNED`, and routes to `confirm` (§4.4). It does not
default to satisfied because the form facet happened to match, and it does not refuse —
we have no evidence either way, and refusing on our own incompleteness punishes the
shopper for our gap.

**2. The pending queue is per facet, not per node.** Approving `huaraches` into `form`
does not create a debt in `use`. The queue holds *facet assignments*, and one node can
have an approved `form` entry and a pending `use` entry simultaneously. Batches cut a new
version per DR 0003 regardless of whether every facet is complete — otherwise a single
unresolvable node blocks every other improvement in the batch, and the queue stops
shipping.

**3. Facet completeness is a measured property of the artifact.** Per facet, per
category: what fraction of nodes carry an assignment. This is a taxonomy quality metric,
it is reportable, and it directly predicts the `confirm` rate — which §5 already requires
us to watch, because a `confirm` on 60% of traffic is a nuisance rather than a product.
A rising `FACET_UNASSIGNED` rate is an early warning that the taxonomy is falling behind
the catalogue.

## Interaction with the verification floor (DR 0007)

The floor is stated **per facet**. `FLOOR(footwear) = {form, size}` says the form facet
must resolve and a size must be present; it says nothing about `use`, so an unassigned
`use` never blocks a footwear verification that nobody asked a use-case question about.

This is the useful case of the rule: a facet only matters when a request constrains it.
An incomplete facet costs nothing until someone asks about it, at which point it costs
one `confirm` rather than a wrong answer.

## What must not happen

**A model must not fill in a missing facet at runtime.** This is DR 0003's pending-queue
rule and DR 0009's monotone rule pointing at the same thing from two directions: a model
inventing `use: athletic` for a node is both an unreviewed taxonomy write and an
`unknown` promoted to `satisfied`. A model may *propose* the assignment into the pending
queue for human approval. It may never apply one.

## Options

**Option 1 — a node is only publishable when every facet is assigned.**
- *For:* the artifact is always complete; no `FACET_UNASSIGNED` state to handle.
- *Against:* one hard node blocks a whole batch; forces guessing to unblock, which is
  exactly the failure the pending queue exists to prevent.

**Option 2 — facets independently optional, absence is `unknown`, queue is per facet,
completeness is measured.**
- *For:* the queue keeps shipping; incompleteness degrades toward `confirm` rather than
  toward a wrong answer; gives an early-warning metric.
- *Against:* one more reason code and one more state in every consumer; the completeness
  metric has to be watched or it silently rots.

**Option 3 — infer missing facets from sibling nodes.**
- *For:* fills coverage cheaply.
- *Against:* an inference presented as an assignment. Siblings in `form` are frequently
  unrelated in `use` — sandals are casual, running sandals are not. This manufactures
  confident wrong answers in exactly the place they are hardest to notice.

## Recommendation

**Option 2.** Option 3 is the tempting one and it is the same mistake as auto-expanding
the taxonomy: it trades a visible gap for an invisible error.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
