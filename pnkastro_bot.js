/**
 * PNK Astro Bot - Telegram & HTTP Bot
 * 
 * Uses:
 * - Ollama embeddings: paraphrase-multilingual:latest
 * - LLM: Sarvam AI (sarvam-m model)
 * - Vector store: ChromaDB (langchain collection)
 * - Interfaces: Telegram Bot API + Express HTTP
 */

import express from "express";
import axios from "axios";
import dotenv from "dotenv";
import TelegramBot from "node-telegram-bot-api";

dotenv.config();

// ============================================================================
// CONFIGURATION
// ============================================================================

const OLLAMA_BASE_URL = "http://127.0.0.1:11434";
const EMBEDDING_MODEL = "paraphrase-multilingual:latest";
const SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions";
const SARVAM_MODEL = "sarvam-m";

const CHROMA_HOST = "127.0.0.1";
const CHROMA_PORT = 8000;
const CHROMA_BASE_URL = `http://${CHROMA_HOST}:${CHROMA_PORT}`;
const WRAPPER_HOST = "127.0.0.1";
const WRAPPER_PORT = 8001;
const WRAPPER_BASE_URL = `http://${WRAPPER_HOST}:${WRAPPER_PORT}`;
const COLLECTION_NAME = "langchain";

// Topic metadata for folder-based filtering
const TOPICS = {
    "1": { folder: "company_detail", name: "Software & Pricing" },
    "4": { folder: "nakshatram", name: "Star Significations" },
    "7": { folder: "numerology", name: "Numerology" },
    "10": { folder: "jamakkol", name: "Jamakkol Arudam" }
};

const TOPIC_FOLDER_MAP = Object.fromEntries(
    Object.entries(TOPICS).map(([id, val]) => [val.folder, val])
);

const SYSTEM_PROMPT = `You are the Automated AI Assistant for PNK ASTRO.

STRICT RULES:
1. OUTPUT FORMAT: Provide ONLY the final answer.
2. NO REASONING: Do not include internal thoughts, mentions of "Context", or explanations about your process.
3. CONCISENESS: Give brief, direct answers. 1-3 sentences maximum.
4. LANGUAGE: Reply in the EXACT language the user used (Tamil or English).
5. KNOWLEDGE: Use ONLY the provided Context. If information is not found, say: "I don't have that specific information in my knowledge base."
6. ACCURACY: Never invent information. When unsure, admit lack of knowledge.`;

// Session-based chat memory (limited to prevent token bloat)
const chatMemory = new Map();

// Express setup
const app = express();
app.use(express.json());

// ============================================================================
// UTILITIES
// ============================================================================

/**
 * Expand query with common synonyms and variations
 * (e.g., "price" + "விலை" trigger synonyms)
 */
function expandQuery(query) {
    let expanded = query.toLowerCase();
    
    // Price-related
    if (expanded.includes("விலை") || expanded.includes("price")) {
        expanded += " cost amount payment fees";
    }
    
    // Demo/video
    if (expanded.includes("demo")) {
        expanded += " youtube video tutorial";
    }
    
    // Extract and append numeric values (helps numerology queries)
    const num = expanded.match(/\d+/);
    if (num) {
        expanded += ` number ${num[0]}`;
    }
    
    return expanded;
}

/**
 * Create embedding via Ollama HTTP API
 * Includes retry logic with exponential backoff
 */
async function createEmbedding(text) {
    const maxTries = 3;
    const url = `${OLLAMA_BASE_URL}/api/embeddings`;
    
    for (let attempt = 1; attempt <= maxTries; attempt++) {
        try {
            const response = await axios.post(
                url,
                { model: EMBEDDING_MODEL, prompt: text },
                { timeout: 30000 }
            );
            
            if (response?.data?.embedding) {
                return response.data.embedding;
            }
            throw new Error("No embedding field in response");
            
        } catch (err) {
            console.warn(`⚠️ Embedding attempt ${attempt}/${maxTries} failed: ${err.message}`);
            
            if (attempt === maxTries) {
                console.error(`❌ Embedding failed after ${maxTries} attempts`);
                return null;
            }
            
            // Exponential backoff
            await new Promise(resolve => setTimeout(resolve, 500 * attempt));
        }
    }
}

