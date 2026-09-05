# guideline.md — annotation guideline, footwear / `en-IN`

> **STATUS: SKELETON. NOT USABLE YET.**
>
> This file contains the **questions** that must be answered before a single label
> exists. It deliberately contains **no answers**. `CLAUDE.md` §3 Stage B requires this
> guideline to be hand-written by the founder, and §5 forbids Claude from producing or
> influencing labelling decisions. Claude wrote the questions and the worked examples so
> the task is concrete; every answer below is the founder's.
>
> **Delete this banner when the file is complete.**

## Why this file exists before any label

Two annotators shown the same pair must produce the same label. Where they disagree,
Cohen's kappa drops, and §10-B says **a low kappa indicts the guideline, not the
annotator.** So every case where a reasonable person could go either way has to be decided
*here*, in advance, in writing. A guideline that says "use your judgement" produces a
number nobody can defend.

The test for whether an entry is finished: **could a stranger, given only this file,
reproduce your label on a hard case?**

---

## 1. Scope

- **Category:** footwear (Stage B, one category — `CLAUDE.md` §3).
- **Locale:** `en-IN`. Every pair carries the locale tag; the same pair may label
  differently in `en-US` (DR 0006).
- **Tier:** 0. We observe a **query**, not the user's words (DR 0008). So the question an
  annotator answers is always *"does this product match this stated query?"* — never
  *"does this match what the user wanted?"* Nothing about intent, provenance, or the agent
  is labelled.

## 2. The label

Per pair, per attribute: `satisfied` · `violated` · `unstated`.
Where the label is not `satisfied` or `violated`, a reason code (DR 0007):

```
FLOOR_NOT_MET · PRODUCT_SILENT · REQUEST_SILENT · INCOMMENSURABLE
LOW_PROVENANCE · UNRESOLVED_TERM · BRANCH_DISAGREEMENT · FACET_UNASSIGNED
```

**Q1 — Does an annotator apply reason codes, or only the ternary?**
Reason codes make the record defensible but roughly double annotation time and add
disagreement surface. Deciding to label only the ternary in Stage B is legitimate; it must
be decided, not defaulted.
→ *Founder answer:*

## 3. The verification floor

DR 0007: some fields are preconditions. Without them there is nothing to verify.

**Q2 — What is `FLOOR(footwear)`?** Proposed `{form facet, size}`.
Consider: is `size` really a floor field when a *query* rarely states it? If yes, the
majority of real queries return `FLOOR_NOT_MET`, which is either an honest finding or a
useless product — worth knowing before labelling, not after.
→ *Founder answer:*

**Q3 — Worked example.** Request `"white shoes under 9k"`, product: white sneaker, size 9,
₹8,499. Query never mentions size. Is the label `satisfied`, or `FLOOR_NOT_MET`?
→ *Founder answer:*

## 4. Criticality class per attribute

Drives whether silence routes to `confirm`. HARD · BOUND · SOFT · COSMETIC.

**Q4 — Fill in the class for every attribute the gold set will use.**

| Attribute | Class | Notes |
|---|---|---|
| size | | |
| width / fit | | |
| colour | | |
| price | | |
| brand | | |
| material | | |
| gender variant (men's / women's / unisex) | | |
| closure (laces / velcro / slip-on) | | |
| form (sneaker / sandal / boot / formal) | | |

→ *Founder completes the table.*

## 5. The `en-IN` boundary case — the one that will split two annotators

DR 0006: in Indian usage "shoes" is often meant as *footwear generally*.

**Q5 — Request `"shoes"`, product: a sandal. Label?**

- `violated` — strict reading; sandals are not shoes.
- `unstated`/`unknown` — the term is genuinely ambiguous in `en-IN` and we cannot tell.

Whichever is chosen, state it as a **rule**, not a preference, and give the annotator a
test they can apply to the next ambiguous term without asking.
→ *Founder answer:*

**Q6 — Request `"sneakers"`, product: a formal leather shoe.** Same question, other
direction — does `en-IN` "sneakers" broaden to shoes generally?
→ *Founder answer:*

## 6. Colour

**Q7 — Request `"white"`, product colour `"off-white"` / `"ivory"` / `"white & grey"`.**
Where is the boundary, and is it the same boundary for all three?
→ *Founder answer:*

## 7. Price

**Q8 — `"under 9k"` and the product is exactly ₹9,000.** Inclusive or exclusive?

**Q9 — Does "under 9k" mean listed price, price after discount, or price including
delivery?** The product snapshot may carry more than one.
→ *Founder answers:*

## 8. Near-miss construction

§3 Stage B: the gold set is *built around near-misses*, not random pairs. Target roughly:

| Near-miss type | Example | Rough share |
|---|---|---|
| Wrong size | request size 9, product size 8 | |
| Wrong colourway | request white, product white-and-black | |
| Wrong gender variant | request women's, product men's | |
| Category decoy | request "shoes", product **shoe rack** | |
| Pack/pair confusion | request one pair, product two-pack | |
| Clean match (control) | — | |
| Clean violation (control) | — | |

**Q10 — Set the shares.** Too few controls and the set cannot measure false `refuse`; too
many and it is not a near-miss set.
→ *Founder answer:*

## 9. Procedure

- Founder labels all 300–500 pairs.
- Second annotator independently labels a random 10%. **They receive this file and nothing
  else** — no discussion, or kappa measures the conversation rather than the guideline.
- Cohen's kappa computed on that 10%. **Below 0.6 → rewrite this file and relabel** (§10-B).

**Q11 — Who is the second annotator?** Still open in `progress.md`. Kappa needs two
humans and it is the actual Stage B exit criterion.
→ *Founder answer:*

## 10. Provenance of the products

**Q12 — Which catalogue, under what permission?** See `progress.md` open question 3. Every
product must be one we may lawfully use, and every attribute must be verified against the
real listing rather than a search snippet — a wrong attribute here poisons the only asset
that can produce an accuracy number.
→ *Founder answer:*
