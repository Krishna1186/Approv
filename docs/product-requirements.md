# Product requirements

Written 12 September 2026, replacing the 8 September PRD (archived — it described the
correction loop, retired after three +0.0 pp studies). `CLAUDE.md` is the engineering
contract; this is the product and commercial shape it serves. Where they disagree,
`CLAUDE.md` wins.

---

## 1. What is being built

A merchant-side service that records what an agent requested, compares it against the
exact product and order the merchant is about to fulfil, emits a deterministic signed
comparison record, and establishes whether a later refund or dispute was caused by the
merchant or by the agent.

**The central claim, stated precisely.** Not that Approv knows whether the customer is
physically satisfied. That Approv creates a defensible record of what the agent requested
and whether the merchant's recorded order matched it.

**Selling:** evidence, attribution, and *later* partial loss protection. Not better
product recommendations.

The merchant is the customer because the merchant absorbs the loss: refund amount, return
shipping, support handling, dispute and chargeback fees, payment-processing consequences
above a network threshold, and trust with the customer or agent platform.

The commercial distinction that makes this a product: **the agent may have made the
mistake, the merchant still bears the financial consequence.**

## 2. The transaction

```
agent request
  -> Approv captures request and provenance
  -> merchant supplies exact SKU, variant, quantity, price, evidence
  -> Approv compares request against the proposed order
  -> deterministic result
  -> signed comparison receipt
  -> merchant fulfils
  -> on refund or dispute, the receipt establishes what was requested and delivered
```

## 3. The integration object — the current gap

**The merchant order must become the centre of gravity.** Today it is `ShoppingCase` +
`Inventory`, which are harness objects, and there is no service surface at all. That gap
is the distance between the pitch and the build.

**Request in:** merchant_id · order_id · agent_session or correlation id · the request or
the agent's representation of it · exact SKU and variant ids · quantity · price · currency
· catalogue snapshot and version · source fields and timestamps · agent identity where
available · checkout and payment state · verification mode.

**Result out:** per-attribute findings · completeness and missingness · deterministic
decision · reason codes · per-finding coverage · receipt id · snapshot hash · signature ·
evaluator and prompt versions.

`ComparisonRecord` already carries the request half well — `request_text`,
`request_constraints`, `completeness`, `unread`, `findings`, `coverage`, `attestation`,
`correlation_id`, the version triple and the hash chain.

**Built, 12 September.** `OrderLine` on the record carries `order_id`, `line_id`, `sku`,
`variant_id`, quantity, `unit_price` as typed `Money`, availability and catalogue version,
and it is inside the digest like everything else, so a price cannot be adjusted after the
outcome is known. Two bindings, both enforced rather than conventional: `ComparisonRecord`
rejects an order line naming a different product from the comparison, and the surface
rejects a catalogue snapshot that identifies itself as a different product from the order.
`availability` and `checkout_state` are the merchant's own terms, recorded verbatim and
decided on by nothing — DR 0004's failure semantics are still open.

`product_snapshot` stays an untyped dict on purpose: it is the merchant's record as it
stood, argued against as-is, and typing it would mean re-typing every merchant's export.
What changed is that nothing load-bearing lives in it any more.

**The entry point is `approv/surface/verification.py`**, framework-free and testable with
no server; `approv/surface/api.py` is the only module in the repo that imports FastAPI
(`POST /v1/verify`, `GET /v1/health`). Schemas, the catalogue reader, the extractor, the
signing key and the floor policy are deployment configuration, not request payload — a
caller cannot supply their own schema, because the party being defended must not define
what counts as a match.

"The product matched" is not a dispute defence. The receipt now names the exact variant,
quantity and price it checked.

## 4. Outcome semantics

`allow` / `confirm` / `refuse` stay as the engine's states — renaming them churns the
engine, the tests and every decision record for nothing. The merchant-facing labels are a
presentation concern and may differ.

**One genuine gap: `system_failure`.** A provider timeout, a malformed model response and
a real product mismatch are materially different events and must not collapse into one
refusal. Nothing currently routes them apart. **No coverage may ever be inferred from a
verification that did not complete.** This is DR 0004, still open.

## 5. Input fidelity decides the product and the price

Approv accepts whatever traffic the merchant receives — structured protocol request,
search query, form fields, tool call, imperfect natural language. It cannot depend on any
agent platform exposing a preferred format (invariant 9).

