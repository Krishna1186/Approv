# learnings.md

`CLAUDE.md` §7 step 8: three lines per session — what I did not understand at the start,
what I understand now, what I still cannot explain.

**How this file is maintained.** Claude writes the *factual* part of each entry: what was
decided, and where the founder corrected Claude (those are observable events). The three
reflection lines are the founder's, in the founder's words. Claude leaving them blank is
not an oversight — a record of the founder's understanding written by Claude would be the
exact failure `CLAUDE.md` §0 exists to prevent, and it is the artifact the December test
reads.

---

## Session 1 — 2026-09-02

**What happened.** `CLAUDE.md` committed. Stage A had no audit subject; the repo was empty.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 2 — 2026-09-03

**What happened.** Prior repo (`payment-agent-harness`) ruled non-ancestral. §8 amended so
Claude may write a body only against a founder-written signature and test. Category fixed:
footwear/apparel. DR 0001 and 0002 opened.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 3 — 2026-09-03/04

**Founder correction #1 — taxonomies are DAGs, not trees.**
Claude asserted a category taxonomy is a tree, and that cycle-safety followed from being a
tree. The founder's counter: a bulb sits under Lighting, Electronics, Decor and Interiors
simultaneously — four parents, therefore not a tree. Both of Claude's claims were wrong.
Claude was reasoning from a textbook taxonomy; the founder was reasoning from a real
catalogue. → DR 0003.

**Founder correction #2 — fail-open on timeout, because the marketplace will not wait.**
Correct, and the constraint most verification layers discover only after a merchant
removes them. Claude added the asymmetry the founder had not separated: fail-open is right
for `mark` and a complete bypass at `gate`, where latency becomes an off-switch. → DR 0004.

**Founder correction #3 — agents fabricate constraints the user never stated.**
Independently derived the mirror of product-side provenance. Without it §2.2 cannot
attribute fault to the agent, because a fabrication and an instruction are byte-identical
in the record. → DR 0005.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 4 — 2026-09-04

**Founder correction #4 — the verification floor.**
Some fields are preconditions, not optional attributes. Footwear cannot be verified
without a size; a request lacking one was never verifiable rather than uncertain, and that
is a different heading from the merchant failing to publish data. Claude had collapsed
both into one reason code. → DR 0007.

**Founder correction #5 — nobody will hand us provenance.**
Claude's DR 0005 assumed a cooperating agent volunteering `PRIOR_CONVERSATION` tags. The
founder: no agent does this, we will not have the prior conversation to validate, and we
may never see the user's actual words at all — only the query the agent composed. This
invalidated the design as written. → DR 0008.

**Founder correction #6 — facet ordering, and the cycle point.**
Asking whether form or use-case sits higher in the hierarchy revealed a modelling error
rather than needing an answer: they are orthogonal facets and forcing them into one
hierarchy manufactures the diamonds. Separately, the founder corrected Claude that a
visited set gives **termination, not cycle detection** — seeing a node twice is a diamond,
not a cycle. → DR 0003 addendum, DR 0011.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 5 — 2026-09-04/05

**Founder correction #7 — ACP carts kill the merchant-side product.**
Under cart-submission protocols the agent submits a decided basket with no query text at
all. Not a weaker comparison — no comparison. And the merchant does not care whether the
cart matches intent, because their liability ends at "I shipped what was ordered." Claude
had been selling a hedge to the only party in the chain that is not exposed. → DR 0010.

**Founder correction #8 — three objections to the latency amendment.**
(a) A vague query is vague against every product, so "no badge when uncertain" empties the
whole results page. (b) "Ask once per person" breaks on gifts. (c) Precomputing verdicts
over top-N queries is building a search index, and the tail is the entire product. All
three were correct; the fixes are one clarification per *search* rather than per product,
a preference record that pre-fills but never authorises, and caching the *product* side
(query-independent) rather than the pair. → DR 0004, second amendment.

**Design freeze.** 2,162 lines of design, zero code, zero labelled pairs. Guarantee
structure fixed as a capped B2B indemnity to the agent operator, quoted only after Stage C.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 6 — 2026-09-05

