# DR 0020: Merchant defence, and the record as a dispute artifact

Date: 2026-09-11. Supersedes the agent-side-necessary conclusion recorded in
`direction-2026-09-11.md` earlier the same day, and reopens what DR 0010 closed.

## What changed

The 11 September direction argued that only agent-side integration can see the human's
raw request, so distribution is a business-development problem with no technical route
around it. That reasoning is sound and its conclusion was still wrong, because it
answered a question the product does not have to ask.

**Proving the agent erred requires the human's request. Proving the merchant did not err
does not.** The first needs access we will never have. The second needs the agent's own
stated request and the merchant's own fulfilment record — both already on the merchant's
side of the wire. Inverting the burden of proof removes the access problem entirely.

## Who bears the loss, and why that is the buyer

A chargeback is a consumer-protection instrument. When the consumer wins, the merchant
loses the goods, the revenue, the return logistics and a per-dispute fee. Beyond the
per-order loss, card networks run dispute-ratio monitoring programmes; crossing a
threshold brings fines and ultimately loss of card acceptance. So a burst of simultaneous
agentic disputes is not a cost line, it is an existential event. Exact thresholds vary by
network and revision and are not quoted here.

This makes the merchant the party with the loss, and therefore the party that pays. It
also makes mass concurrent agentic disputes — not single wrong orders — the risk being
insured against.

## What the record is for

The `ComparisonRecord` is the **dispute artifact**. Not a badge, not a quality signal,
not feedback to the agent. Its purpose is to answer one question at the moment a refund
is demanded: *did the merchant deliver what was asked for?*

Its primary forum is the merchant's own returns desk, not a card network's dispute
process. Most wrong-item losses never become chargebacks; they become returns, where the
merchant is judge and payer and no external body has to accept our evidence format. This
is why the artifact needs no rail to exist.

**The record's strength is proportional to the specificity of the stated request.** A
vague declaration satisfies almost anything, so the completeness vector swells and the
record proves little. That is correct behaviour under §2.2 and it bounds coverage.

## The guarantee

If the merchant is compelled to refund despite a clean record, Approv absorbs a defined
portion of the loss, under caps.

| Cap | Purpose |
|---|---|
| Per order | bounds a single loss |
| Per occurrence, one root cause across any number of orders | the correlated-risk cap that matters |
| Monthly aggregate | bounds the pool regardless of cause |

The claim class stays narrow: the record verified an attribute, and the merchant's own
fulfilment record shows that attribute shipped as verified. Consumer assertion alone is
not a trigger. Coverage attaches per channel, decided once by the merchant, never as a
per-order election — no human is present at an agentic checkout to elect anything.

A consumer-paid fee is rejected. Nobody is at the checkout to consent to it; an
unexpected line item can breach the budget the agent was given and abort the cart; and a
mandatory undisclosed fee for merchant protection is squarely inside junk-fee and
dark-pattern enforcement. The merchant is the beneficiary and pays.

## Where the stated request comes from

In descending order of fidelity, and all of them merchant-side:

1. **Protocol channels** (ACP, AP2, storefront MCP, product feeds) — arrives structured.
2. **On-site search and filter parameters** — first-party analytics the merchant owns.
3. **A declared-intent field addressed to the agent**, on the agentic checkout or in the
   MCP/ACP response: *state the requirements you were given*. Agents comply with page
   instructions. The declaration does not need to be true — it binds the agent's side,
   which is all a merchant-defence record requires.

No declaration, no coverage. That gradient is the merchant's channel policy and it needs
no agent operator's consent.

**Uncovered:** an agent that discovers the product off-site, arrives directly at a
product page, declares nothing and never uses site search. Search terms are stripped from
referrers, so nothing is recoverable. The size of this slice is unmeasured and bounds the
product.

## What this does not change

The engine. Both framings consume a stated request and a product and emit findings, a
decision and a signed record. The agent-side integration of `direction-2026-09-11.md` §2
remains a strictly easier input case — raw text instead of a paraphrase — and is kept as a
product for the world where agent operators are made liable. It is no longer the
precondition for having a business.

`Channel` already distinguishes `AGENT_MESSAGE` from `TOOL_ARGUMENT`, so a record can say
which fidelity it was built from. Degrade explicitly, never silently.

## Status

Open. The two numbers that decide whether this works are unmeasured: the share of
agent-originated orders carrying a recoverable stated request, and the share of clean-record
refunds that are provable from merchant fulfilment records.
