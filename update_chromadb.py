#!/usr/bin/env python3
"""
PNK Astro Knowledge Base Ingestion Script
==========================================

Loads documents from ./docs/, chunks them, generates embeddings via Ollama,
and uploads to a ChromaDB server. If the server is unavailable, writes a
portable JSONL backup.

Supported file types:
  - .txt, .md  → TextLoader
  - .pdf       → PyMuPDF (fitz)
  - .json      → numerology entries converted to natural-language sentences

Usage:
    python update_chromadb.py

Requirements:
    - Ollama running with nomic-embed-text:latest
    - ChromaDB server running (optional; writes backup if unavailable)
    - pip install pymupdf langchain-community langchain-text-splitters chromadb requests
"""

import os
import json
import requests
import time
from pathlib import Path

import chromadb
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("⚠️  PyMuPDF not installed — PDFs will be skipped. Run: pip install pymupdf")


# ============================================================================
# CONFIGURATION
# ============================================================================

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "paraphrase-multilingual:latest"   # multilingual embedding (Tamil+English)
CHROMA_HOST = "127.0.0.1"
CHROMA_PORT = 8000
COLLECTION_NAME = "langchain"

KB_ROOT = "./docs/"
CHUNK_SIZE = 200   # paraphrase-multilingual has small context window (~256 tokens)
CHUNK_OVERLAP = 30
BATCH_SIZE = 64    # ChromaDB upload batch size

BACKUP_DIR = Path.home() / "picobot" / "chroma_db"
BACKUP_FILE = BACKUP_DIR / f"{COLLECTION_NAME}_backup.jsonl"

# File extensions handled by TextLoader
TEXT_EXTENSIONS = {".txt", ".md"}
# Folders whose .json files should be ingested as numerology entries
JSON_FOLDERS = {"numerology"}


# ============================================================================
# EMBEDDINGS
# ============================================================================

def create_embeddings_ollama(texts, model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL):
    """
    Generate embeddings via Ollama HTTP API with retries.
    Chunks are pre-sized to fit the embedding model context window.
    
    Args:
        texts: List of strings to embed
        model: Ollama model name
        base_url: Ollama API base URL
    
    Returns:
        List of embedding vectors
    """
    url = f"{base_url}/api/embeddings"
    embeddings = []
    
    for idx, text in enumerate(texts):
        for attempt in range(1, 4):
            try:
                resp = requests.post(
                    url,
                    json={"model": model, "prompt": text},
                    timeout=60
                )
                resp.raise_for_status()
                data = resp.json()
                
                if "embedding" in data:
                    embeddings.append(data["embedding"])
                    if (idx + 1) % 50 == 0:
                        print(f"   ✓ Embedded {idx + 1}/{len(texts)} documents")
                    break
                else:
                    raise ValueError("No embedding field in response")
                    
            except requests.exceptions.HTTPError as e:
                resp_text = resp.text[:500] if resp.text else "(empty)"
                error_msg = f"{e} | Response: {resp_text}"
                if attempt == 3:
                    print(f"❌ Failed to embed text {idx} after 3 attempts: {error_msg}")
                    raise
                print(f"⚠️ Embedding attempt {attempt}/3 failed for text {idx}: {error_msg}")
                time.sleep(2.0 * attempt)
            except Exception as e:
                if attempt == 3:
                    print(f"❌ Failed to embed text {idx} after 3 attempts: {e}")
                    raise
                print(f"⚠️ Embedding attempt {attempt}/3 failed for text {idx}: {e}")
                time.sleep(2.0 * attempt)
    
    return embeddings


# ============================================================================
# LOAD & CHUNK DOCUMENTS
# ============================================================================

def _load_text_file(file_path):
    """Load a single .txt or .md file. Returns list of Document objects."""
    try:
        loader = TextLoader(str(file_path), encoding="utf-8", autodetect_encoding=True)
        return loader.load()
    except Exception as e:
        print(f"      ⚠️ TextLoader failed for {file_path.name}: {e}")
        return []


def _load_pdf_file(file_path):
    """
    Extract text from a PDF using PyMuPDF.
    Returns list of Document-like objects with .page_content and .metadata.
    """
    if not HAS_PYMUPDF:
        return []

    from langchain_core.documents import Document

    docs = []
    try:
        pdf = fitz.open(str(file_path))
        for page_num in range(len(pdf)):
            page = pdf.load_page(page_num)
            text = page.get_text("text").strip()
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": str(file_path), "page": page_num + 1}
                ))
        pdf.close()
    except Exception as e:
        print(f"      ⚠️ PDF load failed for {file_path.name}: {e}")
    return docs


