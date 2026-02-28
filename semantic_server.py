    # semantic_server.py
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import os
import numpy as np

app = Flask(__name__)

# Load model
model = SentenceTransformer('all-MiniLM-L6-v2')  # lightweight for Pi4

# Load text files from "local_docs" folder
text_chunks = []
chunk_embeddings = []

DOC_FOLDER = "./docs"

def load_docs():
    global text_chunks, chunk_embeddings
    text_chunks = []
    for filename in os.listdir(DOC_FOLDER):
        if filename.endswith(".txt"):
            with open(os.path.join(DOC_FOLDER, filename), "r", encoding="utf-8") as f:
                text = f.read()
                # split into 500-word chunks
                words = text.split()
                for i in range(0, len(words), 500):
                    chunk = " ".join(words[i:i+500])
                    text_chunks.append(chunk)
    # generate embeddings
    chunk_embeddings = model.encode(text_chunks)
    print(f"✅ Loaded {len(text_chunks)} chunks from local_docs")

load_docs()

def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

@app.route("/ask_local", methods=["POST"])
def ask_local():
    data = request.json
    question = data.get("question", "")
    if not question or not text_chunks:
        return jsonify({"answer": None})
    q_emb = model.encode([question])[0]
    sims = [cosine_sim(q_emb, ce) for ce in chunk_embeddings]
    best_idx = np.argmax(sims)
    if sims[best_idx] < 0.55:  # threshold for similarity
        return jsonify({"answer": None})  # no match found
    return jsonify({"answer": text_chunks[best_idx]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)
    
