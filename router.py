"""
PNK Astro Bot — Query Router

Detects user intent and returns:
  - topic_filter : Optional[str]  folder name to narrow ChromaDB search
  - direct_context : Optional[str]  pre-built answer text (bypasses vector search)

Intent categories
-----------------
NUMEROLOGY   — query contains a number → exact JSON lookup + topic filter
PRICING      — price / cost / fees / விலை keywords
COMPANY      — software / features / demo / contact keywords
NAKSHATRA    — star name or "nakshatra" keyword
JAMAKOL      — jamakol / horary keywords
NAADI        — naadi / transit keywords
PLANETS      — planet name keywords
GENERAL      — everything else (no filter)
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# ── Load numerology data once at import time ────────────────────────────────

_NUMEROLOGY: dict = {}   # keyed by int number → entry dict

_JSON_FILES = [
    "./docs/numerology/numerology_upgraded.json",
    "./docs/numerology/numerology_1_108.json",
]


def _load_numerology() -> None:
    for path in _JSON_FILES:
        p = Path(path)
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data:
                num = entry.get("number")
                if isinstance(num, int) and num not in _NUMEROLOGY:
                    _NUMEROLOGY[num] = entry
        except Exception as exc:
            log.warning("Could not load numerology file %s: %s", path, exc)

    log.info("Numerology index loaded: %d entries", len(_NUMEROLOGY))


_load_numerology()


# ── Keyword maps ────────────────────────────────────────────────────────────

# Short greetings that have no knowledge-base answer
_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|helo|greetings|good\s?(morning|afternoon|evening|night)|வணக்கம்|நமஸ்காரம்)[\s!.]*$",
    re.IGNORECASE,
)

# Bot introduction queries
_BOT_INTRO_PATTERNS = re.compile(
    r"(who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+yourself|what\s+can\s+you\s+do|"
    r"what\s+is\s+your\s+purpose|about\s+yourself)",
    re.IGNORECASE,
)

_PRICING_KW = {
    "price", "prices", "cost", "costs", "fees", "fee", "charge",
    "payment", "pay", "rate", "rates", "amount", "விலை", "கட்டணம்",
}
_COMPANY_KW = {
    "software", "app", "application", "feature", "features", "demo",
    "contact", "address", "phone", "email", "whatsapp", "youtube",
    "pnk", "pnkastro", "company", "product", "module", "download",
    "buy", "purchase", "trial",
    # owner / identity queries
    "owner", "founder", "who", "owns", "created", "developed", "built",
    "team", "staff", "support", "website", "pkastro",
}
_SOFTWARE_KW = {
    "software", "app", "application", "feature", "features", "module", "modules",
    "jamakol prasannam", "panchangam", "hora", "lagna", "horoscope", "natal",
    "numerology grid", "tarot", "compatibility", "karakam reference",
    "pkastro", "pnkastro", "download", "demo", "trial", "tool", "tools",
    "மென்பொருள்", "அம்சங்கள்",
}
_BHAVAM_KW = {
    "bhavam", "bhava", "bhaava", "baava", "house", "houses",
    "1st house", "2nd house", "3rd house", "4th house", "5th house",
    "6th house", "7th house", "8th house", "9th house", "10th house",
    "11th house", "12th house",
    "லக்னம்", "பாவம்", "பாவகம்", "இல்லம்",
}
_NAKSHATRA_KW = {
    "nakshatra", "star", "nakshatram", "asterism",
    "ashwini", "bharani", "krittika", "rohini", "mrigashira", "ardra",
    "punarvasu", "pushya", "ashlesha", "magha", "purvaphalguni",
    "uttaraphalguni", "hasta", "chitra", "swati", "vishakha", "anuradha",
    "jyeshtha", "mula", "purvashadha", "uttarashadha", "shravana",
    "dhanishta", "shatabhisha", "purvabhadra", "uttarabhadra", "revati",
    # Tamil names
    "அசுவினி", "பரணி", "கார்த்திகை", "ரோகிணி", "மிருகசீரிடம்",
    "திருவாதிரை", "புனர்பூசம்", "பூசம்", "ஆயில்யம்", "மகம்",
    "பூரம்", "உத்திரம்", "அஸ்தம்", "சித்திரை", "சுவாதி",
    "விசாகம்", "அனுஷம்", "கேட்டை", "மூலம்", "பூராடம்",
    "உத்திராடம்", "திருவோணம்", "அவிட்டம்", "சதயம்",
    "பூரட்டாதி", "உத்திரட்டாதி", "ரேவதி",
}
_JAMAKOL_KW = {
    "jamakol", "horary", "arudam", "prashna", "prasna",
    "ஜமாகோல்", "அருடம்", "ப்ரஸ்னம்",
}
_NAADI_KW = {
    "naadi", "nadi", "transit", "kochar", "brigu", "brighu",
    "நாடி", "கோட்சாரம்",
}
_PLANET_KW = {
    "sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn",
    "rahu", "ketu", "சூரியன்", "சந்திரன்", "செவ்வாய்", "புதன்",
    "குரு", "சுக்கிரன்", "சனி", "ராகு", "கேது",
    "surya", "chandra", "mangal", "budha", "guru", "shukra", "shani",
    # karaka (significator) keywords
    "karaka", "karakam", "காரகம்", "காரகன்",
    # Tamil family/body karaka terms
    "தந்தை", "தாய்", "சகோதரன்", "சகோதரி", "மனைவி", "கணவன்",
    "புத்திரன்", "மகள்",
    # English equivalents
    "father", "mother", "brother", "sister", "wife", "husband", "child",
    "significator", "signification",
}


# ── Intent detection ────────────────────────────────────────────────────────

def _tokens(text: str) -> set:
    """Lowercase token set from query."""
    return set(re.findall(r"[\u0B80-\u0BFF]+|[a-z0-9]+", text.lower()))


def _detect_intent(query: str) -> str:
    """Return one of: NUMEROLOGY, PRICING, SOFTWARE, COMPANY, BHAVAM, NAKSHATRA, JAMAKOL, NAADI, PLANETS, GENERAL"""
    toks = _tokens(query)

    # Numerology: any standalone number mentioned
    if re.search(r"\b\d+\b", query):
        return "NUMEROLOGY"

    if toks & _PRICING_KW:
        return "PRICING"
    if toks & _SOFTWARE_KW:
        return "SOFTWARE"
    if toks & _COMPANY_KW:
        return "COMPANY"
    if toks & _BHAVAM_KW:
        return "BHAVAM"
    if toks & _NAKSHATRA_KW:
        return "NAKSHATRA"
    if toks & _JAMAKOL_KW:
        return "JAMAKOL"
    if toks & _NAADI_KW:
        return "NAADI"
    if toks & _PLANET_KW:
        return "PLANETS"

    return "GENERAL"


# ── Numerology direct lookup ────────────────────────────────────────────────

def _numerology_direct(query: str) -> Optional[str]:
    """
    If query contains a number that exists in the numerology index,
    return a pre-formatted context string (no embedding needed).
    Returns None if no match.
    """
    nums = [int(n) for n in re.findall(r"\b\d+\b", query)]
    for n in nums:
        entry = _NUMEROLOGY.get(n)
        if entry:
            # Format a rich context block
            lines = [
                f"Numerology Number {n} | எண் {n}",
                f"Ruling planet: {entry.get('ruling_planet_eng','')} ({entry.get('ruling_planet_tam','')})",
                f"Nature (EN): {entry.get('general_nature_eng','')}",
                f"Nature (TA): {entry.get('general_nature_tam','')}",
                f"Name suitability (EN): {entry.get('name_suitability_eng','')}",
                f"Name suitability (TA): {entry.get('name_suitability_tam','')}",
                f"Business (EN): {entry.get('business_suitability_eng','')}",
                f"Lucky colors: {entry.get('lucky_colors_eng','')} | {entry.get('lucky_colors_tam','')}",
                f"Lucky gems: {entry.get('lucky_gems_eng','')} | {entry.get('lucky_gems_tam','')}",
                f"Lucky dates: {', '.join(str(d) for d in entry.get('lucky_dates', []))}",
                f"Health: {entry.get('health_tendencies_eng','')}",
                f"Profession (EN): {entry.get('profession_eng','')}",
                f"Profession (TA): {entry.get('profession_tam','')}",
                f"Marriage compatible: {', '.join(str(c) for c in entry.get('marriage_compatibility_numbers', []))}",
                f"Key insight (EN): {entry.get('methodology_specific_insight_eng','')}",
                f"Key insight (TA): {entry.get('methodology_specific_insight_tam','')}",
            ]
            return "\n".join(l for l in lines if l.split(": ", 1)[-1].strip())
    return None


# ── Public route function ───────────────────────────────────────────────────

_INTENT_TO_FOLDER = {
    "NUMEROLOGY": "numerology",
    "PRICING":    "company_detail",
    "COMPANY":    "company_detail",
    "SOFTWARE":   "software",
    "BHAVAM":     "bhavam",
    "NAKSHATRA":  "nakshatram",
    "JAMAKOL":    "jamakol",
    "NAADI":      "naadi",
    "PLANETS":    "planets",
    "GENERAL":    None,
}


def route_query(query: str, explicit_topic: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine retrieval strategy for a query.

    Parameters
    ----------
    query : str
        Raw user message.
    explicit_topic : str, optional
        Topic override passed by the caller (e.g. from Telegram menu).

    Returns
    -------
    topic_filter : Optional[str]
        Folder name to filter ChromaDB search, or None for global search.
    direct_context : Optional[str]
        Pre-built context string that bypasses vector search entirely,
        or None if normal retrieval should proceed.
    """
    # Caller override takes priority for topic filter
    if explicit_topic:
        return explicit_topic, None

    # Bot introduction queries — no retrieval needed
    if _BOT_INTRO_PATTERNS.search(query):
        log.info("Bot intro query detected — returning direct response")
        return None, (
            "I am PNK Astro — an automated AI assistant powered by Vedic astrology, "
            "numerology, and traditional Tamil astrological knowledge. I can help you with:\n"
            "• Nakshatra (star) analysis\n"
            "• Numerology readings (numbers 1-108)\n"
            "• Planet karakas and their significance\n"
            "• Jamakol (horary astrology)\n"
            "• Naadi predictions and transit forecasts\n"
            "• Company services and software information\n\n"
            "Ask me anything about your birth chart, numerology, or astrology!"
        )

    # Short-circuit greetings — no retrieval needed
    if _GREETING_PATTERNS.match(query.strip()):
        log.info("Greeting detected — returning direct response")
        return None, "The user sent a greeting. Reply warmly and briefly, then ask how you can help with astrology or numerology."

    intent = _detect_intent(query)
    log.info("Query intent: %s", intent)

    topic_filter = _INTENT_TO_FOLDER.get(intent)
    direct_context: Optional[str] = None

    # For numerology: attempt exact lookup first
    if intent == "NUMEROLOGY":
        direct_context = _numerology_direct(query)
        if direct_context:
            log.info("Numerology direct hit — skipping vector search")

    return topic_filter, direct_context
