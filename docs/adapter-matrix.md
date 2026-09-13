# Adapter fidelity matrix and enforcement blockers

Date: 2026-09-13. Inspected revision: `c7682e0`.

**Status: contract documented; runtime enforcement blocked by the file fence.**
This applies PRD §5 and DR 0020. It does not introduce priced protection or claim that
the current endpoint enforces the matrix. The audit reproduced an intake defect;
implementation stopped under the instruction to leave `approv/intake.py` to claude1.
No intake, surface, shared type, receipt, evaluator or artifact file was changed.

## Contract

“Eligible” below means eligible for the corresponding future, contract-scoped
coverage assessment. It does not mean insured, guaranteed, or entitled to a payout.
PRD §6 and DR 0012 still govern those commercial promises. A channel's eligibility
cannot turn an unstated, failed, narrowed or unverified finding into a covered one.

`Channel` says how a constraint arrived. `Constraint.source` identifies its field;
`raw_text` preserves the span when prose was read. `Attestation` independently records
which originating halves were signed. A protocol name, an agent-presence heuristic,
or `signed_mandate=True` is not verification of a signature. Do not infer customer
authentication from `MANDATE`, or origin signatures from Approv signing its receipt.

Product evidence is a separate input for every row: exact order line, SKU/variant,
quantity, typed price/currency, and the merchant's snapshot with source fields and
capture/version information. Neither a request nor a selected cart proves what was
fulfilled. Descriptions remain parsed evidence; the catalogue's source policy and
verification floor still apply. A snapshot for another SKU is not usable evidence.

| Input shape | What arrives | What does not arrive | Provenance to retain | Available product evidence | Receipt and eligible scope | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| Structured protocol request | Explicit requirement fields and typed values; supplied protocol locator; mandate artifact if actually supplied | Human conversation, omitted requirements, proof that the agent's declaration is true, proof of signature validity from the shape alone | `TOOL_ARGUMENT` with `<protocol>.<field>`; `MANDATE` only after the mandate basis is established; actual `Attestation` independently | Order and merchant snapshot supplied separately; protocol payment data alone is insufficient | Stated-request comparison when usable requirements and bound product evidence exist; agent-stated scope, potentially stronger with independently established customer authentication | Missing requirement slots: order evidence only. Unmapped/malformed or unread requirements: incomplete verification, no claim on those parts. Invalid product binding: no completed verification receipt |
| Search query plus filters | Literal merchant-observed query and selected requirement filters | Off-site/referrer-stripped query, hidden conversation, requirements not expressed in query or filters | Filter slots: `TOOL_ARGUMENT`, `search.filters.<field>`; read query: `AGENT_MESSAGE`, `search.query`, original span. Retain merchant-derived origin and actual `Attestation` | Merchant snapshot and exact order binding; search results do not prove which variant was ordered or shipped | Comparison limited to the observed query/filter requirements; merchant-derived **partial** scope | No query/filter requirements: order evidence only. Query present but not read: incomplete verification; preserve it as unread and require confirmation, never report a completed clean check |
| Declared-intent free text | The declaration exactly as submitted and the field it came from | Human's raw request, whether the agent paraphrased it faithfully, omitted intent | `AGENT_MESSAGE`, declaration field locator, verbatim text/reading spans, actual `Attestation` | Exact order and separate merchant snapshot | Comparison of the agent's stated request, subject to extraction completeness and the product floor; agent-stated scope | Blank/absent declaration: order evidence only. Reader absent, timeout, malformed response or unusable reading: incomplete/system failure as appropriate, no successful verification or coverage inferred |
| Form fields | Explicitly designated requirement fields and any requirement prose, with their original field locators and origin | Requirements inferred from checkout defaults, shipping details, or chosen cart attributes; proof of who submitted them from the form shape alone | Structured requirement slots can reuse the typed-field normalizer with `form.<field>` locators; prose retains its own channel and span. Preserve whether origin is customer-authenticated, agent-stated, merchant-derived or unknown; actual `Attestation` independently | Merchant order/snapshot separately; final form selections alone are the order, not an independent request | Only explicit requirement fields support comparison. Scope follows established origin: authenticated customer/agent-stated, merchant-derived partial, inferred/unknown none | No independent requirement fields: order evidence only. No native form shape exists today; do not disguise every form as a declared agent protocol call |
| Undeclared traffic / final cart only | Selected order lines and whatever merchant order/snapshot evidence actually exists | **Any stated requirement or customer intent.** Cart contents cannot supply the request half | No request constraints, no invented `Channel`; preserve `Undeclared.why` and actual signatures on available artifacts. Agent detection remains separate from request provenance | Exact order evidence only; record missing snapshot/fulfilment facts honestly | **Order evidence record only. Never intent verification; never intent-coverage eligible.** Distinct, lower-priced evidence product | Valid order: clearly labelled order evidence. Missing required order identity/evidence or signing failure: explicit failure/draft, no completed signed receipt claimed |

`AgentPresence.INFERRED` is an inference that the visitor was an agent. That is distinct
from Approv inventing the visitor's requirements. A real search filter remains an
observed requirement even if visitor classification is uncertain; neither fact upgrades
it to customer-authenticated intent. The current `covered` Boolean cannot express this
matrix's different scopes.

