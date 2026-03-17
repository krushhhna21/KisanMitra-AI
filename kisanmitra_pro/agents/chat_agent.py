from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, MAX_HISTORY
from services.weather import get_weather
from database.db import get_farmer, update_farmer_language, get_land_details, get_soil_reports

groq_client = Groq(api_key=GROQ_API_KEY)

# In-memory conversation history
_sessions = {}

def get_history(user_id: int) -> list:
    if user_id not in _sessions:
        _sessions[user_id] = []
    return _sessions[user_id]

def add_to_history(user_id: int, role: str, content: str):
    h = get_history(user_id)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        _sessions[user_id] = h[-MAX_HISTORY:]

def detect_intent(message: str) -> str:
    """Detect what farmer is asking about"""
    msg = message.lower()
    if any(w in msg for w in ["keeda", "keet", "bug", "pest", "rog", "bimari", "disease", "pila", "sukh"]):
        return "pest"
    elif any(w in msg for w in ["mausam", "barish", "weather", "paani", "sinchai"]):
        return "weather"
    elif any(w in msg for w in ["bhav", "price", "mandi", "rate", "bazar"]):
        return "mandi"
    elif any(w in msg for w in ["yojana", "scheme", "pm-kisan", "bima", "sarkar"]):
        return "scheme"
    elif any(w in msg for w in ["mitti", "soil", "ph", "nitrogen", "khad", "urvara", "fertilizer"]):
        return "soil"
    elif any(w in msg for w in ["fasal", "crop", "beej", "seed", "ugao", "lagao"]):
        return "crop"
    return "other"

def detect_language(message: str) -> str:
    """Detect Hindi vs Marathi vs English"""
    marathi_words = ["माझ्या", "करा", "आहे", "काय", "कसे", "टाकावे", "आली", "झाली", "नाही"]
    if any(w in message for w in marathi_words):
        return "mr"
    hindi_chars = sum(1 for c in message if '\u0900' <= c <= '\u097F')
    if hindi_chars > 3:
        return "hi"
    return "en"


def _build_farmer_context(user_id: int) -> str:
    """
    Build a rich farmer-profile context block from land details and soil reports.
    This is injected into the system prompt so the AI gives fully personalised answers.
    """
    lines = []

    # --- Land parcels ---
    lands = get_land_details(user_id=user_id)
    if lands:
        lines.append("\n🌾 FARMER'S REGISTERED FIELDS:")
        for i, land in enumerate(lands[:3], 1):
            lines.append(
                f"  Field {i}: {land.get('area_acres', '?')} acres | "
                f"Crop: {land.get('crop_type', '?')} | "
                f"Soil type: {land.get('soil_type', '?')} | "
                f"Village: {land.get('village', '?')}, {land.get('district', '?')}, {land.get('state', '?')}"
            )

    # --- Latest soil report ---
    reports = get_soil_reports(user_id=user_id, limit=1)
    if reports:
        r = reports[0]
        ph    = r.get('ph', 0)
        n_val = r.get('nitrogen_kg_ha', 0)
        p_val = r.get('phosphorus_kg_ha', 0)
        k_val = r.get('potassium_kg_ha', 0)
        om    = r.get('organic_matter_pct', 0)
        mc    = r.get('moisture_pct', 0)
        ec    = r.get('ec_ds_m', 0)
        rec   = r.get('recommendation', '')
        lines.append("\n🧪 LATEST SOIL REPORT:")
        lines.append(
            f"  pH={ph} | N={n_val} kg/ha | P={p_val} kg/ha | K={k_val} kg/ha | "
            f"Organic Matter={om}% | Moisture={mc}% | EC={ec} dS/m"
        )
        if rec:
            # Include a short snippet of the previous recommendation as context
            lines.append(f"  Previous recommendation: {rec[:200]}")

        # Derive quick soil-health flags for the AI
        flags = []
        if ph < 5.5:
            flags.append("soil is acidic — may need lime")
        elif ph > 8.0:
            flags.append("soil is alkaline — may need gypsum or sulphur")
        if n_val < 150:
            flags.append("nitrogen is low — consider urea/DAP top-dressing")
        if p_val < 10:
            flags.append("phosphorus is low — consider SSP/DAP")
        if k_val < 100:
            flags.append("potassium is low — consider MOP/SOP")
        if om < 0.5:
            flags.append("organic matter very low — apply FYM/compost")
        if flags:
            lines.append("  ⚠️ Soil health alerts: " + "; ".join(flags))

    return "\n".join(lines) if lines else ""


def chat(user_id: int, message: str) -> tuple:
    """
    Returns: (reply, intent, language)
    """
    farmer = get_farmer(user_id)
    lat      = farmer.get("lat", 18.4088)
    lon      = farmer.get("lon", 76.5604)
    location = farmer.get("location", "Latur, Maharashtra")
    crops    = farmer.get("crops", [])

    weather  = get_weather(lat, lon, location)
    intent   = detect_intent(message)
    language = detect_language(message)

    # Save detected language
    update_farmer_language(user_id, language)

    crops_info     = f"\nFarmer ki fasalein: {', '.join(crops)}" if crops else ""
    farmer_context = _build_farmer_context(user_id)

    system_prompt = f"""You are KisanMitra AI 🌾 — Har khet ka saathi (Every farm's companion).
Expert AI farming assistant for Indian farmers, Maharashtra focus.

Personality: Trusted elder brother / village agronomist. Warm, caring, practical.
Use simple Hindi/Marathi/English. Emojis: 🌱💧☀️🐛

Expertise: Crops, pests, weather decisions, fertilizers (organic first), govt schemes, soil health, market prices.

Agent reasoning steps:
1. Understand what farmer needs
2. Check weather + their personal field/soil data context below
3. Consider current season (March — Rabi harvest ending, Zaid starting)
4. Give PERSONALISED actionable advice referencing their actual soil values and field data when relevant
5. End with one warm encouraging line

Language rule: Detect farmer's language and ALWAYS reply in same language.
Max 250 words. Bullet points for clarity.
{crops_info}
{farmer_context}
Live weather for {location}:
{weather['summary']}"""

    add_to_history(user_id, "user", message)
    messages = [{"role": "system", "content": system_prompt}] + get_history(user_id)

    try:
        res = groq_client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        reply = res.choices[0].message.content.strip()
        add_to_history(user_id, "assistant", reply)
        return reply, intent, language
    except Exception as e:
        print(f"Chat agent error: {e}")
        return "🙏 Maafi kijiye, thodi dikkat hai. Thodi der baad try karein.", "other", "hi"
