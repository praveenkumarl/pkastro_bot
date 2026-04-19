#!/usr/bin/env python3
"""
Import a JSONL backup produced by `update_chromadb.py` into a running Chroma server.

Usage:
  python import_jsonl_to_chroma.py --file ~/picobot/chroma_db/langchain_backup.jsonl

The script will create the collection `langchain` if it does not exist, then add
documents in batches. Embeddings are uploaded along with documents and metadata.
"""
import os
import json
import argparse
import time
from typing import List

import chromadb
from chromadb.errors import NotFoundError


def read_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                continue
            yield json.loads(line)


def batch_iterable(iterable, n):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--file', '-f', default=os.path.expanduser('~/picobot/chroma_db/langchain_backup.jsonl'))
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--collection', default='langchain')
    p.add_argument('--batch', type=int, default=64)
    args = p.parse_args()

    path = os.path.expanduser(args.file)
    if not os.path.exists(path):
        print(f"❌ File not found: {path}")
        return

    print(f"📥 Importing {path} → http://{args.host}:{args.port} collection='{args.collection}'")

    client = chromadb.HttpClient(host=args.host, port=args.port)

    # Ensure collection exists (create if missing)
    try:
        collection = client.get_collection(name=args.collection)
        print(f"ℹ️ Using existing collection: {args.collection}")
    except Exception:
        print(f"ℹ️ Collection '{args.collection}' not found on server; creating it.")
        try:
            collection = client.create_collection(name=args.collection)
        except Exception as e:
            print("❌ Failed to create collection on server:", e)
            return

    items = list(read_jsonl(path))
    total = len(items)
    print(f"🔁 Found {total} records; uploading in batches of {args.batch}...")

    uploaded = 0
    for batch in batch_iterable(items, args.batch):
        ids: List[str] = [r.get('id') for r in batch]
        docs: List[str] = [r.get('document') for r in batch]
        metas: List[dict] = [r.get('metadata') for r in batch]
        embs: List[list] = [r.get('embedding') for r in batch]

        # retry small number of times on transient errors
        tries = 3
        for attempt in range(1, tries + 1):
            try:
                collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
                uploaded += len(batch)
                print(f"   ✓ uploaded {uploaded}/{total}")
                break
            except Exception as e:
                print(f"   ⚠️ upload attempt {attempt} failed: {e}")
                if attempt == tries:
                    print("   ❌ Giving up on this batch. Aborting import.")
                    return
                time.sleep(1.0 * attempt)

    print(f"✅ Import complete: {uploaded}/{total} records uploaded to collection '{args.collection}'")


if __name__ == '__main__':
    main()