## What must be enforced at the live boundary

The following are acceptance requirements for the owning agents, **not implemented
states in this change**:

- Choose the receipt product before comparison. Absent request data selects
  `order_evidence`; it must not be a `ComparisonRecord` with empty requirements.
- Bind the product kind, observed input shape, request-origin basis, event-level
  eligibility/scope, reasons and policy version into the signed object. They must
  survive exporting the receipt independently of its API response.
- An order evidence record has a visible **APPROV ORDER EVIDENCE RECORD** title and
  “No stated request was available; intent was not verified.” It has no purchase
  authorisation verdict or per-finding guarantee masquerading as a comparison. It
  remains an evidence product if no order fulfilment observation has been supplied.
- Billing selects the distinct order-evidence product from the signed kind, with a
  lower tariff than stated-request verification. No monetary tariff is set here.
  There is no existing billing component to wire within this fence.
- A failed or incomplete extraction is not an absent request. Retain the supplied
  request and failure/unread state; do not bill or label it as completed verification,
  and never infer coverage from a verification that did not complete.
- Event eligibility limits per-finding scope. A record marked ineligible cannot
  simultaneously export unqualified `guaranteed` findings. Preserve the comparison's
  mathematical result separately; do not change the evaluator to implement pricing.

## Reproduced gaps

Using the existing `tests/test_surface.py` fixtures and real receipt signing, the
following calls returned receipts whose signatures successfully verified:

| Trigger | Current result at `c7682e0` | Required result |
| --- | --- | --- |
| `Undeclared()` with a valid order and snapshot | `ComparisonRecord`, decision `confirm`, API `covered=False`, title **APPROV ORDER VERIFICATION RECORD**; no signed product-kind or event-eligibility field | Distinct order-evidence product and signed discriminator, correctly labelled on its face |
| `Search(query="must be cotton", filters={"size": "M", "color": "Frost"})`, declared agent, no extractor | `allow`, API `covered=True`, satisfied filter findings labelled `guaranteed`, `record.unread == ()`; unread query appears only in API notes | Incomplete verification with the unprocessed query retained in a load-bearing failure/unread state; no clean verification claim |
| Matching search filters with unknown agent presence | API `covered=False`, but signed findings include `guaranteed`; no signed event-eligibility field | Ineligibility persists inside the signed record and caps displayed finding coverage |

These are deterministic reproduction cases, not an accuracy study or a catalogue-rate
estimate. The illustrative schema is the existing apparel fixture; model and prompt are
`surface-v1`; no model is called.

The reproduction can be repeated without changing any production file:

```python
import runpy
from approv.artifact import render_text
from approv.intake import AgentPresence, Search, Undeclared
from approv.receipts.chain import generate_key, public_key_hex, verify
from approv.surface.verification import verify_order

fixture = runpy.run_path("tests/test_surface.py")
key = generate_key()
cases = [
    (Undeclared(), None),
    (Search(query="must be cotton", filters={"size": "M", "color": "Frost"}),
     AgentPresence.DECLARED),
    (Search(filters={"size": "M", "color": "Frost"}), None),
]
for artifact, agent in cases:
    result = verify_order(
        fixture["request"](artifact=artifact, agent=agent),
        schemas=fixture["SCHEMAS"], signing_key=key,
    )
    verify(result.record, public_key_hex(key))
    print(type(result.record).__name__, result.record.decision, result.covered)
    print(result.record.coverage, result.record.unread, result.intake_notes)
    print(render_text(result.record, public_key=public_key_hex(key)).splitlines()[1])
```

## Required owner changes and stop condition

- **Intake, claude1:** `approv/intake.py:intake` records an unread query only in
  `notes` when no extractor exists, and computes `covered` from nonempty constraints
  and agent presence. Fix the incomplete-reading state; preserve mixed-source
  provenance; define the native form entry or a lossless form mapping. `_sourced`
  currently preserves extractor-supplied channels and source locators, so the caller
  must also enforce that extraction cannot claim stronger provenance than its input.
- **Surface/shared record types:** `verify_order` unconditionally calls
  `build_record`; `VerificationResult.record` is a `ComparisonRecord`;
  `ComparisonRecord` has no signed receipt-product or event-scope discriminator.
  Product routing and the durable classification belong here.
- **Receipt owner:** `chain.seal` revalidates through `ComparisonRecord`; a new sibling
  order-evidence type or extra fields supplied from `approv/schema/` do not survive
  that contract. Extend signing/store/standalone verification together as needed,
  retaining old signed payloads exactly.
- **Artifact owner:** `approv/artifact/render.py:TITLE` is fixed to order verification.
  Render the signed product kind and effective event scope explicitly.

An uncalled policy helper under `approv/schema/`, an unsigned wrapper, or a second
receipt implementation would not enforce the matrix in the deployed path. Those
workarounds are not supplied. Intake and all these integration points are off limits;
the explicit intake stop instruction therefore blocks Task 2 implementation. The
required input-fidelity/record change also needs its decision record before code under
CLAUDE.md invariant 8. This document records the contract and evidence for that owner
handoff; it does not claim the stop condition has been resolved.
