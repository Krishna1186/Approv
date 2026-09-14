# DR 0024: Evidence is scoped to the ordered line

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes what the
engine reads, and therefore which findings a record can carry.

## What was wrong

The catalogue reader was handed a product record and read **every variant in it**.

On an apparel catalogue that is not a partial answer. A duvet in six colours publishes
six colours, and a reader that pools them will find Frost in a record whose ordered line
is Ash — then state it with the same confidence as a correct reading, and sign it into
the same record. Nothing downstream can tell the two apart: the finding says `colour
satisfied`, the coverage says `guaranteed`, and the field path it names is real.

**A wrong reading is worse than no reading, and this one was not rare.** It fires on
essentially every apparel catalogue, which is the population the pilot runs on.

It was found by codex2's producer/consumer contract test, not by ours. The consumer side
of a format we had implemented twice — once to write locators, once to read them — had
never been run against the producer's own fixtures.

## The decision

**Evidence is scoped to the variant named by the order line, before the reader sees it.**

`verify_order` projects the snapshot down to the ordered SKU and passes *that* to
`read_evidence`. Three consequences, all deliberate:

- **The projection is the caller's job, not the reader's.** Only the caller has the order.
  Doing it here means a merchant's own `Reader` cannot read the wrong variant either,
  which a rule inside our default reader would not have given them.
- **The record keeps the snapshot the merchant sent.** Scoping is a reading rule, not an
  edit to the evidence: the merchant recomputes `snapshot_hash` from the payload they
  posted, and the projection is reproducible from the order line the record already
  carries.
- **The root, its metadata and every enclosing object survive the projection.** Inherited
  currency, the option-name table and the parent's own attributes still read. Only the
  variant array is narrowed.

## A snapshot that does not hold the ordered line is a mismatch

It raises, the same way posting product A's snapshot with product B's order line already
raises, and with the same status code. This is the only honest answer available: every
reading in that record belongs to somebody else's SKU, so there is no cautious version of
the comparison — only a wrong one or none.

Two identifiers that disagree are also a mismatch. A variant whose `id` is the one the
order names while its `sku` is somebody else's is a contradiction, not a match, and
resolving it by taking whichever identifier hit first is exactly how the wrong SKU gets
read with full confidence. Only a key of the same kind can contradict: `color_code`
matches the same pattern `sku` does, and vetoing on it would reject every variant in the
array.

## Reading an unselected array

A reader called without an order — the contract tests, an offline conformance run — has
one listing short of an answer. It reads what every variant agrees on and leaves the rest
unstated. Not the first sibling, not a pool, and not a single value because two variants
happened to agree: agreement between two SKUs is a coincidence, and it stops holding on
the next record.

Unstated routes to `confirm` (invariant 4), so the failure mode here is a nuisance
escalation rather than a wrong guarantee. That is the right side to fail on and it is
visible, which the previous behaviour was not.

## The resolver is the producer's own walk

Related, and decided at the same time: the surface no longer walks locators itself. It
calls `approv.schema.catalogue.flatten` — the code that emitted those locators — and
indexes the result by `(locator, attribute)`.

A second walk would have to reproduce the option table, the currency inheritance, the pair
detection, the labelled-clause extraction and the child-over-parent rule *exactly*, and
the day one of them drifted the surface would read a merchant's catalogue differently from
the schema derived out of it. That is seam 1 a second time, silently. Producer and
consumer now agree by construction rather than by test, and the contract test is a
regression on the agreement rather than the only thing holding it together.

One thing the reader knows that the walk does not: what the attribute **settled as**
across the whole catalogue. Size `3XL` reads as an unrecognised unit in isolation and size
`13.5` as a unitless decimal; both are labels once the schema says the attribute is
NOMINAL. Everywhere else the dimensions must agree — a cell read as a Count against an
attribute compared in MASS is INCOMMENSURABLE, which is the answer, and inventing a
conversion is how a guarantee gets made out of a field nobody understood.

## What this does not change

No decision rule moves. `algebra` and `evaluator` do not know the projection happened;
they see fewer, better-attributed pieces of evidence and decide exactly as before.
Coverage language is untouched — an attribute that now reads nothing is `unstated`, and
`unstated` has always been out of coverage under property 6.
