# Catalogue onboarding

`propose_schema()` derives a `CategorySchema` proposal and a verifiability report
from JSON product records. It uses no model, makes no purchase decision, and does
not register or adopt the schema. All implementation and tests live in this folder.

```python
import json
from datetime import datetime, timezone
from approv.schema import propose_schema, confirm_schema

records = json.loads(catalogue_json)  # a list of merchant product records
proposal = propose_schema(
    records,
    category_id="merchant.category",
    observed_at=datetime.now(timezone.utc),
    # currency="GBP",  # only if explicitly established for this catalogue
)

# Present proposed_schema, report and proposal_id to the authenticated reviewer.
# Only call this after that person reviews the sources, dimensions and diagnostics
# and selects the attributes required for this category.
confirmed = confirm_schema(
    proposal,
    reviewer=authenticated_reviewer_id,
    expected_proposal_id=reviewed_proposal_id,
    floor=frozenset(human_selected_attributes),
)
deployment_schema = confirmed.category_schema
```

The caller implements authentication, review UI, storage and deployment. A reviewer
name is an audit field, not authentication. A proposal hash detects a stale review;
it is not a signature or proof of merchant origin. This module never passes a draft
to verification. Integration with the existing verification surface remains deployment
configuration, outside this module.

To persist a proposal, use `proposal.model_dump_json(round_trip=True)` and restore
with `SchemaProposal.model_validate_json(payload)`. Normal `model_dump(mode="json")`
includes the computed rates, intervals and proposal ID for display. Confirmation
returns a separate object, preserves the original proposal, versions the reviewed
schema and recalculates the report against the explicitly selected floor.

## What is inferred

- Nested scalar fields, typed money/quantity objects, named selector dictionaries
  and arrays of label/value pairs. Numbered selectors are joined to their option
  definitions, including definitions above a nested variant collection.
- Sellable rows in a repeated collection with SKU/identifier evidence. Parent fields
  are inherited; a child's explicit missing value does not inherit the parent's
  similarly named value. Flat SKU records can establish sibling groups through an
  explicit product/family/group ID or shared product URL, scoped by merchant when
  supplied. A flat input should contain one merchant, or supply its namespace.
- Dimensions from values: explicit money/currency, supported physical units,
  integer counts, count suffixes and whole nominal labels. Numeric values under an
  explicitly unit-bearing key also carry that unit. Money needs a currency from the
  value, its enclosing object, or trusted onboarding configuration. A numeric option
  selector remains a label; shoe sizes are not counts. Physical quantities use the
  existing `MASS`, `VOLUME` and `LENGTH` dimensions; there is no `QUANTITY` enum.
- Variant axes need different values on distinct sibling identifiers. If explicit
  selectors exist, incidental SKU differences are excluded. Otherwise sibling value
  variation is reported as the basis of the proposal, for human review. Price,
  inventory state, IDs, title text and prose are excluded from this inference.
- Source paths retain provenance. Overlapping ordinary leaf names are qualified by
  path. A path uses `/` segments, `*` for arrays, `~0` for literal `~`, `~1` for literal
  `/`, `~2` for literal `*`, and `~3` for literal `#`. Control characters in keys are
  rejected. A dynamic selector adds `#name=` plus a percent-encoded
  option label. These are source locators, not executable expressions.

Structured fields default to the existing `MERCHANT_GUARANTEED` attribution label and
`EXACT` reading certainty. This assumes the input is the merchant's own catalogue;
it does not establish contractual liability. Explicit label/value clauses in prose
are `PARSED`, with the same source attribution. They never become `EXACT` or establish
a floor. Arbitrary prose is not interpreted. Input fields claiming a liability,
certainty, decision or pre-existing schema are ignored.

Trusted `source_policies` can set `SourcePolicy` for an exact source locator, including
a different liability, reduced certainty or `is_advice=True`. Prose cannot be promoted
to `EXACT`. Source certainty and attribution are independent in the report.

## Floor and report semantics

A catalogue does **not** prove which attributes are necessary for a category. The
proposal suggests one most-published observed selection axis, otherwise one
most-published structured product attribute. This is a minimal comparison anchor,
not a completeness claim about a purchase. The human must explicitly select a
nonempty floor before confirmation. An empty or unusable catalogue cannot be
confirmed by accepting a vacuous floor. For a heterogeneous catalogue, review
category cohorts and their floors separately.

The denominator is expanded listings, with one unresolved row for an ambiguous or
empty variant collection. Input record count is retained separately. Duplicate
input rows remain in the denominator; identifiers are used to prove sibling
variation, not silently deduplicate the export.

Each attribute reports these counts with its denominator, rate and Wilson interval:

