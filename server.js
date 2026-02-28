import express from "express";
import OpenAI from "openai";
import dotenv from "dotenv";
import cors from "cors";
import TelegramBot from "node-telegram-bot-api";

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

  // Use cached data if not expired
  if (now - lastFetchTime < CACHE_DURATION && companyContext !== "") {
    return companyContext;
  }

  try {
    const response = await fetch(process.env.GOOGLE_SHEET_CSV_URL);
    const csvText = await response.text();

    // Convert CSV to readable text
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

// Append company signature to bot responses
function appendSignature(text) {
  const botName = process.env.BOT_NAME || "PK Astro Bot";
  const signature = `\n\nThanks/Regards\n${botName} (on behalf of PERIYANAYAKI ASTRO SOLUTIONS)`;
  // If text already ends with the signature, don't append again
  if (typeof text === "string" && text.trim().endsWith(signature.trim())) {
    return text;
  }
  return (text || "") + signature;
}

/* ===========================
   EXPRESS API
=========================== */

app.post("/chat", async (req, res) => {
  try {
    const { message } = req.body;

    const sheetData = await getCompanyData();

    const response = await openai.chat.completions.create({
      model: "sarvam-m",
      messages: [
        {
          role: "system",
          content: `You are the helpful astrology assistant.
If user asks about company details, answer ONLY using below company data.

Company Data:
${sheetData}`
        },
        { role: "user", content: message }
      ],
    });

    res.json({
      reply: appendSignature(response.choices[0].message.content),
    });

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
    const sheetData = await getCompanyData();

    const response = await openai.chat.completions.create({
      model: "sarvam-m",
      messages: [
        {
          role: "system",
          content: `You are the administrative assistant for PERIYANAYAKI ASTRO SOLUTIONS. You are a helpful astrology assistant as well.
If user asks about company details, answer ONLY using below company data.

Company Data:
${sheetData}`
        },
        { role: "user", content: userMessage }
      ],
    });

    const reply = appendSignature(response.choices[0].message.content);

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
