# Catalogue verifiability report: partner handoff

The handoff is a standalone HTML report, an optional PDF companion, machine-readable
JSON, and the exact unconfirmed schema proposal. It measures catalogue publication
using the existing onboarding reader and harness Wilson intervals. It neither adopts
the proposal nor issues intent verification, an order record, or financial coverage.
This implements the catalogue-report route described in DR 0015 and the verification
floor described in DR 0007; it changes no decision or event-eligibility policy.

## Open the actual outputs

- [Allbirds single-merchant handoff, PDF](../approv/schema/reports/allbirds-2026-09-13.pdf)
  and [full HTML](../approv/schema/reports/allbirds-2026-09-13.html).
- [Cached shopping study, PDF](../approv/schema/reports/shopify-study-2026-09-13.pdf)
  and [full HTML](../approv/schema/reports/shopify-study-2026-09-13.html).
- [Full raw Shopify export, HTML](../approv/schema/reports/shopify-raw-2026-09-13.html).
  This is a mixed-merchant diagnostic appendix, not a single merchant's category report.

Each output has adjacent `.json` and `.proposal.json` files. The JSON includes every
attribute's publication, missing, unusable, exact, floor-eligible and parsed-only shares,
source locators, diagnostics and conditional remediation. Reports preserve all observed
attributes; fields that look incidental require category relevance review before asking
a merchant to publish them. The PDF prioritises concrete publication repair candidates;
the HTML and JSON retain the other source-mapping review items.

## Real snapshot results

All rows below were audited on **2026-09-13**, using derivation
`schema-onboarding-v1`, model `none-deterministic`, prompt `none`. Intervals are Wilson
95%, as in `harness/coverage.py`. Counts are exact for the supplied snapshot; intervals
are descriptive and do not establish confidence about live stock, traffic or accuracy.
The category/cohort and denominator appear with every result.

| Cohort | Finding | Listings / cohort listings | Rate | Wilson 95% interval |
| --- | --- | --- | --- | --- |
| `shopify.study.all` | Usable size publication | 33,485 / 33,485 | 100.0% | 99.9885%-100.00% |
| `shopify.study.all` | Usable color publication | 33,485 / 33,485 | 100.0% | 99.9885%-100.00% |
| `shopify.study.all` | Usable price publication | 33,485 / 33,485 | 100.0% | 99.9885%-100.00% |
| `shopify.study.all` | Below proposed color minimum | 0 / 33,485 | 0.0% | 0.00%-0.0115% |
| `shopify.raw.all` | No published size value | 8,257 / 74,858 | 11.0% | 10.81%-11.26% |
| `shopify.raw.all` | Usable size publication, including labelled prose | 66,591 / 74,858 | 89.0% | 88.73%-89.18% |
| `shopify.raw.all` | Below proposed size minimum | 8,283 / 74,858 | 11.1% | 10.84%-11.29% |
| `shopify.raw.all` | No structured comparison evidence at all | 0 / 74,858 | 0.0% | 0.00%-0.0051% |
| `shopify.raw.all` | Price present but unusable without currency | 74,858 / 74,858 | 100.0% | 99.9949%-100.00% |
| `allbirds.supplied` | No published size value / below proposed size minimum | 2 / 2,857 | 0.0700% | 0.0192%-0.25% |
| `allbirds.supplied` | Price present but unusable without currency | 2,857 / 2,857 | 100.0% | 99.87%-100.00% |
| `allbirds.supplied` | No structured comparison evidence at all | 0 / 2,857 | 0.0% | 0.00%-0.13% |

The raw size-minimum gap is deliberately larger than its missing-field count. In that
same `shopify.raw.all` cohort, 10 / 74,858 listings contain unusable size values
(0.0134%; Wilson 95% interval 0.0073%-0.0246%), and 16 / 74,858 publish usable size
only in parsed prose (0.0214%; Wilson 95% interval 0.0132%-0.0347%). Those readings
cannot satisfy an exact structured minimum. They are not silently counted as missing.

The merchant-facing action is to publish selected size values on the affected SKUs,
correct unusable values, and move relevant labelled prose into structured fields.
For prices, publish an explicit currency with each amount or establish a trusted
catalogue currency during onboarding. No currency was invented for these raw exports.
The cached study already carries explicit currency in its price strings, so its price
publication result is different and must not be presented as raw export readiness.

A catalogue frequency does not establish the category's necessary attributes. The
suggested minimum remains subject to human review. A listing may have some structured
comparison evidence while still failing a particular required attribute. Neither zero
empty-evidence rows nor a passing proposed minimum means every purchase is verifiable.

No traffic weights were supplied. Do **not** claim that a missing-listing share is the
same share of size-sensitive traffic. The supported statement is that requests depending
on size cannot verify that attribute on listings without usable size evidence.

## Scope and reproduction

The study source is `data/cache/shopping-study/shopper-v3.json`; its metadata says
captured `2026-09-10T00:00:00Z`. The audit examines 33,485 / 33,485 supplied variant
records and ignores the embedded schema and precomputed evidence. It is a curated
multi-merchant study cohort, not a complete live merchant catalogue.

