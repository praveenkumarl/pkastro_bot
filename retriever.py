"""
PNK Astro Bot — Retrieval module
Handles: embedding, hybrid BM25+vector search, RRF merging, query expansion.
"""

import re
import time
import logging
from typing import List, Optional, Tuple, Dict

import requests
import chromadb

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    logging.getLogger(__name__).warning(
        "rank_bm25 not installed — falling back to vector-only search. "
        "Run: pip install rank-bm25"
    )

from config import (
    OLLAMA_BASE_URL,
    EMBEDDING_MODEL,
    RERANK_MODEL,
    CHROMA_HOST,
    CHROMA_PORT,
    COLLECTION_NAME,
    TOP_K,
    RERANK_TOP_N,
    DISTANCE_THRESHOLD,
    NO_CONTEXT_THRESHOLD,
    TOPICS,
    TOPIC_FOLDER_MAP,
)

log = logging.getLogger(__name__)

# ── Lazy singleton ChromaDB client ──────────────────────────────────────────

_chroma_client: Optional[chromadb.HttpClient] = None


def _get_chroma() -> chromadb.HttpClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return _chroma_client


# ── BM25 index (built lazily from ChromaDB corpus) ──────────────────────────
# Stores: (BM25Okapi, list[str] of all docs, list[dict] of all metadatas)

_bm25_index: Optional["BM25Okapi"] = None
_bm25_corpus: List[str] = []
_bm25_metadatas: List[dict] = []


def _tokenize(text: str) -> List[str]:
    """
    Language-agnostic tokenizer: splits on whitespace + punctuation.
    Works for both Tamil Unicode and English text.
    """
    text = text.lower()
    # Keep Tamil Unicode ranges (U+0B80–U+0BFF) and ASCII alphanumerics
    tokens = re.findall(r"[\u0B80-\u0BFF]+|[a-z0-9]+", text)
    return tokens if tokens else text.split()


def _build_bm25_index(collection) -> None:
    """
    Load ALL documents from ChromaDB and build an in-memory BM25 index.
    Called once on first query; refreshed if corpus is stale (collection grows).
    """
    global _bm25_index, _bm25_corpus, _bm25_metadatas

    log.info("Building BM25 index from ChromaDB corpus...")
    try:
        # ChromaDB returns max 100 per get(); use limit param to fetch all
        result = collection.get(include=["documents", "metadatas"])
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
    except Exception as exc:
        log.error("Failed to load corpus for BM25: %s", exc)
        return

    if not docs:
        log.warning("No documents in collection — BM25 index empty")
        return

    _bm25_corpus = docs
    _bm25_metadatas = metas
    tokenized = [_tokenize(d) for d in docs]
    _bm25_index = BM25Okapi(tokenized)
    log.info("BM25 index built: %d documents", len(docs))


def _bm25_search(
    query: str,
    topic_folder: Optional[str],
    n: int,
) -> List[Tuple[str, dict]]:
    """
    Score all corpus docs with BM25, apply optional topic filter,
    return top-n as (doc_text, metadata) pairs.
    """
    if not HAS_BM25 or _bm25_index is None:
        return []

    tokens = _tokenize(query)
    scores = _bm25_index.get_scores(tokens)

    # Pair (score, doc, meta), optionally filter by topic
    candidates = []
    for score, doc, meta in zip(scores, _bm25_corpus, _bm25_metadatas):
        if topic_folder and meta.get("source_type") != topic_folder:
            continue
        candidates.append((score, doc, meta))

    # Sort descending by score
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [(doc, meta) for _, doc, meta in candidates[:n]]


# ── Reciprocal Rank Fusion ──────────────────────────────────────────────────

