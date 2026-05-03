"""
soil_fusion.py — Hybrid Soil Restoration Orchestrator
=====================================================
Merges 3 sources into one GoI Soil Health Card response:
  1. XGBoost fertilizer model   (sensor data → dosages)
  2. AgroMonitoring satellite   (NDVI + soil moisture)
  3. Plantix/Groq Vision        (photo → disease/deficiency)

All output is language-aware (Hindi/Marathi/English).
Every external call has a fallback — demo never breaks.
"""

from config import GROQ_API_KEY, GROQ_CHAT_MODEL
from services.soil_xgboost import get_fertilizer_recommendation, format_soil_health_card
from services.agromonitoring import get_satellite_summary
from services.plantix import analyze_plant_health
import threading

# Lazy Groq client — initialized on first use to avoid httpx version conflicts
_groq_client = None
_groq_lock = threading.Lock()

def _get_groq():
    global _groq_client
    if _groq_client is None:
        with _groq_lock:
            if _groq_client is None:
                from groq import Groq
                _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def generate_unified_soil_report(
    n: float,
    p: float,
    k: float,
    ph: float,
    moisture: float = 40.0,
    ec: float = 0.5,
    lat: float = 18.4088,
    lon: float = 76.5604,
    location: str = "Maharashtra",
    image_bytes: bytes = None,
    farmer_name: str = "Kisan",
    crop_type: str = "",
    language: str = "hi",
) -> dict:
    """
    Generate a unified soil report merging all three data sources.

    Parameters
    ----------
    n, p, k, ph, moisture, ec : float — sensor readings
    lat, lon, location        : farmer's location
    image_bytes               : optional crop photo (raw bytes)
    farmer_name               : for Soil Health Card header
    crop_type                 : current crop
    language                  : 'hi', 'mr', 'en'

    Returns
    -------
    dict with keys:
        xgboost_result    : dict from soil_xgboost
        satellite_result  : dict from agromonitoring
        vision_result     : dict from plantix (or None if no photo)
        formatted_card    : str — full GoI Soil Health Card text
        ai_summary        : str — Groq-generated natural language summary
    """
    # ── Source 1: XGBoost Fertilizer Model ────────────────────────────────
    xgboost_result = get_fertilizer_recommendation(n, p, k, ph, moisture, ec)

    # ── Source 2: Satellite Data ──────────────────────────────────────────
    satellite_result = get_satellite_summary(lat, lon, location)

    # ── Source 3: Visual Diagnosis (only if photo provided) ───────────────
    vision_result = None
    if image_bytes:
        vision_result = analyze_plant_health(image_bytes, language=language)

    # ── Merge into unified card ───────────────────────────────────────────
    formatted_card = _format_unified_card(
        xgboost_result, satellite_result, vision_result,
        farmer_name, location, crop_type
    )

    # ── Generate AI summary in farmer's language ──────────────────────────
    ai_summary = _generate_ai_summary(
        xgboost_result, satellite_result, vision_result,
        crop_type, language
    )

    return {
        "xgboost_result": xgboost_result,
        "satellite_result": satellite_result,
        "vision_result": vision_result,
        "formatted_card": formatted_card,
        "ai_summary": ai_summary,
    }


def generate_quick_soil_card(
    n: float, p: float, k: float, ph: float,
    moisture: float, ec: float,
    lat: float, lon: float, location: str,
    farmer_name: str = "Kisan",
    language: str = "hi",
) -> str:
    """
    Quick card (no photo) — for /soilcard command.
    Uses XGBoost + Satellite only.
    Returns formatted text ready for Telegram.
    Includes comprehensive fallbacks to ensure response.
    """
    try:
        xgboost_result = get_fertilizer_recommendation(n, p, k, ph, moisture, ec)
    except Exception as e:
        print(f"[soil_fusion] XGBoost error: {e}, using fallback")
        xgboost_result = {
            "urea_kg_ha": max(0, 250 - n) / 0.46,
            "dap_kg_ha": max(0, 25 - p) / 0.46,
            "mop_kg_ha": max(0, 150 - k) / 0.60,
            "lime_kg_ha": 0,
            "gypsum_kg_ha": 0,
            "soil_health_grade": "C — Average 🟠",
            "score": 50,
            "restoration_steps": ["Apply balanced fertilizers", "Monitor soil moisture"],
            "model_used": "Emergency Fallback",
        }
    
    try:
        satellite_result = get_satellite_summary(lat, lon, location)
    except Exception as e:
        print(f"[soil_fusion] Satellite error: {e}, using fallback")
        satellite_result = {
            "ndvi": None,
            "ndvi_status": "Data unavailable",
            "ndvi_trend": "→ Stable",
            "soil_moisture": moisture,
            "soil_temp": None,
            "data_source": "Local Data Only",
            "raw_summary": f"📍 Field: {location}\n📊 Soil Moisture: {moisture}%",
        }

    try:
        card = _format_unified_card(
            xgboost_result, satellite_result, None,
            farmer_name, location
        )
    except Exception as e:
        print(f"[soil_fusion] Format error: {e}, creating basic card")
        card = f"""╔══════════════════════════════════════════╗
║  🇮🇳  SOIL HEALTH CARD — KisanMitra AI   ║
╠══════════════════════════════════════════╣
║  Farmer : {farmer_name:<30} ║
║  Location: {location:<29} ║
╠══════════════════════════════════════════╣
║  📊 EMERGENCY REPORT (errors occurred)   ║
╚══════════════════════════════════════════╝"""

    try:
        summary = _generate_ai_summary(
            xgboost_result, satellite_result, None,
            "", language
        )
    except Exception as e:
        print(f"[soil_fusion] AI summary error: {e}, using basic summary")
        summary = "Soil analysis data collected. Check the card details above for fertilizer recommendations."

    return f"{card}\n\n💡 *AI Summary:*\n{summary}"