def _numerology_entry_to_text(entry):
    """
    Convert one numerology JSON entry to a natural-language paragraph
    suitable for embedding. Bilingual (English + Tamil).
    """
    n = entry.get("number", "?")
    planet = entry.get("ruling_planet_eng", "")
    planet_ta = entry.get("ruling_planet_tam", "")
    nature = entry.get("general_nature_eng", "")
    nature_ta = entry.get("general_nature_tam", "")
    name_suit = entry.get("name_suitability_eng", "")
    biz = entry.get("business_suitability_eng", "")
    colors = entry.get("lucky_colors_eng", "")
    gems = entry.get("lucky_gems_eng", "")
    lucky_dates = ", ".join(str(d) for d in entry.get("lucky_dates", []))
    health = entry.get("health_tendencies_eng", "")
    profession = entry.get("profession_eng", "")
    insight = entry.get("methodology_specific_insight_eng", "")
    keywords = ", ".join(entry.get("rag_keywords", []))
    compat = ", ".join(str(c) for c in entry.get("marriage_compatibility_numbers", []))

    lines = [
        f"Numerology Number {n} | எண் {n}",
        f"Ruling planet: {planet} ({planet_ta})",
        f"Nature: {nature}",
        f"Tamil: {nature_ta}",
        f"Name suitability: {name_suit}",
        f"Business: {biz}",
        f"Lucky colors: {colors} | Lucky gems: {gems}",
        f"Lucky dates: {lucky_dates}",
        f"Health: {health}",
        f"Profession: {profession}",
        f"Marriage compatibility numbers: {compat}",
        f"Key insight: {insight}",
        f"Keywords: {keywords}",
    ]
    return "\n".join(l for l in lines if l.split(": ", 1)[-1].strip())


def _load_numerology_json(file_path):
    """Load numerology JSON file and convert entries to natural-language Documents."""
    from langchain_core.documents import Document

    docs = []
    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, list):
            data = [data]

        for entry in data:
            if not isinstance(entry, dict):
                continue
            text = _numerology_entry_to_text(entry)
            if text.strip():
                docs.append(Document(
                    page_content=text,
                    metadata={"source": str(file_path)}
                ))
    except Exception as e:
        print(f"      ⚠️ JSON load failed for {file_path.name}: {e}")
    return docs


def load_documents(root_dir=KB_ROOT):
    """
    Load and chunk documents from the docs/ directory tree.
    Handles .txt, .md, .pdf, and numerology .json files.
    Assigns metadata: source_type = folder name.

    Returns:
        List of chunked Document objects
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    all_chunks = []
    root_path = Path(root_dir)

    if not root_path.exists():
        print(f"❌ Directory not found: {root_dir}")
        return []

    for folder_path in sorted(root_path.iterdir()):
        if not folder_path.is_dir():
            continue

        folder_name = folder_path.name
        # Skip scratch / utility folders
        if folder_name.lower() in {"scratch", "gmp"}:
            print(f"⏭️  Skipping folder: {folder_name}")
            continue

        print(f"📁 Processing folder: {folder_name}")
        folder_chunks = []

        for file_path in sorted(folder_path.rglob("*")):
            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()

            # Skip Python scripts and non-data files
            if ext in {".py", ".yaml", ".yml"}:
                continue

            raw_docs = []

            if ext in TEXT_EXTENSIONS:
                raw_docs = _load_text_file(file_path)

            elif ext == ".pdf":
                raw_docs = _load_pdf_file(file_path)

            elif ext == ".json" and folder_name in JSON_FOLDERS:
                raw_docs = _load_numerology_json(file_path)
                # Numerology entries are already sentence-sized — chunk lightly
                for doc in raw_docs:
                    doc.metadata["source_type"] = folder_name.lower()
                chunks = splitter.split_documents(raw_docs)
                folder_chunks.extend(chunks)
                print(f"   📊 {file_path.name}: {len(raw_docs)} entries → {len(chunks)} chunks")
                continue  # skip the generic chunking below

            else:
                continue  # unsupported / unneeded extension

            if raw_docs:
                chunks = splitter.split_documents(raw_docs)
                for chunk in chunks:
                    chunk.metadata["source_type"] = folder_name.lower()
                folder_chunks.extend(chunks)
                print(f"   📄 {file_path.name}: {len(chunks)} chunks")

        print(f"   ✓ Folder total: {len(folder_chunks)} chunks")
        all_chunks.extend(folder_chunks)

    return all_chunks


# ============================================================================
# UPLOAD TO CHROMA
# ============================================================================

def upload_to_chroma(ids, docs, metadatas, embeddings):
    """
    Upload documents and embeddings to ChromaDB server.
    
    Raises:
        Exception if upload fails
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    
    # Get or create collection
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        print(f"✓ Using existing collection: {COLLECTION_NAME}")
    except Exception:
        print(f"ℹ️ Creating collection: {COLLECTION_NAME}")
        collection = client.create_collection(name=COLLECTION_NAME)
    
    # Upload in batches
    total = len(ids)
    for i in range(0, total, BATCH_SIZE):
        batch_ids = ids[i:i+BATCH_SIZE]
        batch_docs = docs[i:i+BATCH_SIZE]
        batch_metas = metadatas[i:i+BATCH_SIZE]
        batch_embs = embeddings[i:i+BATCH_SIZE]
        
        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
            embeddings=batch_embs
        )
        
        print(f"   ✓ Uploaded {min(i+BATCH_SIZE, total)}/{total}")
    
    return True


