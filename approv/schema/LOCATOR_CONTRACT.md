# Catalogue source locator contract

Status: producer contract fixed by the seam-1 ruling. Consumer implementation belongs
to `approv/surface/`; these fixtures do not provide a replacement reader. The format
identifier is `catalogue-locator-v1`. `locators.py` is its shared codec. Existing
`FieldProfile.field_name` stores the entire locator unchanged.

## Wire grammar

A locator starts with `/` and has nonempty object-key or array-step segments separated
by `/`. It names a field, not the document root. Object keys are case-sensitive literal
strings. Dots have no special meaning. Decode escapes **once**, in a single pass:

| Spelling | Meaning |
| --- | --- |
| `~0` | literal `~` |
| `~1` | literal `/` inside a key |
| `~2` | literal `*` inside a key |
| `~3` | literal `#` inside a key |
| entire unescaped segment `*` | traverse an array, never an object wildcard |

This is an extension of JSON Pointer, not an assertion of compatibility with a generic
RFC 6901 resolver. Numeric segments are literal object keys; this producer uses `*`
for arrays, never a positional index. Empty or control-character keys are unsupported.
An unescaped `*` within an object-key segment is invalid. In particular,
`/spec~1sheet/coat.tone` reads key `coat.tone` inside key `spec/sheet`; it does not split
the dot. A root key literally named `/details/size` cannot satisfy `/details/size`.

A terminal `#name=` suffix contains a canonical UTF-8 percent-encoded option label
(`urllib.parse.quote(label, safe="")`). Decode it once. Preserve case, spaces, accents,
punctuation and plus signs; `+` is not a space. Malformed escapes, unknown suffixes,
multiple suffixes and noncanonical percent encodings are invalid, not alternate paths.
The schema's normalized attribute name and this raw option label are different things.

Examples emitted by the fixtures:

```text
/details/size
/variants/*/option1#name=Size
/stock/editions/*/selections/*/selection#name=Bore
/selection/value#name=Couleur%20%2F%20%C3%A9t%C3%A9%20%231
/spec~1sheet/star~2field
```

## Selector guard and SKU boundary

The suffix is a **guard**, not a rename instruction. It cannot turn the current
`option1` into size merely because a different product used that slot for size.

For a pair object, select the first nonblank string label in `LABEL_KEYS` order
(`name`, `label`, `attribute`, `key`, `option`), and the first present value key in
`VALUE_KEYS` order (`value`, `selected_value`, `selection`, `choice`). The source's
terminal segment must be that value key. Its parent object's raw label must exactly
match the decoded selector. Apply this guard inside the pair array before assessing
uniqueness; the Finish and Bore entries are different attributes, not ambiguous SKUs.

For `optionN` / `option_N`, resolve the option definition at that numbered position
in the selected product's enclosing catalogue metadata. Definitions are objects with
`name` and `values` in an array; an explicit integer `position` takes precedence over
its one-based array order. Definitions in the nearest enclosing object take precedence
over inherited definitions. The name must exactly match the guard. Missing, conflicting
or ambiguous definitions provide no evidence. An array of possible option values is
never evidence of the selected value.

The reader receives **one selected-listing snapshot**. For a nested catalogue, retain
the root and its metadata, every enclosing object, and the original variant-array path,
but retain only the chosen SKU inside that array. Keep the chosen SKU's complete pair
arrays. The fixture helper performs only that projection on a deep copy of the actual
input record; it does not flatten, insert typed values or precompute evidence.

An unselected multi-SKU array cannot contribute SKU-specific evidence. Do not pick
the first sibling, pool siblings, use the requested value to select a sibling, or treat
duplicate matches as one because their values happen to agree. A missing/null selected
value is missing even if another SKU publishes it. Variant selection and identity binding
belong to the surface adapter; this grammar is not a cart-to-intent inference mechanism.

After applying a pair's guard, a source must resolve to a unique value within the
selected listing. Zero matches supply no evidence. Ambiguous matches either supply no
evidence for the affected field or raise an explicit catalogue-reading error; neither
may authorise from a guessed value. Reject malformed syntax rather than attempting a
dotted-key or flat-key fallback.

## A resolved value must still be usable evidence

Path resolution alone is insufficient. Interpret the value using the proposed
attribute dimension and source profile. Preserve a whole nominal selector such as
`13.5` as a label when the category schema says NOMINAL. Money needs its currency;
physical quantities need a supported unit. An amount string without currency does not
become a nominal price. Typed object values must not become their string representation.
Do not silently default missing values or drop meaningful zero/false values by truthiness.

Keep `field_name`, `liability`, `certainty` and `is_advice` on emitted `Evidence`. A prose
source can describe multiple attributes: extract only the bounded labelled clause for
the requested attribute, retain PARSED certainty, and never copy the entire description
into every attribute. Arbitrary product instructions are untrusted text. Trusted source
policy can reduce trust, never promote prose. Onboarding's existing `values.py` and
labelled-clause rules establish these typed fixture expectations; this document adds
no model to the decision path.

## Executable handoff

`tests/fixtures/locator_contract.json` references the real fast Shopify cached/raw
fixtures and the independently constructed industrial fixture, plus escaped-key cases.
Expected locators and typed values are explicit JSON, not a second derivation algorithm.

`tests/test_surface_locator_contract.py` verifies producer profiles, then calls the
**production** `surface.verification.evidence_from_snapshot` with the schema derived
from that same catalogue. It requires nonzero evidence and checks the actual values,
source attribution, certainty, selected SKU, and negative selector cases. These tests
run in the default pytest command. There is no test-only resolver, xfail, conditional
skip or exhaustive marker at this seam.

```text
python -m pytest approv/schema/tests/test_surface_locator_contract.py -q
```

At base commit `9484f81` the production reader is still dotted-key based. The positive
consumer checks therefore fail with zero evidence. That is the integration blocker for
claude1 to resolve in surface, coordinated through the user. Passing producer tests alone
does not establish this seam; the consumer tests must pass before claiming integration.
The literal-locator-key negative case also fails on that base: the flat-key fallback
accepts a root key `/details/size` as evidence for a nested path. The seam run has
7 failures / 19 checks and 12 passes / 19 checks on that base; none is skipped.
