import base64
import gzip
import json
import struct
import uuid
import asyncio
import logging
import io
import wave
import math
import time
from pathlib import Path
from urllib import error, request

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
try:
    from websockets.exceptions import InvalidStatus
except Exception:  # pragma: no cover
    InvalidStatus = Exception  # type: ignore[assignment]

from app.core.config import settings

_NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))
logger = logging.getLogger(__name__)


_LAST_DETAIL: str | None = None
_LAST_LOG_ID: str | None = None
_LAST_SERVER_SUMMARY: str | None = None
_LAST_AUDIO_PROBE: str | None = None


def transcribe(audio_bytes: bytes, content_type: str | None = None) -> str:
    global _LAST_DETAIL, _LAST_LOG_ID, _LAST_SERVER_SUMMARY, _LAST_AUDIO_PROBE
    _LAST_DETAIL = None
    _LAST_LOG_ID = None
    _LAST_SERVER_SUMMARY = None
    _LAST_AUDIO_PROBE = None
    if not audio_bytes or not settings.asr_enabled:
        _LAST_DETAIL = "ASR 未启用或音频为空"
        return ""
    _LAST_AUDIO_PROBE = _build_audio_probe(audio_bytes, content_type)

    provider = settings.asr_provider.strip().lower()
    if provider == "mock":
        return "这是语音输入的模拟转写结果。"
    if provider in {"doubao_streaming", "openspeech_streaming"}:
        return _doubao_streaming_transcribe(audio_bytes, content_type=content_type)
    if provider in {"doubao_auc", "openspeech_auc"}:
        text = _doubao_auc_transcribe(audio_bytes, content_type=content_type)
        if text.strip():
            return text
        # Fallback: if AUC returns silence/empty, retry with streaming path to avoid URL/download side effects.
        detail = (_LAST_DETAIL or "").lower()
        if ("20000003" in detail) or ("文本为空" in (_LAST_DETAIL or "")) or ("normal silence audio" in detail):
            prev_detail = _LAST_DETAIL or ""
            stream_text = _doubao_streaming_transcribe(audio_bytes, content_type=content_type)
            if stream_text.strip():
                _LAST_DETAIL = f"{prev_detail}；已自动切换streaming兜底成功"
                return stream_text
            if _LAST_DETAIL:
                _LAST_DETAIL = f"{prev_detail}；streaming兜底失败: {_LAST_DETAIL}"
            else:
                _LAST_DETAIL = f"{prev_detail}；streaming兜底失败"
        return text
    if provider in {"doubao_open", "openspeech"}:
        return _doubao_open_transcribe(audio_bytes, content_type=content_type)
    if provider in {"ark", "doubao"}:
        return _ark_transcribe(audio_bytes, content_type=content_type)
    return ""


