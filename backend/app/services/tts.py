import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import math
from pathlib import Path
import struct
import uuid
from urllib import error, request
from threading import Lock

import websockets

from app.core.config import settings
from app.services.runtime_config import get_runtime_config

_NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))
_TTS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts")
_TTS_JOB_LOCK = Lock()
_TTS_JOBS: dict[str, object] = {}


def synthesize(text: str, emotion: str = "calm") -> str | None:
    content = (text or "").strip()
    if not content or not settings.tts_enabled:
        return None

    provider = settings.tts_provider.strip().lower()
    # If provider is still mock but real OpenSpeech creds are configured, prefer real TTS.
    if provider == "mock":
        has_openspeech_creds = bool(
            (settings.tts_app_id.strip() or settings.asr_app_id.strip())
            and (settings.tts_access_token.strip() or settings.asr_access_token.strip())
            and settings.tts_voice.strip()
        )
        if has_openspeech_creds:
            provider = "openspeech_tts_http"

    result: str | None = None
    if provider == "mock":
        return _mock_audio_data_url(content)
    if provider in {"openspeech_tts", "doubao_tts_ws", "doubao_openspeech_tts"}:
        result = _openspeech_tts_data_url(content)
    elif provider in {"openspeech_tts_http", "doubao_tts_http"}:
        result = _openspeech_tts_http_data_url(content)
    elif provider in {"ark", "doubao"}:
        result = _ark_audio_data_url(content, emotion=emotion)

    if result:
        return result

    if settings.env.strip().lower() == "dev":
        return _mock_audio_data_url(content)
    return None


def synthesize_soft_timeout(text: str, emotion: str = "calm", timeout_ms: int | None = None) -> str | None:
    content = (text or "").strip()
    if not content or not settings.tts_enabled:
        return None

    wait_ms = timeout_ms if timeout_ms is not None else settings.chat_tts_soft_timeout_ms
    if wait_ms <= 0:
        return None

    future = _TTS_EXECUTOR.submit(synthesize, content, emotion)
    try:
        return future.result(timeout=wait_ms / 1000)
    except FutureTimeoutError:
        return None
    except Exception:
        return None


def start_synthesize_job(text: str, emotion: str = "calm") -> str | None:
    content = (text or "").strip()
    if not content or not settings.tts_enabled:
        return None
    job_id = f"tts_{uuid.uuid4().hex}"
    future = _TTS_EXECUTOR.submit(synthesize, content, emotion)
    with _TTS_JOB_LOCK:
        _TTS_JOBS[job_id] = future
    return job_id


def read_synthesize_job(job_id: str, wait_ms: int = 0) -> tuple[str, str | None]:
    if not job_id:
        return "missing", None
    with _TTS_JOB_LOCK:
        future = _TTS_JOBS.get(job_id)
    if future is None:
        return "not_found", None
    try:
        if not future.done() and wait_ms > 0:
            try:
                future.result(timeout=wait_ms / 1000)
            except FutureTimeoutError:
                return "pending", None
        if not future.done():
            return "pending", None
        raw = future.result()
        audio_url = public_audio_url(raw)
        with _TTS_JOB_LOCK:
            _TTS_JOBS.pop(job_id, None)
        return ("done", audio_url) if audio_url else ("failed", None)
    except Exception:
        with _TTS_JOB_LOCK:
            _TTS_JOBS.pop(job_id, None)
        return "failed", None


def public_audio_url(audio_url: str | None) -> str | None:
    normalized = (audio_url or "").strip()
    if not normalized:
        return None
    if normalized.startswith("data:audio/"):
        return _persist_data_audio_url(normalized)
    return normalized


def _mock_audio_data_url(text: str = "") -> str:
    # Audible mono PCM tone for local demo/debug so WebGL lip sync can still be verified.
    sample_rate = 16000
    duration_ms = max(450, min(1800, 280 + len(text) * 18))
    num_samples = int(sample_rate * duration_ms / 1000)
    pcm_frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        envelope = min(1.0, i / (sample_rate * 0.04), (num_samples - i) / (sample_rate * 0.08))
        sample = math.sin(2 * math.pi * 220 * t) * 0.22
        sample += math.sin(2 * math.pi * 330 * t) * 0.12
        sample = max(-1.0, min(1.0, sample * max(0.0, envelope)))
        pcm_frames.extend(struct.pack("<h", int(sample * 32767)))
    pcm = bytes(pcm_frames)
    wav = _wrap_wav_pcm16_mono(pcm, sample_rate=sample_rate)
    encoded = base64.b64encode(wav).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


