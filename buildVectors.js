import axios from "axios";
import fs from "fs";
import csv from "csv-parser";
import dotenv from "dotenv";
import { Readable } from "stream";

dotenv.config();

async function createEmbedding(text) {
  const response = await axios.post("http://localhost:11434/api/embeddings", {
    model: "nomic-embed-text",
    prompt: text
  });

  return response.data.embedding;
}

async function fetchCSV(url) {
  const response = await axios.get(url);
  return response.data;
}

async function parseCSV(csvText) {
  return new Promise((resolve, reject) => {
    const rows = [];
    const stream = Readable.from(csvText);

    stream
      .pipe(csv())
      .on("data", (row) => rows.push(row))
      .on("end", () => resolve(rows))
      .on("error", reject);
  });
}

async function build() {
  const urls = [];

  if (process.env.GOOGLE_SHEET_CSV_URL)
    urls.push(process.env.GOOGLE_SHEET_CSV_URL);

  if (process.env.GOOGLE_SHEET_CSV_URLS) {
    const extra = process.env.GOOGLE_SHEET_CSV_URLS.split(",");
    urls.push(...extra);
  }

  console.log("Found", urls.length, "sheets");

  let allRows = [];

  for (let url of urls) {
    console.log("Fetching:", url);
    const csvText = await fetchCSV(url);
    const rows = await parseCSV(csvText);
    allRows.push(...rows);
  }

  const vectors = [];

  for (let row of allRows) {
    const text = Object.values(row).join(" | ");
    const embedding = await createEmbedding(text);

    vectors.push({
      text,
      embedding
    });

    console.log("Embedded:", text);
  }

  fs.writeFileSync("vectors.json", JSON.stringify(vectors, null, 2));
  console.log("✅ Vector file created with", vectors.length, "entries");
}

build();