def _ark_transcribe(audio_bytes: bytes, content_type: str | None = None) -> str:
    api_key = settings.resolved_asr_api_key()
    model = settings.resolved_asr_model()
    if not api_key or not model:
        return ""

    payload = {
        "model": model,
        "audio": {
            "format": _guess_audio_format(content_type),
            "content": base64.b64encode(audio_bytes).decode("ascii"),
        },
        "language": settings.asr_language,
    }
    req_obj = request.Request(
        url=f"{settings.resolved_asr_base_url()}/audio/transcriptions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with _NO_PROXY_OPENER.open(req_obj, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""

    text = parsed.get("text") or parsed.get("result") or parsed.get("data", {}).get("text")
    return text.strip() if isinstance(text, str) else ""


def _guess_audio_format(content_type: str | None) -> str:
    lowered = (content_type or "").lower()
    if "ogg" in lowered:
        return "ogg"
    if "webm" in lowered:
        return "ogg"
    if "wav" in lowered:
        return "wav"
    if "mpeg" in lowered or "mp3" in lowered:
        return "mp3"
    return "wav"


def _normalize_asr_language(lang: str | None) -> str:
    value = (lang or "").strip()
    if not value:
        return "zh-CN"
    lower = value.lower()
    if lower in {"zh", "zh-cn", "zh_hans", "cmn"}:
        return "zh-CN"
    if lower in {"en", "en-us"}:
        return "en-US"
    return value


def _doubao_streaming_transcribe(audio_bytes: bytes, content_type: str | None = None) -> str:
    global _LAST_DETAIL
    try:
        return asyncio.run(_doubao_streaming_transcribe_async(audio_bytes, content_type))
    except ConnectionClosedOK:
        # Server may close with 1000 after last sequence; treat as normal EOF.
        return ""
    except ConnectionClosed:
        # Different websockets versions may raise ConnectionClosed instead of ConnectionClosedOK.
        return ""
    except InvalidStatus as exc:  # type: ignore[misc]
        code = getattr(exc, "status_code", None)
        resp = getattr(exc, "response", None)
        if code is None and resp is not None:
            code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        _LAST_DETAIL = f"握手失败 InvalidStatus status={code if code is not None else 'unknown'}"
        return ""
    except Exception as exc:
        name = type(exc).__name__
        if "ConnectionClosed" in name:
            return ""
        _LAST_DETAIL = f"streaming 调用异常: {name}"
        return ""


async def _doubao_streaming_transcribe_async(audio_bytes: bytes, content_type: str | None) -> str:
    global _LAST_DETAIL, _LAST_LOG_ID, _LAST_SERVER_SUMMARY, _LAST_AUDIO_PROBE
    app_id = settings.asr_app_id.strip()
    token = settings.asr_access_token.strip()
    resource_id = _resolve_streaming_resource_id(settings.asr_resource_id)
    if not app_id or not token or not resource_id:
        return ""

    stream_bytes, fmt, rate, bits, channel = _normalize_stream_audio(audio_bytes, content_type)
    if not stream_bytes:
        _LAST_DETAIL = "音频无法解析为可识别PCM流"
        return ""
    req_id = uuid.uuid4().hex
    ws_url = settings.asr_ws_url.strip() or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    last_text = ""

    is_nostream = "bigmodel_nostream" in ws_url
    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": req_id,
        "X-Api-Sequence": "-1",
        "X-Api-Connect-Id": req_id,
    }
    try:
        async with websockets.connect(ws_url, additional_headers=headers, max_size=8 * 1024 * 1024) as ws:
            init_payload = {
                "user": {"uid": "law-digital-human"},
                "audio": {
                    "format": fmt if fmt in {"pcm", "raw", "wav", "mp3", "ogg"} else "pcm",
                    "codec": "opus" if fmt == "ogg" else "raw",
                    "rate": rate,
                    "bits": bits,
                    "channel": channel,
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": True,
                    "enable_punc": True,
                    "show_utterances": False,
                },
            }
            if is_nostream:
                init_payload["audio"]["language"] = _normalize_asr_language(settings.asr_language)
            await ws.send(
                _build_frame(
                    message_type=0x1,
                    flags=0x0,
                    serialization=0x1,
                    compression=0x1,
                    payload=json.dumps(init_payload).encode("utf-8"),
                )
            )
            frame = await ws.recv()
            if isinstance(frame, bytes):
                resp = _parse_server_frame(frame)
                _LAST_LOG_ID = _extract_log_id(resp) or _LAST_LOG_ID
                _LAST_SERVER_SUMMARY = _summarize_server_resp(resp)
                err = _extract_error(resp)
                if err:
                    _LAST_DETAIL = err
                    logger.warning("doubao streaming asr setup failed: %s", err)
                    return ""
                last_text = _extract_text(resp) or last_text

            configured_chunk = int(settings.asr_chunk_bytes or 0)
            target_chunk = configured_chunk if configured_chunk > 0 else max(3200, int(rate * channel * (bits // 8) * 0.2))
            chunk_size = max(3200, target_chunk)
            chunks = [stream_bytes[i : i + chunk_size] for i in range(0, len(stream_bytes), chunk_size)] or [stream_bytes]
            for i, chunk in enumerate(chunks):
                is_last = i == len(chunks) - 1
                await ws.send(
                    _build_frame(
                        message_type=0x2,
                        flags=0x2 if is_last else 0x0,
                        serialization=0x0,
                        compression=0x1,
                        payload=chunk,
                    )
                )
                try:
                    recv_frame = await asyncio.wait_for(ws.recv(), timeout=1.5 if is_last else 0.5)
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosedOK:
                    break
                if isinstance(recv_frame, bytes):
                    resp = _parse_server_frame(recv_frame)
                    _LAST_LOG_ID = _extract_log_id(resp) or _LAST_LOG_ID
                    _LAST_SERVER_SUMMARY = _summarize_server_resp(resp)
                    err = _extract_error(resp)
                    if err:
                        _LAST_DETAIL = err
                        logger.warning("doubao streaming asr failed: %s", err)
                        return last_text
                    last_text = _extract_text(resp) or last_text
                    if isinstance(resp, dict) and int(resp.get("sequence", 0)) < 0:
                        break
                if not is_last:
                    await asyncio.sleep(0.12)

            for _ in range(5):
                try:
                    recv_frame = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    break
                except ConnectionClosedOK:
                    break
                if not isinstance(recv_frame, bytes):
                    continue
                resp = _parse_server_frame(recv_frame)
                _LAST_LOG_ID = _extract_log_id(resp) or _LAST_LOG_ID
                _LAST_SERVER_SUMMARY = _summarize_server_resp(resp)
                err = _extract_error(resp)
                if err:
                    _LAST_DETAIL = err
                    logger.warning("doubao streaming asr failed: %s", err)
                    break
                last_text = _extract_text(resp) or last_text
                if isinstance(resp, dict) and int(resp.get("sequence", 0)) < 0:
                    break
    except ConnectionClosed:
        # Normal for server to close after final frame.
        pass

    if not (last_text or "").strip() and not _LAST_DETAIL:
        parts = []
        if _LAST_AUDIO_PROBE:
            parts.append(_LAST_AUDIO_PROBE)
        if _LAST_SERVER_SUMMARY:
            parts.append(f"server={_LAST_SERVER_SUMMARY}")
        probe = "，".join(parts)
        if probe:
            _LAST_DETAIL = f"{probe}；识别结果为空（可能是模型返回空文本）"
        else:
            _LAST_DETAIL = "识别结果为空（可能是静音、音量低或音频格式不匹配）"
    return (last_text or "").strip()


def _resolve_streaming_resource_id(resource_id: str | None) -> str:
    rid = (resource_id or "").strip()
    if not rid:
        return "volc.seedasr.sauc.duration"
    if ".sauc." in rid:
        return rid
    if rid == "volc.seedasr.auc":
        return "volc.seedasr.sauc.duration"
    if rid == "volc.bigasr.auc":
        return "volc.bigasr.sauc.duration"
    if rid.endswith(".auc"):
        return rid.replace(".auc", ".sauc.duration")
    return rid


def _build_frame(message_type: int, flags: int, serialization: int, compression: int, payload: bytes) -> bytes:
    body = gzip.compress(payload) if compression == 0x1 else payload
    header = bytes(
        [
            (0x1 << 4) | 0x1,
            ((message_type & 0xF) << 4) | (flags & 0xF),
            ((serialization & 0xF) << 4) | (compression & 0xF),
            0x00,
        ]
    )
    return header + struct.pack(">I", len(body)) + body


def _parse_server_frame(frame: bytes) -> dict:
    if len(frame) < 8:
        return {}
    header_size = (frame[0] & 0x0F) * 4
    if len(frame) < header_size + 4:
        return {}
    message_type = (frame[1] >> 4) & 0x0F
    flag = frame[1] & 0x0F
    offset = header_size

    if message_type == 0x9:
        sequence = None
        if flag in {0x1, 0x3} and len(frame) >= offset + 4:
            sequence = struct.unpack(">i", frame[offset : offset + 4])[0]
            offset += 4
        if len(frame) < offset + 4:
            return {}
        payload_size = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        payload = frame[offset : offset + payload_size]
        if (frame[2] & 0x0F) == 0x1:
            try:
                payload = gzip.decompress(payload)
            except Exception:
                return {}
        if ((frame[2] >> 4) & 0x0F) == 0x1:
            try:
                data = json.loads(payload.decode("utf-8", errors="ignore"))
                if isinstance(data, dict):
                    if sequence is not None:
                        data["sequence"] = sequence
                    return data
                return {}
            except Exception:
                return {}
        return {"sequence": sequence} if sequence is not None else {}

    if message_type == 0xF:
        if len(frame) < offset + 8:
            return {"error": {"message": "unknown streaming asr error frame"}}
        code = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        err_size = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        err_payload = frame[offset : offset + err_size]
        try:
            data = json.loads(err_payload.decode("utf-8", errors="ignore"))
        except Exception:
            data = {}
        msg = data.get("message") if isinstance(data, dict) else ""
        return {"error": {"code": code, "message": msg or "streaming asr error"}}

    if len(frame) < offset + 4:
        return {}
    payload_size = struct.unpack(">I", frame[offset : offset + 4])[0]
    offset += 4
    payload = frame[offset : offset + payload_size]
    if (frame[2] & 0x0F) == 0x1:
        try:
            payload = gzip.decompress(payload)
        except Exception:
            return {}
    if ((frame[2] >> 4) & 0x0F) == 0x1:
        try:
            data = json.loads(payload.decode("utf-8", errors="ignore"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_text(resp: dict) -> str:
    if not isinstance(resp, dict):
        return ""
    result = resp.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    text = resp.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


def _extract_error(resp: dict) -> str:
    if not isinstance(resp, dict):
        return ""
    err = resp.get("error")
    if not isinstance(err, dict):
        return ""
    msg = err.get("message")
    code = err.get("code")
    if isinstance(msg, str) and msg.strip():
        return f"code={code} message={msg.strip()}"
    if code is not None:
        return f"code={code}"
    return "unknown error"


def _extract_log_id(resp: dict) -> str:
    if not isinstance(resp, dict):
        return ""
    result = resp.get("result")
    if isinstance(result, dict):
        additions = result.get("additions")
        if isinstance(additions, dict):
            lid = additions.get("log_id")
            if isinstance(lid, str):
                return lid.strip()
    return ""


def get_last_asr_debug() -> tuple[str | None, str | None]:
    return _LAST_DETAIL, _LAST_LOG_ID


def _summarize_server_resp(resp: dict) -> str:
    if not isinstance(resp, dict):
        return "resp=non-dict"
    result = resp.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        txt = text.strip() if isinstance(text, str) else ""
        utterances = result.get("utterances")
        utt_len = len(utterances) if isinstance(utterances, list) else 0
        return f"text_len={len(txt)}, utterances={utt_len}, seq={resp.get('sequence', 'na')}"
    if isinstance(result, list):
        return f"result=list[{len(result)}], seq={resp.get('sequence', 'na')}"
    return f"result_type={type(result).__name__}, seq={resp.get('sequence', 'na')}"


def _build_audio_probe(audio_bytes: bytes, content_type: str | None) -> str:
    size = len(audio_bytes)
    mime = (content_type or "").strip() or "unknown"
    prefix = f"input={mime}, bytes={size}"
    if size <= 64:
        return f"{prefix}, 音频过短"
    if "wav" not in mime.lower():
        return prefix
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            raw = wf.readframes(frames)
        duration_ms = int(frames * 1000 / rate) if rate else 0
        rms, peak = _pcm_stats(raw, width)
        return (
            f"{prefix}, wav={channels}ch/{width * 8}bit/{rate}Hz,"
            f" duration={duration_ms}ms, rms={rms}, peak={peak}"
        )
    except Exception:
        return f"{prefix}, wav解析失败"


def _pcm_stats(raw: bytes, sample_width: int) -> tuple[int, int]:
    if not raw or sample_width not in {1, 2, 4}:
        return 0, 0
    if sample_width == 1:
        samples = [int(b) - 128 for b in raw]
    elif sample_width == 2:
        count = len(raw) // 2
        samples = struct.unpack("<" + "h" * count, raw[: count * 2]) if count else ()
    else:
        count = len(raw) // 4
        samples = struct.unpack("<" + "i" * count, raw[: count * 4]) if count else ()
    if not samples:
        return 0, 0
    peak = max(abs(int(x)) for x in samples)
    mean_square = sum(float(x) * float(x) for x in samples) / len(samples)
    rms = int(math.sqrt(mean_square))
    return rms, peak


def _normalize_stream_audio(audio_bytes: bytes, content_type: str | None) -> tuple[bytes, str, int, int, int]:
    mime = (content_type or "").lower()
    if "wav" in mime:
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                channel = wf.getnchannels()
                bits = wf.getsampwidth() * 8
                rate = wf.getframerate()
                raw_pcm = wf.readframes(wf.getnframes())
            # For streaming chunk upload, send raw PCM bytes instead of chunking WAV container bytes.
            return raw_pcm, "pcm", rate or 16000, bits or 16, channel or 1
        except Exception:
            return audio_bytes, "pcm", 16000, 16, 1
    guessed = _guess_audio_format(content_type)
    if guessed == "ogg":
        return audio_bytes, "ogg", 16000, 16, 1
    if guessed == "mp3":
        return audio_bytes, "mp3", 16000, 16, 1
    return audio_bytes, "pcm", 16000, 16, 1


def _doubao_open_transcribe(audio_bytes: bytes, content_type: str | None = None) -> str:
    app_id = settings.asr_app_id.strip()
    access_token = settings.asr_access_token.strip()
    resource_id = settings.asr_resource_id.strip()
    base = settings.resolved_asr_base_url() or "https://openspeech.bytedance.com"
    if not app_id or not access_token or not resource_id:
        return ""

    fmt = _guess_audio_format(content_type)
    payload = {
        "user": {"uid": "law-digital-human"},
        "audio": {
            "format": fmt,
            "content": base64.b64encode(audio_bytes).decode("ascii"),
        },
        "request": {"model_name": "bigmodel"},
    }
    req_obj = request.Request(
        url=f"{base}{settings.asr_submit_path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Api-App-Key": app_id,
            "X-Api-Access-Key": access_token,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": uuid.uuid4().hex,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with _NO_PROXY_OPENER.open(req_obj, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""

    text = (
        parsed.get("text")
        or parsed.get("result")
        or parsed.get("data", {}).get("text")
        or parsed.get("payload", {}).get("result")
    )
    return text.strip() if isinstance(text, str) else ""


def _doubao_auc_transcribe(audio_bytes: bytes, content_type: str | None = None) -> str:
    global _LAST_DETAIL, _LAST_LOG_ID
    app_id = settings.asr_app_id.strip()
    access_token = settings.asr_access_token.strip()
    resource_id = settings.asr_resource_id.strip() or "volc.bigasr.auc"
    base = settings.resolved_asr_base_url() or "https://openspeech.bytedance.com"
    public_base = settings.asr_audio_public_base_url.strip().rstrip("/")
    if not app_id or not access_token or not public_base:
        _LAST_DETAIL = "AUC缺少配置：ASR_APP_ID/ASR_ACCESS_TOKEN/ASR_AUDIO_PUBLIC_BASE_URL"
        return ""

    suffix = "wav" if "wav" in (content_type or "").lower() else "bin"
    file_name = f"{uuid.uuid4().hex}.{suffix}"
    store_dir = Path(settings.asr_audio_store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    file_path = store_dir / file_name
    file_path.write_bytes(audio_bytes)
    audio_url = f"{public_base}/api/asr/files/{file_name}"
    task_id = uuid.uuid4().hex

    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": task_id,
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    submit_payload = {
        "user": {"uid": "law-digital-human"},
        "audio": {
            "url": audio_url,
            "format": "wav" if "wav" in (content_type or "").lower() else "raw",
            "language": _normalize_asr_language(settings.asr_language),
        },
        "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True, "show_utterances": False},
    }
    submit_req = request.Request(
        url=f"{base}{settings.asr_submit_path}",
        data=json.dumps(submit_payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with _NO_PROXY_OPENER.open(submit_req, timeout=20) as resp:
            _LAST_LOG_ID = resp.headers.get("X-Tt-Logid", "")
            status_code = resp.headers.get("X-Api-Status-Code", "")
            status_msg = resp.headers.get("X-Api-Message", "")
            if status_code and status_code != "20000000":
                _LAST_DETAIL = f"submit失败 status={status_code} msg={status_msg}"
                return ""
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        probe = f"{_LAST_AUDIO_PROBE}，" if _LAST_AUDIO_PROBE else ""
        _LAST_DETAIL = f"{probe}submit HTTPError={exc.code} body={body[:300]}"
        return ""
    except Exception as exc:
        _LAST_DETAIL = f"submit异常={type(exc).__name__}"
        return ""

    query_headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": task_id,
        "Content-Type": "application/json",
    }
    query_req = request.Request(
        url=f"{base}{settings.asr_query_path}",
        data=b"{}",
        headers=query_headers,
        method="POST",
    )
    deadline = time.time() + max(5, int(settings.asr_auc_timeout_sec))
    while time.time() < deadline:
        try:
            with _NO_PROXY_OPENER.open(query_req, timeout=20) as resp:
                _LAST_LOG_ID = resp.headers.get("X-Tt-Logid", "") or _LAST_LOG_ID
                status_code = (resp.headers.get("X-Api-Status-Code") or "").strip()
                status_msg = (resp.headers.get("X-Api-Message") or "").strip()
                body = resp.read().decode("utf-8", errors="ignore")
                parsed = json.loads(body) if body else {}
        except Exception as exc:
            _LAST_DETAIL = f"query异常={type(exc).__name__}"
            return ""

        if status_code in {"20000001", "20000002"}:
            time.sleep(max(0.2, settings.asr_auc_poll_interval_ms / 1000.0))
            continue
        if status_code != "20000000":
            probe = f"{_LAST_AUDIO_PROBE}，" if _LAST_AUDIO_PROBE else ""
            if status_code == "20000003":
                # Retry with flash API using base64 audio.data to bypass remote URL download path.
                flash_text, flash_detail = _doubao_flash_transcribe(audio_bytes, content_type, task_id=task_id)
                if flash_text:
                    _LAST_DETAIL = f"{probe}query静音后，flash兜底成功"
                    return flash_text
                if flash_detail:
                    _LAST_DETAIL = f"{probe}query失败 status={status_code} msg={status_msg}；flash兜底失败: {flash_detail}"
                    return ""
            _LAST_DETAIL = f"{probe}query失败 status={status_code or 'unknown'} msg={status_msg}"
            return ""

        result = parsed.get("result")
        if isinstance(result, dict):
            text = result.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        probe = f"{_LAST_AUDIO_PROBE}，" if _LAST_AUDIO_PROBE else ""
        _LAST_DETAIL = f"{probe}AUC返回成功但文本为空"
        return ""

    probe = f"{_LAST_AUDIO_PROBE}，" if _LAST_AUDIO_PROBE else ""
    _LAST_DETAIL = f"{probe}AUC轮询超时"
    return ""


def _doubao_flash_transcribe(audio_bytes: bytes, content_type: str | None, task_id: str | None = None) -> tuple[str, str]:
    app_id = settings.asr_app_id.strip()
    access_token = settings.asr_access_token.strip()
    resource_id = settings.asr_resource_id.strip() or "volc.bigasr.auc"
    base = settings.resolved_asr_base_url() or "https://openspeech.bytedance.com"
    req_id = task_id or uuid.uuid4().hex
    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": req_id,
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    fmt = "wav" if "wav" in (content_type or "").lower() else "raw"
    payload = {
        "user": {"uid": "law-digital-human"},
        "audio": {
            "data": base64.b64encode(audio_bytes).decode("ascii"),
            "format": fmt,
            "language": _normalize_asr_language(settings.asr_language),
        },
        "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True, "show_utterances": False},
    }
    req = request.Request(
        url=f"{base}/api/v3/auc/bigmodel/recognize/flash",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with _NO_PROXY_OPENER.open(req, timeout=30) as resp:
            status_code = (resp.headers.get("X-Api-Status-Code") or "").strip()
            status_msg = (resp.headers.get("X-Api-Message") or "").strip()
            body = resp.read().decode("utf-8", errors="ignore")
        if status_code and status_code != "20000000":
            return "", f"flash status={status_code} msg={status_msg}"
        parsed = json.loads(body) if body else {}
        result = parsed.get("result")
        if isinstance(result, dict):
            text = result.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip(), ""
        return "", "flash返回成功但文本为空"
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return "", f"flash HTTPError={exc.code} body={body[:200]}"
    except Exception as exc:
        return "", f"flash异常={type(exc).__name__}"
