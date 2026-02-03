import base64
import json
import struct
from urllib import error, request

from app.core.config import settings

_NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))


def synthesize(text: str, emotion: str = "calm") -> str | None:
    content = (text or "").strip()
    if not content or not settings.tts_enabled:
        return None

    provider = settings.tts_provider.strip().lower()
    if provider == "mock":
        return _mock_audio_data_url()
    if provider in {"ark", "doubao"}:
        return _ark_audio_data_url(content, emotion=emotion)
    return None


def _mock_audio_data_url() -> str:
    # 250ms mono 16-bit PCM silence; stable fallback that browsers can play.
    sample_rate = 8000
    duration_ms = 250
    num_samples = int(sample_rate * duration_ms / 1000)
    pcm = b"\x00\x00" * num_samples
    wav = _wrap_wav_pcm16_mono(pcm, sample_rate=sample_rate)
    encoded = base64.b64encode(wav).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


def _ark_audio_data_url(text: str, emotion: str) -> str | None:
    if not settings.tts_api_key or not settings.tts_model:
        return None
    payload = {
        "model": settings.tts_model,
        "input": text[:600],
        "voice": settings.tts_voice,
        "emotion": emotion,
        "format": "wav",
    }
    req_obj = request.Request(
        url=f"{settings.tts_base_url.rstrip('/')}/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.tts_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with _NO_PROXY_OPENER.open(req_obj, timeout=30) as resp:
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except (error.HTTPError, error.URLError, TimeoutError, OSError):
        return None

    if not body:
        return None

    lowered = content_type.lower()
    if "audio/" in lowered:
        mime = content_type.split(";")[0].strip() or "audio/wav"
        return f"data:{mime};base64,{base64.b64encode(body).decode('ascii')}"

    try:
        parsed = json.loads(body.decode("utf-8", errors="ignore"))
        b64 = parsed.get("audio_base64") or parsed.get("data", {}).get("audio_base64")
        if isinstance(b64, str) and b64.strip():
            return f"data:audio/wav;base64,{b64.strip()}"
    except Exception:
        return None
    return None


def _wrap_wav_pcm16_mono(pcm: bytes, sample_rate: int) -> bytes:
    channels = 1
    bits_per_sample = 16
    block_align = channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    data_size = len(pcm)
    riff_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm
