from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL

groq_client = Groq(api_key=GROQ_API_KEY)

def find_schemes(query: str) -> str:
    try:
        res = groq_client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": f"""Government scheme expert for Indian farmers.
Query: {query}
List 3-5 most relevant schemes. Each include:
- 🏛️ Scheme name
- 💰 Benefit
- 👤 Eligibility (1 line)
- 📋 How to apply (1 line)
Hindi. Emojis. Simple and actionable."""}],
            max_tokens=500,
            temperature=0.3
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"Scheme finder error: {e}")
        return "🙏 Yojana jaankari abhi nahi. Baad mein try karein."

def get_crop_calendar() -> str:
    from datetime import datetime
    month = datetime.now().month
    calendars = {
        1:  ("January 🌾", ["Gehu nichais karein", "Sarson insecticide spray", "Chana check karein", "Thandi se bachayein"]),
        2:  ("February 🌿", ["Gehu mein doosri khad", "Makka taiyaari", "Keede check karein", "Irrigation timing"]),
        3:  ("March 🌻", ["Gehu+Chana harvesting", "Zaid prep — Moong/Urad", "Khali khet jotaai", "Beej store karein"]),
        4:  ("April 🌱", ["Moong/Urad/Mungfali lagaayein", "Tarbuz/Kheera buwai", "Drip irrigation", "Keet niyantran"]),
        5:  ("May ☀️", ["Kharif ke liye khet taiyaar", "Dhan nursery shuru", "Mitti pariksha", "Khad+beej order"]),
        6:  ("June 🌧️", ["Mansoon mein Dhan lagaayein", "Soyabean/Makka buwai", "Kharif vegetables", "Drainage check"]),
        7:  ("July 🌿", ["Dhan mein urvarak", "Soyabean nikaai-gundai", "Neem spray", "Field drainage"]),
        8:  ("August 💧", ["Dhan top dressing", "Soyabean pod borer check", "Tuvar buwai", "Irrigation if needed"]),
        9:  ("September 🌾", ["Dhan bali check", "Soyabean harvest taiyaari", "Rabi planning", "Beej+khad order"]),
        10: ("October 🎉", ["Dhan/Soyabean harvest", "Khet saaf karein", "Rabi buwai — Gehu/Chana", "Phosphorus dein"]),
        11: ("November 🌱", ["Gehu buwai — best time!", "Sarson/Chana/Masoor", "Irrigation schedule", "DAP khaad"]),
        12: ("December ❄️", ["Gehu pehli sinchai", "Sarson flowering check", "Paudhon ko thandi se bachao", "Relax — keede kam"]),
    }
    name, tasks = calendars.get(month, ("This Month", ["Agronomist se sampark karein"]))
    task_list = "\n".join([f"  ✅ {t}" for t in tasks])
    return f"📅 *{name} — Is Mahine Ke Kaam:*\n\n{task_list}"
