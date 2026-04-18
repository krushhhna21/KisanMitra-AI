import os
import traceback
from groq import Groq
from config import GROQ_API_KEY, GROQ_WHISPER_MODEL
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

# Fallback model if primary Whisper model is unavailable on the free tier
WHISPER_FALLBACK_MODEL = "whisper-large-v3-turbo"


def transcribe_voice(audio_bytes: bytes) -> str | None:
    """
    Transcribe a Telegram voice message (OGG/OPUS) using Groq Whisper.
    
    Returns the transcribed text string, or None on failure.
    Works with groq >= 1.0.0
    """
    temp_path = "temp_voice.ogg"

    try:
        # Save audio bytes to a temp file
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        print(f"[Voice] Audio saved ({len(audio_bytes)} bytes). Sending to Groq Whisper...")

        # Try primary Whisper model first
        text = _call_whisper(temp_path, GROQ_WHISPER_MODEL)

        # If primary model returns nothing, try the turbo fallback
        if not text:
            print(f"[Voice] Primary model returned empty. Trying fallback: {WHISPER_FALLBACK_MODEL}")
            text = _call_whisper(temp_path, WHISPER_FALLBACK_MODEL)

        if text:
            print(f"[Voice] Transcription successful: '{text[:80]}...'")
        else:
            print("[Voice] Both models returned empty transcription.")

        return text

    except Exception as e:
        print(f"[Voice] Unexpected error in transcribe_voice: {e}")
        traceback.print_exc()
        return None

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("[Voice] Temp file cleaned up.")


def _call_whisper(file_path: str, model: str) -> str | None:
    """
    Internal helper: call Groq Whisper transcription API.
    Returns stripped text or None.
    """
    try:
        with open(file_path, "rb") as f:
            result = _get_groq().audio.transcriptions.create(
                model=model,
                file=(os.path.basename(file_path), f, "audio/ogg"),
                language="hi",           # Primary = Hindi; Whisper auto-detects if wrong
                response_format="text",  # Returns plain string directly
            )

        # groq >= 1.0 returns a str when response_format="text"
        if isinstance(result, str):
            text = result.strip()
        else:
            # Older behaviour: object with .text attribute
            text = getattr(result, "text", "").strip()

        return text if text else None

    except Exception as e:
        print(f"[Voice] Whisper model '{model}' failed: {e}")
        traceback.print_exc()
        return None
