# DR 0006 — One ontology, many lexicons

- **Status:** ON HOLD 2026-09-04 — approach accepted, sequenced after the node structure. Lexicons are derived from the ontology, so the ontology is authored first.
- **Raised:** 2026-09-04, by the founder
- **Touches:** `profiles/`, entity linking, the record's version pins, internationalisation
- **Blocks:** the taxonomy artifact's file format

---

## The question

In Indian English "shoes" is frequently used to mean *footwear generally*, and
"sneakers" is often used to mean *shoes generally*. In American English neither is
true. The founder's question: do we maintain one semantically strict DAG plus a
separate India-specific one that behaves differently?

The founder also noted the correct scoping constraint: **the verifier is not
India-specific, only the payment leg is.** UPI makes India the first market, but
nothing about comparing a stated request to a product is local. Forking the core
structure per country would be a permanent tax on the one component that should
generalise for free.

---

## The observation that resolves it

**Sandals are not sneakers anywhere on Earth.** What varies between markets is not the
structure of the world, it is which words point at which parts of it.

The ontology is universal. The vocabulary is local. Those are two different artifacts
that have been conflated because in a single-market system they can be.

This is not a novel move — it is how SKOS separates concepts from labels, and how
WordNet separates synsets from lemmas. It is novel *here* only because verification
systems typically hardcode one market's vocabulary into their category list and then
discover the problem at the border.

## Proposal

**One ontology. N lexicons.**

**The ontology** — the DAG. Nodes are concepts with opaque, non-linguistic ids
(`node:footwear.sneaker`, not `"sneakers"`). Edges are `is-a`. This is what `algebra/`
runs subsumption over. It is **never localised**, changes rarely, and is *authored*.

**A lexicon** — per locale (`en-IN`, `en-US`, `hi-IN`). Maps surface terms to
candidate node ids, each with a **reading**:

| Locale | Surface term | Candidate node | Reading |
|---|---|---|---|
| `en-US` | "shoes" | `footwear.shoe` | exact |
| `en-IN` | "shoes" | `footwear.shoe` | exact |
| `en-IN` | "shoes" | `footwear` | **broadened** |
| `en-IN` | "sneakers" | `footwear.shoe.sneaker` | exact |
| `en-IN` | "sneakers" | `footwear.shoe` | **broadened** |
| `en-IN` | "chappals" | `footwear.sandal.flipflop` | exact |

Lexicons are *learned* from traffic (via the pending queue in DR 0003), reviewed in
batches, and versioned independently of the ontology. Different change rates:
ontology quarterly, lexicon weekly.

## How a broadened reading behaves — no new machinery required

A surface term resolves to a **set** of candidate nodes, not one. Run subsumption
against every candidate:

- **All candidates agree** → that is the answer. Ambiguity that does not change the
  outcome is not ambiguity worth surfacing. In practice this is the large majority of
  cases: a shopper who types "shoes" in India and is shown a *sneaker* gets `satisfied`
  under both the exact and broadened readings.
- **Candidates disagree** → `unknown` → `confirm` (§4.4). This is exactly the sandals
  case: strict reading says `violated`, broadened reading says `satisfied`, so we do
  not know, so we ask.

The ambiguity machinery already required for multi-parent DAGs and multi-candidate
entity linking absorbs localisation with **no additional mechanism**. Broadening is
just another source of candidate multiplicity.

## Why this is worth more than it looks

1. **Adding a market is a data file, not a fork.** No second DAG to keep in sync, and
   no risk of two ontologies silently drifting into disagreement — which is the failure
   mode that makes per-country forks unmaintainable by year two.
2. **The lexicon is the asset that compounds per geography.** Each market's vocabulary
   is built from that market's own traffic through the pending queue. It is slow to
   accumulate, cheap to keep, and cannot be copied quickly by a competitor entering the
   same market later. Geography *adds* to the moat instead of diluting it.
3. **It makes a colloquialism measurable.** "Does `en-IN` 'shoes' broaden to footwear?"
   becomes a reviewable data claim with an accuracy consequence, rather than an
   assumption buried in someone's category list.
4. **`lexicon_version` pins into the record** alongside `taxonomy_version`. A receipt
   stays reproducible even after the vocabulary moves, which it will, weekly.

## Consequences for the guideline

`data/guideline.md` must instruct annotators on the reading, not just the label. If an
annotator is shown *(request: "shoes", product: sandals)*, is the gold label
`satisfied`, `violated`, or `unknown`? Under this proposal it is `unknown` for `en-IN`
and `violated` for `en-US`, which means **the gold set is locale-tagged** and the
accuracy number carries a locale alongside the denominator, category, model version,
prompt version and date required by §4.6.

That is a new field on §4.6's list, and it should be added.

## Options

**Option 1 — one strict ontology, no localisation.**
- *For:* simplest; semantically defensible.
- *Against:* refuses legitimate Indian purchases at a rate nobody will tolerate, in the
  launch market.

**Option 2 — one ontology per locale.**
- *For:* each market gets exactly what it needs.
- *Against:* N structures drifting apart; a fix applied once must be applied N times;
  by the third market this dominates engineering time.

**Option 3 — one ontology, N lexicons with per-term readings.**
- *For:* everything above.
- *Against:* two versioned artifacts instead of one; entity linking must return a
  candidate *set* rather than an id, which every downstream consumer must handle.

## Recommendation

**Option 3.** The set-valued return is required anyway — DR 0003 already forces
multi-candidate handling for multi-parent products — so the marginal cost is close to
zero, and it converts internationalisation from a fork into a data-entry problem.

## Decision

*(founder — fill in, then set Status to CLOSED and record the date)*
