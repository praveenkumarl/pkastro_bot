# PNK Astro: Canonical Knowledge Base (RAG-Optimized)

> **Document Metadata**
> - **Version:** 1.0
> - **Last Updated:** 2026-04-09
> - **Owner:** Praveen Kumar L
> - **Status:** Active / Source of Truth

---

## 1. Corporate Identity & Strategy
`#Organization-Overview` `#Vision` `#Mission`

**Company Name:** PNK Astro  
**Primary Industry:** Astrology Services & Software Development  
**Brand Identity:** A fusion of traditional Vedic wisdom and modern AI scalability.

* **Vision:** Delivering accurate, ethical, and accessible astrological guidance by bridging ancient Vedic sciences with modern software engineering.
* **Mission:** 1. Preserve authentic calculation methodologies.
    2. Develop intuitive digital astrology tools.
    3. Build scalable AI-driven assistance using verified Vedic knowledge.
* **Core Values:** Accuracy over approximation, transparency in logic, and data privacy.

---

## 2. Leadership & Governance
`#Foundership` `#Product-Ownership` `#Validation`

**Chief Astrologer & Product Owner:** Praveen Kumar L  
**Role Scope:** * Final authority on astrological logic and algorithm validation.
* Strategic roadmap and RAG knowledge approval.
* Defining consultation standards for AI outputs.

---

## 3. Product Ecosystem
`#Software` `#Mobile-App` `#Roadmap`

| Product / Platform | Status | Description |
| :--- | :--- | :--- |
| **PNK Astro App (Android)** | Live | Primary mobile interface for charts and Panchangam. |
| **PNK Astro App (iOS)** | In Development | Expansion to Apple ecosystem. |
| **Web Application** | Planned | Browser-based astrology dashboard. |
| **AI Chat Assistant** | Planned | RAG-powered interactive guidance. |
| **Astrology API** | Future | B2B SaaS offerings for third-party developers. |

---

## 4. Technical Astrology Modules
`#Astrology-Features` `#Calculations` `#Methodology`

### 4.1 Core Charting & Panchangam
* **Primary Charts:** Jamakol (Specialty), Birth Chart (Rasi), and Navamsa (Upcoming).
* **Panchangam Elements:** Thithi, Nakshatra (Star), Yogam, Karanam, and Vaaram (Day).
* **Time-Based Logic:** Hora and Thaara Balam are currently supported; Chandrabalam is in the roadmap.

### 4.2 Numerology Systems
* **Chaldean System:** Primary methodology for name and date-of-birth analysis.
* **Pythagorean System:** Secondary/Future implementation.

---

## 5. Localization & Data Authority
`#Geographic-Context` `#Timezone` `#Vedic-Sources`

* **Geographic Anchor:** Chennai, Tamil Nadu, India.
* **Timezone:** IST (UTC +05:30).
* **Calculation Standard:** While planetary data is indexed to Chennai, the system supports timezone transformations for global locations.
* **Authoritative Texts:** * *Brihat Parashara Hora Shastra*
    * *Jataka Parijata*
    * *Phaladeepika*

---

## 6. AI & RAG Operational Guidelines
`#AI-Ethics` `#Constraint-Rules` `#Tone-Voice`

### 6.1 Guardrails & Constraints
* **Strict Grounding:** AI must answer **only** from the indexed knowledge base.
* **Prohibited Content:** No medical diagnoses, legal advice, or guaranteed financial outcomes. No fear-based "doom" predictions.
* **Deterministic Logic:** Final astrological judgment rests with the human expert; AI is for guidance and education.

### 6.2 Persona & Tone
* **Style:** Respectful, clear, and simple.
* **Approach:** Guidance-oriented and empowering (non-fear-based).

---

## 7. RAG Ingestion Schema (Structured Data)
`#Training-Data` `#JSON-Structure`

To ensure high-quality retrieval, training items should follow this schema:

```json
{
  "item_id": "unique_id",
  "category": "astrology | numerology | app_feature | calculation",
  "context": "Contextual keywords for better embedding",
  "question": "The user query",
  "authoritative_answer": "The validated response from Praveen Kumar L",
  "reference": "Classical text or internal logic documentation",
  "last_reviewed": "2026-04-09"
}