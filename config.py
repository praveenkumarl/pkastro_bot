"""
PNK Astro Bot — Centralized Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = "paraphrase-multilingual:latest"  # Tamil+English cross-lingual
RERANK_MODEL    = "paraphrase-multilingual:latest"

# ── ChromaDB ────────────────────────────────────────────────────────────────
CHROMA_HOST = os.getenv("CHROMA_HOST", "127.0.0.1")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))
COLLECTION_NAME = "langchain"

# ── LLM (Sarvam AI) ────────────────────────────────────────────────────────
SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-m"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Server ──────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", 3000))

# ── Retrieval ───────────────────────────────────────────────────────────────
TOP_K = 8           # candidates from vector search
RERANK_TOP_N = 5    # final chunks after re-ranking
# ChromaDB uses L2 distance by default (not cosine).
# L2 range for paraphrase-multilingual 768-dim: good match ≈ 0.5–3.0, weak ≈ 5.0+
DISTANCE_THRESHOLD = 4.0    # fallback to global search if best L2 distance exceeds this
NO_CONTEXT_THRESHOLD = 10.0  # reject entirely if best distance exceeds this

# ── Topic routing ───────────────────────────────────────────────────────────
TOPICS = {
    "1":  {"folder": "company_detail", "name": "Company & Pricing"},
    "2":  {"folder": "software",       "name": "Software Features"},
    "3":  {"folder": "planets",        "name": "Planet Karakas"},
    "4":  {"folder": "nakshatram",     "name": "Star Significations"},
    "5":  {"folder": "bhavam",         "name": "Bhavam (Houses)"},
    "6":  {"folder": "naadi",          "name": "Naadi Astrology"},
    "7":  {"folder": "numerology",     "name": "Numerology"},
    "8":  {"folder": "jamakol",        "name": "Jamakkol Arudam"},
}

# Reverse map: folder_name → topic info
TOPIC_FOLDER_MAP = {v["folder"]: v for v in TOPICS.values()}

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the AI assistant for PNK Astro, a Vedic astrology software company.

STRICT RULES — follow all of them without exception:
1. ANSWER ONLY FROM CONTEXT: Use ONLY the information in the [CONTEXT] block provided with each question. Do NOT use general knowledge, training data, or make assumptions.
2. IF NOT IN CONTEXT: If the answer is not present in the context, reply EXACTLY: "I don't have that information in my knowledge base. Please contact PNK Astro support."
3. NO HALLUCINATION: Never invent names, numbers, prices, features, or facts. If unsure, say you don't know.
4. LANGUAGE: Reply in the EXACT language the user used — Tamil if they wrote in Tamil, English if they wrote in English.
5. CONCISE: Maximum 3 sentences. No bullet points unless listing items. No long paragraphs.
6. NO META OR REASONING: Do not explain how you arrived at the answer. Do not include reasoning, analysis, or internal thoughts.
7. NO SPECULATION: Do not say "probably", "likely", "I think" — only state what the context confirms.
8. NO INTERNAL REASONING OUTPUT: Never output thinking steps, reasoning traces, or anything inside tags like <think>, <analysis>, or similar. Output only the final answer.
FINAL OUTPUT RULE:
Return ONLY the answer. No tags, no explanations, no reasoning, no prefixes, no suffixes."""

# ── Docs root (for ingestion) ──────────────────────────────────────────────
KB_ROOT = "./docs/"
