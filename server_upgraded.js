import express from "express";
import OpenAI from "openai";
import dotenv from "dotenv";
import cors from "cors";
import TelegramBot from "node-telegram-bot-api";
import axios from "axios";

dotenv.config();

const app = express();
app.use(express.json());
app.use(cors());

/* ===========================
   SARVAM SETUP
=========================== */
const openai = new OpenAI({
  apiKey: process.env.SARVAM_API_KEY,
  baseURL: "https://api.sarvam.ai/v1",
});

/* ===========================
   GOOGLE SHEET (CSV FETCH)
=========================== */
let companyContext = "Loading company data...";
let lastFetchTime = 0;
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

async function getCompanyData() {
  const now = Date.now();
  if (now - lastFetchTime < CACHE_DURATION && companyContext !== "") {
    return companyContext;
  }
  try {
    const response = await fetch(process.env.GOOGLE_SHEET_CSV_URL);
    const csvText = await response.text();
    const rows = csvText.split("\n").map(row => row.replace(/,/g, " | "));
    companyContext = rows.join("\n");
    lastFetchTime = now;
    console.log("✅ Google Sheet data refreshed");
    return companyContext;
  } catch (error) {
    console.error("Google Sheet Fetch Error:", error);
    return "Company data unavailable.";
  }
}

/* ===========================
   SEMANTIC SEARCH (LOCAL DOCS)
=========================== */
async function getLocalChunks(message) {
  try {
    const res = await axios.post("http://localhost:5005/ask_local", {
      question: message
    });
    return res.data.answer; // array of chunks or null
  } catch (err) {
    console.error("Local Semantic Search Error:", err.message);
    return null;
  }
}

async function answerWithContext(question, chunks) {
  const context = chunks.join("\n\n");
  const prompt = `Answer the question based on the following information:

Information:
${context}

Question: ${question}
Answer:`;
  
  const response = await openai.chat.completions.create({
    model: "sarvam-m",
    messages: [{ role: "user", content: prompt }],
  });
  return response.choices[0].message.content;
}

/* ===========================
   EXPRESS API
=========================== */
app.post("/chat", async (req, res) => {
  try {
    const { message } = req.body;

    // 1️⃣ Try local semantic search first
    const localChunks = await getLocalChunks(message);
    if (localChunks && localChunks.length > 0) {
      const answer = await answerWithContext(message, localChunks);
      return res.json({ reply: answer });
    }

    // 2️⃣ Fallback to Google Sheet + OpenAI
    const sheetData = await getCompanyData();
    const response = await openai.chat.completions.create({
      model: "sarvam-m",
      messages: [
        {
          role: "system",
          content: `You are a helpful astrology assistant.
If user asks about company details, answer ONLY using below company data.
Company Data:
${sheetData}`
        },
        { role: "user", content: message }
      ],
    });
    res.json({ reply: response.choices[0].message.content });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: "Something went wrong" });
  }
});

/* ===========================
   TELEGRAM BOT
=========================== */
const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, {
  polling: true,
});
console.log("🤖 Telegram bot started...");

bot.on("message", async (msg) => {
  const chatId = msg.chat.id;
  const userMessage = msg.text;
  if (!userMessage) return;

  try {
    // 1️⃣ Local semantic search
    const localChunks = await getLocalChunks(userMessage);
    if (localChunks && localChunks.length > 0) {
      const answer = await answerWithContext(userMessage, localChunks);
      await bot.sendMessage(chatId, answer);
      return;
    }

    // 2️⃣ Fallback to Google Sheet + OpenAI
    const sheetData = await getCompanyData();
    const response = await openai.chat.completions.create({
      model: "sarvam-m",
      messages: [
        {
          role: "system",
          content: `You are a helpful astrology assistant.
If user asks about company details, answer ONLY using below company data.
Company Data:
${sheetData}`
        },
        { role: "user", content: userMessage }
      ],
    });
    const reply = response.choices[0].message.content;
    await bot.sendMessage(chatId, reply);
  } catch (error) {
    console.error("Telegram Error:", error);
    await bot.sendMessage(chatId, "Sorry, something went wrong.");
  }
});

/* ===========================
   START SERVER
=========================== */
app.listen(process.env.PORT || 3000, () => {
  console.log(`🚀 Server running on port ${process.env.PORT || 3000}`);
});
