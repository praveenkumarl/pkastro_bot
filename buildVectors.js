import axios from "axios";
import fs from "fs";
import path from "path";
import csv from "csv-parser";
import dotenv from "dotenv";
import { Readable } from "stream";

dotenv.config();

const OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings";
const MODEL = "nomic-embed-text";
const DOCS_DIR = "./docs"; // Local text files
const CONCURRENT_REQUESTS = 3;

// --- 1. LOCAL DOCS PROCESSING ---
function createLocalChunks(content, fileName, folderCategory) {
    // Split by double newline to separate the context-rich blocks
    return content.split(/\n\s*\n/).map(para => {
        const text = para.trim();
        
        // Regex to extract [Category: ... | Keywords: ...]
        const metaRegex = /^\[Category:\s*(.*?)\s*\|\s*Keywords:\s*(.*?)\s*\]/;
        const match = text.match(metaRegex);

        if (match) {
            // If explicit metadata is found in the text, extract it
            return {
                type: "local_doc",
                category: match[1].trim(), // Extracted category (e.g., 'வாஸ்து (Vastu)')
                keywords: match[2].trim(), // Extracted keywords
                source: fileName,
                text: text // Keep full text including tags for better vector context
            };
        } else {
            // Fallback to original logic: folder name as category, empty keywords
            return {
                type: "local_doc",
                category: folderCategory.toLowerCase(),
                keywords: "",
                source: fileName,
                text: text
            };
        }
    }).filter(c => c.text.length > 20);
}

// --- 2. GOOGLE SHEETS PROCESSING ---
function createCSVChunks(row, type) {
    const text = Object.values(row).join(" ").trim();
    // Added 'keywords' field for consistent JSON schema across all chunk types
    return text ? [{ type: `sheet_${type}`, category: "general", keywords: "", text }] : [];
}

async function createEmbedding(text) {
    try {
        const res = await axios.post(OLLAMA_URL, { model: MODEL, prompt: text });
        return res.data.embedding;
    } catch (e) { return null; }
}

async function parseCSV(csvText) {
    return new Promise((resolve) => {
        const rows = [];
        Readable.from(csvText).pipe(csv()).on("data", r => rows.push(r)).on("end", () => resolve(rows));
    });
}

async function build() {
    let allChunks = [];

    // STEP A: Fetch and Process Google Sheets
    const urls = (process.env.GOOGLE_SHEET_CSV_URLS || "").split(",").filter(u => u.trim());
    for (let url of urls) {
        console.log("⬇ Fetching Sheet:", url);
        try {
            const res = await axios.get(url);
            const rows = await parseCSV(res.data);
            rows.forEach(row => allChunks.push(...createCSVChunks(row, "google")));
        } catch (err) {
            console.error("❌ Failed to fetch sheet:", err.message);
        }
    }

    // STEP B: Process Local Docs (UPDATED FOR SUBFOLDERS & INTERNAL METADATA)
    if (fs.existsSync(DOCS_DIR)) {
        const folders = fs.readdirSync(DOCS_DIR, { withFileTypes: true })
            .filter(dirent => dirent.isDirectory())
            .map(dirent => dirent.name);

        for (const folder of folders) {
            const folderPath = path.join(DOCS_DIR, folder);
            const files = fs.readdirSync(folderPath).filter(f => f.endsWith(".txt"));

            files.forEach(file => {
                console.log(`📖 Reading Local [${folder}]: ${file}`);
                const content = fs.readFileSync(path.join(folderPath, file), "utf-8");
                // Pass folder name as the fallback category
                allChunks.push(...createLocalChunks(content, file, folder));
            });
        }
    } else {
        console.log(`⚠️ Docs folder not found at ${DOCS_DIR}`);
    }

    // STEP C: Generate Embeddings
    console.log(`🧠 Embedding ${allChunks.length} total chunks...`);
    const vectors = [];
    
    for (let i = 0; i < allChunks.length; i += CONCURRENT_REQUESTS) {
        const batch = allChunks.slice(i, i + CONCURRENT_REQUESTS);
        console.log(`⚡ Embedding batch ${i + 1} to ${i + batch.length} of ${allChunks.length}`);
        
        const results = await Promise.all(batch.map(async (chunk, idx) => {
            const embedding = await createEmbedding(chunk.text);
            return embedding ? { id: `v_${i + idx}`, ...chunk, embedding } : null;
        }));
        
        vectors.push(...results.filter(v => v !== null));
    }

    fs.writeFileSync("vectors.json", JSON.stringify(vectors, null, 2));
    console.log("✅ Hybrid vectors.json created successfully with internal metadata and folder fallbacks!");
}

build();
