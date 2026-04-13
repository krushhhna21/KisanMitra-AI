import requests
from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, MANDI_API_KEY
from database.db import get_conn

_groq_client = None
def _get_groq():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client

CROP_MAP = {
    "pyaaz": "Onion", "onion": "Onion", "kanda": "Onion",
    "tamatar": "Tomato", "tomato": "Tomato",
    "aalu": "Potato", "potato": "Potato",
    "gehu": "Wheat", "wheat": "Wheat",
    "chawal": "Rice", "rice": "Rice",
    "dhan": "Paddy", "paddy": "Paddy",
    "soyabean": "Soyabean", "soya": "Soyabean",
    "chana": "Gram", "gram": "Gram",
    "makka": "Maize", "maize": "Maize",
    "tur": "Arhar/Tur", "arhar": "Arhar/Tur",
    "moong": "Moong", "urad": "Urad",
    "sarson": "Mustard", "mustard": "Mustard",
}

def get_mandi_prices(crop_query: str) -> str:
    crop_name = "Onion"
    for key, val in CROP_MAP.items():
        if key in crop_query.lower():
            crop_name = val
            break

    # Try govt API
    try:
        url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
        params = {
            "api-key": MANDI_API_KEY,
            "format": "json",
            "limit": "5",
            "filters[State]": "Maharashtra",
            "filters[Commodity]": crop_name
        }
        res = requests.get(url, params=params, timeout=8)
        data = res.json()

        if data.get("records"):
            records = data["records"][:5]

            # Cache in DB
            conn = get_conn()
            for r in records:
                conn.execute("""
                    INSERT INTO mandi_cache (crop, market, price, date)
                    VALUES (?, ?, ?, ?)
                """, (crop_name, r.get("Market", ""), float(r.get("Modal_Price", 0) or 0), r.get("Arrival_Date", "")))
            conn.commit()
            conn.close()

            lines = [f"• {r.get('Market')} ({r.get('District')}): ₹{r.get('Modal_Price')}/quintal" for r in records]
            return f"💰 *{crop_name} — Maharashtra Mandi Bhav:*\n\n" + "\n".join(lines) + f"\n\n📅 _{records[0].get('Arrival_Date', 'Recent')}_\n_1 quintal = 100 kg_"
    except Exception as e:
        print(f"Mandi API error: {e}")

    # AI fallback
    return _ai_price_fallback(crop_query)

def _ai_price_fallback(crop_query: str) -> str:
    try:
        res = _get_groq().chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": f"""Indian farmer asking mandi price: {crop_query}
Give approximate current Maharashtra mandi price range (₹/quintal).
Include: price range, good/average/low rating, best time to sell, 2-3 major mandis.
Hindi. Short. Emojis."""}],
            max_tokens=250,
            temperature=0.3
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI mandi fallback error: {e}")
        return "💰 Mandi bhav abhi fetch nahi hua. Local mandi se pata karein."