# ─── Card Formatter ─────────────────────────────────────────────────────────

def _format_unified_card(
    xgb: dict, sat: dict, vis: dict | None,
    farmer_name: str, location: str, crop_type: str = ""
) -> str:
    """Format unified GoI Soil Health Card."""

    # Section 1: Sensor Data (from XGBoost input context)
    # Add safety checks for missing data
    if not xgb:
        xgb = {"soil_health_grade": "N/A", "score": 0, "restoration_steps": []}
    if not sat:
        sat = {"ndvi": None, "ndvi_status": "N/A", "ndvi_trend": "→ Stable", "soil_moisture": None}
    
    grade = xgb.get("soil_health_grade", "N/A")
    score = xgb.get("score", 0)

    # Section 2: Vision (if available)
    vision_section = ""
    if vis and vis.get("disease", "None") != "None":
        vision_section = (
            f"╠══════════════════════════════════════════╣\n"
            f"║  🔬 VISUAL DIAGNOSIS                     ║\n"
            f"║  Disease  : {vis.get('disease', 'Unknown')[:28]:<28} ║\n"
            f"║  Severity : {vis.get('severity', 'N/A'):<28} ║\n"
            f"║  Confidence: {int(vis.get('confidence', 0)*100)}%{' '*24}║\n"
            f"║  💊 {vis.get('treatment', 'N/A')[:36]:<36} ║\n"
        )
    elif vis and vis.get("deficiency", "None") != "None":
        vision_section = (
            f"╠══════════════════════════════════════════╣\n"
            f"║  🔬 VISUAL DIAGNOSIS                     ║\n"
            f"║  Deficiency: {vis.get('deficiency', 'Unknown')[:27]:<27} ║\n"
            f"║  💊 {vis.get('treatment', 'N/A')[:36]:<36} ║\n"
        )
    elif vis:
        vision_section = (
            f"╠══════════════════════════════════════════╣\n"
            f"║  🔬 VISUAL DIAGNOSIS                     ║\n"
            f"║  ✅ No disease/deficiency detected       ║\n"
        )

    # Section 3: Satellite
    ndvi = sat.get("ndvi")
    ndvi_text = f"{ndvi:.2f}" if ndvi is not None else "N/A"
    ndvi_status = sat.get("ndvi_status", "N/A")
    ndvi_trend = sat.get("ndvi_trend", "→ Stable")
    soil_moist = sat.get("soil_moisture")
    soil_moist_text = f"{soil_moist:.3f} m³/m³" if soil_moist is not None else "N/A"

    # Section 4: Restoration steps
    steps = xgb.get("restoration_steps", [])
    steps_text = "\n".join([f"   {i+1}. {s}" for i, s in enumerate(steps)])

    # Build the card
    crop_line = f"║  Crop  : {crop_type:<31} ║\n" if crop_type else ""

    card = f"""╔══════════════════════════════════════════╗
║  🇮🇳  SOIL HEALTH CARD — KisanMitra AI   ║
╠══════════════════════════════════════════╣
║  Farmer : {farmer_name:<30} ║
║  Location: {location:<29} ║
{crop_line}╠══════════════════════════════════════════╣
║  📊 SOIL HEALTH GRADE                    ║
║  Grade: {grade:<33} ║
║  Score: {score}/100                            ║
╠══════════════════════════════════════════╣
║  🧪 NUTRIENT LEVELS (Sensor Data)        ║
║  ➤ Urea   : {xgb['urea_kg_ha']:>6} kg/ha              ║
║  ➤ DAP    : {xgb['dap_kg_ha']:>6} kg/ha              ║
║  ➤ MOP    : {xgb['mop_kg_ha']:>6} kg/ha              ║
║  ➤ Lime   : {xgb['lime_kg_ha']:>6} kg/ha              ║
║  ➤ Gypsum : {xgb['gypsum_kg_ha']:>6} kg/ha              ║
║  Model   : {xgb['model_used']:<30} ║
{vision_section}╠══════════════════════════════════════════╣
║  🛰️ SATELLITE HEALTH                     ║
║  NDVI    : {ndvi_text:<30} ║
║  Status  : {ndvi_status:<30} ║
║  Trend   : {ndvi_trend:<30} ║
║  Moisture: {soil_moist_text:<30} ║
║  Source  : {sat.get('data_source', 'N/A'):<30} ║
╠══════════════════════════════════════════╣
║  🌱 RESTORATION ROADMAP                  ║
╚══════════════════════════════════════════╝
{steps_text}"""

    return card


