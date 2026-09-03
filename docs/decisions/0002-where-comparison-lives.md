# DR 0002 — Where do the comparison operators live?

- **Status:** OPEN — founder decides
- **Raised:** 2026-09-03
- **Touches:** the §2.4 stage boundary, the §2 layout, and the §4.1 import test
- **Blocks:** the first line of code in any module

---

## The question

`CLAUDE.md` §2.4 names two stages:

> `semantic/` emits fields and may never return a decision. `evaluator/` is
> hand-written pure functions and may never call a model.

There is a third thing, and the two-stage split has no home for it.

Take `"white shoes under 9k"` against a product listing. Three jobs happen:

1. **Translate.** Query → typed constraints. Product metadata → typed attributes.
   *Needs a model.* This is `semantic/`.
2. **Compare.** Is `Sneakers` subsumed by `Shoes`? Is `₹8,499 ≤ ₹9,000`? Is `250g`
   comparable to `250ml` at all? Each produces one ternary.
   ***Needs no model, and makes no decision.*** **This has no home.**
3. **Decide.** Given all the ternaries plus the category's criticality profile →
   `allow | confirm | refuse`. *Needs no model.* This is `evaluator/`.

Job 2 is deterministic code that is neither translation nor decision. It is graph
walks over a taxonomy, unit conversion, lattice membership, interval arithmetic. It
is where the accuracy actually comes from, and it will be substantially more code than
the decision rules are.

## Why it cannot just go in one of the two existing stages

**Not in `semantic/`.** §4.3: the semantic stage returns fields, *"never a verdict,
never a score that stands in for a verdict."* A per-attribute ternary is very close to
a verdict about that attribute. Worse, putting comparison next to the model call means
nothing structurally stops the model from being consulted during a comparison. §1's
non-negotiable — no model in the decision path — would then rest on discipline rather
than on architecture. §2.4 is explicit that the boundary is *enforced in code*.

**Not in `evaluator/`.** Two problems. First, §4.2 caps the evaluator at under 500
lines of pure functions; dimensional-quantity arithmetic and taxonomy traversal alone
will exceed that, so the cap would have to be abandoned — and the cap exists so the
founder can hold the whole thing in their head. Second, §4.2 reserves the evaluator
for the founder by hand. Folding comparison into it means hand-writing unit conversion
tables and lattice loaders, which is weeks spent on the least differentiated code in
the system.

## Options

**Option 1 — two stages, comparison inside `evaluator/`.**
- *For:* §2.4 unchanged. One import test, exactly as §4.1 specifies.
- *Against:* breaks the 500-line cap, mixes two concerns in the module that must stay
  smallest and clearest, and puts the founder's hand-writing time on the wrong code.

**Option 2 — three stages: `semantic/` → `algebra/` → `evaluator/`.**
`algebra/` holds the operators. Deterministic, no model, no decision. Consumes typed
constraints and typed attributes, emits ternaries.
- *For:* each module has one job. The evaluator stays small enough to defend from
  memory. The §4.1 invariant gets *stronger*, not weaker — it becomes two assertions
  (`evaluator` imports no `semantic`; `algebra` imports no `semantic`), and the
  no-model-in-the-decision-path claim is now enforced across the whole path rather
  than at one seam. Operators become independently testable, which matters because
  they are where the metamorphic invariants in §5 actually bite.
- *Against:* §2.4 and the §2 layout both need editing. Three modules to keep straight
  instead of two.

**Option 3 — three stages, but `algebra/` is also founder-hand-written.**
As Option 2, with §4.2's hand-written rule extended to cover it.
- *For:* maximum ownership of the code that produces the accuracy.
- *Against:* this is the slowest possible path to Stage C's first number, and much of
  it (unit conversion, graph traversal) is textbook code where hand-writing teaches
  little. The learning is in the *design* of the operators — return types, edge cases,
  what counts as incommensurable — not in typing the traversal.

## A consequence that has to be handled either way

All three modules need to name the same things: `Constraint`, `Attribute`, `Quantity`,
`Provenance`, the ternary itself. If `evaluator/` imports those from `semantic/`, §4.1
is violated on line one.

So the shared vocabulary needs its own module with **no logic in it** — types and
enums only. Proposed layout:

```
approv/
  types/       shared vocabulary. Types and enums only, no logic, imports nothing.
  semantic/    model -> typed constraints + typed attributes. No comparison, no verdict.
  algebra/     (constraint, attribute) -> ternary. Deterministic. No model, no decision.
  evaluator/   ternaries + criticality profile -> allow|confirm|refuse. Founder, by hand.
  profiles/    per-category criticality profiles + taxonomies + attribute lattices.
  receipts/    signed, hash-chained record of every decision
  harness/     runs corpora through the decision path, emits metrics
  surfaces/    (Stage E)
```

`evaluator/` then imports `types/` and nothing else, which is a cleaner and more
easily asserted invariant than the one §4.1 currently describes.

## Recommendation

**Option 2.** It preserves every substantive commitment in §1, §2.4 and §4 — and
strengthens the enforcement of the central one — at the cost of editing a layout
diagram. Option 3's extra ownership is real but is bought in the wrong currency: the
defensible-in-December knowledge lives in the operator *design*, which §7 step 4
already assigns to the founder regardless of who types the traversal.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
