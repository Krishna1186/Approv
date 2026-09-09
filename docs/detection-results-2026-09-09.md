# First measured signal: 9 September 2026

Approv's findings separate human-exact from non-exact candidates on real Amazon shopping
queries. This is the project's first result whose interval excludes zero. It measures
**detection**, not agent outcomes, and the ground truth is a borrowed relevance label
rather than the §5 gold set, so it is a first number and not an accuracy claim.

## What was measured

60 held-out ESCI queries, each carrying at least one constraint the catalogue can check,
selected on the query's surface form only — never on labels, products or outcomes. One
`gpt-oss-20b` interpretation per query (extractor v4), then deterministic checks over the
top 20 lexically-ranked candidates from a shared 4,009-product catalogue. Labels are
original Amazon E/S/C/I judgements, read only after the findings were computed.

503 judged candidates. 57 of 60 interpretations parsed.

## Result

| Population | flagged, non-exact | flagged, exact | difference |
|---|---:|---:|---:|
| All judged candidates | 20.8% (55/265) | 9.7% (23/238) | **+11.1 pp** |
| Candidates the catalogue could actually check | 30.4% (55/181) | 13.0% (23/177) | **+17.4 pp** |

Cluster bootstrap over the 59 contributing queries, 5,000 resamples:

- All candidates: **+11.1 pp, 95% CI [0.8, 23.2]**; 1.7% of resamples at or below zero.
- Checkable candidates: **+17.4 pp, 95% CI [3.1, 34.0]**.
- Precision of a flag: **70.5%**.

The headline is the conservative row. The lower bound is 0.8 pp, so the effect clears
zero but is not tightly estimated; do not quote a point estimate without its interval.

**The gap is not an artifact of field availability.** A product can only be flagged if it
publishes the attribute, and exact products were *more* checkable than non-exact ones
(74.4% against 68.3%). They had more opportunity to be flagged and were flagged less.

## The false flags are mostly Approv being right

16 of the 23 flags on human-exact products are third-party compatible replacements:

| asked for | brand of record | listing |
|---|---|---|
| brother | myCartridge | myCartridge Compatible Toner Cartridge Replacement for Brother TN730 |
| brother | LEMERO | LEMERO Compatible Toner Cartridge Replacement for Brother TN760 |
| brother | Valuetoner | Valuetoner Compatible Toner Cartridge Replacement for Brother TN |

Approv said the seller of record is not Brother. That is true of every one of these
listings. Amazon's annotators labelled them exact because a compatible cartridge is
*relevant to the search*, which is a different question from whether the shopper got the
brand they asked for — and silently substituting a third-party cartridge mid-purchase is
precisely the failure this product exists to surface.

Excluding those 16 gives 20.8% against 3.2%, a **+17.6 pp** difference, CI [6.3, 30.1].
That is the other reading of "correct", recorded for completeness. It is not the headline:
reclassifying a label after seeing which way it cuts is how a measurement stops being one.

## What this does not establish

Detection is not outcome. Nothing here shows an agent acts on a finding, changes a
selection, or ends a session better off; the three-arm end-to-end comparison is separate.

An E/S/C/I judgement measures relevance to a query. It does not measure whether a shopper
got what they asked for, was satisfied, or would have kept the item. The toner cases show
the two definitions diverging systematically, and diverging hardest on exactly the
substitutions that matter commercially. **A borrowed label cannot serve as this product's
ground truth**, which is the empirical case for the §5 hand-labelled gold set.

Recall is low by construction: the published-text extractor is precision-first, and 32%
of non-exact candidates published nothing the constraint could be checked against.

One model, one extractor version, one locale, one lexical ranker, 60 queries. The
constrained-query population is 25.6% of real US ESCI queries; effects here do not
transfer to the other 74% and must always be quoted with that funnel attached.

## The labelling task this identifies

The 78 flagged pairs are where relevance and constraint-satisfaction disagree, so they are
the highest-information pairs to hand-label against a written guideline asking *did the
shopper get what they asked for?* rather than *is this relevant?* That is a founder task
under §5 and it converts this first signal into a defensible number.