/**
 * Compute cosine similarity between two embedding vectors
 * (optional utility for debugging/logging)
 */
function cosineSimilarity(a, b) {
    const dotProduct = a.reduce((sum, x, i) => sum + x * b[i], 0);
    const normA = Math.sqrt(a.reduce((sum, x) => sum + x * x, 0));
    const normB = Math.sqrt(b.reduce((sum, x) => sum + x * x, 0));
    return normA && normB ? dotProduct / (normA * normB) : 0;
}

// ============================================================================
// RETRIEVAL
// ============================================================================

/**
 * Retrieve context from ChromaDB using semantic similarity
 * Uses direct HTTP calls to Chroma server API
 * 
 * @param {string} query - User query
 * @param {string} selectedTopic - Optional folder/topic filter (e.g., "numerology")
 * @returns {Promise<Array>} - Relevant document chunks
 */
async function retrieveContext(query, selectedTopic = null) {
    try {
        // 1. Expand query and generate embedding
        const expandedQuery = expandQuery(query);
        const queryEmbedding = await createEmbedding(expandedQuery);
        
        if (!queryEmbedding) {
            console.error("❌ Failed to create query embedding");
            return [];
        }
        
        // 2. Build query payload
        const payload = {
            query_embedding: queryEmbedding,
            n_results: 8,
            include: ["documents", "distances", "metadatas"]
        };
        
        // 3. Apply topic filter if specified
        if (selectedTopic) {
            payload.where = { source_type: selectedTopic };
            console.log(`📍 Filtering by topic: ${selectedTopic}`);
        }
        
        // 4. Query wrapper API
        console.log(`🔗 Querying Chroma via wrapper at ${WRAPPER_BASE_URL}/api/query...`);
        
        const response = await axios.post(
            `${WRAPPER_BASE_URL}/api/query`,
            payload,
            { timeout: 30000 }
        );
        
        if (!response.data) {
            console.error("❌ Empty response from wrapper");
            return [];
        }
        
        // 5. Extract results
        const docs = response.data.documents?.[0] || [];
        const distances = response.data.distances?.[0] || [];
        const metadatas = response.data.metadatas?.[0] || [];
        
        // Log retrieval metrics
        if (docs.length > 0) {
            console.log(`📊 Retrieved ${docs.length} documents (top distance: ${distances[0].toFixed(3)})`);
            docs.forEach((doc, i) => {
                console.log(`   [${i}] dist=${distances[i].toFixed(3)}, source=${metadatas[i]?.source_type || "unknown"}`);
            });
        } else {
            console.warn(`⚠️ No documents retrieved for query: "${query}"`);
        }
        
        // 6. Fallback: if topic-filtered search returns weak results, search globally
        if (selectedTopic && (docs.length === 0 || distances[0] > 1.5)) {
            console.log(`⚠️ Weak topic-filtered results. Searching globally...`);
            delete payload.where;
            try {
                const globalResponse = await axios.post(
                    `${WRAPPER_BASE_URL}/api/query`,
                    payload,
                    { timeout: 30000 }
                );
                return globalResponse.data.documents?.[0] || [];
            } catch (_) {
                return [];
            }
        }
        
        return docs;
        
    } catch (err) {
        console.error(`❌ Retrieval error: ${err.message}`);
        if (err.response?.data) {
            console.error(`   Wrapper response:`, err.response.data);
        }
        return [];
    }
}

// ============================================================================
// LLM RESPONSE GENERATION
// ============================================================================

/**
 * Get AI response using Sarvam API
 * 
 * @param {string} userMessage - User query
 * @param {string} sessionId - Session identifier (for memory)
 * @param {string} selectedTopic - Optional topic filter
 * @returns {Promise<string>} - AI-generated response
 */
