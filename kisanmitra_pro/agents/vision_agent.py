import base64
from groq import Groq
from config import GROQ_API_KEY, GROQ_VISION_MODEL, GROQ_CHAT_MODEL

groq_client = Groq(api_key=GROQ_API_KEY)

def analyze_crop_photo(image_bytes: bytes) -> tuple:
    """
    Analyze crop photo for pest/disease.
    Returns: (analysis, crop_detected, pest_detected)
    """
    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        response = groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": """You are KisanMitra AI — expert plant pathologist for Indian farmers.

Analyze this crop/plant image and respond in this EXACT format:

CROP: [crop name in English]
PEST: [pest/disease name or 'None']
SEVERITY: [low/medium/high]

REPORT:
1. 🌿 FASAL: [What crop/plant is this?]
2. 🐛 SAMASYA: [Disease or pest? If none, say healthy]
3. 🔍 LAKSHAN: [Visible symptoms]
4. 💊 ILAAJ: [Step-by-step treatment — practical]
5. 🛡️ BACHAO: [Prevention for future]
6. ⚡ ABHI KARO: [What to do RIGHT NOW]

Reply in Hindi. Under 300 words. Practical and specific. Emojis.
If not a plant image, say: "Kripya fasal ki photo bhejein." """
                    }
                ]
            }],
            max_tokens=700,
            temperature=0.3
        )

        full_response = response.choices[0].message.content.strip()

        # Parse crop and pest from structured response
        crop_detected = "unknown"
        pest_detected = "none"
        lines = full_response.split("\n")
        for line in lines[:5]:
            if line.startswith("CROP:"):
                crop_detected = line.replace("CROP:", "").strip().lower()
            elif line.startswith("PEST:"):
                pest_detected = line.replace("PEST:", "").strip().lower()

        # Extract just the report part for display
        if "REPORT:" in full_response:
            display_text = "🔬 *Fasal Analysis Report*\n\n" + full_response.split("REPORT:")[1].strip()
        else:
            display_text = "🔬 *Fasal Analysis Report*\n\n" + full_response

        return display_text, crop_detected, pest_detected

    except Exception as e:
        print(f"Vision agent error: {e}")
        # Fallback
        try:
            res = groq_client.chat.completions.create(
                model=GROQ_CHAT_MODEL,
                messages=[{"role": "user", "content": "Farmer ne fasal photo bheji. Unhe text mein symptoms batane ko bolein. Hindi mein, 2 lines."}],
                max_tokens=100
            )
            return res.choices[0].message.content.strip(), "unknown", "none"
        except Exception:
            return "🙏 Photo analyze nahi hua. Text mein batayein — kaun si fasal, kya problem?", "unknown", "none"
