# Adapter fidelity matrix and enforcement blockers

Updated: 2026-09-14. Inspected revision: `10cd413`.

**Signed eligibility is fixed; product routing and intake enforcement remain blocked.**
DR 0023 now puts `covered` and `coverage_notes` inside the digest and withdraws all
finding guarantees for uncovered channels. That resolves the original unsigned-
eligibility blocker. It does not give a cart-only event a different record product:
the current endpoint still emits **APPROV ORDER VERIFICATION RECORD** without a request.

This applies PRD §5 and DRs 0020, 0022 and 0023. It does not introduce priced protection
or claim the endpoint enforces the matrix. The current audit reproduced the remaining
surface and intake defects using the real store-owned signing path. Implementation
stopped at the explicit fence. No intake, surface, shared type, receipt, evaluator,
artifact, report or billing implementation was changed or replaced.

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
| Search query plus filters | Literal merchant-observed query and selected requirement filters | Off-site/referrer-stripped query, hidden conversation, requirements not expressed in query or filters | Filter slots: `TOOL_ARGUMENT`, `search.filters.<field>`; read query: `AGENT_MESSAGE`, `search.query`, original span. Retain merchant-derived origin and actual `Attestation` | Merchant snapshot and exact order binding; search results do not prove which variant was ordered or shipped | Comparison limited to the observed query/filter requirements; merchant-derived **partial** scope | No query/filter requirements: order evidence only. Required extractor absent: incomplete verification with the unread query retained, never a completed clean check. A completed but partial reading follows the configured DR 0022 unread policy; the default withdraws guarantees without blocking the sale |
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
  `order_evidence`; it must not be a verification-labelled comparison with empty requirements.
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

## Reproduction on the merged implementation

The following cases use the existing apparel fixture in `tests/test_surface.py`,
model and prompt version `surface-v1`, audit date 2026-09-14. No model is called.
They are deterministic counterexamples, not sampled accuracy or catalogue rates;
sampling intervals are not applicable. Each draft was appended through `ReceiptStore`
and its signature verified before its artifact title was inspected.

| Trigger | Observed at `10cd413` | Status |
| --- | --- | --- |
| `Undeclared()` with valid order and snapshot | `ComparisonRecord`, `decision=confirm`, `completion=completed`, signed `covered=False`, no signed product kind; title **APPROV ORDER VERIFICATION RECORD** | **BLOCKED:** cart-only traffic still produces the wrong product |
| `Search(query="must be cotton", filters={"size": "M", "color": "Frost"})`, declared agent, no extractor | `allow`, `completed`, signed `covered=True`, guaranteed filter findings, empty `unread`; the unprocessed query is mentioned only in signed notes | **BLOCKED:** notes now survive signing but still do not enforce the unread/failure state |
| Matching search filters with unknown agent presence | Signed `covered=False`; every finding `out_of_coverage` | **FIXED by DR 0023:** previously uncovered channels could retain guaranteed findings |
| `Structured(protocol="form", fields={"size": "M"})`, no declared origin | Intake infers a declared agent from the protocol-shaped object; signed `covered=True`, source `form.size` | **BLOCKED:** treating a form as an arbitrary protocol name fabricates its origin |

The old audit at `c7682e0` correctly identified unsigned eligibility. That diagnosis
is historical now; it must not be repeated as the remaining blocker.

Reproduce from the checkout without changing any production file:

```python
import runpy
import tempfile
from pathlib import Path

from approv.artifact import render_text
from approv.intake import AgentPresence, Search, Structured, Undeclared
from approv.receipts.chain import generate_key, public_key_hex, verify
from approv.receipts.store import ReceiptStore
from approv.surface.verification import verify_order
from approv.types.core import ComparisonRecord

fixture = runpy.run_path("tests/test_surface.py")
key = generate_key()
scratch = Path("approv/schema/.pytest-tmp-matrix-audit")
scratch.mkdir(exist_ok=True)
cases = [
    (Undeclared(), None),
    (Search(query="must be cotton", filters={"size": "M", "color": "Frost"}),
     AgentPresence.DECLARED),
    (Search(filters={"size": "M", "color": "Frost"}), None),
    (Structured(protocol="form", fields={"size": "M"}), None),
]
with tempfile.TemporaryDirectory(dir=scratch) as temporary:
    store = ReceiptStore(Path(temporary) / "audit.sqlite")
    for index, (artifact, agent) in enumerate(cases):
        request = fixture["request"](artifact=artifact, agent=agent).model_copy(
            update={"correlation_id": f"matrix-audit-{index}"})
        draft = verify_order(request, schemas=fixture["SCHEMAS"])
        payload = store.append(draft.record, signing_key=key)
        verify(payload, public_key_hex(key))
        record = ComparisonRecord.model_validate(payload)
        print(type(record).__name__, record.decision, record.completion)
        print(record.covered, record.coverage, record.coverage_notes, record.unread)
        print(getattr(record, "record_kind", None))
        print(next(line for line in render_text(
            record, public_key=public_key_hex(key)).splitlines() if "APPROV ORDER" in line))
```

