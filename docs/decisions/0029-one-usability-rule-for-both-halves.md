# DR 0029: One usability rule, applied by both halves

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes what evidence
the reader emits, and therefore findings, decisions and coverage.

## What was wrong

Two functions answered the same question — *may this catalogue cell be compared as a
nominal label?* — and neither knew the other existed:

| | rule |
|---|---|
| `schema.derive._usable` | a value, **or** an option cell whose issue is `unitless_decimal` / `unknown_or_ambiguous_unit` |
| `surface.verification._settled_value` | anything whose issue is not in `_NOT_TEXT` |

The audit's `reader_emits_source_reported_as_never_usable` check exists for exactly this,
and on the fifty-store cohort it fired 29 times, all in one store. ILIA Beauty writes in
its descriptions:

```
What else you need to know: Size: 1 fl oz | 30 ml
```

Derivation refused it — `ambiguous_quantity_expression`, published **0 of 341** — and the
reader emitted it anyway, as `size = Term("1 fl oz | 30 ml")` from `/body_html`, at
`merchant_guaranteed` liability.

**That reading can only ever lose.** It is a nominal label, so it matches only a request
that states those exact seventeen characters. Every real size request — *30 ml*, *1 oz*,
*30ml* — comes back `violated`, on a guaranteed source, generated out of marketing copy.
It is a manufactured mismatch, and on the near-miss substitution §7 ranks first it is the
wrong answer in the expensive direction.

## What the disagreement was really about

Not `option`. The counter-case settles it: `/details/size` = `3XL` is a plain field, not a
selector, and it is obviously a size label that merely failed to type because `XL` is not a
unit. Derivation called it unusable; the reader read it; **the reader was right**, and the
locator contract already asserted so.

So each half was right about one case and wrong about the other, and the axis that
separates them is the *issue code*, not where the cell came from:

- `unitless_decimal`, `unknown_or_ambiguous_unit` — *we could not type this label.* The
  whole surface text is what the merchant published. Keep it as a label.
- `ambiguous_quantity_expression` — *this string holds more than one quantity reading.*
  There is no single label here to keep; `1 fl oz | 30 ml` is two statements of one fact.

## The decision

**One function, `schema.catalogue.nominal_label`, called by both.** Not two rules kept in
agreement — agreement is a thing that has to be maintained, and these two were written
months apart and drifted. Three ways to be a label:

1. the reading succeeded;
2. it failed only to *type* a whole label — `unitless_decimal`,
   `unknown_or_ambiguous_unit`. This is `3XL`;
3. the merchant **enumerated** it. DR 0028's principle: the value is one of the choices on
   offer, whatever we failed to make of it.

`ambiguous_quantity_expression` joins `_NOT_TEXT`, and an absent cell is refused inside the
function rather than beside it.

## Two corrections the measurement made, which reading the diff did not

**The first cut dropped the enumerated branch** on the grounds that `3XL` proved `option`
was not the axis. It is not the *only* axis. Gift cards are sold as `$35`, `read_value`
refuses that as money because `$` is not an ISO currency, and the value is neither typed
nor `_LABEL_SAFE` — so the reader went silent on it. The cohort's correct rate fell from
**98.51% to 98.10%**, 44 selected slots, every one a gift card. A selector value the
merchant listed is a label; that branch is load-bearing and it is back.

**The second cut then read an empty option slot as the literal label `None`**, because
`option` alone admitted a cell with no value and no issue. Caught by an onboarding
fixture whose published count went from 4 to 5. `present` is now checked inside the
function, which is where the two-rule version had it on one side only.

Both are pinned. The audit found the first and the suite found the second, which is the
argument for running both against every change to this rule.

## Measured consequence

- The reader stops emitting from prose it could not resolve: 29 of 7,179 probed variants
  before, zero after.
- Derivation counts `3XL`-shaped labels wherever they appear rather than only inside a
  selector, which is what the reader already did.
- Correct and wrong selected slots are unchanged — 98.5% and 0.0%.

## What this costs

A genuine single-quantity fact written only as a dual-unit string — *"500 g | 1.1 lb"* —
is now unread rather than read as a label. That is a coverage loss and the report shows it
as unpublished, which is the direction chosen in DR 0027 and DR 0028 and for the same
reason: an attribute nobody guarantees is cheaper than one guaranteed against a string no
request will ever match.

## What it does not decide

Whether a dual-unit expression should be *parsed* into a quantity with two spellings. That
is a comparator question, it is worth doing, and it is not this.