# ─── AI Summary Generator ───────────────────────────────────────────────────

def _generate_ai_summary(
    xgb: dict, sat: dict, vis: dict | None,
    crop_type: str, language: str
) -> str:
    """
    Use Groq LLM to generate a natural-language summary
    in the farmer's language, combining all data sources.
    """
    lang_map = {
        "hi": "Reply in simple Hindi (Hinglish OK). Use farming terms a village farmer understands.",
        "mr": "Reply in simple Marathi. Use farming terms a Maharashtra farmer understands.",
        "en": "Reply in simple English. Use farming terms an Indian farmer understands.",
    }
    lang_instruction = lang_map.get(language, lang_map["hi"])

    # Build context from all sources
    context_parts = []

    # XGBoost
    context_parts.append(f"Soil Grade: {xgb.get('soil_health_grade', 'N/A')}, Score: {xgb.get('score', 0)}/100")
    context_parts.append(f"Fertilizer Rx: Urea {xgb['urea_kg_ha']}kg/ha, DAP {xgb['dap_kg_ha']}kg/ha, MOP {xgb['mop_kg_ha']}kg/ha")
    if xgb.get('lime_kg_ha', 0) > 0:
        context_parts.append(f"Lime needed: {xgb['lime_kg_ha']}kg/ha")
    if xgb.get('gypsum_kg_ha', 0) > 0:
        context_parts.append(f"Gypsum needed: {xgb['gypsum_kg_ha']}kg/ha")
    context_parts.append(f"Restoration steps: {'; '.join(xgb.get('restoration_steps', []))}")

    # Satellite
    ndvi = sat.get("ndvi")
    if ndvi is not None:
        context_parts.append(f"Satellite NDVI: {ndvi:.2f} ({sat.get('ndvi_status', '')}), Trend: {sat.get('ndvi_trend', '')}")
    if sat.get("soil_moisture") is not None:
        context_parts.append(f"Satellite soil moisture: {sat['soil_moisture']:.3f} m³/m³")

    # Vision
    if vis:
        if vis.get("disease", "None") != "None":
            context_parts.append(f"Photo diagnosis: {vis['disease']} (Severity: {vis['severity']}, Confidence: {int(vis['confidence']*100)}%)")
            context_parts.append(f"Treatment: {vis['treatment']}")
        elif vis.get("deficiency", "None") != "None":
            context_parts.append(f"Nutrient deficiency detected: {vis['deficiency']}")
            context_parts.append(f"Treatment: {vis['treatment']}")
        else:
            context_parts.append("Photo analysis: No disease or deficiency detected (healthy)")

    crop_ctx = f" for {crop_type}" if crop_type else ""

    prompt = f"""You are KisanMitra AI — soil restoration advisor{crop_ctx}.
Based on this comprehensive soil analysis data, give a SHORT actionable summary (max 120 words):

{chr(10).join(context_parts)}

Instructions:
- Focus on the TOP 3 most important actions the farmer should take THIS WEEK
- Include exact fertilizer names and amounts
- If disease was found in photo, mention it and treatment
- Mention soil restoration progress (NDVI trend) if available
- Use emojis (🌾🧪💊🛰️) for readability
- {lang_instruction}"""

    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.5,
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"[soil_fusion] AI summary error: {e}")
        # Return a basic summary from the data itself
        basic = []
        for step in xgb.get("restoration_steps", [])[:3]:
            basic.append(f"• {step}")
        return "\n".join(basic) if basic else "Soil analysis complete. Check the card above for details."
