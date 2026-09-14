# DR 0028: A value the merchant enumerated is a label, not an expression

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes what derivation
reports as publishable, and therefore which attributes can be guaranteed.

## What was wrong

Found by the public-feed audit. Apparel feeds size trousers on a combined axis:

```json
{"options":  [{"name": "Waist/Length", "values": ["30/32L", "34/32L"]}],
 "variants": [{"id": 11, "sku": "a", "option1": "30/32L"},
              {"id": 12, "sku": "b", "option1": "34/32L"}]}
```

Derivation flagged `30/32L` as `ambiguous_quantity_expression` — a slash between two
numbers could be a fraction, a ratio or a range — so no cell was usable and the attribute
reported **published 0 of 2**. The reader, meeting the same value through
`evidence_from_snapshot`, emitted exact nominal evidence for it.

So the two halves of the same system disagreed about one feed. The audit caught it as
`reader_emits_source_reported_as_never_usable`, which is the check written for exactly
this and the first thing it found on real data.

## Which half was wrong

The general rule is sound: a bare `30/32` in free text really is ambiguous, and refusing
to guess is right. What makes this case different is **where the value came from**.

`30/32L` is not a string we found lying in a field. It is one of the values the merchant
*enumerated* in a named option table. The merchant has declared the complete domain of the
axis and has declared that this is one of its members. There is no expression to evaluate,
because there is no arithmetic anywhere in the merchant's intent — the set is the meaning.
Parsing it is us imposing a reading on a closed set somebody else defined.

The consequence ranking settles it independently of the semantics. If the reader is
silenced to match derivation, we lose a real, common apparel axis — waist/length sizing is
precisely the near-miss substitution §7 ranks first. If derivation is corrected to match
the reader, a partner stops being told an axis is unusable while we are in fact verifying
and guaranteeing it. **Guaranteeing an axis our own report calls 0% usable is the worse of
the two**, because it is a promise made outside anything we audit.

## The decision

**A value drawn from a published option table is nominal by construction.** Quantity
ambiguity is not raised against it; it is compared as a label, exactly as the reader
already does, and derivation counts it as published.

This holds only for values the merchant enumerated in a name table. The same string in a
title, a description or an unlabelled field is still ambiguous and still refused — nothing
about the general rule changes.

## What this costs

Nominal comparison is literal. A request for *"32 inch leg"* does not match the label
`30/32L`, and never will under this decision. That is the schema-expressiveness limit
already recorded in `progress.md`: the axis is checkable against a request that names the
merchant's own label, and out of coverage against one that does not. Under-claiming, in
the direction we have chosen everywhere else.
