# Security and reliability register

Updated 2026-09-08 for DR 0017. These are software properties, not payment assurance.
The payment evaluator and signing system do not exist in this implementation.

| Property | Current implementation | Evidence / limit |
|---|---|---|
| Unit/dimension integrity | Quantity operators validate the canonical unit against its dimension and claim spec | test_forged_dimension_fails_loudly |
| Source profiles | Runner requires registered fields, applies certainty ceilings, and respects profile attribute scopes | test_unprofiled_source_cannot_supply_clean_match; test_profile_caps_spoofed_certainty_and_advice |
| Advice handling | Advice is reported but excluded from supporting evidence | Same profile test; does not establish legal liability |
| Nominal identity | Whole normalized names, explicit aliases, or trusted IDs; no token-containment identity | test_nominal_overlap_is_not_identity; test_explicit_aliases_do_not_combine_into_fictional_brand |
| Conflicting fields | Pairwise disagreement produces an unresolved finding and actionable repair, independent of input order | test_conflict_is_order_independent_and_actionable; test_disagreement_detected_when_both_fields_reject_claim |
| Missing checks | Duplicate claims and unsupported attributes are explicit findings; schema floors are validated | test_all_duplicate_claims_reported; test_unknown_claim_reported |
| Fixed request | Session snapshots the case; action schema cannot override constraints or submit evidence provenance | test_observation_is_a_copy; test_action_cannot_inject_provenance |
| Frozen inventory | Source hash binds to the actual typed inventory and source snapshots; duplicate IDs and malformed dimensions rejected | Inventory validation; test_traces_replay_against_original_snapshot |
| Bounded experiments | Equal action limits; review opportunities recorded; invalid/empty/truncated/provider failures remain failures | test_bound_budget_cannot_be_bypassed; test_failures_are_not_abstentions |
| Trace integrity | Hash links plus a retained manifest and deterministic response replay | test_trace_tampering_rejected; test_manifest_missing_arm_is_rejected |
| Independent scoring | Human outcome labels kept outside execution inputs; exact SKU/count scoring imports no comparison operator | test_gold_is_optional_and_never_used_during_execution |
| Local browser surface | Loopback binding, Host/Origin checks, opaque current-session tokens, request-size limits, textContent rendering | HTTP integration tests and browser QA; not a hosted multi-user service |

**Trust boundaries that still matter**

Source profiles are trusted configuration. The runner cannot prove that an arbitrary
caller acquired a field honestly. In the shopping harness, the inventory loader supplies
evidence and the action schema does not let agents replace it. A future merchant/MCP/
browser adapter must establish the same boundary before a provenance ceiling is useful.

Closed-vocabulary extraction and structured JSON are not proofs of injection resistance.
An attacker can ask for a permitted but wrong value. Deterministic arithmetic over
model-chosen facts is still dependent on those facts. The current tests establish the
listed boundary properties; they do not demonstrate robustness against an independently
constructed hostile-text corpus.

A source-attribution enum is not a contract, an enforceable remedy, or a finding of legal
liability. Extraction assurance is not a calibrated probability that a product fact is
true. Product listings can be stale, misbound to variants, or wrong about physical goods.

Hashes establish integrity against a retained manifest. They do not establish signer
identity, timestamp authority or completeness when the manifest itself can be replaced.
A chain alone does not detect a missing suffix. Retain a separate checkpoint for audit
use. Signing, key management, revocation, independent witnesses, and purchase binding
remain planned work.

External command/gateway integrations are trusted code and are not filesystem-sandboxed
by this harness. Keep answer keys inaccessible to the external agent. Browser operators
must reset agent context between tasks; the server cannot reset an opaque agent's memory.
Provider credentials are not written into request metadata, and provider exception bodies
are not logged. User-written adapters must follow the same credential discipline.

No purchase authorization, timeout-to-allow behavior, indemnity decision, or live merchant
checkout was added. Tests on artificial software fixtures must never become published
agent accuracy figures. See [the run guide](shopping-harness.md) for independent labels,
replay, metrics and experiment limitations.
