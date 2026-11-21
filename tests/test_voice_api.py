"""POST /voice/transcribe with a fake transcriber (offline)."""

from fastapi.testclient import TestClient

import api.main as main
from sentinel.voice_intake import VoiceIntakeError, VoiceTicket


def test_transcribe_returns_subject_body_language(monkeypatch):
    seen = {}

    def fake(audio, mime):
        seen.update(audio=audio, mime=mime)
        return VoiceTicket(subject="VPN down", body="Our VPN is down.", language="en")

    monkeypatch.setattr(main, "transcribe_ticket", fake)
    r = TestClient(main.app).post("/voice/transcribe", content=b"RIFFdata", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert r.json() == {"subject": "VPN down", "body": "Our VPN is down.", "language": "en"}
    assert seen == {"audio": b"RIFFdata", "mime": "audio/wav"}


def test_transcription_failure_is_a_422_with_a_message(monkeypatch):
    def fake(audio, mime):
        raise VoiceIntakeError("No speech found in the recording.")

    monkeypatch.setattr(main, "transcribe_ticket", fake)
    r = TestClient(main.app).post("/voice/transcribe", content=b"x", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 422 and "No speech" in r.json()["detail"]


def test_too_long_recording_is_rejected(monkeypatch):
    monkeypatch.setattr(main, "MAX_VOICE_BYTES", 4)
    r = TestClient(main.app).post("/voice/transcribe", content=b"12345", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 413
