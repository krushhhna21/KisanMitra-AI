import os
from groq import Groq
from config import GROQ_API_KEY, GROQ_WHISPER_MODEL

groq_client = Groq(api_key=GROQ_API_KEY)

def transcribe_voice(audio_bytes: bytes):
    """Transcribe voice message using Groq Whisper. Returns text or None."""
    temp_path = "temp_voice.ogg"
    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        with open(temp_path, "rb") as f:
            result = groq_client.audio.transcriptions.create(
                model=GROQ_WHISPER_MODEL,
                file=("voice.ogg", f, "audio/ogg"),
                language="hi",
                response_format="text"
            )

        text = result if isinstance(result, str) else getattr(result, 'text', str(result))
        return text.strip() if text else None

    except Exception as e:
        print(f"Voice agent error: {e}")
        return None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