## Specific owner changes needed to enforce the matrix

**Surface and record vocabulary: choose the receipt product before calling the
comparison builder.** `verify_order` still unconditionally invokes `build_record`,
and `VerificationResult.record` still accepts only `ComparisonRecord`. Introduce a
signed product discriminator and a real order-evidence payload/route carrying the
order, snapshot, provenance, absence reason and explicit statement that no intent was
verified. An order-evidence payload must not present an authorisation verdict or
comparison/guarantee fields as its product result. Keep genuine stated-request
comparisons distinct, including comparisons from uncovered channels. `covered=False`
is not a product discriminator.

Classify **absence from the input**, not from an empty extracted constraint list.
`Undeclared`, an empty/blank declaration, and genuinely empty request slots select
order evidence. Supplied request content that was unmapped, could not be read, or
failed extraction is a failed/incomplete verification attempt with that content and
failure retained; it must not be laundered into either absent intent or a clean check.
A final cart, selected form defaults or SKU attributes cannot create requirements.

**Intake and surface: make unprocessed request content load-bearing.** In the Search
and FreeText branches, no extractor currently adds a note but no unread/failure state.
Retain the original unread span and explicitly signal that required extraction did
not run. Surface must record the appropriate incomplete `Completion`, with
`covered=False` and no guarantees. Keep this separate from a completed but partial
reading, whose configured DR 0022 policy may permit the sale while withdrawing coverage.
Do not route either rule through a new evaluator policy.

**Intake: preserve actual request origin, including forms.** A native form artifact or
an explicitly provenance-preserving form mapping must distinguish independent request
fields from checkout/fulfilment fields and carry the observed submission basis. Merely
setting `Structured.protocol="form"` currently calls `_implied_presence` and promotes
the source to a declared agent. Existing `Channel` locators plus actual `Attestation`
should be retained; neither proves customer authentication by itself. `_sourced` also
preserves arbitrary extractor-supplied channels and source locators, so extraction can
claim `MANDATE` or another field of origin without enforcement. The owner must constrain
those claims to the input's established provenance. Remove personal details before
intake under invariant 10; a shipping form is not a request artifact wholesale.

**Artifact and receipt owners: preserve and render the product distinction.** The
fixed `artifact.render.TITLE` must dispatch from the signed product kind. Order evidence
must say **APPROV ORDER EVIDENCE RECORD** and “No stated request was available; intent
was not verified.” Extend store-owned signing, standalone verification and consumers
for that product, preserving historical signed bytes. A wrapper or schema-only sibling
type cannot satisfy the current `ComparisonRecord`-only signing/store contract.

**Commercial integration:** select the lower-priced `order_evidence` tariff from the
signed product kind, never from an unsigned API flag or empty findings. Actual fees
remain merchant configuration; no tariff amounts or underwriting promises are defined
here. There is no billing component within this fence to connect.

DR 0023 explicitly leaves coverage policy and pricing unchanged. It authorises the
durable eligibility fields, not these additional product/origin decisions. The owner
must record the remaining decision-path/coverage-language changes under invariant 8
before implementing them; authoring that decision record is also outside this fence.

An uncalled policy helper under `approv/schema/`, an unsigned label wrapper, or a second
receipt implementation would not enforce the deployed matrix. None was supplied.
The producer option-table contract can proceed independently; matrix runtime enforcement
stops here until the user coordinates these specific off-fence changes.