The raw source is `data/cache/shopify-raw.json`. The audit examines 74,858 / 74,858
expanded listings from 7,875 / 7,875 supplied product records across 19 / 19 supplied
hosts. Its capture time is not preserved in the export. The Allbirds demonstration
uses 2,857 / 2,857 expanded listings from 294 / 294 supplied product records for
`www.allbirds.com`; it does not claim that this host is a partner or that the export
exhausts its live store. Source and payload SHA-256 values are in each report.

Run these from a checkout containing the local caches, adjusting the cache path if
using an isolated worktree. The output prefix remains inside `approv/schema/reports/`.

```text
python -m approv.schema.report_cli data/cache/shopping-study/shopper-v3.json --shape shopping-study --merchant "Shopify study cohort" --scope "All supplied variants in the curated study; live-store completeness unmeasured" --category shopify.study.all --observed-at 2026-09-13T00:00:00+00:00 --output approv/schema/reports/shopify-study-2026-09-13
python -m approv.schema.report_cli data/cache/shopify-raw.json --shape shopify-export --merchant "Shopify raw export cohort" --scope "All supplied hosts; mixed categories require separate review" --category shopify.raw.all --observed-at 2026-09-13T00:00:00+00:00 --output approv/schema/reports/shopify-raw-2026-09-13
python -m approv.schema.report_cli data/cache/shopify-raw.json --shape shopify-export --host www.allbirds.com --merchant "Allbirds / supplied catalogue snapshot" --scope "Single-merchant supplied snapshot; live-store completeness unmeasured" --category allbirds.supplied --observed-at 2026-09-13T00:00:00+00:00 --output approv/schema/reports/allbirds-2026-09-13
```

These commands reproduce the counts; the supplied display/scope strings are part of
the report context and may differ from the checked-in handoff wording. The persisted
proposal captures the exact catalogue-derived result for re-rendering without rerunning
the exhaustive derivation. No full-catalogue work runs in the default test suite.

## Integration status

The locator contract is in `approv/schema/LOCATOR_CONTRACT.md`. The earlier surface
seam failures are closed on `1ff539a`; surface now uses schema's discovery walk.
Agreement between these two readers cannot independently establish correctness.
The [fresh public-catalogue study](public-catalogue-study.md) therefore checks raw
option tables without importing the producer, its value parser, or the algebra.

The study spans fresh stores in every requested sector, with failed endpoints and
partial captures explicitly retained. Its standalone reports are review drafts,
not an authorisation to adopt their schemas.
The discovered image-metadata defect is an Approv mapping issue requiring correction.
No production reader or decision-path change is included in that study.

Adapter billing classification remains dependent on the order-evidence record type
and the surface/intake fixes assigned to claude1. This report changes none of them.

## Pilot prerequisites: confirm before accepting an order

| Prerequisite | Merchant handoff | Failure if absent |
| --- | --- | --- |
| Order-addressable identity | Demonstrate a real order line naming the catalogue product and exactly one selected variant. Preserve SKU and variant-ID namespaces; confirm their crosswalk if the order system uses different identifiers. | A catalogue with no identifier the order can name cannot be integrated. A multi-variant snapshot with no unique matching line raises a hard mismatch. A title, array position, or another variant's identifier is not an acceptable substitute. |
| Nonempty order SKU | Supply the SKU required by `OrderLine`, even if the public feed omits it; establish its relationship to the published variant ID. | A public numeric variant ID can support binding but does not fill an absent order SKU. Do not manufacture one from product text. |
| Order-time commercial facts | Supply quantity, charged unit price, explicit ISO currency, and the snapshot/version used at the time. | Raw price strings cannot establish currency, checkout discounts, taxes, or historical availability. |
| Selected-option context | Retain the option-name table, its positions and the variant's selected values together. | A bare `option1` value loses its meaning. A whole variant array is not permission to borrow evidence from another SKU. |
| Reviewed source scope | Identify actual product fields; exclude image dimensions, image URLs and other operational metadata from product requirements. Review opaque UUID-valued selectors. | A well-typed value can describe the wrong thing. Producer/consumer agreement does not make image pixels a product attribute. |
| Category and floor confirmation | Split mixed categories; review differently named and component-specific selectors before choosing the minimum. Confirm the proposal ID explicitly through the onboarding API. | A common label such as `size` is not a universal category requirement. Bundle component sizes may exist under other names; a missing exact attribute is not proof all sizing information is absent. |
| Request and provenance | Supply what the agent stated, with its source/channel and attestation. | A cart with no usable request supports order evidence only. It must not receive an intent-verification label or price. |
| Fulfilment and retention | Retain the exact order, original product snapshot and corresponding fulfilment record so the comparison can be replayed and the shipped item identified. | Today's public feed cannot establish what the merchant offered or shipped on an earlier order. |

These are integration prerequisites, not a financial-coverage offer. A merchant must
confirm which publication gaps matter to its actual request traffic before using
listing shares to prioritise work. No messages have been sent to any merchant.
