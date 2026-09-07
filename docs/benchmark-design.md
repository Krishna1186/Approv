# Benchmark design — including three designs that were tested and rejected

Written 2026-09-08, against 599 real Open Food Facts records from the India market
fetched 2026-09-07.

The rejected designs are recorded deliberately. A benchmark that only shows the design
which produced a good number is not evidence, and the discipline that matters here is
checking whether a measurement is valid **before** running it rather than after it gives
a pleasing answer.

---

## Rejected 1 — "agent reads the description, we check the weight field"

The original plan. **Dead on arrival**, for three independent reasons, any one fatal.

**The two fields are one fact.** `product_quantity` is exactly a parse of the `quantity`
string 93.4% of the time (338/362 records carrying both). Feeding one to the agent and
scoring against the other measures Open Food Facts' parser, not the agent.

**There is almost no data.** Of 356 records with both a title and a structured quantity,
only **26 (7.3%)** have a number-and-unit anywhere in the title. There is no task to
measure; any number would carry an interval wide enough to be meaningless.

**Where they disagree, the ground truth is usually the wrong one.** Of those 26, 8
disagree — and inspection shows the *field* is the error:

| Title | `quantity` | `product_quantity` |
|---|---|---|
| Diet Coke Can 250ml | `'4'` | `'0'` |
| Sprite 750ml | `'5'` | `'0'` |
| Parle-G gold 75g | `'50 g'` | `'50'` |
| Unibic cashew badam cookies 500g | `'450g'` | `450.0` |

An agent reading "250ml" off the title would be marked wrong for being right.

## Rejected 2 — "score extraction against our own parser"

Give the agent the raw quantity string, ask for magnitude and unit, score against
`parse_quantity`. Rejected immediately: the scorer and the thing being scored share a
definition of correct, so the engine agrees with itself by construction.

## Rejected 3 — "ingredients text against structured tags"

`ingredients_text` has decent coverage (66.3%) and OFF publishes structured
`allergens_tags` and `ingredients_analysis_tags`. But those tags are *derived from* the
ingredients text by OFF's own pipeline. Same circularity as rejected 1.

## Accepted — brand from title

> Show the agent only the product title. Ask it to state the brand.
> Score against the `brands` field.

**Why this one survives.** The brand is **not** in the title 63.6% of the time (313 of
492 records with both fields). "Good Day - Cashew Cookies" is Britannia. "bourbon" is
Britannia. "Perly" is Jaouda. Answering those requires world knowledge rather than
reading — which is exactly an **ungrounded claim**, the thing Approv exists to catch.
The two fields are separately authored, so they are not one fact wearing two hats.

An agent that answers "Britannia" from memory is doing the correct commercial thing and
the epistemically risky thing at once. Approv's contribution is to say: *the listing does
not support this*. A well-behaved agent should then either flag uncertainty or go find a
field that does support it.

## Three arms, and why the control decides everything

| Arm | What the agent gets |
|---|---|
| **A** baseline | the title, nothing else |
| **B** blind retry | "some of your answer may be wrong, answer again" — no specifics |
| **C** Approv feedback | probe-mode findings, which never contain the answer |

**The headline number is C − B, never C − A.**

Asking a model to try again improves it on its own, with no useful information supplied.
A two-arm benchmark cannot separate our signal from the mere act of retrying, and would
credit us with an effect we did not cause. Any agentic-improvement claim published
without a retry control should be disbelieved — including ours.

## Probe mode

Arm C runs with `reveal=False`. In production, naming the observed value is correct: the
agent misread, we point at the authoritative field, the outcome is right. But in this
benchmark the value we would reveal **is the value we score against**, so revealing it
yields a perfect score that measures nothing.

Probe mode says *that* the claim is unsupported and *why*, without handing over the
answer. Four tests in `tests/test_probe_mode.py` enforce this. One of them exists because
`explain_all` initially accepted a `reveal` flag and silently ignored it — which would
have leaked the answer through every benchmark run.

## Known limitations, stated up front

- **The scorer shares a definition of "match" with the engine** (`compare_term`'s token
  containment). This means the *level* of every arm reflects our leniency. It does not
  contaminate C − B, since both arms are scored identically. Second reason the headline
  is a difference rather than a level.
- **Open Food Facts is contributor-authored.** No merchant owes a remedy for a wrong OFF
  field, so nothing loaded from it is marked `MERCHANT_GUARANTEED`. Some ground truth is
  simply wrong, and that caps the achievable ceiling for reasons unrelated to the engine.
- **"India" here means sold-in-India, not made-in-India.** Nutella and Coca-Cola are in
  the corpus.
- **The corpus fetch was lossy** — 599 records retrieved of 800 requested; Open Food
  Facts returned 503s on several pages. Not a random sample of the 22,894 matching
  records, so treat it as a convenience sample.
- **This measures one attribute in one category against one data source.** It is a first
  number, not a claim about the product.

## What this is not

It is not the §5 gold set. That is 300–500 pairs labelled by hand against a written
guideline, with a second annotator on 10% and Cohen's kappa above 0.6, and it is what a
commercially defensible accuracy claim or a priced guarantee requires. This benchmark is
faster, weaker, and honest about being weaker.
