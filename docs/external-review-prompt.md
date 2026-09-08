# External review prompt

Paste everything below the line into a fresh chat. It is written to invite disagreement
rather than encouragement — a reviewer who agrees with all of it has not read it
carefully.

Two things to do first:
1. Attach or paste `approv/algebra/quantity.py`, `approv/algebra/term.py` and
   `approv/types/core.py` if the tool accepts files. The critique is much better with
   the code than without it.
2. Do **not** paste API keys, and do not ask it to write the evaluator.

---

I am building a company called Approv and I want you to try to break it. Be adversarial.
Tell me what is wrong, what is naive, and what a skeptical investor or a payments
engineer would attack first. Do not be encouraging. If you think the whole thing is a bad
idea, say so and say why.

## The problem

AI agents are starting to buy things on people's behalf — via ChatGPT/Perplexity
shopping, via protocols like ACP and Google's AP2, via agentic browsers, and in India via
NPCI's forthcoming Unified Agent Protocol. When a human buys, the PIN or the checkout
click is proof of consent. When an agent buys, that proof disappears.

Nobody in the chain holds both halves of the story. The merchant sees an order but not
the request. The agent operator sees the request but not the return outcome. The payment
rail confirms the payment is authentic without ever inspecting the basket.

## What Approv does

It sits beside any agent that can move money and answers one question about each thing
the agent claims:

> **Did the agent read this product correctly, and from which field?**

Note that this is *not* "does this product match the user's intent." We deliberately
narrowed to grounding, because intent is unverifiable — we never see the user's actual
words, only what the agent composed. Every channel we checked (web search, browser
session control, ACP, AP2, UAP, MCP) delivers at most the agent's paraphrase.

Three separate checks:
- **Consistency** — the agent searched for 5kg and put 1kg in the cart. Provable from the
  agent's own structured tool arguments. No catalogue, no model, no ambiguity.
- **Grounding** — the agent claims "5kg"; is that supported by the listing, and by which
  field?
- **Satisfaction** — does the product meet what was asked for?

## The technical design, and the parts I think are load-bearing

**No model in the decision path.** A model may describe a match; a deterministic engine
authorises. Comparison operators are hand-written pure functions.

**Operators are per data type, not per category.** Six of them — quantity with units,
money, integer count, nominal term, date, bound. Comparing 500g to 1kg is the same code
for flour as for paint. A new category supplies a schema (which attributes exist, what
type, which are critical) plus a criticality table, not new logic. That is how we intend
to cover thousands of categories quickly.

**Incommensurable is not false.** 5kg against a listing that publishes only 500ml returns
`UNSTATED` with reason `INCOMMENSURABLE`, never "mismatch". We are saying we could not
look, not that the product is wrong. Those attribute to different parties.

**Two independent provenance axes, which I think is the most novel bit:**
- *Liability* — who owes a remedy if this text is wrong (a merchant's own description is
  a guarantee; a customer review is not)
- *Certainty* — how sure we are we read it correctly (a weight field is unambiguous;
  marketing prose is not)

A description scores **high liability, low certainty** simultaneously. Liability decides
whether a claim is coverable; certainty caps how confident we may be. The certainty axis
sets a ceiling on confidence, so a value read only from prose can never clear a hard
constraint no matter how confident the extractor sounds. That is our injection defence:
planted text lands in the weakest tier by construction.

A consequence I like: because merchant-authored text is merchant-liable, injecting
instructions into a product description is self-incriminating — whoever plants it inherits
liability. Residual risk concentrates in text nobody is answerable for (reviews, Q&A,
third-party seller copy).

**Findings are actionable, not verdicts.** Coding agents got good because compilers say
which line and what is wrong. Every non-clean finding names the move that resolves it
(`PICK_DIFFERENT_PRODUCT`, `RESTATE_CLAIM`, `FIND_BETTER_SOURCE`, `NOT_RESOLVABLE`), and
reports *every* problem rather than the first, because each round trip costs.

**Wording is rendered from fields, never stored.** The signed record holds codes; the
sentence is generated at the boundary. So messages can be rewritten without invalidating
receipts.

**Records are signed and hash-chained.** Each side signs its own half and they join on a
correlation id — we are not a man-in-the-middle proxy, because that would require two
parties to adopt simultaneously.

## Where I actually am

~80 tests passing. Types, three comparison operators, a check runner, a feedback layer,
an Open Food Facts loader, a coverage report, and a three-arm benchmark harness. No
evaluator yet (I write that by hand, deliberately). No production deployment, no
customers, no revenue.

**A real coverage result, on 599 Indian-market Open Food Facts records:** 43.9% publish
no usable size at all, and 18.2% have a quantity field that is filled in but unparseable
(`'1'`, `'75'`, `'1.73 - 3.00'`, `','`). That number needs no agent and no ground truth,
and it bounds what *any* verification layer could achieve on that data.

**No benchmark number yet.** I designed four benchmarks and killed three before running:
one because the two fields I planned to compare turned out to be 93% derived from each
other, one because the scorer shared a definition of "correct" with the thing being
scored, one for the same circularity in another guise. The fourth ran on six records,
produced +0.0%, and reading the transcript showed the feedback text itself was buggy — so
that number was meaningless too.

## Questions I want attacked

1. **Revenue, and this is my biggest worry.** I assumed I would sell an indemnity to
   agent operators. But they probably do not carry the loss — their terms disclaim it, the
   payment rail authorised a valid transaction, and the actual cost lands on the merchant
   (returns) and the consumer (hassle). So who pays me, and why? My current best answer is
   observability — an agent operator cannot see *why* its agent picked wrong, and error
   monitoring is bought with existing engineering budget and needs no liability story. Is
   that right, or am I talking myself into a smaller company?

2. **Is grounding enough to be a business?** Verifying "the agent read the field
   correctly" is much more tractable than intent, but is it valuable enough that anyone
   pays? Or have I traded away the interesting problem for a solvable one?

3. **Why will the platforms not build this themselves?** My answer is independence — a
   company cannot credibly grade its own agent for its own risk committee, its bank, or a
   regulator, the same reason firms with good internal accountants still buy an external
   audit. Is that a real moat or a comforting story?

4. **Attack the benchmark.** Three arms: baseline, blind retry (control), and Approv
   feedback in "probe mode" that never reveals the value being scored against. I report
   C − B, never C − A, because retrying alone improves a model. What is still wrong with
   this design? What would you not believe?

5. **Attack the provenance model.** Is splitting liability from certainty actually
   meaningful or is it two names for one thing? Where does it break?

6. **The corpus problem.** A defensible accuracy number needs hand-labelled data, which
   needs a merchant partner, which needs a working product, which needs the number. What
   would you do?

7. **What am I not seeing?** Regulatory, competitive, technical — what is the thing that
   kills this that I have not mentioned anywhere above?

Be specific and concrete. Where you think I am wrong, say what you would do instead.