But the shapes are not equivalent and must not be priced as though they were. For each
adapter, document: what request data arrives, what cannot, how provenance is represented,
what product evidence exists, whether a receipt can be produced, whether the event is
coverage-eligible, and the fallback state.

**An adapter receiving only a final cart and no request cannot produce intent
verification.** It can produce an order evidence record. That is a different product,
labelled differently and priced lower.

`Channel` and `Attestation` already carry this distinction — populate them honestly rather
than defaulting. Missing original intent is a **product state**, not an implementation
failure:

| State | Coverage-eligible |
|---|---|
| Customer-authenticated request | yes, strongest |
| Agent-stated request (declared intent, protocol) | yes |
| Merchant-derived (site search, filters) | partial |
| Inferred | no |
| No usable request | no — order evidence only |

## 6. Coverage contract — unanswered, and not to be promised until it is

Until these are answered, **coverage is a future direction and must not be stated as a
current promise in any merchant conversation.**

What mistakes are covered · is it limited to agent-caused intent mismatch · are merchant
catalogue errors excluded · stale inventory · what if the request was unavailable · what if
the agent fabricated a constraint · customer changed their mind · non-delivery or damage ·
what evidence files a claim · per transaction, merchant or incident · cap · deductible ·
who funds the reserve · is Approv an insurer, administrator, warranty provider or
technology vendor · jurisdiction and contractual language.

The last one decides regulatory exposure and has never been asked. Owner: founder plus
counsel, not an engineering task. DR 0012 is the record.

## 7. Merchant-loss taxonomy

Distinct from `docs/error-catalogue.md`, which catalogues engine errors. This catalogues
*loss causes*, and it drives both the pilot dashboard and future underwriting.

Wrong product · wrong variant · wrong quantity · wrong pack size · prohibited substitution
· missing request provenance · agent-invented constraint · merchant catalogue error ·
stale snapshot · price mismatch · availability mismatch · customer changed mind ·
fulfilment error · delivery or damage · payment or chargeback · Approv unavailable ·
Approv result overridden by merchant.

Only a subset is ever attributable to the agent. Only a subset of *that* is insurable.

## 8. First market

A merchant or small marketplace that is starting to take agentic traffic, already has
expensive returns or disputes, controls its own catalogue and order system, can expose
request and order data, cannot influence the major agent platforms, and has enough volume
to measure but not enough risk infrastructure to build this itself.

Payment networks and dominant marketplaces are eventual distribution or underwriting
partners, not the first implementation customer.

**The pilot:** one merchant · one category with clear attributes · one verification
endpoint · one defined loss type · one pilot period · one before/after measurement · one
capped commercial offer.

First sale is *"an auditable record, and less ambiguity in agent-originated returns."*
Coverage is introduced only when data supports pricing.

## 9. Revenue, in order

Per-verification fee → monthly platform minimum → premium for retained receipts, replay
and reporting → risk fee on volume and measured exposure → claims or coverage fee for
defined protected events.

A basis-point fee on agent-originated order value is easier for a merchant to understand
than a per-attribute model, and it should be tied to the loss Approv prevents or
underwrites. Do not present all five at once.

**Not a revenue stream:** reselling merchant behavioural or shopper preference data. It
introduces trust and privacy exposure and contradicts the positioning. The defensible
asset is the verified event and aggregate risk knowledge.

## 10. What to measure now

The shopping experiment debugs the comparison engine. It is not the business metric. Pick
few and measure them properly:

1. Share of agent orders with sufficient request provenance
2. Share of orders with exact SKU binding
3. **Refund rate after a clean receipt** — one of DR 0020's two decisive unknowns
4. Guaranteed false-allow rate, with denominator and interval (§3.6)

Then latency p50/p95, determinate-result rate, merchant override rate, and conversion
impact. Arms must include merchant flow without Approv and merchant flow with receipt
only — otherwise the study measures the engine again rather than the evidence value the
product sells. The correction-feedback arm is retired.

## 11. Receipt hardening — known gaps

Built: canonical serialisation, Ed25519 signing, hash chain, standalone verifier that
imports no engine code, asserted by test.

Missing: **key rotation · signature versioning · replay protection · key management ·
independently retained manifest.** The receipt must prove what Approv saw at decision
time, not that Approv later generated some JSON.

## 12. Milestone

```
merchant order event -> verification API -> signed receipt
                     -> merchant-readable result -> retained audit record
```

One category, one merchant integration, one exact order path, one measurable loss type.
Reduce surface until that works end to end.
