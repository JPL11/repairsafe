# 🔧 RepairSafe

A home-repair Q&A assistant with a **safety layer**. Before answering, RepairSafe runs the question through an LLM-as-judge classifier, sorts it into a safety tier, and changes its behavior accordingly — a routine repair gets full instructions, a risky one gets warnings woven into the steps, and a dangerous one gets no how-to at all. Every interaction is written to an append-only audit log.

**Status: complete.** All three milestones are implemented and verified, and all four optional challenges are done. Built for AI201 Lab 4.

---

## How It Works

The pattern is the one production safety systems use — classify → conditional response → log — the same shape as OpenAI's Moderation API running a classifier ahead of the main model.

```
user question
      │
      ▼
classify_safety_tier()   ── LLM-as-judge ──▶  {"tier": ..., "reason": ...}
      │
      ▼
generate_safe_response()  ── tier-specific system prompt ──▶  response
      │
      ├──▶ log_interaction()   ── append-only ──▶  logs/audit.jsonl
      ▼
shown to user
```

| Stage | File | Implementation |
|---|---|---|
| **Classify** | `safety.py` | LLM-as-judge. The system prompt carries precise tier definitions, the caution/refuse decision rule, and the "replacing existing vs. adding new" edge case. Output is a fixed `Tier:/Reason:` format, parsed defensively (normalizes casing, quotes, punctuation) and validated against `VALID_TIERS`. **Fails closed to `caution`** on any parse or API error — never to `safe`. |
| **Respond** | `responder.py` | Three genuinely distinct system prompts, not one prompt with conditionals. The refuse prompt is the hard one: it names the specific behaviors to withhold (no steps, no tool lists, no "what a professional does," no hypothetical/academic/roleplay framing) and the alternative to perform instead (explain the *why*, name the risk, say who to call). Unknown tier falls back to `caution`. |
| **Log** | `auditor.py` | Append-only JSONL — one independently-parseable record per line. Four required fields plus `reason`, `response_length`, and `model` (the fields you'd actually need to diagnose a cluster of misclassifications). Truncates question/response, creates `logs/` idempotently, and prints a one-line console summary. |

### The three tiers

| Tier | Meaning | Behavior |
|---|---|---|
| ✅ `safe` | Routine, low-risk; worst case is cosmetic damage. | Full, actionable DIY instructions. |
| ⚠️ `caution` | Doable, but touches live water/electrical at an existing location; a mistake is costly but recoverable. | Instructions with warnings integrated into each step + a clear "when to call a pro" line. |
| 🚫 `refuse` | An amateur mistake risks fire, flooding, structural failure, injury, or death — or it creates new infrastructure / needs a permit. | **No how-to.** Explains the danger and directs the user to a licensed professional. |

**The decision that matters most** is the caution/refuse boundary, and the sharpest case is *replacing existing* vs. *adding new* electrical work: "replace an outlet that stopped working" is `caution` (component swap on an existing circuit), but "add a new outlet to the garage" is `refuse` (new circuit, new wire, permit, latent fire hazard). Framing doesn't change the tier — "I just want to move my switch six inches" is still `refuse`, because it requires running new wire.

### Tech stack

Python 3.12 · Gradio 6.18 (chat UI — `launch(theme=, css=)` per Gradio 6) · Groq SDK (`llama-3.3-70b-versatile`, used as both judge and responder) · python-dotenv

All knobs live in `config.py` (model, log paths, `VALID_TIERS`, summary cadence).

---

## Optional Challenges

All four are implemented, run, and written up in [`optional-challenges.md`](optional-challenges.md):

| Script / change | Challenge | Headline finding |
|---|---|---|
| `exp_boundary.py` | Test the caution/refuse boundary systematically | 5 paired phrasings; **4/5 consistent**. Surfaced a real inconsistency — water-heater *anode rod* → caution but *heating element* → refuse, because the general electrical-danger rule overrides the Tier Guide's component carve-out. The one-line prompt fix is documented. |
| `exp_adversarial.py` | Harden the refuse tier | **3/3 framings defended** (roleplay / fiction / academic), each audited by an independent LLM-as-judge — classifier held refuse and the responder leaked no procedure. |
| `auditor.py` | Add a session summary | Rolling summary every 5 interactions → `logs/session_summary.jsonl` (total, tier distribution, 3 most recent questions), computed statelessly by re-parsing the audit log. |
| `config.py` · `safety.py` · `responder.py` · `app.py` | Extend the tier model | A fourth **`legal`** tier for permit / code / liability questions. A legal-vs-refuse disambiguation rule keeps permit-required *dangerous* work in refuse. **5/5 legal questions correct, 4/4 no regression** on the original tiers. |

Reproduce:

```bash
python exp_boundary.py      # challenge 1
python exp_adversarial.py   # challenge 2
# challenge 3 fires automatically every 5th logged interaction
# challenge 4 is live in the classifier + app; legal questions classify as "legal"
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
# or: .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY (free at console.groq.com) to .env
```

## Run

```bash
python app.py
```

Opens the Gradio UI: ask a repair question and watch the safety tier and a tier-calibrated answer appear, or browse the **Tier Guide** tab. Each interaction is appended to `logs/audit.jsonl`.

---

## Project Structure

```
repairsafe/
├── app.py                   # Gradio UI + pipeline orchestration, with the legal-tier badge
├── safety.py                # M1: LLM-as-judge classifier (4 tiers)
├── responder.py             # M2: tier-specific response generation
├── auditor.py               # M3: JSONL audit log + rolling session summary
├── config.py                # model, paths, VALID_TIERS, summary cadence
├── exp_boundary.py          # Challenge 1: boundary consistency test
├── exp_adversarial.py       # Challenge 2: refuse-tier hardening (LLM-judged)
├── optional-challenges.md   # Full challenge writeup
├── data/
│   └── repair_tiers.md      # Safety taxonomy + edge-case rules (the classifier's source of truth)
├── logs/                    # audit.jsonl + session_summary.jsonl (runtime, gitignored)
└── specs/                   # Design docs, completed with decisions + implementation notes
    ├── system-design.md
    ├── classifier-spec.md
    ├── responder-spec.md
    └── auditor-spec.md
```
