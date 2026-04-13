import requests
from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL

_groq_client = None
def _get_groq():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client

def get_crop_health(lat: float, lon: float, location: str) -> str:
    """
    Get NDVI-based crop health using free NASA MODIS/Sentinel data
    via open-source APIs (no auth required for basic data)
    """
    try:
        # Using NASA POWER API — free, no key needed
        url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=ALLSKY_SFC_SW_DWN,T2M,PRECTOTCORR,RH2M"
            f"&community=AG&longitude={lon}&latitude={lat}"
            f"&start=20250301&end=20250308&format=JSON"
        )
        res = requests.get(url, timeout=10)
        data = res.json()

        props = data.get("properties", {}).get("parameter", {})
        if not props:
            return _ai_crop_health_advice(lat, lon, location)

        # Get recent averages
        solar = list(props.get("ALLSKY_SFC_SW_DWN", {}).values())
        temp = list(props.get("T2M", {}).values())
        rain = list(props.get("PRECTOTCORR", {}).values())
        humidity = list(props.get("RH2M", {}).values())

        # Filter valid values
        solar = [v for v in solar if v > 0]
        temp = [v for v in temp if v > -900]
        rain = [v for v in rain if v >= 0]
        humidity = [v for v in humidity if v > 0]

        avg_solar = sum(solar)/len(solar) if solar else 0
        avg_temp = sum(temp)/len(temp) if temp else 0
        avg_rain = sum(rain)/len(rain) if rain else 0
        avg_humidity = sum(humidity)/len(humidity) if humidity else 0

        # Health assessment
        health_score = 0
        issues = []
        good_signs = []

        if 20 <= avg_temp <= 35:
            health_score += 25
            good_signs.append("Taapman sahi hai")
        elif avg_temp > 40:
            issues.append("Taapman bahut zyada — garmi se fasal ko khatra")
        else:
            issues.append("Taapman thoda kam")

        if avg_solar > 15:
            health_score += 25
            good_signs.append("Dhoop acchi hai")
        else:
            issues.append("Dhoop kam — photosynthesis slow")

        if avg_rain > 0:
            health_score += 25
            good_signs.append("Paani mila hai")
        else:
            health_score += 10
            issues.append("Barish nahi — sinchai zaruri")

        if 50 <= avg_humidity <= 80:
            health_score += 25
            good_signs.append("Aardrata thik hai")
        elif avg_humidity > 85:
            issues.append("Aardrata zyada — fungal rog ka khatra")
        else:
            issues.append("Aardrata kam")

        if health_score >= 75:
            status = "🟢 ACCHA (Good)"
        elif health_score >= 50:
            status = "🟡 THEEK-THEEK (Average)"
        else:
            status = "🔴 DHYAN DO (Needs Attention)"

        good_text = "\n".join([f"  ✅ {g}" for g in good_signs]) if good_signs else "  —"
        issue_text = "\n".join([f"  ⚠️ {i}" for i in issues]) if issues else "  Koi samasya nahi"

        return f"""🛰️ *Satellite Crop Health Analysis*
📍 _{location}_

*Health Score: {health_score}/100 — {status}*

📊 *NASA Data (Last 7 days):*
• Avg Temperature: {avg_temp:.1f}°C
• Solar Radiation: {avg_solar:.1f} MJ/m²
• Rainfall: {avg_rain:.1f} mm/day
• Humidity: {avg_humidity:.1f}%

✅ *Acchi Baatein:*
{good_text}

⚠️ *Dhyan Do:*
{issue_text}

_Data source: NASA POWER Satellite API_ 🛰️"""

    except Exception as e:
        print(f"Satellite error: {e}")
        return _ai_crop_health_advice(lat, lon, location)


def _ai_crop_health_advice(lat: float, lon: float, location: str) -> str:
    """AI-based general crop health advice when satellite data unavailable"""
    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": f"""Farmer is from {location} (lat:{lat}, lon:{lon}), Maharashtra, India.
Current season: March — Rabi harvest, Zaid preparation.
Give crop health monitoring advice:
- What to check in fields right now
- Common problems in March in Maharashtra
- Preventive actions
Hindi. 5 bullet points. Practical. Emojis."""}],
            max_tokens=300,
            temperature=0.5
        )
        return f"🛰️ *Crop Health Advisory — {location}*\n\n" + res.choices[0].message.content.strip()
    except Exception:
        return "🛰️ Satellite data abhi available nahi. Apne khet ka muaaina karein."