def _persist_data_audio_url(audio_url: str) -> str | None:
    try:
        header, payload = audio_url.split(",", 1)
    except ValueError:
        return None

    if ";base64" not in header:
        return None

    mime = header[5:].split(";", 1)[0].strip().lower()
    ext = {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/ogg": ".ogg",
    }.get(mime, ".bin")
    try:
        content = base64.b64decode(payload, validate=True)
    except Exception:
        return None

    base_dir = Path(settings.tts_audio_store_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"tts_{uuid.uuid4().hex}{ext}"
    target = (base_dir / file_name).resolve()
    target.write_bytes(content)
    public_base = (settings.tts_audio_public_base_url or "http://127.0.0.1:8000").rstrip("/")
    return f"{public_base}/api/tts/files/{file_name}"


def _ark_audio_data_url(text: str, emotion: str) -> str | None:
    api_key = settings.resolved_tts_api_key()
    model = settings.resolved_tts_model()
    if not api_key or not model:
        return None
    payload = {
        "model": model,
        "input": text[:600],
        "voice": settings.tts_voice,
        "emotion": emotion,
        "format": "wav",
    }
    req_obj = request.Request(
        url=f"{settings.resolved_tts_base_url()}/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with _NO_PROXY_OPENER.open(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
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


def _openspeech_tts_data_url(text: str) -> str | None:
    try:
        return asyncio.run(_openspeech_tts_data_url_async(text))
    except Exception:
        return None


def _openspeech_tts_http_data_url(text: str) -> str | None:
    app_id = settings.tts_app_id.strip() or settings.asr_app_id.strip()
    access_token = settings.tts_access_token.strip() or settings.asr_access_token.strip()
    resource_id = settings.tts_resource_id.strip() or "seed-tts-1.0"
    speaker = settings.tts_voice.strip()
    fmt = (settings.tts_audio_format or "wav").strip().lower()
    sample_rate = int(settings.tts_sample_rate or 24000)
    if not app_id or not access_token or not speaker:
        return None
    payload = {
        "user": {"uid": "law-digital-human"},
        "req_params": {
            "text": text[:600],
            "speaker": speaker,
            "audio_params": {"format": fmt, "sample_rate": sample_rate},
        },
    }
    req_obj = request.Request(
        url=settings.tts_http_url.strip() or "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_openspeech_auth_headers(
            app_id=app_id,
            access_token=access_token,
            resource_id=resource_id,
            request_id=f"tts_{uuid.uuid4()}",
            content_type="application/json",
        ),
        method="POST",
    )
    try:
        with _NO_PROXY_OPENER.open(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
            body = resp.read()
            content_type = (resp.headers.get("Content-Type", "") or "").lower()
    except (error.HTTPError, error.URLError, TimeoutError, OSError):
        return None
    if not body:
        return None
    # HTTP unidirectional may return direct audio bytes.
    if "audio/" in content_type or body[:4] == b"RIFF":
        mime = "audio/wav" if fmt == "wav" else ("audio/mpeg" if fmt == "mp3" else "audio/ogg")
        return f"data:{mime};base64,{base64.b64encode(body).decode('ascii')}"
    audio_bytes = _extract_openspeech_audio_bytes(body, fmt)
    if audio_bytes:
        mime = "audio/wav" if fmt == "wav" else ("audio/mpeg" if fmt == "mp3" else "audio/ogg")
        return f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    return None


async def _openspeech_tts_data_url_async(text: str) -> str | None:
    app_id = settings.tts_app_id.strip() or settings.asr_app_id.strip()
    access_token = settings.tts_access_token.strip() or settings.asr_access_token.strip()
    resource_id = settings.tts_resource_id.strip() or "seed-tts-1.0"
    ws_url = settings.tts_ws_url.strip() or "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
    speaker = settings.tts_voice.strip()
    audio_format = (settings.tts_audio_format or "wav").strip().lower()
    sample_rate = int(settings.tts_sample_rate or 24000)
    if not app_id or not access_token or not speaker:
        return None

    payload = {
        "user": {"uid": "law-digital-human"},
        "req_params": {
            "text": text[:600],
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
        },
    }

    headers = _openspeech_auth_headers(
        app_id=app_id,
        access_token=access_token,
        resource_id=resource_id,
        request_id=f"tts_{uuid.uuid4()}",
    )
    frame = _build_tts_send_text_frame(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    audio_chunks: list[bytes] = []

    async with websockets.connect(ws_url, additional_headers=headers, max_size=16 * 1024 * 1024) as ws:
        await ws.send(frame)
        for _ in range(512):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
            except asyncio.TimeoutError:
                break
            if not isinstance(raw, (bytes, bytearray)):
                continue
            kind, event_code, data = _parse_tts_frame(bytes(raw))
            if kind == "audio" and event_code == 352 and data:
                audio_chunks.append(data)
            elif kind == "json" and event_code == 152:
                break
            elif kind == "error":
                return None

    if not audio_chunks:
        return None
    audio = b"".join(audio_chunks)
    mime = "audio/wav" if audio_format == "wav" else ("audio/mpeg" if audio_format == "mp3" else "audio/ogg")
    return f"data:{mime};base64,{base64.b64encode(audio).decode('ascii')}"


def _openspeech_auth_headers(
    *,
    app_id: str,
    access_token: str,
    resource_id: str,
    request_id: str,
    content_type: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-Api-App-Id": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _extract_openspeech_audio_bytes(body: bytes, fmt: str) -> bytes | None:
    text = body.decode("utf-8", errors="ignore").strip()
    if not text:
        return None

    candidates = [line.strip() for line in text.splitlines() if line.strip()] if ("\n" in text or "\r" in text) else [text]
    chunks: list[bytes] = []

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        raw_data = parsed.get("data")
        b64 = parsed.get("audio_base64")
        if not b64 and isinstance(raw_data, dict):
            b64 = raw_data.get("audio_base64")
        if not b64 and isinstance(raw_data, str) and raw_data.strip():
            b64 = raw_data.strip()
        if isinstance(b64, str) and b64.strip():
            try:
                chunks.append(base64.b64decode(b64.strip()))
            except Exception:
                continue

    if not chunks:
        return None

    audio = b"".join(chunks)
    if fmt == "wav":
        return _normalize_streamed_wav_bytes(audio)
    return audio


def _normalize_streamed_wav_bytes(audio: bytes) -> bytes:
    if len(audio) < 12 or audio[:4] != b"RIFF":
        return audio

    normalized = bytearray(audio)
    struct.pack_into("<I", normalized, 4, max(0, len(normalized) - 8))

    data_index = normalized.find(b"data")
    if data_index >= 0 and data_index + 8 <= len(normalized):
        data_size = len(normalized) - (data_index + 8)
        struct.pack_into("<I", normalized, data_index + 4, max(0, data_size))

    return bytes(normalized)


def _build_tts_send_text_frame(payload: bytes) -> bytes:
    # v1, header size=4, full client request, JSON, no compression.
    header = bytes([0x11, 0x10, 0x10, 0x00])
    return header + struct.pack(">I", len(payload)) + payload


def _parse_tts_frame(frame: bytes) -> tuple[str, int, bytes]:
    if len(frame) < 8:
        return "unknown", 0, b""
    header_size = (frame[0] & 0x0F) * 4
    if header_size <= 0 or len(frame) < header_size:
        return "unknown", 0, b""
    msg_type = (frame[1] >> 4) & 0x0F
    flags = frame[1] & 0x0F
    offset = header_size
    event_code = 0

    if msg_type == 0xF:
        return "error", 0, b""

    # TTS v3 response frames use event number in optional field.
    if flags == 0x4 and len(frame) >= offset + 4:
        event_code = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        if len(frame) < offset + 4:
            return "unknown", event_code, b""
        sid_len = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4 + sid_len
        if len(frame) < offset + 4:
            return "unknown", event_code, b""
        payload_len = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        data = frame[offset : offset + payload_len]
    else:
        payload_len = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        data = frame[offset : offset + payload_len]

    if msg_type == 0xB:
        return "audio", event_code, data
    if msg_type == 0x9:
        return "json", event_code, data
    return "unknown", event_code, data


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
