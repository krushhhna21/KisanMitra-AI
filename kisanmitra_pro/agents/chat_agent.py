from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, MAX_HISTORY
from services.weather import get_weather
from database.db import (
    get_farmer, update_farmer_language, get_land_details, get_soil_reports, 
    get_recent_queries, get_latest_sensor_data, get_farmer_intelligence,
    get_soil_history, get_sensor_history, analyze_soil_trend, 
    analyze_sensor_trend, detect_community_risk, get_local_pest_reports,
    analyze_fertilizer_log
)
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
    PHASE 2 IMPLEMENTATION - Comprehensive Farmer Context Builder
    
    Uses Farmer Intelligence Engine to fetch ALL available data:
    - Soil trends (not just latest report)
    - Sensor trends (not just latest reading)
    - Pest alerts (community risk)
    - Fertilizer history
    - Estimated crop stage
    
    Returns formatted context string for system prompt
    """
    lines = []

    # Get comprehensive farmer intelligence
    try:
        intelligence = get_farmer_intelligence(user_id, email)
    except Exception as e:
        print(f"[WARN] Error fetching farmer intelligence: {e}")
        return _build_farmer_context_fallback(user_id, email)

    farmer = intelligence.get('farmer', {})
    lands = intelligence.get('lands', [])
    soil_history = intelligence.get('soil_history', [])
    sensor_history = intelligence.get('sensor_history', [])
    pest_alerts = intelligence.get('pest_alerts', [])
    fertilizer_log = intelligence.get('fertilizer_log', {})

    # --- Farmer Summary ---
    lines.append(f"\n🌾 FARMER: {farmer.get('name', 'Unknown')} ({farmer.get('username', '')})")
    lines.append(f"  Location: {farmer.get('location', 'Not set')}")
    lines.append(f"  Crops registered: {', '.join(farmer.get('crops', []) or ['Not specified'])}")

    # --- Land Details ---
    if lands:
        lines.append("\n🏞️  REGISTERED FIELDS:")
        for i, land in enumerate(lands[:3], 1):
            area = land.get('area_acres', '?')
            crop = land.get('crop_type', '?')
            soil_type = land.get('soil_type', '?')
            district = land.get('district', '?')
            
            # Estimate crop stage based on soil report dates
            crop_stage = _estimate_crop_stage(crop, soil_history)
            
            lines.append(
                f"  Field {i}: {area} acres | Crop: {crop} ({crop_stage}) | "
                f"Soil: {soil_type} | {district}"
            )

    # --- Soil Analysis ---
    if soil_history:
        latest_soil = soil_history[0]
        lines.append("\n🧪 SOIL STATUS (Lab Analysis):")
        
        ph = latest_soil.get('ph', 0)
        n = latest_soil.get('nitrogen_kg_ha', 0)
        p = latest_soil.get('phosphorus_kg_ha', 0)
        k = latest_soil.get('potassium_kg_ha', 0)
        
        lines.append(
            f"  Latest: pH={ph} | N={n} kg/ha | P={p} kg/ha | K={k} kg/ha"
        )
        
        # Soil trend
        soil_trend = analyze_soil_trend(soil_history)
        lines.append(f"  Trend: {soil_trend}")
        
        # Soil recommendations
        soil_alerts = []
        if ph < 5.5:
            soil_alerts.append("🔴 Acidic soil - needs lime")
        elif ph > 8.0:
            soil_alerts.append("🔴 Alkaline soil - needs gypsum")
        if n < 150:
            soil_alerts.append("🟡 Low N - apply urea/DAP")
        if p < 10:
            soil_alerts.append("🟡 Low P - apply SSP")
        if k < 100:
            soil_alerts.append("🟡 Low K - apply MOP")
        
        if soil_alerts:
            lines.append("  Actions: " + " | ".join(soil_alerts))

    # --- Sensor Data (Real-time) ---
    if sensor_history:
        latest_sensor = sensor_history[0]
        lines.append("\n📡 REAL-TIME SENSOR DATA:")
        
        moisture = latest_sensor.get('moisture', 0)
        temp = latest_sensor.get('temperature', 0)
        hours_ago = latest_sensor.get('hours_ago', 0)
        
        lines.append(
            f"  Latest ({hours_ago}h ago): Moisture={moisture}% | Temp={temp}°C | "
            f"pH={latest_sensor.get('ph', '?')}"
        )
        
        # Sensor trend
        sensor_trend = analyze_sensor_trend(sensor_history)
        lines.append(f"  Trend: {sensor_trend}")
        
        # Sensor alerts
        if latest_sensor.get('alerts'):
            for alert in latest_sensor['alerts']:
                lines.append(f"  ⚠️  {alert}")

    # --- Community Pest Risk ---
    if pest_alerts:
        risk_assessment = detect_community_risk(
            farmer.get('location', ''),
            farmer.get('crops', [''])[0] if farmer.get('crops') else '',
            pest_alerts
        )
        if risk_assessment:
            lines.append(f"\n🐛 PEST ALERT: {risk_assessment}")
            
            # List recent pests
            recent_pests = pest_alerts[:3]
            for pest in recent_pests:
                days = _calculate_days_ago_from_dict(pest)
                lines.append(f"  - {pest.get('pest', '?')} on {pest.get('crop', '?')} ({days}d ago in {pest.get('location', '?')})")

    # --- Fertilizer History ---
    if fertilizer_log and fertilizer_log.get('total_applications', 0) > 0:
        lines.append(f"\n📋 FERTILIZER HISTORY:")
        lines.append(f"  Recent applications: {fertilizer_log.get('total_applications', 0)}")
        if fertilizer_log.get('common_fertilizers'):
            ferts = fertilizer_log['common_fertilizers']
            top_ferts = sorted(ferts.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append(f"  Common: {', '.join([f'{f[0]} ({f[1]}x)' for f in top_ferts])}")

    return "\n".join(lines) if lines else ""


def _build_farmer_context_fallback(user_id: int, email: str = "") -> str:
    """
    Fallback context builder if intelligence engine fails
    Uses original simpler approach
    """
    lines = []
    lands = get_land_details(email=email) if email else get_land_details(user_id=user_id)
    if lands:
        lines.append("\n🌾 FARMER'S FIELDS:")
        for i, land in enumerate(lands[:3], 1):
            lines.append(
                f"  Field {i}: {land.get('area_acres', '?')} acres | "
                f"Crop: {land.get('crop_type', '?')} | "
                f"Location: {land.get('village', '?')}, {land.get('district', '?')}"
            )

    reports = get_soil_reports(email=email, limit=1) if email else get_soil_reports(user_id=user_id, limit=1)
    if reports:
        r = reports[0]
        lines.append("\n🧪 LATEST SOIL REPORT:")
        lines.append(
            f"  pH={r.get('ph', '?')} | N={r.get('nitrogen_kg_ha', '?')} | "
            f"Moisture={r.get('moisture_pct', '?')}%"
        )

    return "\n".join(lines)


def _estimate_crop_stage(crop: str, soil_history: list) -> str:
    """
    Estimate crop growth stage based on time since planting
    Inferred from soil report dates (farmer typically does soil test at key stages)
    """
    if not soil_history:
        return "Unknown stage"
    
    days_since_report = soil_history[0].get('days_ago', 999)
    crop_lower = crop.lower() if crop else ""
    
    # Rough stage estimation (varies by crop)
    if days_since_report < 30:
        return "Early growth (0-30d)"
    elif days_since_report < 60:
        return "Mid-season (30-60d)"
    elif days_since_report < 120:
        return "Flowering/Development (60-120d)"
    else:
        return "Late season (>120d)"


def _calculate_days_ago_from_dict(obj: dict) -> int:
    """Helper to get days_ago from dict"""
    return obj.get('days_ago', 0) if isinstance(obj.get('days_ago'), int) else 0





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
    
    system_prompt = f"""You are KisanMitra AI 🌾 - An expert agronomist advisor.

