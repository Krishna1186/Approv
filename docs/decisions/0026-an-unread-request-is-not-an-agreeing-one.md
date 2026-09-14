# DR 0026: Request text nothing read is unknown, not agreement

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes the decision
path and coverage language.

## What was wrong

A search artifact carries two things side by side: filters the agent ticked, and a query
somebody typed. Intake read the filters, noted that nothing had read the query, and
carried on.

Measured on the shape that shows it worst — filters `{size: M, color: Frost}`, query
*"actually make it the Ash one, and it must be organic"*, no extractor configured:

```
decision=allow   covered=True   completion=completed   coverage=[guaranteed, guaranteed]
notes: ["search query was not read: no extractor was supplied"]
```

The request contradicted the filters in its first four words and we guaranteed both
attributes. The note was there. Nothing acted on it.

**This is the failure we have measured to cost money, arriving through a different door.**
DR 0022 priced an unread *requirement* and chose to withdraw the guarantee. DR 0004 ruled
that no coverage may be inferred from a verification that did not complete. Both were
about text we had read and partly failed to encode. Nobody had ruled on text that was
never read at all, and it fell through as though the shopper had said nothing.

Invariant 4 settles what it is: unknown routes to confirm, never allow. An empty reading
of a **non-empty** request is unknown. It is not agreement, and it is not silence either —
silence is an order that carried no stated request, which intake already handles.

## The decision

**Request text that nothing read makes the verification incomplete.** It joins DR 0004's
`Completion` axis as `REQUEST_UNPROCESSED` rather than becoming a fifth coverage flag,
because it is the same fact those codes record — the verification did not run to a
conclusion — and because that axis already does both of the things this needs:

| | mechanism | effect |
|---|---|---|
| never authorises | `floor_met = not incomplete and ...` | `allow` is unreachable |
| no coverage | `coverage_of(..., incomplete=True)` | every guarantee withdrawn |

A refusal still refuses. Withdrawal takes GUARANTEED away and never REFUSED, which is the
rule all four existing withdrawals follow: an attribute the catalogue contradicts is
contradicted whether or not we finished reading the request.

**The findings survive.** Unlike the other completion codes, the comparison here really
did run — against a partial request. Discarding the findings would throw away the filters
we read and the catalogue we read correctly, and hand the merchant a record that says less
than we know. So this is the first completion that carries a full finding set, and the
record's own fields say exactly which half was incomplete.

## Two shapes of it

- **Nothing was available to read it.** A deployment with no extractor, handed a query.
  The honest reading of that is not "the shopper agreed with the filters".
- **Something read it and produced nothing at all.** No constraints, no unread notes, no
  supersessions, from non-empty prose. Indistinguishable from the first from where the
  record sits, and treated the same. An extractor that read something and could not encode
  part of it is a *different* case and stays DR 0022's: it reported what it missed.

## A named requirement is DR 0022's case, not this one

A protocol call carrying a field this category has no attribute for — `gift_wrap` on an
apparel schema — had the same hole: the field was noted, the order was allowed, and the
findings were guaranteed. That one is a requirement we can name and did not check, which
is precisely what DR 0022 defines as unread, so it now becomes an unread requirement under
the existing `"Unsupported requirement: "` vocabulary and takes DR 0022's answer: the
guarantee is withdrawn, the sale proceeds, and `unread_policy` remains the merchant's
knob.

The two are graded differently on purpose, and the line is what we know:

| | what we know | answer |
|---|---|---|
| unmapped protocol field | the requirement, by name | withdraw the guarantee |
| unprocessed request text | nothing at all about its content | withdraw, and no `allow` |

Text we never read can contradict everything we did read — it did, in the measurement
above. A named field cannot: we know what it asked for and we know we did not check it.

## What this does not change

No comparison is weakened and no new coverage vocabulary is added — `REQUEST_UNPROCESSED`
reuses DR 0004's incomplete path end to end. `Undeclared` traffic is untouched: an order
with no stated request has always been out of coverage, and this is about an order that
had one.

It will move search traffic from `allow` to `confirm` wherever prose arrives at a
deployment that cannot read prose. That is the correct cost. The repair is on our side and
it is the one we were already committed to: read the query.
