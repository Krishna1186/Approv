# Fresh public catalogues: method and current blocker

**Written at `1ff539a`, and three of the things it calls blockers have since been ruled
on — read this for the method, and `progress.md` for the current counts.** The defects it
pinned became DR 0027 (image metadata is not product evidence), DR 0028 (a value the
merchant enumerated is a label) and DR 0029 (one usability rule for both halves), each
implemented and measured. Retrieval also moved from 32 stores to 38 once the fetcher
stopped recording a TLS handshake failure as a merchant's refusal. Everything below about
*how* the cohort was collected and what the counts may and may not be used for still
stands unchanged, which is why it is kept as written rather than edited in place.

This implements the founder's public-feed instruction using DR 0015's catalogue-report
route and DR 0007's floor counts. It changes no production decision, source policy or
coverage language. All proposals require human confirmation. The base under audit is
`1ff539a`; `schema-onboarding-v1`, model `none-deterministic`, prompt `none`.

The frozen candidate cohort is in
[`cohort.json`](../approv/schema/public_catalogues/cohort.json). It is purposive, not a
random sample of Shopify or D2C merchants. Access failures stay in the cohort; they
must never be called schema failures or silently removed from the denominator.
Public terms were checked and archived. The founder's explicit limited public-feed
instruction is the collection authorisation; terms flags are recorded, not presented
as legal clearance. Robots denials, HTTP failures and authentication barriers are
not bypassed. The earlier extra approval question was withdrawn as unnecessary.

The standalone report index carries dated counts, Wilson intervals, sector denominators
and a handoff for each fetched store. It is thirteen megabytes of generated HTML and is
not committed; regenerate it with the audit command under **Reproduce** below, which reads
the local cache and writes an `index.html` next to one report per store. Each report has publication/missingness by attribute, its proposed minimum,
remediation, order-addressability prerequisites and the independent-reader audit.
The store table distinguishes pagination-complete and capped captures.

## Collection and provenance

Requests use the declared `ApprovCatalogueAudit/1.0` user agent, no authentication or
cookies, no alternate private backend, and no retries or access-control bypass. Starts
are globally spaced by at least 1.5 seconds across at most two workers. Public robots
and terms responses are cached first. A short policy linking same-store terms is
followed; a missing policy is recorded as unavailable. A successful policy HTTP response
does not establish that comprehensive terms were published: Graza's policy concerns
messaging, and Heath's linked terms page contains contact text. These limitations remain
review items, not legal clearance. Keyword screening is conservative triage, not legal
interpretation; Tower 28 also limits commercial use despite no automation keyword.

Feed pages use `limit=250`, advance `page`, and stop at a short or empty page. A repeated
response, access failure, invalid JSON, byte cap or page cap stops collection with an
explicit partial/error state. The default page cap is twenty pages. These are retrieval
parameters, not published population estimates. Pagination exhaustion does not prove
live-store completeness or snapshot consistency during a changing inventory.

The local cache is `data/cache/public-catalogues/2026-09-14/` in the main workspace.
Every response records requested/final URL, UTC start/end, HTTP status, response bytes,
SHA-256, content type, ETag and Last-Modified where supplied. Sensitive response headers
are not retained. The aggregate product file has its own hash, checked before derivation.
Raw feeds and archived terms remain in the ignored local cache; this work does not
redistribute a merchant corpus. Per-store audit JSON includes capture provenance.

An initial connectivity probe used `limit=1` on Chubbies, Graza, Koio and Cocokind before
the cohort was frozen. Those responses were not retained and are excluded from every
reported denominator. Chubbies returned HTTP 404; the other probes returned HTTP 200.
No catalogue findings are derived from those transient probes.

## What the counts mean

* **Retrieved** means a nonempty public feed was captured, including an explicitly
  partial capture. **Derivable with a usable minimum** means schema construction succeeds,
  yields attributes and a nonempty proposed floor, and at least one captured listing
  meets it. This does not mean the proposal is correct or ready to adopt.
* Attribute shares and the proposed-floor gap reuse the onboarding publication patterns
  and `harness.coverage` Wilson implementation. The denominator is expanded captured
  listings; request frequency and conversion are unmeasured. Mixed categories and exact
  option-label aliases need review before interpreting a gap as absent product information.
* Locator frequencies are reported both per store and per proposed field profile. The
  taxonomy includes object pointers, variant/array fields, selected slots with option
  tables, named-pair selectors, and labelled-prose selectors. Zero observed examples of
  a shape is not evidence the resolver supports that shape universally.
