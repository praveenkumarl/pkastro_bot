#!/usr/bin/env python3
"""
Simplified embedding function replacement - removes all truncation complexity
"""

SIMPLE_EMBEDDING_FUNCTION = '''
def create_embeddings_ollama(texts, model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL):
    """
    Generate embeddings via Ollama HTTP API with retries.
    No truncation - chunks are already sized to fit.
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
                    raise ValueError("No embedding in response")
                    
            except Exception as e:
                if attempt == 3:
                    print(f"❌ Failed: {e}")
                    raise
                print(f"⚠️  Attempt {attempt}/3 failed, retrying...")
                time.sleep(2.0 * attempt)
    
    return embeddings
'''

print(SIMPLE_EMBEDDING_FUNCTION)
