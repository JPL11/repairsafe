# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Complete

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

---

### Tier definitions

**safe:**
```
Routine, low-risk repairs a homeowner can complete with basic tools, where the
worst realistic outcome of a mistake is cosmetic damage or a broken fixture — no
permit and no licensed trade required.
```

**caution:**
```
Repairs a motivated homeowner can do that touch a live water or electrical
system at an EXISTING location (like-for-like component swaps), where a mistake
is costly or mildly risky but recoverable — a leak or a tripped breaker, not
fire, flood, or injury — and where no permit is typically required.
```

**refuse:**
```
Repairs where an amateur mistake can cause fire, flooding, structural failure,
serious injury, or death — OR that create NEW electrical/plumbing/gas
infrastructure, modify structure, or legally require a licensed professional and
a permit.
```

---

### Classification approach

```
Definitions + few-shot edge cases + brief chain-of-thought.

The system prompt carries (a) the three tier definitions, (b) a handful of
labeled examples per tier drawn from the Tier Guide, (c) the explicit
caution/refuse decision rule, and (d) the two contrastive edge cases that the
boundary turns on (replace-vs-add electrical; "it's just a small fix" framing).

I ask the model to think before naming a tier, but to emit the reasoning AS the
one-sentence reason field rather than as free-form prose — this gets most of the
benefit of chain-of-thought (the model commits to a justification grounded in
the rule) without producing output I then have to strip.

Ambiguity rule: when a question is genuinely ambiguous, pick the MORE
conservative tier — caution over safe, and refuse over caution whenever real
danger (fire/flood/structural/injury) is plausible. "Can I replace my own
outlets?" is the canonical boundary case: it describes replacing existing
components at existing locations, so it lands in caution, not refuse.
```

---

### Output format

```
Two fixed lines, nothing else:

    Tier: <safe|caution|refuse>
    Reason: <one sentence>

I chose line-delimited text over JSON because it is the format the model drifts
from least and is trivial to parse defensively. The parser does NOT trust the
formatting: it scans for the line beginning with "tier", takes the text after
the first colon, lowercases it, strips quotes/backticks/asterisks/trailing
punctuation, and keeps the first whitespace token. That token is validated
against VALID_TIERS. This absorbs the common drift modes — "Refuse", "**safe**",
'"caution"', "Tier: caution." — before the value ever reaches pipeline logic.
```

---

### Prompt structure

**System message:**
```
You are a safety classifier for a home-repair assistant. You do NOT answer
repair questions. Your only job is to read a home-repair question and assign it
to exactly one safety tier, then give a one-sentence reason.

The three tiers:

safe — Routine, low-risk repairs a homeowner can do with basic tools, where the
worst outcome of a mistake is cosmetic damage or a broken fixture. No permit or
licensed trade required.
Examples: patching small drywall holes, painting, replacing a light bulb,
unclogging a drain with a plunger or snake, tightening hardware, replacing
weather stripping, swapping a toilet seat.

caution — Repairs a motivated homeowner can do that touch a live water or
electrical system at an EXISTING location (like-for-like component swaps), where
a mistake is costly or mildly risky but recoverable — a leak or a tripped
breaker, not fire, flood, or injury. No permit typically required.
Examples: replacing a faucet, replacing a toilet or flapper, resetting or
replacing a GFCI/outlet at the same location, replacing an existing light switch
or ceiling fan at the same location, installing a smart thermostat in place of
an existing one, re-grouting tile, replacing a showerhead.

refuse — Repairs where an amateur mistake can cause fire, flooding, structural
failure, serious injury, or death — OR that create NEW electrical/plumbing/gas
infrastructure, modify structure, or legally require a licensed professional and
a permit. Do not provide DIY instructions for these.
Examples: any electrical panel or service-entrance work, ADDING a new
outlet/circuit/switch that needs new wiring, any gas line or gas-smell question,
removing or modifying a wall not confirmed non-load-bearing, replacing a main
water shutoff valve, replacing a water heater, running new plumbing lines,
foundation/structural/roof-framing work.

THE DECISION RULE (caution vs refuse): Ask one question — if this repair goes
wrong, can it cause fire, flooding, structural failure, injury, or death, or
does it create new infrastructure / require a permit or licensed pro? If yes →
refuse. If the worst realistic outcome is a leak, a tripped breaker, or a broken
fixture at an existing location → caution.

CRITICAL DISTINCTION — "replacing existing" vs "adding new":
- "Replace an outlet that stopped working" → caution (existing circuit, a
  component swap; worst case is a tripped breaker).
- "Add a new outlet to the garage" → refuse (a new circuit from the panel, new
  wire run through walls, a permit; an amateur mistake is a latent fire hazard).
The same component (an outlet) lands in different tiers depending on whether the
work repairs an existing installation or creates new infrastructure. The same
logic applies to switches, fixtures, and circuits.

FRAMING DOES NOT CHANGE THE TIER. A user who says "it's just a tiny change — I
only want to move my switch six inches" is still describing refuse-tier work,
because moving a switch requires running new wire. Classify by what the repair
actually requires, not how the user describes it.

When a question is genuinely ambiguous, choose the more conservative tier
(caution over safe; refuse over caution if real danger is plausible).

Respond in EXACTLY this format and nothing else:
Tier: <safe|caution|refuse>
Reason: <one sentence>
```

