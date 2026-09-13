# Decision records — index

23 records, **9 still open**. Read this
file instead of opening them. Full text is kept for the reasoning, not for re-reading.

Under the 10 September contract only a §3.8 change earns a new record: the decision path,
coverage language, or a number that will be published. Nothing else does.

| # | Question | Status |
|---|---|---|
| [0001](0001-unstated-vs-unavailable.md) | Does the ternary need a fourth value? | closed |
| [0002](0002-where-comparison-lives.md) | Where do the comparison operators live? | closed |
| [0003](0003-taxonomy-shape.md) | Taxonomy shape, entity linking, and who may edit the taxonomy | closed |
| [0004](0004-latency-budget-and-degradation.md) | Latency budget, and which way we fail when it runs out | closed |
| [0005](0005-request-side-provenance.md) | Constraints carry provenance too | **OPEN** |
| [0006](0006-ontology-vs-lexicon.md) | One ontology, many lexicons | on hold |
| [0007](0007-verification-floor.md) | The verification floor: minimum data per category | closed |
| [0008](0008-what-we-actually-receive.md) | What we actually receive, and what we can honestly claim from it | **OPEN** |
| [0009](0009-monotone-model-use.md) | Can Approv itself be an agent? The monotone safety rule | **OPEN** |
| [0010](0010-agent-side-product.md) | The agent is the customer, and the badge is an underwriting instrument | closed |
| [0011](0011-partial-facets.md) | Partial facet coverage: a node exists, its other facets do not | closed |
| [0012](0012-loss-data-and-underwriting.md) | Loss data, and what makes an indemnity priceable | **OPEN** |
| [0013](0013-confirmation-surface.md) | The confirmation surface | **OPEN** |
| [0014](0014-escalation-ladder.md) | Who receives a `confirm`? The escalation ladder | **OPEN** |
| [0015](0015-breaking-the-data-deadlock.md) | Breaking the corpus deadlock | **OPEN** |
| [0016](0016-grounding-reframe-and-position.md) | The grounding reframe, the graded score, and where Approv sits on the wire | **OPEN** |
| [0017](0017-traceable-shopping-experiments.md) | Traceable shopping experiments and comparison corrections | closed |
| [0018](0018-original-requests-and-synthetic-experiments.md) | DR 0018: Original requests and disclosed synthetic experiments | closed |
| [0019](0019-candidate-evidence-review.md) | DR 0019: Review the retrieved shelf with explicit evidence limits | closed |
| [0020](0020-merchant-defence-and-the-dispute-artifact.md) | Merchant defence, and the record as a dispute artifact | **OPEN** |
| [0021](0021-what-unread-means.md) | What `unread` means, and why two definitions were live | closed |
| [0022](0022-what-an-unread-request-does.md) | What an unread request does to the answer | closed |
| [0023](0023-coverage-belongs-on-the-record.md) | Coverage belongs on the record | closed |

## The open ones, and whether they still matter

Several were opened before DR 0016 moved the question from intent-matching to grounding,
and before three studies measured +0.0 pp against control. They should be closed or
dropped rather than carried:

- **0014 escalation ladder** — blocks `gate`, which is in this weekend's scope. Needs a decision.
- **0013 confirmation surface** — blocks the confirmation screen. Needs a decision if that ships.
- **0016 grounding reframe** — already adopted; it is §1 of the contract. Close it.
- **0015 data deadlock** — answered: answer keys derive from published fields by code. Close it.
- **0004, 0005, 0008, 0009** — written for the intent-matching framing DR 0016 replaced. Re-read against §1 before spending more on them.
- **0012 underwriting** — unparked by DR 0020. The guarantee is now the product, not a
  someday feature. Still blocked on loss data, but it is the thing to go get.
- **0010 agent-side product** — reopened by DR 0020. Its conclusion that the agent is the
  customer is demoted: the agent-side surface is kept as an easier input case, but the
  merchant is the buyer.

DR 0020 is the live one. Its two unmeasured numbers — the share of agent orders carrying a
recoverable stated request, and the share of clean-record refunds provable from merchant
fulfilment records — decide whether the product works.

