"""
plantix.py — Plantix Vision API + Groq Vision Fallback
========================================================
Sends crop photo to Plantix B2B API for disease/deficiency detection.
If Plantix is unavailable, falls back to Groq Llama-4 Vision (existing).
Always returns a normalized dict for the fusion layer.
"""

import base64
import requests
from config import GROQ_API_KEY, GROQ_VISION_MODEL, PLANTIX_API_KEY, PLANTIX_ENABLED

# Lazy Groq client — initialized on first use to avoid httpx version conflicts at import
_groq_client = None

def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client

# Plantix B2B API config
PLANTIX_BASE_URL = "https://api.plantix.net"
PLANTIX_ANALYZE_ENDPOINT = "/v2/image_analysis"


def analyze_plant_health(image_bytes: bytes, language: str = "hi") -> dict:
    """
    Main entry point. Analyze a crop photo for disease/nutrient deficiency.

    Parameters
    ----------
    image_bytes : raw JPEG/PNG bytes from Telegram
    language    : 'hi', 'mr', or 'en' — used for Groq fallback prompt

    Returns
    -------
    dict with keys:
        disease       : str — detected disease/pest name (or 'None')
        deficiency    : str — nutrient deficiency detected (or 'None')
        treatment     : str — recommended treatment text
        confidence    : float — 0.0–1.0
        severity      : str — 'low', 'medium', 'high'
        source        : str — 'Plantix API' or 'Groq Vision AI'
        raw_analysis  : str — full text analysis for display
    """
    if PLANTIX_ENABLED:
        try:
            result = _plantix_api_call(image_bytes)
            if result:
                return result
        except Exception as e:
            print(f"[plantix] API error, falling back to Groq: {e}")

    # Fallback: Groq Llama-4 Vision
    return _groq_vision_fallback(image_bytes, language)


def _plantix_api_call(image_bytes: bytes) -> dict | None:
    """
    Call Plantix B2B Vision API.
    Returns normalized dict or None on failure.
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {PLANTIX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "image": image_b64,
        "language": "en",  # Plantix API returns English; we translate in fusion layer
    }

    resp = requests.post(
        f"{PLANTIX_BASE_URL}{PLANTIX_ANALYZE_ENDPOINT}",
        json=payload,
        headers=headers,
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"[plantix] HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    data = resp.json()

    # Parse Plantix response (structure varies by version)
    diagnosis = data.get("diagnosis", [{}])
    top = diagnosis[0] if diagnosis else {}

    disease = top.get("name", "None")
    confidence = top.get("probability", 0.0)
    severity = "high" if confidence > 0.8 else ("medium" if confidence > 0.5 else "low")

    treatments = top.get("treatment", {})
    treatment_text = treatments.get("chemical", "") or treatments.get("biological", "") or ""
    if isinstance(treatment_text, list):
        treatment_text = "; ".join(treatment_text)

    deficiency = top.get("nutrient_deficiency", "None")

    return {
        "disease": disease,
        "deficiency": deficiency if deficiency else "None",
        "treatment": treatment_text if treatment_text else "Consult local expert",
        "confidence": round(confidence, 2),
        "severity": severity,
        "source": "Plantix API",
        "raw_analysis": f"Disease: {disease} (Confidence: {int(confidence*100)}%)\nTreatment: {treatment_text}",
    }


def _groq_vision_fallback(image_bytes: bytes, language: str = "hi") -> dict:
    """
    Fallback: Use Groq Llama-4 Vision to analyze crop photo.
    Returns same normalized dict as Plantix, so fusion layer works identically.
    """
    lang_instruction = {
        "hi": "Reply in Hindi (Hinglish OK).",
        "mr": "Reply in Marathi.",
        "en": "Reply in English.",
    }.get(language, "Reply in Hindi (Hinglish OK).")

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        response = _get_groq().chat.completions.create(
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
                        "text": f"""You are KisanMitra AI — expert plant pathologist for Indian farmers.
Analyze this crop/plant image. Respond in this EXACT structured format:

DISEASE: [disease/pest name or 'None']
DEFICIENCY: [nutrient deficiency or 'None']
SEVERITY: [low/medium/high]
CONFIDENCE: [0.0 to 1.0]

TREATMENT:
[2-3 specific treatment steps with exact dosages if applicable]

ANALYSIS:
[3-4 bullet points covering: what you see, root cause, immediate action, prevention]

{lang_instruction}
If not a plant/crop image, set DISEASE=None, DEFICIENCY=None, SEVERITY=low, CONFIDENCE=0.0."""
                    }
                ]
            }],
            max_tokens=500,
            temperature=0.3,
        )

        full_text = response.choices[0].message.content.strip()

        # Parse structured response
        disease = "None"
        deficiency = "None"
        severity = "medium"
        confidence = 0.7
        treatment = ""
        analysis = full_text

        for line in full_text.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("DISEASE:"):
                disease = line_stripped.replace("DISEASE:", "").strip()
            elif line_stripped.startswith("DEFICIENCY:"):
                deficiency = line_stripped.replace("DEFICIENCY:", "").strip()
            elif line_stripped.startswith("SEVERITY:"):
                severity = line_stripped.replace("SEVERITY:", "").strip().lower()
            elif line_stripped.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_stripped.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.7

        # Extract treatment section
        if "TREATMENT:" in full_text:
            parts = full_text.split("TREATMENT:")
            if len(parts) > 1:
                treatment_block = parts[1].split("ANALYSIS:")[0] if "ANALYSIS:" in parts[1] else parts[1]
                treatment = treatment_block.strip()

        # Extract analysis section for display
        if "ANALYSIS:" in full_text:
            analysis = full_text.split("ANALYSIS:")[1].strip()

        return {
            "disease": disease,
            "deficiency": deficiency,
            "treatment": treatment if treatment else "Local expert se salah lein",
            "confidence": round(confidence, 2),
            "severity": severity if severity in ["low", "medium", "high"] else "medium",
            "source": "Groq Vision AI",
            "raw_analysis": analysis,
        }

    except Exception as e:
        print(f"[plantix] Groq Vision fallback error: {e}")
        return {
            "disease": "None",
            "deficiency": "None",
            "treatment": "Photo analysis unavailable — describe symptoms in text",
            "confidence": 0.0,
            "severity": "low",
            "source": "Fallback (Error)",
            "raw_analysis": "Photo analysis mein dikkat — text mein batayein kya problem hai.",
        }