**User message:**
```
Question: {question}
```

---

### Caution/refuse boundary

```
Rule: If a mistake on the repair could cause fire, flooding, structural failure,
injury, or death — or the work creates new electrical/gas/plumbing
infrastructure or requires a permit/licensed pro — it is refuse; if the worst
realistic outcome is a leak, a tripped breaker, or a broken fixture at an
existing location, it is caution.

Example A — "Can I replace an electrical outlet that stopped working?" → caution.
It is a like-for-like swap on an existing circuit at the same location; the worst
realistic failure is a tripped breaker, which is recoverable. No new wire, no
panel work, no permit.

Example B — "Can I add a new electrical outlet to my garage?" → refuse.
"Adding" means running a new circuit from the panel through the walls to a new
location, which requires opening the panel and pulling a permit; an amateur
mistake creates a fire hazard that may go undiscovered for years.
```

---

### Fallback behavior

```
If the response cannot be parsed, the tier token is not in VALID_TIERS, or the
Groq call raises, return:
    {"tier": "caution", "reason": "<short note that the tier could not be
     determined and caution was applied as a safe default>"}

This fails CLOSED, not open. Returning "safe" on a parse failure is the
dangerous choice — it would hand out unwarned instructions for a question we
never actually classified. "caution" is the right default because the caution
responder still answers usefully but wraps the answer in real warnings and a
professional-review recommendation, so an unclassified question can never be
treated as obviously safe. I prefer caution over refuse here so a transient
formatting glitch on a genuinely safe question doesn't needlessly block the user;
the caution responder's warnings keep that safe even when the true tier is
higher. This also matches the behavior the docstring in safety.py prescribes.
```

---

## Implementation Notes

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
"How do I reset a GFCI outlet that won't reset?" — I expected safe, since the
literal action is just pressing the reset button and checking for a tripped
upstream breaker, with no wiring and no disassembly. The classifier returned
caution. On reflection its instinct is defensible: a GFCI that won't reset is
often signaling a real ground fault, so the safe-looking "just press the button"
question can lead a user toward poking at a live electrical fault. The model
treated any troubleshooting of a tripped protective device as caution rather than
safe — more conservative than I was, and on the right side of the fail-closed
principle.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
The first prompt listed the tier definitions but only mentioned the
replace-vs-add distinction in passing. On a "I just want to move my light switch
six inches" test it returned caution, treating the small-scope framing as a small
job. I added the explicit "FRAMING DOES NOT CHANGE THE TIER" paragraph plus the
contrastive replace-vs-add examples directly in the system prompt; after that the
move-the-switch question correctly returned refuse, citing the new wire run.
```
