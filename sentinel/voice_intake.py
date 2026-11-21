"""Voice ticket intake: a recorded voice message -> subject + body, ready for SentinelAgent.triage.

    from sentinel.voice_intake import transcribe_ticket
    vt = transcribe_ticket(audio_bytes, mime_type="audio/wav")    # -> VoiceTicket(subject, body, language)

Gemini listens to the audio and returns a verbatim transcript in the speaker's language (English or German) plus a
short subject line, with GEMINI_VOICE_MODEL (default gemini-3.5-flash-lite). Uses GEMINI_API_KEY, or Vertex AI with GOOGLE_GENAI_USE_VERTEXAI=true (same switch as
agent/llm_router.py). Raises VoiceIntakeError with a readable message on any failure.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from shared.settings import Settings, get_settings

# Transcription needs a fast audio model, not the drafting model (gemini-4-hydrogen timed out on a 7 s clip).
VOICE_MODEL = os.environ.get("GEMINI_VOICE_MODEL", "gemini-3.5-flash-lite")

PROMPT = (
    "This is a voice message from a customer to an IT support desk. Transcribe it word for word in the language it "
    "is spoken in (English or German); do not translate, summarise or add anything. Then write a short subject line "
    "(max 10 words) in the same language. Return JSON with keys subject, body (the transcript) and language "
    "('en' or 'de'). If there is no speech, return an empty body."
)


class VoiceTicket(BaseModel):
    subject: str = ""
    body: str = Field(default="", description="Verbatim transcript")
    language: str = "en"


class VoiceIntakeError(RuntimeError):
    pass


_client = None


def _get_client(settings: Settings):
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        http_options = types.HttpOptions(timeout=int(max(settings.gemini_timeout_s, 60) * 1000))
        if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() == "true":
            _client = genai.Client(http_options=http_options)
        elif settings.gemini_api_key:
            _client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
        else:
            raise VoiceIntakeError("Voice input needs GEMINI_API_KEY in .env (or GOOGLE_GENAI_USE_VERTEXAI=true).")
    return _client


def transcribe_ticket(
    audio: bytes, mime_type: str = "audio/wav", settings: Settings | None = None, client=None
) -> VoiceTicket:
    if not audio:
        raise VoiceIntakeError("No audio recorded.")
    settings = settings or get_settings()
    try:
        from google.genai import types

        client = client or _get_client(settings)
        resp = client.models.generate_content(
            model=VOICE_MODEL,
            contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=VoiceTicket),
        )
        ticket = VoiceTicket.model_validate(json.loads(resp.text))
    except VoiceIntakeError:
        raise
    except Exception as e:  # network, quota, bad JSON: show it, never crash the page
        raise VoiceIntakeError(f"Could not transcribe the recording: {str(e)[:200]}") from e
    ticket.body = ticket.body.strip()
    ticket.subject = ticket.subject.strip()
    if ticket.language not in ("en", "de"):
        ticket.language = "en"
    if not ticket.body:
        raise VoiceIntakeError("No speech found in the recording.")
    return ticket
