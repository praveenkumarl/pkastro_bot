# PNK Astro Bot

AI assistant for PNK Astro — answers questions about astrology, numerology, software pricing, and company info via Telegram and HTTP API.

---

## Architecture

```
User (Telegram / HTTP)
        │
        ▼
   bot.py  ──────────────── router.py
   FastAPI                  Intent detection
   + Telegram polling       Numerology exact lookup
        │
        ├── direct_context (numerology hit → skip vector search)
        │
        └── retriever.py
            Hybrid search
            ├── ChromaDB  (vector / semantic)
            └── BM25      (keyword / exact match)
            └── RRF merge (Reciprocal Rank Fusion)
                │
                ▼
           Sarvam AI LLM
                │
           chat_memory.py
           SQLite (persistent sessions)
```

### Files

| File | Role |
|---|---|
| `bot.py` | FastAPI HTTP server + Telegram long-polling |
| `config.py` | All constants, env vars, system prompt |
| `retriever.py` | Hybrid BM25 + vector retrieval with RRF merge |
| `router.py` | Intent detection, topic routing, numerology direct lookup |
| `chat_memory.py` | SQLite-backed persistent session memory |
| `update_chromadb.py` | Ingestion: docs → chunks → embeddings → ChromaDB |
| `deploy/` | systemd units, Nginx config, install script |

---

## Requirements

- Ubuntu VPS, 2 CPU, 4 GB RAM
- Python 3.9+
- Ollama with `nomic-embed-text:latest` pulled
- ChromaDB running on port 8000
- Nginx
- Sarvam AI API key + Telegram Bot token in `.env`

---

## First-Time Setup

### 1. Clone and create virtualenv
```bash
cd /home/picoadmin
git clone <your-repo> picobot
cd picobot
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Configure environment
```bash
cp .env.example .env   # or edit .env directly
```

Required values in `.env`:
```
SARVAM_API_KEY=sk_...
TELEGRAM_BOT_TOKEN=...
PORT=3000
```

### 3. Pull Ollama models
```bash
ollama pull nomic-embed-text:latest
ollama pull paraphrase-multilingual:latest
```

### 4. Run install script (installs deps, systemd, nginx, cron)
```bash
bash deploy/install.sh
```

### 5. Build the knowledge base (first time)
```bash
source .venv/bin/activate
python update_chromadb.py
```

### 6. Verify everything is running
```bash
sudo systemctl status pnkastro-bot chromadb
curl -s http://localhost/health
```

---

## Daily Operations

### View live logs
```bash
sudo journalctl -fu pnkastro-bot
sudo journalctl -fu chromadb
```

### Restart bot (after code changes)
```bash
sudo systemctl restart pnkastro-bot
```

### Restart ChromaDB
```bash
sudo systemctl restart chromadb
# Then restart bot too (BM25 index needs rebuild)
sudo systemctl restart pnkastro-bot
```

### Test the HTTP endpoint
```bash
curl -s -X POST http://localhost/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is number 7 in numerology?", "sessionId": "test"}'
```

---

## Adding New Documents

### Step 1 — Add the file

Place the file inside the relevant subfolder under `docs/`:

```
docs/
  Basics/          → astrology fundamentals
  Bhavam/          → house significations
  company_detail/  → company info, pricing, software
  Jamakol/         → horary astrology
  Naadi/           → naadi / transit predictions
  Nakshatram/      → star significations
  numerology/      → numerology data (JSON or text)
  Planets/         → planetary significations
  PaagaiMurai/     → degree-based astrology
  Vasthu/          → vasthu rules
```

**Supported formats:** `.txt`, `.md`, `.pdf`, `.json` (numerology only)

> The folder name becomes the `source_type` metadata tag used for topic filtering. Keep files inside the correct folder.

### Step 2 — Re-ingest

```bash
cd /home/picoadmin/picobot
source .venv/bin/activate

# Delete old collection (required to avoid duplicate IDs)
python -c "
import chromadb
c = chromadb.HttpClient()
c.delete_collection('langchain')
print('Collection deleted')
"

# Re-ingest all docs
python update_chromadb.py
```

### Step 3 — Restart bot (to rebuild BM25 index)
```bash
sudo systemctl restart pnkastro-bot
```

---

## Adding a New Topic/Folder

If you add an entirely new subject folder (e.g. `docs/Yogam/`):

**1.** Add the folder with your documents.

**2.** Register the topic in `config.py`:
```python
TOPICS = {
    ...
    "11": {"folder": "Yogam", "name": "Yoga Combinations"},
}
```

**3.** Add routing keywords in `router.py` — add a new keyword set and map it:
```python
_YOGAM_KW = {"yoga", "yogam", "combination", "யோகம்"}

# in _detect_intent():
if toks & _YOGAM_KW:
    return "YOGAM"

