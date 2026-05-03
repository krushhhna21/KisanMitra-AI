from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, MAX_HISTORY
from services.weather import get_weather
from database.db import get_farmer, update_farmer_language, get_land_details, get_soil_reports, get_recent_queries, get_latest_sensor_data
import threading

_groq_client = None
_groq_lock = threading.Lock()

def _get_groq():
    global _groq_client
    if _groq_client is None:
        with _groq_lock:
            if _groq_client is None:
                _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client

def get_history(user_id: int) -> list:
    """Fetch chat history directly from the database to retain context across sessions."""
    queries = get_recent_queries(user_id, limit=MAX_HISTORY)
    history = []
    for q in queries:
        # Add user message
        if q.get('message'):
            history.append({"role": "user", "content": q['message']})
        # Add AI response
        if q.get('response'):
            history.append({"role": "assistant", "content": q['response']})
    return history


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
    """Detect Hindi vs Marathi vs English with better accuracy"""
    # Count script characters
    marathi_chars = sum(1 for c in message if '\u0900' <= c <= '\u097F')  # Devanagari
    english_chars = sum(1 for c in message if c.isalpha() and ord(c) < 128)  # ASCII letters
    
    # Specific Marathi indicators
    marathi_words = ["माझ्या", "करा", "आहे", "काय", "कसे", "टाकावे", "आली", "झाली", "नाही", "एकर", "गव्ह"]
    if any(w in message for w in marathi_words):
        return "mr"
    
    # If Marathi script detected and is significant
    if marathi_chars > len(message) * 0.3:  # >30% Marathi characters
        return "mr"
    
    # If Hindi script detected and is significant
    if marathi_chars > 3 and marathi_chars <= len(message) * 0.3:  # Devanagari but not majority Marathi
        return "hi"
    
    # If mostly English/ASCII
    if english_chars > len(message) * 0.6:  # >60% English letters
        return "en"
    
    # Default based on content
    if marathi_chars > english_chars:
        return "mr"
    elif english_chars > 0:
        return "en"
    else:
        return "hi"


def _build_farmer_context(user_id: int, email: str = "") -> str:
    """
    Build a rich farmer-profile context block from land details and soil reports.
    This is injected into the system prompt so the AI gives fully personalised answers.
    """
    lines = []

    # --- Land parcels ---
    lands = get_land_details(email=email) if email else get_land_details(user_id=user_id)
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
    reports = get_soil_reports(email=email, limit=1) if email else get_soil_reports(user_id=user_id, limit=1)
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
        lines.append("\n🧪 LATEST SOIL REPORT (Lab Test):")
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

    # --- Latest real-time sensor data (IoT) ---
    sensors = get_latest_sensor_data(email=email, user_id=user_id, limit=1) if email or user_id else []
    if sensors:
        s = sensors[0]
        sensor_time = s.get('created_at', 'Unknown')
        lines.append("\n📡 LATEST REAL-TIME SENSOR DATA (IoT):")
        lines.append(
            f"  Soil Moisture: {s.get('moisture', '?')}% | "
            f"pH: {s.get('ph', '?')} | "
            f"Temperature: {s.get('temperature', '?')}°C | "
            f"EC: {s.get('ec', '?')} | "
            f"N: {s.get('nitrogen', '?')} | "
            f"P: {s.get('phosphorus', '?')} | "
            f"K: {s.get('potassium', '?')}"
        )
        lines.append(f"  Recorded: {sensor_time}")
        
        # Real-time alerts
        sensor_flags = []
        moisture = s.get('moisture', 0)
        sensor_ph = s.get('ph', 0)
        
        if moisture < 20:
            sensor_flags.append("⚠️ Soil moisture critically low — irrigate immediately")
        elif moisture > 70:
            sensor_flags.append("⚠️ Soil moisture too high — risk of waterlogging")
        
        if sensor_ph and (sensor_ph < 5.5 or sensor_ph > 8.5):
            sensor_flags.append(f"⚠️ Soil pH {sensor_ph} is off-balance")
        
        if sensor_flags:
            lines.append("  " + " | ".join(sensor_flags))

    return "\n".join(lines) if lines else ""


def generate_pest_advisory(pest: str, crop: str, location: str) -> str:
    """
    Generate a short, actionable broadcast message for a pest outbreak.
    """
    system_prompt = f"""You are KisanMitra AI 🌾.
A severe outbreak of '{pest}' on '{crop}' has been reported by multiple farmers in {location}.
Generate an EMERGENCY BROADCAST MESSAGE to alert nearby farmers.

Requirements:
- Start with a clear RED ALERT 🚨 emoji.
- Explain the threat briefly.
- Provide 2-3 immediate STRICT precautions.
- Provide the EXACT fertilizers/pesticides with dosage to be used.
- Reply primarily in simple Hindi (or Hinglish) so all Indian farmers can understand.
- Keep it under 150 words. Do NOT use markdown headers, just simple bold text and bullet points.
"""
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Alert! Outbreak of {pest} on {crop} in {location}. Generate advisory."}]
    
    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=messages,
            max_tokens=400,
            temperature=0.5
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"Pest advisory generation error: {e}")
        return f"🚨 *ALERT: {pest} on {crop}* detected in your area!\n\nPlease take immediate precautions. Spray recommended pesticides immediately and consult local experts."


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
    email    = farmer.get("email", "")

    # Save detected language
    update_farmer_language(user_id, language)

    crops_info     = f"\nFarmer ki fasalein: {', '.join(crops)}" if crops else ""
    farmer_context = _build_farmer_context(user_id, email=email)

    # Language-specific instruction
    lang_map = {
        "en": "English",
        "hi": "Hindi (use Devanagari script)",
        "mr": "Marathi (use Devanagari script)"
    }
    lang_name = lang_map.get(language, "English")
    
    system_prompt = f"""You are KisanMitra AI 🌾.
Expert AI farming assistant for Indian farmers.

🔴 **CRITICAL INSTRUCTION: You MUST respond ONLY in {lang_name}. Do NOT mix languages.**

Follow these strict reasoning steps to generate your response:
1. Check the farmer's registered land and crop details.
2. Check any other pest queries submitted by the farmer.
3. Check the chat history for past fertilizers used and analyze soil reports.
4. Calculate and recommend the EXACT amount of fertilizer to be sprayed based on records.

Format rules:
- Keep it MINIMAL and direct to the point. NO lengthy paragraphs or fluff.
- Use short bullet points.
- Include emojis (🌾🚜🧪🐛💧) to make reading interesting.
- Reply ONLY in {lang_name} - every single word must be in this language.
- Never translate or use other languages.

Farmer's Data Context:
{crops_info}
{farmer_context}
Live weather for {location}:
{weather['summary']}"""

    messages = [{"role": "system", "content": system_prompt}] + get_history(user_id) + [{"role": "user", "content": message}]

    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        reply = res.choices[0].message.content.strip()
        return reply, intent, language
    except Exception as e:
        print(f"Chat agent error: {e}")
        return "🙏 Maafi kijiye, thodi dikkat hai. Thodi der baad try karein.", "other", "hi"