# ============================================================================
# BACKUP (JSONL)
# ============================================================================

def write_jsonl_backup(ids, docs, metadatas, embeddings):
    """
    Write a portable JSONL backup of documents + embeddings.
    Each line is a JSON record: {id, document, metadata, embedding}
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(BACKUP_FILE, 'w', encoding='utf-8') as fh:
        for _id, doc, meta, emb in zip(ids, docs, metadatas, embeddings):
            record = {
                "id": _id,
                "document": doc,
                "metadata": meta,
                "embedding": emb
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"✓ Wrote JSONL backup: {BACKUP_FILE}")
    print(f"  Use: python scripts/import_jsonl_to_chroma.py --file {BACKUP_FILE}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("📄 PNK Astro Knowledge Base Ingestion")
    print("=" * 70)
    
    # 1. Load documents
    print("\n1️⃣  Loading documents...")
    chunks = load_documents(KB_ROOT)
    
    if not chunks:
        print("❌ No documents found. Check ./docs/ folder.")
        return
    
    print(f"✓ Total chunks: {len(chunks)}")
    
    # 2. Prepare data
    print("\n2️⃣  Preparing data...")
    ids = [f"doc_{i}" for i in range(len(chunks))]
    docs = [c.page_content for c in chunks]
    metadatas = [c.metadata for c in chunks]
    
    print(f"✓ Ready to embed {len(docs)} documents")
    
    # 3. Generate embeddings
    print("\n3️⃣  Generating embeddings via Ollama (nomic-embed-text)...")
    
    # Debug: show first document
    print(f"\n📋 First document preview:")
    print(f"   Length: {len(docs[0])} characters")
    print(f"   First 200 chars: {repr(docs[0][:200])}")
    
    try:
        embeddings = create_embeddings_ollama(docs)
        print(f"✓ Generated {len(embeddings)} embeddings")
    except Exception as e:
        print(f"❌ Embedding failed: {e}")
        return
    
    # 4. Upload to Chroma
    print("\n4️⃣  Uploading to ChromaDB...")
    try:
        upload_to_chroma(ids, docs, metadatas, embeddings)
        print(f"✅ SUCCESS: {len(docs)} documents uploaded to Chroma server")
        
    except Exception as e:
        print(f"⚠️ Chroma upload failed: {e}")
        print(f"   Writing JSONL backup instead...")
        try:
            write_jsonl_backup(ids, docs, metadatas, embeddings)
            print(f"✅ Backup saved. You can import it later:")
            print(f"   python scripts/import_jsonl_to_chroma.py --file {BACKUP_FILE}")
        except Exception as backup_err:
            print(f"❌ Backup failed: {backup_err}")
            return
    
    print("\n" + "=" * 70)
    print("✅ Ingestion complete")
    print("=" * 70)


if __name__ == "__main__":
    main()