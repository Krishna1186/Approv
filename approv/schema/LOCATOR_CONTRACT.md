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
For a numbered slot, the suffix additionally binds the exact option-name table as
`&table=` followed by a percent-encoded plain source pointer. `name` comes first and
`table` second, each at most once. No other parameters are defined. Pair selectors do
not carry a table. Literal ampersands inside labels are encoded as `%26`.

Examples emitted by the fixtures:

```text
/details/size
/variants/*/option1#name=Size&table=%2Foptions
/option1#name=Size&table=%2Foptions
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

For `optionN` / `option_N`, use the explicit table procedure below. An array of possible
option values is never evidence of the selected value.

### Numbered slots and the option-name table (ruling, 2026-09-14)

The standard Shopify shape is supported: selected values in `option1`, `option2`, etc.,
with their names in a separate `options` array. The same mechanism supports a flat SKU
record or arbitrarily nested merchant tables without a hard-coded `options` key.

```json
{
  "id": "product-a",
  "options": [
    {"name": "Color", "position": 2, "values": ["navy", "sand"]},
    {"name": "Size", "position": 1, "values": ["8", "9"]}
  ],
  "variants": [{"sku": "sku-a", "option1": "8", "option2": "navy"}]
}
```

The size profile is `/variants/*/option1#name=Size&table=%2Foptions`. A flat SKU carrying
the same table and `option1` directly uses `/option1#name=Size&table=%2Foptions`.
The selector is the expected raw name; the table parameter is its catalogue witness.
The locator never embeds a fabricated mapping such as `option1=Size` as authority.

1. Decode the table parameter once as UTF-8 percent encoding, then parse its pointer
   escapes once. It must be a plain absolute pointer into the **same snapshot**, not
   a URL, a relative path, a pointer with its own selector, or an external lookup.
2. Resolve the table in the selected-listing context. Require exactly one array of
   definition objects with nonblank string `name` and array `values`. Any `*` in a
   table path is subject to the same selected-SKU restriction as the value path.
   No sibling SKU's table can name this SKU's slot.
3. Establish positions: an explicit positive integer `position` wins over array order;
   otherwise use the one-based array position. Boolean, string, zero and negative
   positions are invalid. Duplicate positions are ambiguous, even when names agree.
   Reordering entries with explicit positions must not change which slot is read.
4. Read the definition at the numbered value field's position and require an exact,
   case-sensitive match with `#name`. Never match any arbitrary sibling string or
   select the first entry whose name happens to match. Missing, malformed, mismatched,
   or ambiguous tables supply no evidence or an explicit catalogue-reading error.
   Do not fall back to an ancestor, another table, the name alone or a cart value.
5. Read the selected scalar from the value path. The definition's `values` is metadata,
   not a replacement for a missing selected value. Preserve numeric size labels as
   NOMINAL where the schema says NOMINAL. Keep the full locator on emitted evidence.

During derivation, table arrays come from the input's structure. Local definitions in
the nearest enclosing object replace inherited definitions as a whole. The producer
retains that object's table path per slot rather than merging labels from an ancestor.
If multiple tables in that object claim the same slot, or a definition is malformed,
proposal generation raises an explicit error instead of guessing a name. Control-field
containers such as `evidence` and `field_profiles` cannot provide naming authority.

For a table under `envelope["names/#~*"]`, its pointer is
`/envelope/names~1~3~0~2`, encoded in the parameter as
`%2Fenvelope%2Fnames~1~3~0~2`. For a table inside the selected variant, the parameter
can be `%2Fvariants%2F%2A%2Fchoice_names`. `%2A` here encodes the wildcard segment in
the inner pointer; a literal asterisk key uses `~2` before percent encoding.

The pointer, key escapes and `#name` guard remain unchanged. `table` is an additive,
explicit binding for numbered slots. Existing locators without `table` still parse
unchanged. Historical numbered locators require the previous deterministic nearest-
table lookup with the same uniqueness and exact-name checks; rejecting all such
locators or quietly accepting their names without metadata is not compatibility.
New numbered profiles always emit `table`; new derivations use `schema-onboarding-v2`
so a changed mapping cannot reuse the earlier schema version. Historical proposals and
published snapshot reports remain unchanged and are not automatically adopted again.
When re-deriving, trusted `source_policies` for a matched historical numbered locator
must be reviewed and migrated to the full table-bound locator. The producer rejects
the stale policy key rather than silently dropping a trust reduction and applying
default merchant attribution. It does not automatically approve a policy migration.

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
Its raw Shopify consumer cases now require the explicit `/options` table binding.
`tests/fixtures/option_table_catalogue.json` adds flat SKU records, reordered explicit
positions, escaped table keys, units in values and a table inside each selected SKU.
`tests/test_option_tables.py` checks those producer mappings and rejects ambiguous
metadata. It is not a replacement surface resolver or a claim that surface conformance
has already been completed.

`tests/test_surface_locator_contract.py` verifies producer profiles, then calls the
**production** `surface.verification.evidence_from_snapshot` with the schema derived
from that same catalogue. It requires nonzero evidence and checks the actual values,
source attribution, certainty, selected SKU, and negative selector cases. These tests
run in the default pytest command. There is no test-only resolver or exhaustive marker.
At `10cd413`, the founder pinned the remaining failing consumer cases individually as
strict xfails so main stays green. Clauses already passing are not marked; a fixed case
must XPASS and fail the suite until its owner removes the obsolete marker.

```text
python -m pytest approv/schema/tests/test_surface_locator_contract.py -q
```

Historical result at `9484f81`: the production reader was still dotted-key based. The positive
consumer checks therefore fail with zero evidence. That is the integration blocker for
claude1 to resolve in surface, coordinated through the user. Passing producer tests alone
does not establish this seam; the consumer tests must pass before claiming integration.
The literal-locator-key negative case also fails on that base: the flat-key fallback
accepts a root key `/details/size` as evidence for a nested path. The seam run has
7 failures / 19 checks and 12 passes / 19 checks on that base; none is skipped.

Current owner handoff at `10cd413`: surface has a partial pointer reader. Its remaining
strict xfails are the cached typed values, the numbered-option cases, nested typed/prose
evidence, escaped/Unicode selectors, unselected multi-SKU evidence, and duplicate pair
selectors. The null-selection and other negative cases already pass. No marker was
removed, broadened or added by this option-table change; surface ownership is unchanged.

Validation on 2026-09-14: the focused option-table run passed 24 / 24 checks. The final
default suite collected 753 / 753 tests, with 740 passes / 753 collected, 4 skips / 753
collected and 9 existing expected failures / 753 collected. The full local raw Shopify
export's option metadata was also scanned successfully against the new definition
validation, independently of the default sampled acceptance tests. This is contract
validation without a model, not a catalogue accuracy estimate; sampling intervals do
not apply to these test outcomes.
