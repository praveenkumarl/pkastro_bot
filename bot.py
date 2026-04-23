#!/usr/bin/env python3
"""
PNK Astro Bot — FastAPI HTTP server + Telegram bot
Replaces: pnkastro_bot.js + chroma_api_wrapper.py

Run:
    python bot.py
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import (
    PORT,
    SARVAM_API_KEY,
    SARVAM_API_URL,
    SARVAM_MODEL,
    SYSTEM_PROMPT,
    TELEGRAM_BOT_TOKEN,
    CHROMA_HOST,
    CHROMA_PORT,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
)
from retriever import retrieve_context
from chat_memory import load_history, save_turn, prune_old_sessions
from router import route_query

log = logging.getLogger(__name__)


# ── LLM call ───────────────────────────────────────────────────────────────

async def call_llm(user_message: str, session_id: str = "default", topic: Optional[str] = None) -> str:
    """Retrieve context, call Sarvam LLM, return cleaned answer."""
    log.info('Processing: "%s"', user_message)

    # 1. Route query → determine topic filter + check for direct lookup
    topic_filter, direct_context = route_query(user_message, topic)

    # 2. Retrieve relevant chunks (skip vector search if direct context available)
    if direct_context:
        context_chunks = [direct_context]
    else:
        context_chunks = await asyncio.to_thread(retrieve_context, user_message, topic_filter)

    if not context_chunks:
        log.warning("No context retrieved")
        return (
            "I don't have specific information about that in my knowledge base. "
            "Please ask me about astrology, numerology, planet karakas, nakshatras, "
            "or our services. You can also type 'Who are you?' to learn more about me!"
        )

    # 3. Build message payload (history loaded from SQLite)
    history = load_history(session_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {
            "role": "user",
            "content": f"[CONTEXT]\n{chr(10).join(f'[{i+1}] {c}' for i, c in enumerate(context_chunks))}\n[/CONTEXT]\n\nQuestion: {user_message}",
        },
    ]

    # 4. Call Sarvam AI
    log.info("Calling Sarvam API (%d messages)", len(messages))
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                SARVAM_API_URL,
                json={"model": SARVAM_MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 250},
                headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.error("Sarvam API error: %s", exc)
        # Log response body for debugging 400/422 errors
        if hasattr(exc, "response") and exc.response is not None:
            try:
                log.error("Sarvam response body: %s", exc.response.text[:500])
            except Exception:
                pass
        return "Sorry, I'm having trouble connecting to the AI brain. Please try again later."

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    # Clean reasoning tags, prefixes, and meta-commentary
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"^(ANSWER:|Response:|Output:)", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"(?i)^(based on (the |my )?context[,:]?|according to (the |my )?context[,:]?|from (the |my )?context[,:]?)\s*", "", content).strip()

    # 5. Persist to SQLite
    save_turn(session_id, user_message, content)

    log.info("Response sent (%d chars)", len(content))
    return content


# ── Telegram bot (polling in background task) ──────────────────────────────

async def _run_telegram_polling():
    """Long-poll the Telegram getUpdates endpoint."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    offset = 0

    async with httpx.AsyncClient(timeout=60) as client:
        log.info("Telegram bot polling started")
        while True:
            try:
                resp = await client.get(
                    f"{base}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    if not text or not chat_id or text.startswith("/"):
                        continue

                    # Send typing indicator
                    await client.post(
                        f"{base}/sendChatAction",
                        json={"chat_id": chat_id, "action": "typing"},
                    )

                    # Get AI reply
                    reply = await call_llm(text, str(chat_id))

                    # Send reply
                    await client.post(
                        f"{base}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": reply,
                            "parse_mode": "Markdown",
                        },
                    )
            except httpx.ReadTimeout:
                continue  # normal long-poll timeout
            except Exception as exc:
                log.error("Telegram polling error: %s", exc)
                await asyncio.sleep(5)


# ── FastAPI app ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Telegram polling as a background task
    # Prune stale sessions on startup
    await asyncio.to_thread(prune_old_sessions)
    task = asyncio.create_task(_run_telegram_polling())
    log.info("=" * 60)
    log.info("PNK Astro Bot listening on port %d", PORT)
    log.info("HTTP endpoint: POST /chat")
    log.info("Health check:  GET /health")
    log.info("Telegram bot:  %s", "enabled" if TELEGRAM_BOT_TOKEN else "disabled")
    log.info("=" * 60)
    yield
    task.cancel()


app = FastAPI(title="PNK Astro Bot", version="2.0.0", lifespan=lifespan)


# ── Request / response models ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    sessionId: Optional[str] = None
    topic: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    session = req.sessionId or request.client.host
    reply = await call_llm(req.message, session, req.topic)
    return ChatResponse(reply=reply)


@app.get("/health")
async def health():
    import chromadb
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        cols = client.list_collections()
        chroma_ok = True
        col_names = [c.name for c in cols]
    except Exception as exc:
        chroma_ok = False
        col_names = []

    return {
        "status": "ok" if chroma_ok else "degraded",
        "chroma": {
            "host": CHROMA_HOST,
            "port": CHROMA_PORT,
            "connected": chroma_ok,
            "collections": col_names,
        },
        "embedding_model": EMBEDDING_MODEL,
        "llm_model": SARVAM_MODEL,
    }


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