* Every rate includes its numerator, denominator and descriptive Wilson 95% interval.
  Counts are exact for retained rows. Intervals do not make the purposive store selection
  representative, repair access selection bias, or imply a product-truth accuracy result.
* Each store has a stable hash sample of at most two hundred variants for the production
  reader probe. The independent answer key reads root option positions and the selected
  variant directly; it imports no Approv code. Nominal values must preserve the whole raw
  label. Typed values have a narrow independent source-fidelity check; unsupported unit
  alias cases are explicitly unassessed. A faithfully read `9 M` still needs category
  review before anyone claims that it describes metres rather than a footwear size label.
* Missing evidence, wrong selected evidence, reader/binding exceptions, image-metadata
  evidence and report/reader disagreements are counted separately. Synthetic probes with a published SKU use
  a diagnostic order with zero amount and ISO no-currency code `XXX`; they never call
  verification, produce receipts, or masquerade as actual merchant orders. Without a
  published nonempty SKU, binding is explicitly unassessed and the evidence reader is
  checked against an independently selected raw variant. An invented SKU must not
  manufacture a false binding-failure result.
* Raw identity completeness is counted across every retained variant, not only the probe
  sample. A published variant ID is only a candidate join key: the merchant must demonstrate
  that its order system can name it. Empty SKU and no order-addressable identifier are
  deliberately different measures.

## Defects and onboarding findings

**Confirmed structural defect: image metadata becomes product evidence.** The public
feed carries `variants[].featured_image.width`, `.height`, `.src` and sometimes `.alt`.
Discovery proposes those sources as product attributes, and surface reads them with exact
merchant attribution. Pixel dimensions and image URLs are not product dimensions or
customer selection attributes. This is a wrong subject, not merely missing data.

The minimal synthetic reproducer is the `records` fixture in
[`test_public_catalogues.py`](../approv/schema/tests/test_public_catalogues.py). The
correct contract is pinned as an individual strict expected failure. It must fail if
the fix lands without clearing the marker. The requested source-policy change is to
exclude media metadata from product discovery without indiscriminately discarding
similarly named legitimate product fields. Because surface now consumes this walk,
that fix changes runtime evidence and needs the owner's decision record first under
CLAUDE invariant 8. No production discovery or surface edit was made here.

**Confirmed report/reader disagreement: combined waist/length labels.** A selected value
such as `34/32L` is reported as unusable publication by schema derivation, but surface emits
it as exact nominal evidence. A second individual strict expected failure pins this
contract. The owner must choose consistent nominal-selector usability between
`schema.derive._usable` and `surface.verification._settled_value`; this work changes
neither. Source-specific zero-publication reports cannot be used as proof that the
deployed reader emits no evidence from those sources.

**Semantic review items, not automatic defect labels:** UUID-shaped option selections
can represent operational listing identities; bundle selectors often name a component
and its size instead of the bare label `Size`; a `Colors` selector is not silently merged
with `Color`. The report identifies the scope and requests mapping review rather than
asking a merchant to republish facts it may already supply under another name. Currency-
ambiguous gift-card denominations remain missing readings, not wrong values or guessed
USD amounts.

The [partner handoff](catalogue-verifiability-report.md#pilot-prerequisites-confirm-before-accepting-an-order)
now states order identity, SKU mapping, currency, source context, category/floor review,
stated request, and fulfilment retention prerequisites explicitly.

## Reproduce

Run from this checkout, adjusting the cache path when working outside the main workspace:

```text
python -m approv.schema.public_catalogues.fetch C:/Users/omen/Approv/data/cache/public-catalogues/2026-09-14 --terms-policy record-only
python -m approv.schema.public_catalogues.audit C:/Users/omen/Approv/data/cache/public-catalogues/2026-09-14 approv/schema/reports/public-2026-09-14
python -m pytest approv/schema/tests/test_public_catalogues.py -q
```

Acquisition is explicit and cached; normal pytest never accesses the network or scans a
full live/cache catalogue. The independent key generator has network-free adversarial
tests for borrowed-variant values, absence versus wrong evidence, option positions,
duplicate option definitions, identifier absence and unsupported type scope. Acquisition
tests pin repeated-page termination, terms/robots/access stops and cache hash validation.

Human spot-checks of the key generator remain **pending**. Per-store raw/evidence packets
are retained at `<host>/human-review-packet.json` in the local cache; model inspection is
not labelled a human audit. No store has been contacted and no report has been sent.
