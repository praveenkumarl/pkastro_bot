import express from "express";
import axios from "axios";
import dotenv from "dotenv";
import TelegramBot from "node-telegram-bot-api";
import { ChromaClient } from "chromadb";

dotenv.config();

const app = express();
app.use(express.json());

/* ===============================
   CONFIG & SYSTEM PROMPT
================================= */
const OLLAMA_BASE_URL = "http://127.0.0.1:11434";
// FIX 1: Added ':latest' to match your Ollama local tag exactly
const EMBEDDING_MODEL = "paraphrase-multilingual:latest"; 
const SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions";

const chroma = new ChromaClient({ host: "127.0.0.1", port: 8000 });

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
2. NO REASONING: Do not include internal thoughts or mentions of "Context".
3. CONCISENESS: Give brief, direct answers.
4. LANGUAGE: Always reply in the EXACT language the user used (Tamil or English).
5. KNOWLEDGE: Use ONLY the provided Context. If not found, say: "I don't have that specific information in my knowledge base."`;

const chatMemory = new Map();

/* ===============================
   UTILITIES
================================= */
function normalizeText(text) {
    if (!text) return "";
    return text.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, "").replace(/\s+/g, " ").trim();
}

function expandQuery(query) {
    let q = query.toLowerCase();
    if (q.includes("விலை") || q.includes("price")) q += " cost amount payment fees";
    if (q.includes("demo")) q += " youtube video tutorial";
    const num = q.match(/\d+/);
    if (num) q += ` number ${num[0]}`; // Helps catch the specific number
    return q;
}

async function createEmbedding(text) {
    const response = await axios.post(`${OLLAMA_BASE_URL}/api/embeddings`, {
        model: EMBEDDING_MODEL,
        prompt: text
    });
    return response.data.embedding;
}

/* ===============================
   FIXED RETRIEVAL (STRICT FOLDER + NUMERIC FILTER)
================================= */
async function retrieveContext(query, selectedTopic = null) {
    try {
        const expandedString = expandQuery(query);
        const queryEmbedding = await createEmbedding(expandedString);
        const collection = await chroma.getCollection({ name: "langchain" });
        
        let queryOptions = {
            queryEmbeddings: [queryEmbedding],
            nResults: 3
        };

        // Improved Numerology Filter
        if (selectedTopic === "numerology") {
            const numMatch = query.match(/\d+/);
            if (numMatch) {
                // We use the "number_val" we just added in Python
                queryOptions.where = {
                    "$and": [
                        { "source_type": "numerology" },
                        { "number_val": { "$eq": numMatch[0] } }
                    ]
                };
            } else {
                queryOptions.where = { "source_type": "numerology" };
            }
        } else if (selectedTopic) {
            queryOptions.where = { "source_type": selectedTopic };
        }

        let results = await collection.query(queryOptions);
        
        // Safety check to prevent "undefined" errors
        let docs = (results.documents && results.documents[0]) ? results.documents[0] : [];
        let dists = (results.distances && results.distances[0]) ? results.distances[0] : [];
        let bestDist = dists.length > 0 ? dists[0] : 999; 

        // If no results or match is too weak (> 1.5)
        if (selectedTopic && (docs.length === 0 || bestDist > 1.5)) {
            console.log(`⚠️ Weak match in ${selectedTopic} (Dist: ${bestDist.toFixed(2)}). Fallback...`);
            delete queryOptions.where; // Search entire database
            results = await collection.query(queryOptions);
            docs = results.documents[0] || [];
        }

        return docs;
    } catch (err) {
        console.error("Retrieval Error:", err.message);
        return [];
    }
}

/* ===============================
   CENTRAL AI LOGIC (WITH MEMORY)
================================= */
async function getCommonAIResponse(userMessage, sessionId = "default", selectedTopic = null) {
    console.log(`\n--- 🔍 REQUEST: ${userMessage} ---`);

    const topicInfo = TOPICS[selectedTopic] || TOPIC_FOLDER_MAP[selectedTopic];
    const topicFolderFilter = topicInfo?.folder || (typeof selectedTopic === 'string' ? selectedTopic : null);

    const contextChunks = await retrieveContext(userMessage, topicFolderFilter);

    if (!contextChunks || contextChunks.length === 0) {
        return "I don't have that specific information in my knowledge base. Please contact our support directly.";
    }

    let history = chatMemory.get(sessionId) || [];
    const hasTopicShift = contextChunks[0].includes("[SYSTEM NOTE]");

    const messagesPayload = [
        { role: "system", content: SYSTEM_PROMPT },
        ...history.slice(-4), // Keep last 2 exchanges to save tokens
        {
            role: "user",
            content: hasTopicShift 
                ? `🚨 TOPIC SHIFT DETECTED. User is asking about a different category.\nContext:\n${contextChunks.join("\n\n")}\n\nQuestion: ${userMessage}`
                : `Context:\n${contextChunks.join("\n\n")}\n\nQuestion: ${userMessage}`
        }
    ];

    try {
        const response = await axios.post(SARVAM_API_URL, {
            model: "sarvam-m",
            messages: messagesPayload,
            temperature: 0.1
        }, {
            headers: { Authorization: `Bearer ${process.env.SARVAM_API_KEY}` }
        });

        let cleanContent = response.data.choices[0].message.content
            .replace(/<think>[\s\S]*?<\/think>/gi, '')
            .trim();

        if (cleanContent.includes("ANSWER:")) {
            cleanContent = cleanContent.split("ANSWER:")[1].trim();
        }

        // Save exchange to memory
        history.push({ role: "user", content: userMessage });
        history.push({ role: "assistant", content: cleanContent });
        chatMemory.set(sessionId, history.slice(-6)); 

        return cleanContent;

    } catch (err) {
        console.error("AI Error:", err.response?.data || err.message);
        return "Sorry, I am having trouble connecting to the AI brain. Please try again later.";
    }
}

/* ===============================
   INTERFACES
================================= */
app.post("/chat", async (req, res) => {
    try {
        const { message, sessionId, topic } = req.body;
        const reply = await getCommonAIResponse(message, sessionId || req.ip, topic);
        res.json({ reply });
    } catch (e) {
        res.status(500).json({ error: "Server error" });
    }
});

const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, { polling: true });
bot.on("message", async (msg) => {
    if (!msg.text || msg.text.startsWith('/')) return;
    const reply = await getCommonAIResponse(msg.text, msg.chat.id);
    bot.sendMessage(msg.chat.id, reply, { parse_mode: "Markdown" });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 PNK Astro Bot running on port ${PORT}`));