# DR 0023: Coverage belongs on the record

Date: 2026-09-13. Closed the same day. Required by invariant 8: it changes coverage
language.

## What was wrong

`Intake` decides whether the channel an order arrived through earns coverage at all — DR
0020's gradient, *no declaration, no coverage* — and that verdict was returned **beside**
the record, as `VerificationResult.covered`, not on it.

I put it there deliberately and wrote down why: *"kept off the record because it is policy
about the channel rather than a fact about the comparison."* The reasoning was defensible
and wrong, for a reason the reasoning could not see: **the dispute artifact renders the
record and nothing else.** So `approv/artifact` printed "Covered" for an order intake had
ruled out. That is the exact failure the document exists to prevent, arriving through a
field the document cannot see.

Two agents hit it from opposite sides within a day — the same defect also appears as
cart-only traffic producing a verification-labelled record whose eligibility sits outside
the signature. A verdict that two independent readers both expected to find on the record
is a field belonging on the record.

## The decision

**`covered` and `coverage_notes` move onto `ComparisonRecord`, inside the digest.**

| field | what it says |
|---|---|
| `covered` | whether this channel earns coverage at all (DR 0020) |
| `coverage_notes` | why it does not, stated rather than implied by a false |
| `coverage` | per finding, what is guaranteed / refused / out (property 6) |

Inside the digest for the same reason as the order half: a coverage claim that can be
edited after a dispute opens is not a claim, and the party with the motive to edit it is
us. `VerificationResult.covered` and `.intake_notes` survive as views onto the record, so
existing callers keep working and there is exactly one source of the fact.

## `covered: false` withdraws every guarantee

Otherwise the record can say the channel earned no coverage and, three fields later, that
six findings are `guaranteed`. A renderer picking either one is right, which means neither
is. So a channel that earns no coverage produces no guaranteed findings, by the same
mechanism as the other three withdrawals.

There are now four reasons a guarantee is withheld, and they are kept distinct at the call
site because they are different facts, each with its own field on the record:

| reason | scope | recorded as |
|---|---|---|
| narrowed reading | one attribute | `unread` + the quote |
| unread request (DR 0022) | the record | `unread` |
| incomplete verification (DR 0004) | the record | `completion` |
| uncovered channel (this DR) | the record | `covered` |

## What this does not change

Coverage policy and pricing are untouched: nothing here decides *which* channels earn
coverage, only where the answer is written down. The gradient is still DR 0020's and still
merchant channel policy.

Nor does it change a decision. `covered` has never gated `allow` / `confirm` / `refuse` and
still does not — an uncovered order is authorised or refused on its merits, and what
changes is only what we promise about it. Coupling the two would turn a commercial
eligibility rule into a reason to block a sale, which is precisely the confusion property 6
exists to prevent.