**Founder correction #9 — "doesn't `confirm` ruin the whole point?"**
The strongest objection raised so far. If the answer to every ambiguity is *ask the human*,
the design has reintroduced the human-in-the-loop that agentic purchasing exists to remove.
Correct as stated, and it exposed a real error: Claude had been treating `confirm` as a
single destination. It is a *decision state*, not a *recipient* — it can be answered by the
preference record, by the agent re-picking, or by a human, in ascending order of cost, and
only the `gate` call site ever reaches a person. → DR 0014, which also fixes the three kill
thresholds *before* measurement so a bad confirm rate cannot be rationalised afterwards.

**Founder correction #10 — the corpus deadlock.**
"I need a verified dataset, but I can't get vendor data till I pilot, and I need an MVP to
pilot." Real, but only under two assumptions Claude had left unexamined: that the catalogue
must come from a large marketplace, and that the first thing shipped must be the gate.
→ DR 0015.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

---

## Session 7 — 2026-09-06

**Founder correction #11 — the field ladder has two axes, not one.**
Claude ranked product fields by *extraction certainty*: structured field > title >
free-text description. The founder's counter: the description is the merchant's own
published guarantee, so a wrong description obliges them to take the return, which makes
description-sourced claims **more** valuable than title-sourced ones, not less. Both are
right about different things. The ladder splits into **liability** (who owes a remedy if
this text is wrong) and **extraction certainty** (how sure we are we read it correctly).
Liability decides whether a claim is coverable; certainty decides whether it is confident.
A variant field is high on both; a description is high liability / low certainty; a review
is low on both.

Consequence Claude had not seen: because merchant-authored text is merchant-liable,
**injection into a description is self-incriminating** — whoever plants it inherits the
liability. The residual injection risk therefore concentrates in text nobody is liable
for: reviews, Q&A, third-party seller content. That is a structural defence, and it is
stronger than the technical one Claude had proposed.

**Founder proposal — graded output instead of a hard ternary.**
Founder asked for every comparison to return a distribution over the outcomes
(e.g. 0.30 satisfied / 0.65 unsure / 0.05 refuse). The instinct is accepted; the shape was
corrected. A distribution over `unsure` is a category error — uncertainty is a state of
our knowledge, not a state of the world, so nothing can be 65% likely to be unsure.
The correct shape is **one number over the fact** (P(the product really is 5kg)) with the
allow/confirm/refuse verdict derived from founder-set thresholds plus attribute
criticality. Score inside, verdict outside. This keeps §4.3 intact. Also flagged: a
calibrated probability cannot exist at 300-500 pairs, so v1 ships the number as a
**ranking**, not a probability. Pending DR 0016.

**Founder correction #12 — seller advice must not be able to upgrade a claim.**
Founder proposed an `others` bucket (seller recommendations, reviews) usable for decisions
when the source is the seller. Accepted for evidence, corrected on direction: "runs small,
order a size up" is *advice*, not an attribute claim. It does not change the fact that the
item is a size 9. Advice may only **lower** confidence or force a `confirm`; if it can
raise a verdict, planting one line of copy moves the decision, which reopens the injection
channel the ladder just closed. Monotone rule (DR 0009) applied to advice.

**Reframe accepted — the check is now grounding, not intent matching.**
The question changes from "does this product match the user's intent" to "did the agent
read this page correctly, and from which field." Ground truth moves onto the page, which
makes labelling objective and unblocks Stage B. Demotes DR 0003/0006/0011 (taxonomy,
ontology, lexicons) out of v1 and promotes the provenance ladder to the main event.

**External input — call with a former Zepto senior (payments side).**
Not evidence: he left before any agentic work started, so this is an informed prior, not
an observation. Load-bearing points: quick-commerce platforms are already exposing public
MCP, which he expects to be their main agentic channel; liability for a bad pick sits with
the agent, but the *cost* (returns, trust) lands on the platform; and payments teams will
not change a flow but **will happily outsource a liability**. That last one reframes the
pitch from "buy our accuracy" to "take this off your books." Pilots: newer or smaller
marketplaces. Feedback: payments PMs at large platforms. Consistent with DR 0010 and
DR 0015 Route B, reached independently.

- Didn't understand at the start:
- Understand now:
- Still cannot explain:

