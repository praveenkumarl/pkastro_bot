import axios from "axios";
import fs from "fs";
import path from "path";
import csv from "csv-parser";
import dotenv from "dotenv";
import { Readable } from "stream";

dotenv.config();

const OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings";
const MODEL = "nomic-embed-text"; // Your embedding model
const DOCS_DIR = "./docs"; 
const CONCURRENT_REQUESTS = 3;

// --- 1. LOCAL DOCS WITH SLIDING WINDOW CHUNKING ---
function createLocalChunks(content, fileName, folderCategory) {
    const finalChunks = [];
    const blocks = content.split(/\n\s*\n/); // Still split by major paragraphs first

    for (const block of blocks) {
        const text = block.trim();
        if (text.length < 20) continue;

        // Extract metadata if it exists
        const metaRegex = /^\[Category:\s*(.*?)\s*\|\s*Keywords:\s*(.*?)\s*\]/;
        const match = text.match(metaRegex);

        const category = match ? match[1].trim() : folderCategory.toLowerCase();
        const keywords = match ? match[2].trim() : "";

        // --- THE SLIDING WINDOW LOGIC ---
        // We split the block into words. If it's too long, we chunk it with overlap.
        const maxWords = 150; // Max size of a chunk
        const overlap = 30;   // How many words to overlap between chunks
        const words = text.split(/\s+/);

        if (words.length <= maxWords) {
            // If the paragraph is short, keep it as one chunk
            finalChunks.push({ type: "local_doc", category, keywords, source: fileName, text });
        } else {
            // If it's long, slide a window over it to prevent Boundary Loss
            for (let i = 0; i < words.length; i += (maxWords - overlap)) {
                const chunkText = words.slice(i, i + maxWords).join(" ");
                finalChunks.push({ type: "local_doc", category, keywords, source: fileName, text: chunkText });
                
                // Stop if we've reached the end of the words
                if (i + maxWords >= words.length) break;
            }
        }
    }
    return finalChunks;
}

// --- 2. IMPROVED GOOGLE SHEETS PROCESSING ---
function createCSVChunks(row, type) {
    // Maps keys to values: "Name: John, Role: Developer" instead of "John Developer"
    const text = Object.entries(row)
        .filter(([_, value]) => value && value.trim() !== "") 
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ");
        
    return text ? [{ type: `sheet_${type}`, category: "general", keywords: "", source: "Google Sheet", text }] : [];
}

async function createEmbedding(text) {
    try {
        const res = await axios.post(OLLAMA_URL, { model: MODEL, prompt: text });
        return res.data.embedding;
    } catch (e) { 
        // Added error logging so silent failures don't ruin your database
        console.error(`❌ Embedding failed for chunk: ${text.substring(0, 30)}...`, e.message);
        return null; 
    }
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

    // STEP B: Process Local Docs 
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
                allChunks.push(...createLocalChunks(content, file, folder));
            });
        }
    } else {
        console.log(`⚠️ Docs folder not found at ${DOCS_DIR}`);
    }

    // STEP C: Generate Embeddings
    console.log(`🧠 Found and chunked ${allChunks.length} total pieces of data. Generating Embeddings...`);
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
    console.log("✅ Hybrid vectors.json created successfully with sliding-window chunks!");
}

build();
