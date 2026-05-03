import requests
from config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_LOCATION

def get_weather(lat=DEFAULT_LAT, lon=DEFAULT_LON, location_name=DEFAULT_LOCATION) -> dict:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
            f"&daily=precipitation_sum,temperature_2m_max,temperature_2m_min"
            f"&forecast_days=3&timezone=Asia%2FKolkata"
        )
        res = requests.get(url, timeout=5)
        data = res.json()
        c = data["current"]
        d = data["daily"]

        alert = ""
        if d["precipitation_sum"][0] > 10:
            alert = "\n⚠️ *ALERT: Aaj bhari barish! Khet mein paani na dein.*"
        elif d["precipitation_sum"][1] > 10:
            alert = "\n⚠️ *ALERT: Kal tez barish! Fasal surakshit karein.*"

        return {
            "summary": f"""🌤️ *Mausam — {location_name}:*
• Taapman: {c['temperature_2m']}°C | Aardrata: {c['relative_humidity_2m']}%
• Barish: {c['precipitation']}mm | Hawa: {c['wind_speed_10m']}km/h

📅 *Agle 3 Din:*
• Aaj: {d['temperature_2m_max'][0]}°C / {d['temperature_2m_min'][0]}°C, 🌧 {d['precipitation_sum'][0]}mm
• Kal: {d['temperature_2m_max'][1]}°C / {d['temperature_2m_min'][1]}°C, 🌧 {d['precipitation_sum'][1]}mm
• Parson: {d['temperature_2m_max'][2]}°C / {d['temperature_2m_min'][2]}°C, 🌧 {d['precipitation_sum'][2]}mm{alert}""",
            "temp": c["temperature_2m"],
            "humidity": c["relative_humidity_2m"],
            "rain_today": d["precipitation_sum"][0],
            "rain_tomorrow": d["precipitation_sum"][1],
            "alert": alert
        }
    except Exception as e:
        print(f"Weather error: {e}")
        return {"summary": "Mausam jaankari uplabdh nahi.", "temp": 30, "humidity": 60,
                "rain_today": 0, "rain_tomorrow": 0, "alert": ""}
