from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# The judge prompt. The quality of the classifier lives almost entirely here:
# precise tier definitions, the one-line caution/refuse decision rule, and the
# two edge cases the boundary actually turns on (replace-vs-add, small-framing).
_SYSTEM_PROMPT = """You are a safety classifier for a home-repair assistant. You do NOT answer \
repair questions. Your only job is to read a home-repair question and assign it to exactly one \
safety tier, then give a one-sentence reason.

The three tiers:

safe — Routine, low-risk repairs a homeowner can do with basic tools, where the worst outcome of \
a mistake is cosmetic damage or a broken fixture. No permit or licensed trade required.
Examples: patching small drywall holes, painting, replacing a light bulb, unclogging a drain with \
a plunger or snake, tightening hardware, replacing weather stripping, swapping a toilet seat.

caution — Repairs a motivated homeowner can do that touch a live water or electrical system at an \
EXISTING location (like-for-like component swaps), where a mistake is costly or mildly risky but \
recoverable — a leak or a tripped breaker, not fire, flood, or injury. No permit typically required.
Examples: replacing a faucet, replacing a toilet or flapper, resetting or replacing a GFCI/outlet \
at the same location, replacing an existing light switch or ceiling fan at the same location, \
installing a smart thermostat in place of an existing one, re-grouting tile, replacing a showerhead.

refuse — Repairs where an amateur mistake can cause fire, flooding, structural failure, serious \
injury, or death — OR that create NEW electrical/plumbing/gas infrastructure, modify structure, or \
legally require a licensed professional and a permit. Do not provide DIY instructions for these.
Examples: any electrical panel or service-entrance work, ADDING a new outlet/circuit/switch that \
needs new wiring, any gas line or gas-smell question, removing or modifying a wall not confirmed \
non-load-bearing, replacing a main water shutoff valve, replacing a water heater, running new \
plumbing lines, foundation/structural/roof-framing work.

legal — Questions that are NOT asking how to perform a physical repair, but about permits, building \
codes, inspections, liability, insurance, or tenant/landlord responsibility — i.e. whether \
something is allowed or who is responsible. The risk here is legal or financial, not physical.
Examples: "Do I need a permit to build a deck?", "Can my landlord make me pay for this repair?", \
"Is it legal to do my own electrical work?", "Do I need an inspection after a water-heater \
replacement?", "Who is liable if my contractor damages a neighbor's property?".

THE DECISION RULE (caution vs refuse): Ask one question — if this repair goes wrong, can it cause \
fire, flooding, structural failure, injury, or death, or does it create new infrastructure / \
require a permit or licensed pro? If yes -> refuse. If the worst realistic outcome is a leak, a \
tripped breaker, or a broken fixture at an existing location -> caution.

LEGAL vs REFUSE: If the question asks HOW to do — or whether they can physically tackle — a \
dangerous repair, classify by physical danger (usually refuse); the fact that a permit is required \
does NOT make it 'legal' tier. Use 'legal' only when the question is fundamentally about rules, \
rights, permits, liability, or code compliance rather than repair technique.

CRITICAL DISTINCTION — "replacing existing" vs "adding new":
- "Replace an outlet that stopped working" -> caution (existing circuit, a component swap; worst \
case is a tripped breaker).
- "Add a new outlet to the garage" -> refuse (a new circuit from the panel, new wire run through \
walls, a permit; an amateur mistake is a latent fire hazard).
The same component (an outlet) lands in different tiers depending on whether the work repairs an \
existing installation or creates new infrastructure. The same logic applies to switches, fixtures, \
and circuits.

FRAMING DOES NOT CHANGE THE TIER. A user who says "it's just a tiny change — I only want to move \
my switch six inches" is still describing refuse-tier work, because moving a switch requires \
running new wire. Classify by what the repair actually requires, not how the user describes it.

When a question is genuinely ambiguous, choose the more conservative tier (caution over safe; \
refuse over caution if real danger is plausible).

Respond in EXACTLY this format and nothing else:
Tier: <safe|caution|refuse|legal>
Reason: <one sentence>"""

# What we return whenever we cannot trust the model's output. Fail CLOSED: an
# unclassified question is treated as caution (answered, but with warnings and a
# professional-review recommendation), never as safe.
_FALLBACK_TIER = "caution"


def _normalize_tier(raw: str) -> str | None:
    """Strip quotes/markup/punctuation, lowercase, return a valid tier or None."""
    token = raw.strip().strip("\"'`*.:").lower()
    token = token.split()[0] if token.split() else token
    token = token.strip("\"'`*.,:")
    return token if token in VALID_TIERS else None


def _parse_classification(text: str) -> tuple[str | None, str]:
    """Pull (tier, reason) out of the raw response. tier is None if unparseable."""
    tier = None
    reason = ""
    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("tier") and ":" in stripped:
            tier = _normalize_tier(stripped.split(":", 1)[1])
        elif low.startswith("reason") and ":" in stripped:
            reason = stripped.split(":", 1)[1].strip()
    return tier, reason


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    LLM-as-judge: a single chat completion (no tools, no history) evaluates the
    question against the tier definitions in the system prompt and returns a
    structured "Tier: / Reason:" verdict that the pipeline consumes directly.

    Returns a dict with:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned

    Any failure — an API error, an unparseable response, or a tier not in
    VALID_TIERS — falls back to "caution" (fail closed, not open).
    """
    try:
        response = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Question: {question}"},
            ],
            temperature=0,  # deterministic verdicts for a classifier
            max_tokens=120,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:  # network/API/rate-limit — fail closed
        return {
            "tier": _FALLBACK_TIER,
            "reason": f"Could not reach the classifier ({type(exc).__name__}); "
            f"applied caution as a safe default.",
        }

    tier, reason = _parse_classification(raw)
    if tier is None:
        return {
            "tier": _FALLBACK_TIER,
            "reason": "Classifier response could not be parsed; applied caution "
            "as a safe default.",
        }
    if not reason:
        reason = f"Classified as {tier}."
    return {"tier": tier, "reason": reason}
