"""Voice intake with a fake Gemini client (offline)."""

from types import SimpleNamespace

import pytest

from sentinel.voice_intake import VoiceIntakeError, transcribe_ticket
from shared.settings import Settings


def _client(text=None, exc=None):
    seen = {}

    def generate_content(model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        if exc:
            raise exc
        return SimpleNamespace(text=text)

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)), seen


S = Settings(_env_file=None, gemini_api_key="test-key", gemini_model="gemini-test")


def test_transcribes_into_subject_and_body():
    client, seen = _client('{"subject": " VPN down ", "body": " Our VPN is down since 9. ", "language": "en"}')
    vt = transcribe_ticket(b"RIFF....", "audio/wav", settings=S, client=client)
    assert (vt.subject, vt.body, vt.language) == ("VPN down", "Our VPN is down since 9.", "en")
    assert seen["model"] == "gemini-3.5-flash-lite"
    assert seen["contents"][0].inline_data.mime_type == "audio/wav"
    assert seen["config"].response_mime_type == "application/json"


def test_german_and_unknown_language():
    client, _ = _client('{"subject": "VPN-Ausfall", "body": "Das VPN geht nicht.", "language": "de"}')
    assert transcribe_ticket(b"x", settings=S, client=client).language == "de"
    client, _ = _client('{"subject": "", "body": "hola", "language": "es"}')
    assert transcribe_ticket(b"x", settings=S, client=client).language == "en"


@pytest.mark.parametrize("audio,text,exc", [
    (b"", None, None),
    (b"x", '{"subject": "", "body": "  ", "language": "en"}', None),
    (b"x", "not json", None),
    (b"x", None, RuntimeError("429 quota")),
])
def test_failures_are_readable_errors(audio, text, exc):
    client, _ = _client(text, exc)
    with pytest.raises(VoiceIntakeError):
        transcribe_ticket(audio, settings=S, client=client)