| Field | Meaning |
| --- | --- |
| `occupied` | A source contains a nonmissing value, whether usable or not |
| `published` | At least one typed, non-advice reading and no conflicting readings |
| `exact` | Published with an EXACT reading, regardless of attribution |
| `floor_eligible` | Published EXACT merchant-attributed evidence, excluding advice |
| `parsed_only` | Published with PARSED evidence and no EXACT reading |
| `conflicted` | Different typed readings of this attribute on the same listing |
| `variant_groups` | Proven varying groups / all groups with distinct sibling IDs |

Source-level counts retain their separate locators and certainty. Listings count
once per attribute, even if several sources publish it. Wholly missing fields still
appear in the report with no proposed dimension. Conflicting dimensions are excluded,
except heterogeneous option labels, which preserve the whole literal value as
NOMINAL. Unusable amounts, ambiguous units and unsupported multiple-value fields
remain visible as diagnostics, without satisfying the floor.

`no_comparable_attributes` counts listings without any floor-eligible attribute.
`cannot_verify` counts listings that fail the proposed or reviewed floor. Both are
about this deterministic reader and this floor, not a universal verification limit,
product truth, accuracy, or insurance coverage. The report includes the category,
observation date, derivation version, `model_version="none-deterministic"` and
`prompt_version="none"`. Empty denominators have no rate.

## Validation

From the checkout containing this module:

```text
python -m pytest -q
```

`industrial_catalogue.json` is an independently constructed nested catalogue with
different field names, missing values, string prices and units in values.
The default suite also runs checked-in Shopify samples, without needing the local
cache. Their assertions are shared with the exhaustive tests: source dimensions,
variant axes, field publication counts and listing denominators are still checked.
Samples retain sibling SKU context across available hosts; the generator and source
hashes are in `tests/fixtures/`. They are regression fixtures, not a statistical
estimate of catalogue behaviour.

The full cached Shopify study and raw export remain available explicitly:

```text
python -m pytest --schema-exhaustive -m schema_exhaustive -q
```

These tests exercise every original row and retain their full-catalogue assertions.
They skip in the default run before opening the caches, and also explicitly skip
when requested without the required local cache. A skip is not an acceptance pass.
The existing `pyproject.toml` testpaths entry must retain `approv/schema/tests` so
both the fast tests and the exhaustive option are collected by the default command.

Unsupported or ambiguous structures require review: unrelated repeated collections
are never combined into a cartesian product, opaque multiple-value fields are not
treated as a selected value, and currencies or ambiguous units are never guessed.

## Locator integration contract

See [LOCATOR_CONTRACT.md](LOCATOR_CONTRACT.md) for the exact grammar, selected-SKU
snapshot boundary, selector guards and typed evidence requirements. `locators.py`
owns the shared codec; surface owns resolution. The default suite calls the real
surface reader against derived schemas and explicit JSON fixtures. The base reader
at `9484f81` fails that seam; those failures are visible and must be fixed in surface
before this integration can be claimed. The report below audits onboarding's reader,
not a completed production verification or signed coverage event.

## Partner-facing catalogue report

```python
from approv.schema.report import ReportContext, build_partner_report, render_html

report = build_partner_report(proposal, ReportContext(
    merchant="Merchant display name",
    scope="All supplied category listings; completeness against live stock unmeasured",
    source="merchant-export.json",
    captured_at="2026-09-10T00:00:00Z",  # omit if unknown
))
html = render_html(report)
```

The renderer reuses the proposal's counts, `Share` intervals from harness coverage,
and publication patterns for explicitly conditional repair scenarios. It does not
adopt the schema, determine event eligibility, read a request or issue a receipt.
Missing, present-but-unusable, prose-only and minimum-eligible evidence stay distinct.
Remediation prioritises the proposed floor, observed selection axes, monetary fields
and parsed facts; incidental fields require a relevance review before new publication
requirements are proposed. Initial parse diagnostics on a successfully preserved
nominal label do not become a request to change that label's units.

The offline CLI writes standalone printable HTML, a machine-readable report and a
round-trippable `.proposal.json` without adding dependencies to the default suite:

```text
python -m approv.schema.report_cli merchant-export.json --merchant "Merchant" --scope "Supplied category snapshot" --category merchant.category --output approv/schema/reports/merchant
```

`--shape shopping-study` unwraps only IDs, URLs and merchant details from the local
study cache. `--shape shopify-export` unwraps the host/products envelope and supplies
the host namespace; `--host` restricts it to one merchant. Neither reads an embedded
schema or precomputed product evidence. Currency must be supplied by the catalogue
or explicitly established using `--currency`, never guessed from a host.

Optional PDFs use `reportlab` and the same report JSON:

```text
python -m approv.schema.report_pdf approv/schema/reports/merchant.json approv/schema/reports/merchant.pdf
```

Install `reportlab` in your environment only when exporting PDFs; it is not imported
by the normal CLI or tests. The checked-in reports were rendered and visually
inspected using PyMuPDF because Poppler was unavailable in the authoring environment.
See [the handoff and measured results](../../docs/catalogue-verifiability-report.md).
