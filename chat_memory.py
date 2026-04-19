"""
PNK Astro Bot — Persistent chat memory backed by SQLite.

Schema:
    CREATE TABLE messages (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        session   TEXT    NOT NULL,
        role      TEXT    NOT NULL,   -- 'user' | 'assistant'
        content   TEXT    NOT NULL,
        ts        INTEGER NOT NULL    -- Unix timestamp (seconds)
    )

Usage:
    from chat_memory import load_history, save_turn, prune_old_sessions
"""

import sqlite3
import time
import threading
import logging
from typing import List

log = logging.getLogger(__name__)

DB_PATH = "./chat_memory.db"
MAX_TURNS = 3            # keep last N user/assistant pairs per session (= 6 rows)
SESSION_TTL_HOURS = 24   # prune sessions older than this

# Thread-local connections so each thread gets its own sqlite3 connection
_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads
        _init_schema(_local.conn)
    return _local.conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            session TEXT    NOT NULL,
            role    TEXT    NOT NULL,
            content TEXT    NOT NULL,
            ts      INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session, ts)")
    conn.commit()


# ── Public API ──────────────────────────────────────────────────────────────

def load_history(session_id: str) -> List[dict]:
    """
    Return the last MAX_TURNS*2 messages for this session as
    {"role", "content"} dicts, oldest first.

    Sarvam requires strict alternation starting with 'user'.
    We enforce this by:
      1. Stripping any leading assistant turns (window cut an incomplete pair at start)
      2. Stripping any trailing user turns  (window cut an incomplete pair at end)
    Result is always [] or [user, assistant, user, assistant, ...]
    """
    conn = _conn()
    rows = conn.execute(
        """
        SELECT role, content FROM (
            SELECT role, content, ts FROM messages
            WHERE session = ?
            ORDER BY ts DESC
            LIMIT ?
        ) ORDER BY ts ASC
        """,
        (session_id, MAX_TURNS * 2),
    ).fetchall()
    history = [{"role": row[0], "content": row[1]} for row in rows]

    # Drop leading assistant turns (history window started mid-pair)
    while history and history[0]["role"] != "user":
        history.pop(0)

    # Drop trailing user turns (history window ended mid-pair)
    # This ensures the last entry is always 'assistant', so appending
    # the new user message always maintains alternation.
    while history and history[-1]["role"] != "assistant":
        history.pop()

    return history


def save_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Persist one user/assistant exchange to the database."""
    now = int(time.time())
    conn = _conn()
    conn.executemany(
        "INSERT INTO messages (session, role, content, ts) VALUES (?, ?, ?, ?)",
        [
            (session_id, "user",      user_msg,      now),
            (session_id, "assistant", assistant_msg, now),
        ],
    )
    conn.commit()


def prune_old_sessions() -> int:
    """
    Delete messages older than SESSION_TTL_HOURS.
    Returns number of rows deleted. Safe to call on startup or periodically.
    """
    cutoff = int(time.time()) - SESSION_TTL_HOURS * 3600
    conn = _conn()
    cur = conn.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
    conn.commit()
    deleted = cur.rowcount
    if deleted:
        log.info("Pruned %d stale chat memory rows (older than %dh)", deleted, SESSION_TTL_HOURS)
    return deleted