🔴 **LANGUAGE RULE (CRITICAL)**: You MUST respond ONLY in {lang_name}. NEVER mix languages. Every single word must be in {lang_name}.

FARMER'S COMPLETE SITUATION:
{crops_info}
{farmer_context}

WEATHER (for {location}):
{weather['summary']}

YOUR REASONING PROCESS (follow STRICTLY):
1. ✅ Analyze farmer's soil status - Check trends (improving/declining)
2. ✅ Analyze sensor readings - Check patterns and alerts
3. ✅ Check community pest risk - Warn if outbreak nearby
4. ✅ Recall fertilizer history - What has farmer used before?
5. ✅ Generate SPECIFIC advice - Not generic, tailored to THIS farmer's situation

RESPONSE FORMAT (strict):
- Keep MINIMAL - 3-4 sentences max
- Use emojis: 🌾🚜🧪💧🐛⚠️
- If action needed: EXACT dosage + timing + method
- Only list schemes/subsidies if explicitly asked
- If weather risk: warn about timing
- Reply ONLY in {lang_name}"""
    
    messages = [{"role": "system", "content": system_prompt}] + get_history(user_id) + [{"role": "user", "content": message}]

    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=messages,
            max_tokens=1000,  # Increased from 500 to prevent truncation
            temperature=0.7
        )
        reply = res.choices[0].message.content.strip()
        return reply, intent, language
    except Exception as e:
        print(f"Chat agent error: {e}")
        return "🙏 Maafi kijiye, thodi dikkat hai. Thodi der baad try karein.", "other", "hi"
