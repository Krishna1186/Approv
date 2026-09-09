# What the agent gets right without us — 10 September 2026

Three agents, two presentations, 40 identical held-out Shopify cases, one answer key
computed from published merchant fields.

| Agent | Presentation | Correct | 95% CI |
|---|---|---:|---|
| gpt-oss-20b | grouped | 38/40 = 95.0% | 83–99% |
| gpt-oss-20b | flat | 40/40 = 100% | 91–100% |
| qwen3.8-27b | grouped | 39/40 = 97.5% | 87–100% |

Every arm also declined correctly on the unfillable requests. No provider errors.

**On a well-structured merchant catalogue, with the request stating its constraints
explicitly, a cheap agent does not make mistakes.** There is nothing for a verification
layer to catch, and no honest experiment on this data will show one.

## Two hypotheses tested and rejected

**Presentation.** Repeating each product description under every variant, rather than
once per product, was 3.1x more expensive per call and scored *better* (100% against
95%). The tidier layout did not create the ceiling. This had been the working
explanation for the jump from a 38.5% baseline the day before; it was wrong.

**Model family.** Qwen 3.8-27b, a different family, landed at 97.5%. The ceiling is not
one model's quirk.

## What actually made the earlier task hard

The 9 September pack asked for a named product in a given size, over 40 near-identical
rows differing only by a size token. The 10 September pack asks for a named product in a
given colour *and* size. Adding a constraint made the task **easier**, because each
constraint the candidate list displays is another search key rather than another hurdle.

That is worth stating plainly, because the intuition runs the other way: **constraints
only create difficulty when satisfying them requires a fact the candidate list does not
put next to the product.** Colour and size sit in the variant label, so they discriminate
rather than challenge.

## Where the difficulty actually lives

Measured earlier on 132,832 Amazon products: size appears only in the description, never
in the title, for **26.9%** of listings. That is the gap this product was designed for,
and Shopify D2C catalogues do not have it — their variant options are complete and
structured, which is exactly why their agents score 95–100%.

So the two available corpora fail in opposite directions:

| Corpus | Has the grounding gap? | Usable answer key? |
|---|---|---|
| Shopify D2C | no — options are structured and complete | yes, computed from published fields |
| Amazon ESCI | yes — 26.9% of size is prose-only | no — relevance labels answer a different question |

**Neither supports a clean demonstration**, and inventing one that does is how a benchmark
becomes a press release.

## What this means commercially

Agent accuracy on identical work ranged from 38.5% to 100% across models and packs. The
defensible claim is not that agents fail at some rate — it is that a merchant accepting
agentic traffic **cannot know which agent is calling**, and the spread is that wide.
Verification is insurance against variance, not against a fixed error rate.

It also follows that measured "value" depends entirely on which agent is tested. Every
earlier baseline in this project was one point on a wide distribution reported as though
it were the distribution. That was the methodological error under all of them.

## What would settle it

A corpus with the grounding gap *and* an answer key independent of the checker. The only
honest route is hand-labelled: real listings where the constraint is stated only in prose,
labelled against a written guideline by a person. That is the §5 gold set, and this run is
the clearest argument yet for why it cannot be substituted.
