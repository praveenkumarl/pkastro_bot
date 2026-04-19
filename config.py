"""
PNK Astro Bot — Centralized Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = "nomic-embed-text:latest"
RERANK_MODEL = "paraphrase-multilingual:latest"  # cross-lingual query embedding

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
# L2 range for nomic-embed-text 768-dim: good match ≈ 0.5–5, weak ≈ 10+
DISTANCE_THRESHOLD = 12.0  # fallback to global search if best L2 distance exceeds this
NO_CONTEXT_THRESHOLD = 18.0  # so high it means truly no relevant doc exists

# ── Topic routing ───────────────────────────────────────────────────────────
TOPICS = {
    "1":  {"folder": "company_detail", "name": "Software & Pricing"},
    "4":  {"folder": "Nakshatram",     "name": "Star Significations"},
    "7":  {"folder": "numerology",     "name": "Numerology"},
    "10": {"folder": "Jamakol",        "name": "Jamakkol Arudam"},
}

# Reverse map: folder_name → topic info
TOPIC_FOLDER_MAP = {v["folder"]: v for v in TOPICS.values()}

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the Automated AI Assistant for PNK ASTRO.

STRICT RULES:
1. OUTPUT FORMAT: Provide ONLY the final answer.
2. NO REASONING: Do not include internal thoughts, mentions of "Context", or explanations about your process.
3. CONCISENESS: Give brief, direct answers. 1-3 sentences maximum.
4. LANGUAGE: Reply in the EXACT language the user used (Tamil or English).
5. KNOWLEDGE: Use ONLY the provided Context. If information is not found, say: "I don't have that specific information in my knowledge base."
6. ACCURACY: Never invent information. When unsure, admit lack of knowledge."""

# ── Docs root (for ingestion) ──────────────────────────────────────────────
KB_ROOT = "./docs/"
