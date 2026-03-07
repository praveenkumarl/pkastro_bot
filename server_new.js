require("dotenv").config();
const fs = require("fs");
const path = require("path");
const axios = require("axios");
const TelegramBot = require("node-telegram-bot-api");

// ======================
// ENV VARIABLES
// ======================
const SARVAM_API_KEY = process.env.SARVAM_API_KEY;
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const PORT = process.env.PORT || 3000;

if (!SARVAM_API_KEY || !TELEGRAM_BOT_TOKEN) {
  console.error("Missing environment variables");
  process.exit(1);
}

// ======================
// LOAD ASTROLOGY DOCUMENTS
// ======================
const DOCS_FOLDER = path.join(__dirname, "docs");

function loadDocuments() {
  let allText = "";
  const files = fs.readdirSync(DOCS_FOLDER);
  files.forEach(file => {
    if (file.endsWith(".txt")) {
      const content = fs.readFileSync(path.join(DOCS_FOLDER, file), "utf8");
      allText += "\n" + content;
    }
  });
  return allText;
}

const FULL_TEXT = loadDocuments();

function splitIntoChunks(text, chunkSize = 600) {
  const chunks = [];
  for (let i = 0; i < text.length; i += chunkSize) {
    chunks.push(text.substring(i, i + chunkSize));
  }
  return chunks;
}

const CHUNKS = splitIntoChunks(FULL_TEXT);

// ======================
// RELEVANT ASTROLOGY CONTEXT
// ======================
function getRelevantContext(question) {
  const planets = [
    "சூரியன்",
    "சந்திரன்",
    "செவ்வாய்",
    "புதன்",
    "குரு",
    "சுக்கிரன்",
    "சனி",
    "ராகு",
    "கேது"
  ];

  const matchedPlanet = planets.find(p => question.includes(p));
  if (!matchedPlanet) return CHUNKS.slice(0, 2).join("\n");

  const regex = new RegExp(
    `${matchedPlanet}[\\s\\S]*?(?=சூரியன்|சந்திரன்|செவ்வாய்|புதன்|குரு|சுக்கிரன்|சனி|ராகு|கேது|$)`,
    "g"
  );
  const match = FULL_TEXT.match(regex);
  return match && match.length > 0 ? match[0] : CHUNKS.slice(0, 2).join("\n");
}

// ======================
// GOOGLE SHEET FETCH
// ======================
// New
const GOOGLE_SHEET_CSV_URL = process.env.GOOGLE_SHEET_CSV_URL;

if (!GOOGLE_SHEET_CSV_URL) {
  console.error("Missing GOOGLE_SHEET_CSV_URL in .env");
  process.exit(1);
}

async function getCompanyData() {
  try {
    const response = await axios.get(GOOGLE_SHEET_CSV_URL, { timeout: 5000 });
    if (!response.data) throw new Error("Empty sheet data");
    return response.data;
  } catch (error) {
    console.error("Google Sheet Error:", error.message);
    return "Company data unavailable.";
  }
}

// ======================
// ASTROLOGY KEYWORD CHECK
// ======================
function isAstrologyQuestion(text) {
  const astrologyKeywords = [
    "சூரியன்",
    "சந்திரன்",
    "செவ்வாய்",
    "புதன்",
    "குரு",
    "சுக்கிரன்",
    "சனி",
    "ராகு",
    "கேது",
    "காரகம்",
    "ஜாதகம்"
  ];
  return astrologyKeywords.some(word => text.includes(word));
}

// ======================
// TELEGRAM BOT
// ======================
const bot = new TelegramBot(TELEGRAM_BOT_TOKEN, { polling: true });

bot.on("message", async (msg) => {
  const chatId = msg.chat.id;
  const userMessage = msg.text?.trim();
  if (!userMessage) return;

  try {
    let finalMessages = [];

    // ===== Astrology Detection =====
    if (isAstrologyQuestion(userMessage)) {
      const contextData = getRelevantContext(userMessage);

      finalMessages = [
        {
          role: "system",
          content: `You are a Tamil astrology expert.
Answer ONLY using the provided astrology text.
If the answer is not present, reply "தகவல் இல்லை".`
        },
        {
          role: "user",
          content: `Astrology Data:\n${contextData}\n\nQuestion:\n${userMessage}`
        }
      ];
    }

    // ===== Company Detection =====
    else if (userMessage.toLowerCase().match(/company|office|contact|phone|address|email|location/i)) {
      const sheetData = await getCompanyData();

      finalMessages = [
        {
          role: "system",
          content: "You are a company assistant. Answer ONLY using the provided company data."
        },
        {
          role: "user",
          content: `Company Data:\n${sheetData}\n\nQuestion:\n${userMessage}`
        }
      ];
    }

    // ===== General =====
    else {
      finalMessages = [
        {
          role: "system",
          content: "You are a helpful assistant."
        },
        {
          role: "user",
          content: userMessage
        }
      ];
    }

    // ===== Call SARVAM API =====
    const response = await axios.post(
      "https://api.sarvam.ai/v1/chat/completions",
      {
        model: "sarvam-m",
        messages: finalMessages,
        temperature: 0.3
      },
      {
        headers: {
          Authorization: `Bearer ${SARVAM_API_KEY}`,
          "Content-Type": "application/json"
        }
      }
    );

    const reply = response.data.choices[0].message.content;
    await bot.sendMessage(chatId, reply);

  } catch (error) {
    console.error("Telegram Error:", error.response?.data || error.message);
    await bot.sendMessage(chatId, "Sorry, something went wrong.");
  }
});

console.log("Bot is running...");