def _rrf_merge(
    vector_docs: List[str],
    bm25_pairs: List[Tuple[str, dict]],
    k: int = 60,
) -> List[str]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion.
    RRF score = Σ 1 / (k + rank_i)
    Returns deduplicated list ordered by combined score.
    """
    scores: Dict[str, float] = {}
    doc_order: Dict[str, str] = {}  # canonical text (first seen)

    # Vector list contributes
    for rank, doc in enumerate(vector_docs, start=1):
        key = doc[:120]  # use prefix as dedup key
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
        doc_order[key] = doc

    # BM25 list contributes
    for rank, (doc, _meta) in enumerate(bm25_pairs, start=1):
        key = doc[:120]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
        doc_order[key] = doc

    ranked = sorted(scores.keys(), key=lambda k_: scores[k_], reverse=True)
    return [doc_order[k] for k in ranked]


# ── Embedding via Ollama ────────────────────────────────────────────────────

def create_embedding(text: str, model: str = EMBEDDING_MODEL) -> Optional[List[float]]:
    """Generate a single embedding vector via Ollama with retries."""
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                url,
                json={"model": model, "prompt": text},
                timeout=60,
            )
            resp.raise_for_status()
            emb = resp.json().get("embedding")
            if emb:
                return emb
            raise ValueError("No embedding field in response")
        except Exception as exc:
            log.warning("Embedding attempt %d/3 failed: %s", attempt, exc)
            if attempt == 3:
                log.error("Embedding failed after 3 attempts")
                return None
            time.sleep(1.5 * attempt)
    return None


# ── Query expansion ─────────────────────────────────────────────────────────

def expand_query(query: str) -> str:
    """Add synonyms / variations to improve recall."""
    q = query.lower()
    extras: List[str] = []

    if "விலை" in q or "price" in q:
        extras.append("cost amount payment fees")
    if "demo" in q:
        extras.append("youtube video tutorial")

    nums = re.findall(r"\d+", q)
    for n in nums:
        extras.append(f"number {n}")

    if extras:
        return f"{query} {' '.join(extras)}"
    return query


# ── Resolve topic filter ───────────────────────────────────────────────────

def resolve_topic(selected_topic: Optional[str]) -> Optional[str]:
    """Return the folder name to filter on, or None."""
    if not selected_topic:
        return None
    info = TOPICS.get(selected_topic) or TOPIC_FOLDER_MAP.get(selected_topic)
    if info:
        return info["folder"]
    return selected_topic if isinstance(selected_topic, str) else None


# ── Hybrid retrieval ────────────────────────────────────────────────────────

def retrieve_context(
    query: str,
    selected_topic: Optional[str] = None,
) -> List[str]:
    """
    Hybrid retrieval: vector search (ChromaDB) + keyword search (BM25),
    merged with Reciprocal Rank Fusion.

    Steps:
      1. Expand query, embed it
      2. Vector search in ChromaDB (with optional topic filter)
      3. BM25 keyword search over in-memory index (same filter)
      4. RRF merge → top RERANK_TOP_N results
      5. Fallback to global vector search if topic filter gives weak results
    """
    expanded = expand_query(query)
    embedding = create_embedding(expanded)
    if embedding is None:
        log.error("Failed to create query embedding")
        return []

    client = _get_chroma()
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception:
        log.error("Collection '%s' not found in ChromaDB", COLLECTION_NAME)
        return []

    # Build BM25 index lazily (once per process lifetime)
    if HAS_BM25 and _bm25_index is None:
        _build_bm25_index(collection)

    topic_folder = resolve_topic(selected_topic)

    # ── 1. Vector search ─────────────────────────────────────────────────────
    query_opts: dict = {
        "query_embeddings": [embedding],
        "n_results": TOP_K,
        "include": ["documents", "distances", "metadatas"],
    }
    if topic_folder:
        query_opts["where"] = {"source_type": topic_folder}
        log.info("Vector search: filtering by topic=%s", topic_folder)

    results = collection.query(**query_opts)
    vector_docs = (results.get("documents") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    if vector_docs:
        best_dist = distances[0]
        log.info("Vector: %d docs (top dist=%.3f)", len(vector_docs), best_dist)
        # If best distance is so high nothing is relevant, return empty early
        if not topic_folder and best_dist > NO_CONTEXT_THRESHOLD:
            log.warning("Best L2 distance %.3f > NO_CONTEXT_THRESHOLD %.1f — no relevant docs",
                        best_dist, NO_CONTEXT_THRESHOLD)
            return []
    else:
        log.warning("Vector search returned no results")

    # Fallback: if topic filter gave weak vector results, also run global vector search
    if topic_folder and (not vector_docs or distances[0] > DISTANCE_THRESHOLD):
        log.info("Weak topic-filtered vector results — adding global vector fallback")
        fallback_opts = dict(query_opts)
        fallback_opts.pop("where", None)
        fb_results = collection.query(**fallback_opts)
        fb_docs = (fb_results.get("documents") or [[]])[0]
        # Merge: topic results first (may be empty), then fallback
        vector_docs = vector_docs + [d for d in fb_docs if d not in vector_docs]

    # ── 2. BM25 keyword search ───────────────────────────────────────────────
    bm25_pairs: List[Tuple[str, dict]] = []
    if HAS_BM25 and _bm25_index is not None:
        bm25_pairs = _bm25_search(expanded, topic_folder, n=TOP_K)
        log.info("BM25: %d candidate docs", len(bm25_pairs))

        # Same fallback: if topic filter produced too few BM25 hits, search globally
        if topic_folder and len(bm25_pairs) < 3:
            log.info("Too few BM25 topic hits — adding global BM25")
            global_pairs = _bm25_search(expanded, None, n=TOP_K)
            seen = {doc for doc, _ in bm25_pairs}
            bm25_pairs += [(doc, meta) for doc, meta in global_pairs if doc not in seen]

    # ── 3. RRF merge ─────────────────────────────────────────────────────────
    if bm25_pairs:
        merged = _rrf_merge(vector_docs, bm25_pairs)
        log.info("RRF merged: %d unique docs → returning top %d", len(merged), RERANK_TOP_N)
    else:
        # BM25 unavailable — use vector results only
        merged = vector_docs

    return merged[:RERANK_TOP_N]
