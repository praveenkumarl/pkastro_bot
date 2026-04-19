#!/usr/bin/env python3
"""
Simple FastAPI wrapper around ChromaDB
Exposes REST endpoints that the Node.js bot can query
"""

import os
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

import chromadb

# ============================================================================
# Configuration
# ============================================================================

CHROMA_HOST = "127.0.0.1"
CHROMA_PORT = 8000
COLLECTION_NAME = "langchain"

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title="Chroma API Wrapper", version="1.0.0")

# ChromaDB client
chroma_client = None

@app.on_event("startup")
async def startup():
    global chroma_client
    try:
        chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        # Test connection
        collections = chroma_client.list_collections()
        print(f"✓ Connected to Chroma. Collections: {[c.name for c in collections]}")
    except Exception as err:
        print(f"❌ Failed to connect to Chroma: {err}")
        sys.exit(1)

# ============================================================================
# Request/Response Models
# ============================================================================

class QueryRequest(BaseModel):
    query_embedding: List[float]
    n_results: int = 8
    include: Optional[List[str]] = ["documents", "distances", "metadatas"]
    where: Optional[dict] = None

class QueryResponse(BaseModel):
    documents: List[List[str]]
    distances: List[List[float]]
    metadatas: List[List[dict]]

# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health():
    try:
        collections = chroma_client.list_collections()
        return {
            "status": "ok",
            "chroma": {
                "host": CHROMA_HOST,
                "port": CHROMA_PORT,
                "collections": [c.name for c in collections]
            }
        }
    except Exception as err:
        raise HTTPException(status_code=503, detail=f"Chroma error: {err}")

# ============================================================================
# Query Endpoint
# ============================================================================

@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """Query the langchain collection"""
    try:
        # Get collection
        try:
            collection = chroma_client.get_collection(name=COLLECTION_NAME)
        except Exception as err:
            raise HTTPException(status_code=404, detail=f"Collection '{COLLECTION_NAME}' not found")
        
        # Build query options
        query_options = {
            "query_embeddings": [req.query_embedding],
            "n_results": req.n_results,
            "include": req.include
        }
        
        if req.where:
            query_options["where"] = req.where
        
        # Query
        results = collection.query(**query_options)
        
        return QueryResponse(
            documents=results["documents"],
            distances=results["distances"],
            metadatas=results["metadatas"]
        )
        
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Query error: {err}")

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("WRAPPER_PORT", 8001))
    print(f"🚀 Starting Chroma API Wrapper on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port)
