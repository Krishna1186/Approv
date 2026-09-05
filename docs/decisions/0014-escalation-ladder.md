# DR 0014 — Who receives a `confirm`? The escalation ladder

- **Status:** OPEN — founder decides, including the kill threshold
- **Raised:** 2026-09-05, by the founder
- **Touches:** §2.3, §2.5, §5, DR 0004, DR 0010, DR 0012, DR 0013
- **Blocks:** nothing in Stage B; it is the criterion Stage C is judged against

---

## The founder's objection

> The entire product is that we auto-verify if the agent is right. If the agent had to
> consult the user every time, there would be no point. Now every time we're ambiguous we
> send to confirm by the user manually — doesn't it kind of ruin the purpose?

This is the strongest challenge raised against the design so far, and it is correct as
stated. A verification layer whose answer to uncertainty is *"ask the human"* has
reintroduced the human-in-the-loop that agentic purchasing exists to remove. §5 already
concedes the failure mode — *"if `confirm` fires on 60% of traffic we have a nuisance, not
a product"* — but the design has been treating `confirm` as a single destination, and that
is the actual error.

---

## The error: `confirm` was conflated with "interrupt the user"

`confirm` is a *decision state*, not a *recipient*. Three parties can receive it, and they
cost wildly different amounts:

| Recipient | Cost | When |
|---|---|---|
| **The preference record** | ~zero | the answer is already known from prior confirmed purchases (§2.8) |
| **The agent** | milliseconds, one round trip | the agent can re-pick or supply the missing attribute |
| **The human** | seconds, and a possible lost sale | nobody else can resolve it |

In an agent-mediated flow, `confirm` mostly does **not** mean "ask the human." It means
**"agent: this is not good enough — pick again, or tell me the missing attribute."** That
is precisely the repair signal DR 0010 describes as the capability upgrade, and it never
touches the user.

This is the compiler analogy again. A type error does not page the customer; it goes back
to the thing that produced the code. Only an unrecoverable failure reaches a person.

## The ladder

An `unknown` descends only as far as it must:

```
1. RESOLVE          deterministically, in algebra/          — free
                    all candidate branches agree? done (DR 0004)
2. PREFERENCE       known from this shopper's history        — free
                    SOFT only; HARD pre-fills, never authorises (DR 0004)
3. AGENT            return the reason code, agent re-picks   — milliseconds
                    or supplies the missing attribute
4. HUMAN            targeted question, one per search        — seconds
                    only when 1-3 cannot resolve it
```

**Every DR written so far is an attempt to widen rung 1.** Typed constraint algebra, DAG
subsumption, dimensional quantities, the lexicon's candidate branches, faceted
classification — none of that exists for elegance. It exists so that cases a naive checker
must escalate get *resolved deterministically instead*. A naive checker confirms constantly
because it cannot tell a shoe rack from a shoe. The engine's sophistication **is** the
confirm-rate reduction.

## The three call sites already have different escalation targets

§2.5's split resolves most of the objection on its own:

| Call site | `confirm` means | Does a human see it? |
|---|---|---|
| **mark** | no badge on that result | **No.** The shopper browses normally and never knows |
| **verify** | agent re-picks | **No.** Rung 3 |
| **gate** | ask before the debit | **Yes** — and only here, for money about to move irreversibly |

So "everything ambiguous goes to confirm" was never "everything ambiguous interrupts the
user." Only the gate reaches a person, and the gate is the one place an interruption is
obviously worth it.

## Why the alternative is worse

On an ambiguous case there are exactly three options:

- **allow** — a wrong purchase, and under DR 0010/0012 we pay for it.
- **refuse** — a lost sale, unrecoverable, and the shopper is not told why.
- **confirm** — recoverable, and per §2.2 it transfers the outcome to whoever answered.

`confirm` is the only branch that is recoverable, and per DR 0012 it is what keeps the loss
ratio finite. The objection is not that `confirm` exists — it is that it must be **rare**,
and that rarity is an engineering result, not a design assumption.

## The honest part: a kill threshold, set before measurement

The founder's worry cannot be argued away, only measured. So the threshold is written down
**now**, before Stage C produces a number, precisely so it cannot be rationalised
afterwards.

**Proposed, for the founder to set:**

| Metric | Kill threshold |
|---|---|
| Human-facing confirm rate at `gate` | > ____% → the product is a nuisance |
| Agent-facing confirm rate at `verify` | > ____% → the engine is punting, not resolving |
| No-badge rate at `mark` | > ____% → the badge is not worth rendering |

Note these are three separate numbers, per §4.7's rule that call sites are never averaged.
A high `mark` no-badge rate is survivable; a high `gate` human-confirm rate is not.

**If the human-facing rate at `gate` exceeds the threshold, the honest conclusion is that
the category is not verifiable at the fidelity we receive** — not that the threshold was
too strict. Writing it down first is what makes that conclusion available.

## Options

**Option 1 — `confirm` is a single state; the surface decides who to ask.**
- *For:* nothing to build; already the implicit design.
- *Against:* the founder's objection stands, because the default reading is "ask the user"
  and that is what will get implemented.

**Option 2 — `confirm` carries an escalation target; the ladder is explicit in the record
and the human rung is the last one.**
- *For:* makes the cheap rungs the default; the record shows *who* was asked, which matters
  for §2.2 fault attribution; the three call sites get distinct thresholds.
- *Against:* the record grows a field; the agent rung requires the operator to implement a
  re-pick loop, which is an integration cost on their side.

**Option 3 — Option 2, plus refusing rather than confirming when the agent cannot resolve.**
- *For:* zero human friction.
- *Against:* converts every unresolved case into a lost sale, and silently. Worse for the
  merchant than a question, and it removes the labelled negatives DR 0012 depends on.

## Recommendation

**Option 2.** It answers the objection structurally rather than by hoping the confirm rate
comes out low, and it makes the ladder visible in the record so a high human-escalation
rate is diagnosable — you can see *which rung* failed, rather than only that a human was
asked.

## Decision

*(founder — fill in, set the three kill thresholds, then close)*
