import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"
LOG_FILE = "logs/audit.jsonl"
SUMMARY_FILE = "logs/session_summary.jsonl"  # optional challenge 3: rolling session summaries
SUMMARY_EVERY = 5                            # write a summary after every N interactions
VALID_TIERS = {"safe", "caution", "refuse", "legal"}  # 'legal' added in optional challenge 4
