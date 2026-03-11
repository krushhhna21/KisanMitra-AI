from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, MAX_HISTORY
from services.weather import get_weather
from database.db import get_farmer, update_farmer_language

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
    elif any(w in msg for w in ["fasal", "crop", "beej", "seed", "khad", "fertilizer", "ugao", "lagao"]):
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

def chat(user_id: int, message: str) -> tuple:
    """
    Returns: (reply, intent, language)
    """
    farmer = get_farmer(user_id)
    lat = farmer.get("lat", 18.4088)
    lon = farmer.get("lon", 76.5604)
    location = farmer.get("location", "Latur, Maharashtra")
    crops = farmer.get("crops", [])

    weather = get_weather(lat, lon, location)
    intent = detect_intent(message)
    language = detect_language(message)

    # Save detected language
    update_farmer_language(user_id, language)

    crops_info = f"\nFarmer ki fasalein: {', '.join(crops)}" if crops else ""

    system_prompt = f"""You are KisanMitra AI 🌾 — Har khet ka saathi (Every farm's companion).
Expert AI farming assistant for Indian farmers, Maharashtra focus.

Personality: Trusted elder brother / village agronomist. Warm, caring, practical.
Use simple Hindi/Marathi/English. Emojis: 🌱💧☀️🐛

Expertise: Crops, pests, weather decisions, fertilizers (organic first), govt schemes, soil health, market prices.

Agent reasoning steps:
1. Understand what farmer needs
2. Check weather context
3. Consider current season (March — Rabi harvest ending, Zaid starting)
4. Give clear actionable advice in 3-5 bullet points
5. End with one warm encouraging line

Language rule: Detect farmer's language and ALWAYS reply in same language.
Max 250 words. Bullet points for clarity.
{crops_info}
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
