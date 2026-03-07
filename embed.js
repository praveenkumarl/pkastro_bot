import axios from "axios";

export async function createEmbedding(text) {
  const response = await axios.post("http://localhost:11434/api/embeddings", {
    model: "nomic-embed-text",
    prompt: text
  });

  return response.data.embedding;
}
