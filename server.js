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
    // Support multiple CSV URLs (tabs) in env var GOOGLE_SHEET_CSV_URLS (comma-separated)
    const raw = process.env.GOOGLE_SHEET_CSV_URLS || process.env.GOOGLE_SHEET_CSV_URL || "";
    const urls = raw.split(',').map(s => s.trim()).filter(Boolean);
    if (urls.length === 0) {
      throw new Error('No Google Sheet CSV URL(s) configured in GOOGLE_SHEET_CSV_URLS/GOOGLE_SHEET_CSV_URL');
    }

    const parts = await Promise.all(urls.map(async (u, idx) => {
      const r = await fetch(u);
      const txt = await r.text();
      const rows = txt.split('\n').map(row => row.replace(/,/g, ' | ')).join('\n');
      // Add a clear header for each sheet/tab
      return `--- Sheet ${idx + 1} ---\n${rows}`;
    }));

    companyContext = parts.join('\n\n');
    lastFetchTime = now;
    console.log('✅ Google Sheet data refreshed (merged', urls.length, 'sheets)');
    return companyContext;

  } catch (error) {
    console.error('Google Sheet Fetch Error:', error);
    return 'Company data unavailable.';
  }
}

// Append company signature to bot responses
function appendSignature(text) {
  const botName = process.env.BOT_NAME || "PK Astro Bot";
  const signature = `\n\nThanks/Regards\n${botName}\n(on behalf of PERIYANAYAKI ASTRO SOLUTIONS)`;
  // If text already ends with the signature, don't append again
  if (typeof text === "string" && text.trim().endsWith(signature.trim())) {
    return text;
  }
  return (text || "") + signature;
}

// Convert simple Markdown emphasis to HTML for Telegram HTML parse_mode.
function mdToHtml(text) {
  if (!text) return "";
  // Escape HTML
  let out = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Code blocks ```lang
  out = out.replace(/```([\s\S]*?)```/g, (m, p1) => `<pre><code>${p1.replace(/&/g,'&amp;')}</code></pre>`);
  // Inline code `code`
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold **text** or __text__
  out = out.replace(/\*\*([\s\S]+?)\*\*/g, '<b>$1</b>');
  out = out.replace(/__([\s\S]+?)__/g, '<b>$1</b>');

  // Italic *text* or _text_
  out = out.replace(/\*([^\*\s][\s\S]*?)\*/g, '<i>$1</i>');
  out = out.replace(/_([^_\s][\s\S]*?)_/g, '<i>$1</i>');

  return out;
}

/* ===========================
   SYSTEM PROMPT
=========================== */

const SYSTEM_PROMPT_TEMPLATE = `You are the administrative and astrology assistant for PERIYANAYAKI ASTRO SOLUTIONS.

CRITICAL RULES FOR YOUR RESPONSES:
1. Be extremely brief, concise, and direct. 
2. Answer ONLY the exact question asked. Do NOT provide extra details unless requested.
3. MATCH THE USER'S LANGUAGE: 
   - If the user asks in English, reply strictly and purely in English.
   - If the user asks in Tamil, reply strictly and purely in Tamil (Tamil script).
4. DO NOT mix languages or use brackets like "சூரியன் (Sun)". Translate the data smoothly into the language the user is speaking.
5. If the user asks about company, training details or planet karaka answer ONLY using the data below.

Data:
`;

/* ===========================
   EXPRESS API
=========================== */

app.post("/chat", async (req, res) => {
  try {
    const { message } = req.body;

    const sheetData = await getCompanyData();

    const response = await openai.chat.completions.create({
      model: "sarvam-m",
      temperature: 0.3, // Enforces factual, concise answers
      max_tokens: 200,  // Prevents the bot from rambling
      messages: [
        {
          role: "system",
          content: SYSTEM_PROMPT_TEMPLATE + sheetData
        },
        { role: "user", content: message }
      ],
    });

    const replyText = appendSignature(response.choices[0].message.content);
    const replyHtml = mdToHtml(replyText);

    // If client asked for HTML (either via body.html=true or ?format=html), return HTML in `reply`.
    const wantsHtml = req.body && req.body.html === true || (req.query && req.query.format === 'html');

    if (wantsHtml) {
      res.json({ reply: replyHtml, reply_html: replyHtml, reply_text: replyText, is_html: true });
    } else {
      res.json({ reply: replyText, reply_html: replyHtml, is_html: false });
    }

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
      temperature: 0.3, // Enforces factual, concise answers
      max_tokens: 200,  // Prevents the bot from rambling
      messages: [
        {
          role: "system",
          content: SYSTEM_PROMPT_TEMPLATE + sheetData
        },
        { role: "user", content: userMessage }
      ],
    });

    const reply = appendSignature(response.choices[0].message.content);
    const replyHtml = mdToHtml(reply);

    await bot.sendMessage(chatId, replyHtml, { parse_mode: 'HTML', disable_web_page_preview: true });

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