# in _INTENT_TO_FOLDER:
"YOGAM": "Yogam",
```

**4.** Re-ingest and restart (Steps 2–3 above).

---

## Updating Numerology Data

The numerology JSON files are the single source of truth for number lookups.

### File locations
```
docs/numerology/numerology_upgraded.json   ← numbers 1–9 (primary)
docs/numerology/numerology_1_108.json      ← numbers 1–108 (extended)
```

### JSON entry schema
```json
{
  "number": 7,
  "ruling_planet_eng": "Ketu",
  "ruling_planet_tam": "கேது",
  "is_auspicious": true,
  "general_nature_eng": "...",
  "general_nature_tam": "...",
  "name_suitability_eng": "...",
  "name_suitability_tam": "...",
  "business_suitability_eng": "...",
  "business_suitability_tam": "...",
  "lucky_colors_eng": "...",
  "lucky_colors_tam": "...",
  "lucky_gems_eng": "...",
  "lucky_gems_tam": "...",
  "lucky_dates": [7, 16, 25],
  "unlucky_dates": [8, 17, 26],
  "health_tendencies_eng": "...",
  "health_tendencies_tam": "...",
  "profession_eng": "...",
  "profession_tam": "...",
  "marriage_compatibility_numbers": [2, 6],
  "methodology_specific_insight_eng": "...",
  "methodology_specific_insight_tam": "...",
  "rag_keywords": ["ketu", "spiritual", "research"]
}
```

After editing the JSON: re-ingest + restart (both `router.py` and `update_chromadb.py` load from this file).

---

## Ingestion Details

`update_chromadb.py` processes files in this order:

| Format | Loader | Notes |
|---|---|---|
| `.txt`, `.md` | TextLoader (langchain) | Auto-detects encoding |
| `.pdf` | PyMuPDF page-by-page | Tamil Unicode preserved |
| `.json` (numerology folder only) | Custom | Each entry → natural-language paragraph |
| `.py`, `.yaml`, `.yml` | Skipped | Dev scripts, not knowledge |
| `scratch/`, `GMP/` folders | Skipped | Not ingested |

Chunk settings (in `config.py`):
```python
CHUNK_SIZE    = 512   # characters
CHUNK_OVERLAP = 64    # characters
```

---

## Retrieval Flow

For every user query:

```
1. router.py  → detect intent → topic_filter + optional direct_context
                │
                ├── Numerology number found → return JSON entry directly (no embedding)
                │
                └── Otherwise → topic_filter passed to retriever.py

2. retriever.py
   ├── Expand query (add synonyms for price/demo/numbers)
   ├── Embed query with nomic-embed-text via Ollama
   ├── Vector search ChromaDB (top 8, filtered by topic if set)
   ├── BM25 keyword search (in-memory index, same filter)
   └── RRF merge → top 5 chunks returned

3. bot.py  → build prompt (system + history + context + question)
4. Sarvam AI → generate answer
5. chat_memory.py → save exchange to SQLite
```

---

## Resource Usage (2 CPU / 4 GB VPS)

| Service | Approx. RAM |
|---|---|
| Ollama (nomic-embed-text) | ~800 MB |
| Ollama (paraphrase-multilingual) | ~600 MB |
| ChromaDB | ~200 MB |
| Python bot (FastAPI + BM25 index) | ~150–300 MB |
| OS + Nginx | ~400 MB |
| **Total** | **~2.2–2.3 GB** |

BM25 index lives in memory as long as `bot.py` is running. It is rebuilt once on startup from ChromaDB. Larger corpora = more RAM; monitor with `free -h`.

---

## Troubleshooting

### Bot not responding
```bash
sudo systemctl status pnkastro-bot
sudo journalctl -fu pnkastro-bot --since "5 min ago"
curl -s http://localhost/health
```

### ChromaDB errors
```bash
sudo systemctl status chromadb
sudo journalctl -fu chromadb
# If collection is corrupt:
python -c "import chromadb; c=chromadb.HttpClient(); c.delete_collection('langchain')"
python update_chromadb.py
sudo systemctl restart pnkastro-bot
```

### Ollama embedding fails
```bash
curl http://127.0.0.1:11434/api/tags   # list loaded models
ollama pull nomic-embed-text:latest    # re-pull if missing
```

### High memory usage
```bash
free -h
sudo journalctl --vacuum-size=100M   # shrink journal logs
# Reduce BM25 index by increasing RERANK_TOP_N in config.py (loads fewer items)
```

### Telegram bot not receiving messages
- Confirm `TELEGRAM_BOT_TOKEN` is set in `.env`
- Only one process can poll a bot token at a time — ensure the old Node.js bot (`pnkastro_bot.js`) is stopped
- Check for conflicts: `sudo systemctl stop pnkastro_bot_js` (if it exists)
