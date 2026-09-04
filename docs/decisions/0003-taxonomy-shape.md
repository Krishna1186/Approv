# DR 0003 — Taxonomy shape, entity linking, and who may edit the taxonomy

- **Status:** CLOSED 2026-09-04 — Option 2, with a manually-approved pending queue
- **Raised:** 2026-09-03, by the founder, correcting a claim of Claude's
- **Touches:** the category operator, `profiles/`, the record's version pins, §6
- **Blocks:** the first operator (`subsumes`) and the annotation guideline

---

## Origin

Claude asserted in session that a category taxonomy is a tree and that being a tree is
what protects the traversal from cycles. **The founder's objection: a bulb belongs to
Lighting, Electronics, Home Decor and Interiors simultaneously.** That is a node with
four parents, which is not a tree, and the objection is correct.

Recorded here because §7 makes the founder's correct disagreements the point of the
exercise, not a footnote.

---

## What the correction changes

### 1. The structure is a DAG, not a tree

Multi-parent membership is normal, not exceptional. Marketplace category systems
(Amazon browse nodes, Flipkart categories) are directed acyclic graphs and products
carry a *set* of assignments, not one.

Consequences:

- **Traversal is reachability, not a parent walk.** Does *any* upward path from *any*
  assigned category of the product reach the requested category?
- **Acyclicity is no longer free.** A tree cannot contain a cycle by construction; a
  DAG is only acyclic if something enforces it. So: validated at write time when the
  taxonomy artifact is built, **and** a visited-set in the traversal regardless,
  because a merged supplier feed or a bad import will eventually produce a cycle in
  data that passed validation under an earlier version.
- **The edges stay directed.** `Sneakers → Shoes` must not imply `Shoes → Sneakers`.
  An undirected graph cannot express subsumption at all.

### 2. Multi-membership is permissive, not ambiguous

The founder's concern was that a product mapping to three categories forces us to pick
one and risk picking wrong. It does not. The category constraint asks a single yes/no
question — *is this thing a shoe?* — and if any assignment path reaches `Shoes`, the
answer is yes. No selection is required and no ambiguity arises.

**Ambiguity lives on the request side, not the product side.** "lights" may mean
`Lighting > Bulbs` or `Decor > Fairy Lights`, and those are different purchases. That
is an entity-linking failure, handled below, not a subsumption failure.

### 3. Entity linking is a separate, separately-scored step

The founder's second objection: a shopper types "joggers", "kicks", "chappals", or
describes the thing without naming it — none of which lexically resembles the taxonomy
node. (The stated analogy: searching YouTube by typing song lyrics, which share no
structure with the title, and it works anyway.)

This is real, but it is not the comparison operator's problem:

```
surface text  --[ semantic/, model, fallible ]-->  node id
node id       --[ algebra/,  deterministic   ]-->  ternary
```

Splitting it buys three things:

- **Entity-linking accuracy becomes its own number** — what fraction of surface terms
  resolve to the correct node — measurable against the gold set, separate from
  comparison correctness. Folded together, neither is measurable.
- **The model is constrained to a closed vocabulary.** It may only emit an id that
  exists in the taxonomy, so it cannot invent a category and cannot be injected into
  emitting one. Unresolvable text yields *no id*, which is `unknown`, which is
  `confirm` (§4.4) — never a guess.
- **The comparison stage never sees free text**, which removes untrusted product prose
  from the deterministic path entirely.

Note the direction of the original worry is inverted for the common case. A shopper who
means sneakers but types "shoes" is **not** a false negative: `subsumes(shoes, sneakers)`
is satisfied, because breadth in the request is permissive by construction. The failure
is only when the surface term does not resolve at all.

### 4. A taxonomy boundary is a market assumption, and belongs in the guideline

In Indian usage "shoes" is frequently meant as *footwear generally*, including sandals.
Under a strict taxonomy `Sandals ⊄ Shoes`, so a shopper who would have been happy gets
`violated` → `refuse`. A lost sale caused by an authoring choice, not by a bug.

Where the `Shoes` node's boundary is drawn therefore encodes a claim about how the
target market speaks. It is not a code decision and it must be written into
`data/guideline.md` **before** any labelling, or two annotators will silently disagree
and kappa will indict the guideline (§10-B) without saying why.

### 5. The taxonomy is a versioned artifact and never self-edits

The founder proposed accumulating unrecognised categories to expand coverage. The
instinct is right; the mechanism must not be automatic.

**If an unrecognised category can insert itself, then anyone who can put text in front
of the extractor can author taxonomy nodes** — and whoever authors the nodes controls
what subsumes what, which controls what gets authorised. That is a write primitive
into the decision path, and it belongs in §6 under record-integrity attacks.

So: unknowns are **logged for review**, promoted deliberately, and the taxonomy ships
as a versioned artifact. `taxonomy_version` pins into the `ComparisonRecord` alongside
`model_version`, `evaluator_version` and `prompt_version` — otherwise a receipt cannot
be re-verified later, because the graph it was computed against has moved.

### 6. Sourcing

Building the taxonomy from observed marketplace inventory "through Google and stuff"
is subject to §5 without exception: public data only, ToS checked before collection,
nothing behind authentication, no personal data. Flagged, not resolved. Tracked as
open question 3 in `progress.md`.

---

## Options

**Option 1 — tree, single assignment per product.**
- *For:* simplest traversal, acyclic for free.
- *Against:* factually wrong about how catalogues work. Fails on the bulb.

**Option 2 — DAG, multi-assignment, entity linking as a separate scored step.**
- *For:* matches reality; makes two error rates separately measurable; closed-vocabulary
  linking is an injection defence rather than a hope.
- *Against:* reachability traversal with a visited set is more code than a parent walk;
  the taxonomy artifact needs a build-time validator.

**Option 3 — Option 2, plus per-edge confidence weights.**
- *For:* could express "sandals are weakly shoes".
- *Against:* reintroduces a score into the deterministic path, which §2.1 and §4.3
  forbid. A weight is a verdict wearing a different hat. **Not recommended.**

## Recommendation

**Option 2.** Option 3 is the trap: it looks like it solves the sandals boundary, but
it smuggles a continuous score back into the one place the architecture forbids one.
The sandals boundary is an authoring and guideline problem, and it should be solved
where authoring problems are solved.

## Decision

**2026-09-04 — Option 2 adopted.** Taxonomy is a DAG with multi-assignment; entity
linking is a separate scored step.

On §5, the founder's mechanism, adopted verbatim: **the taxonomy is never edited
directly.** New category findings and unrecognised terms observed in traffic accumulate
in a **pending queue**. The queue is reviewed and approved **manually, in batches**, and
each approved batch produces a **new taxonomy version**. Nothing enters the graph
without a human in the loop, and every comparison pins the version it ran against.

Locale-specific vocabulary is out of scope for this DR and spun out to **DR 0006**.

**Status: CLOSED.**