async function getCommonAIResponse(userMessage, sessionId = "default", selectedTopic = null) {
    console.log(`\n🔍 Processing: "${userMessage}"`);
    
    // Resolve topic folder
    const topicInfo = TOPICS[selectedTopic] || TOPIC_FOLDER_MAP[selectedTopic];
    const topicFilter = topicInfo?.folder || (typeof selectedTopic === "string" ? selectedTopic : null);
    
    // Retrieve context
    const contextChunks = await retrieveContext(userMessage, topicFilter);
    
    if (!contextChunks || contextChunks.length === 0) {
        console.warn("⚠️ No context retrieved");
        return "I don't have that specific information in my knowledge base. Please contact our support directly.";
    }
    
    // Build message history (keep last ~3 exchanges to save tokens)
    let history = chatMemory.get(sessionId) || [];
    
    const messagesPayload = [
        { role: "system", content: SYSTEM_PROMPT },
        ...history.slice(-6),  // Keep last 3 user/assistant pairs
        {
            role: "user",
            content: `Context:\n${contextChunks.join("\n---\n")}\n\nQuestion: ${userMessage}`
        }
    ];
    
    try {
        // Call Sarvam AI
        console.log(`📡 Calling Sarvam API (${messagesPayload.length} messages)...`);
        const response = await axios.post(
            SARVAM_API_URL,
            {
                model: SARVAM_MODEL,
                messages: messagesPayload,
                temperature: 0.1
            },
            {
                headers: { Authorization: `Bearer ${process.env.SARVAM_API_KEY}` },
                timeout: 30000
            }
        );
        
        let content = response.data?.choices?.[0]?.message?.content || "";
        
        // Clean response
        content = content
            .replace(/<think>[\s\S]*?<\/think>/gi, "")  // Remove reasoning tags
            .replace(/^(ANSWER:|Response:|Output:)/i, "")  // Remove prefixes
            .trim();
        
        // Save to memory
        history.push({ role: "user", content: userMessage });
        history.push({ role: "assistant", content });
        chatMemory.set(sessionId, history.slice(-6));
        
        console.log(`✅ Response sent (${content.length} chars)`);
        return content;
        
    } catch (err) {
        console.error(`❌ Sarvam API error: ${err.message}`);
        if (err.response?.data) {
            console.error(`   Response:`, err.response.data);
        }
        return "Sorry, I'm having trouble connecting to the AI brain. Please try again later.";
    }
}

// ============================================================================
// HTTP ENDPOINT
// ============================================================================

app.post("/chat", async (req, res) => {
    try {
        const { message, sessionId, topic } = req.body;
        
        if (!message) {
            return res.status(400).json({ error: "Message required" });
        }
        
        const reply = await getCommonAIResponse(message, sessionId || req.ip, topic);
        res.json({ reply });
        
    } catch (err) {
        console.error("❌ HTTP endpoint error:", err.message);
        res.status(500).json({ error: "Server error" });
    }
});

// ============================================================================
// TELEGRAM BOT
// ============================================================================

const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, { polling: true });

bot.on("message", async (msg) => {
    if (!msg.text || msg.text.startsWith("/")) return;
    
    try {
        // Show typing indicator
        await bot.sendChatAction(msg.chat.id, "typing");
        
        // Get response
        const reply = await getCommonAIResponse(msg.text, String(msg.chat.id));
        
        // Send reply
        await bot.sendMessage(msg.chat.id, reply, { parse_mode: "Markdown" });
    } catch (err) {
        console.error("❌ Telegram error:", err.message);
        await bot.sendMessage(msg.chat.id, "Sorry, something went wrong. Please try again later.");
    }
});

// ============================================================================
// SERVER STARTUP
// ============================================================================

// Health check endpoint
app.get("/health", async (req, res) => {
    try {
        const wrapperStatus = await axios.get(`${WRAPPER_BASE_URL}/health`, { timeout: 5000 });
        return res.json({
            status: "ok",
            wrapper: wrapperStatus.data,
            embedding_model: EMBEDDING_MODEL,
            sarvam_model: SARVAM_MODEL
        });
    } catch (err) {
        return res.status(503).json({
            status: "error",
            wrapper: { url: WRAPPER_BASE_URL, error: err.message },
            message: "Chroma wrapper is not accessible"
        });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`${"=".repeat(70)}`);
    console.log(`🚀 PNK Astro Bot listening on port ${PORT}`);
    console.log(`📧 HTTP endpoint: POST /chat`);
    console.log(`🏥 Health check: GET /health`);
    console.log(`💬 Telegram bot: ${process.env.TELEGRAM_BOT_TOKEN ? "enabled" : "disabled"}`);
    console.log(`${"=".repeat(70)}`);
});