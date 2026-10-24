"""เชื่อม Provider ภายนอก: Claude (Anthropic SDK) และ Gemini (REST)

ไม่ส่ง temperature (API เวอร์ชัน 2026-10-21 ไม่รับแล้ว)
โมเดล Claude ที่รองรับ ใส่ fallbacks: "default" ไว้ เผื่อโมเดลปฏิเสธคำขอ
ถ้าตัวที่เลือกใช้ไม่ได้ service จะลองตัวถัดไปตามลำดับสำรอง แล้วจบที่คำใบ้ต้นฉบับ (Offline)
"""

import asyncio
import time
from dataclasses import dataclass

import anthropic
import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5"}
TIMEOUT = 25.0


class ProviderError(Exception):
    pass


class ProviderBusy(ProviderError):
    """Provider รับงานไม่ไหวชั่วคราว (429, 503) ลองรุ่นสำรองหรือรอแล้วลองใหม่ได้"""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


def _claude_error(error: Exception) -> ProviderError:
    if isinstance(error, anthropic.AuthenticationError):
        return ProviderError("API key ของ Claude ไม่ถูกต้อง")
    if isinstance(error, anthropic.PermissionDeniedError):
        return ProviderError("API key นี้ไม่มีสิทธิ์ใช้โมเดลที่เลือก")
    if isinstance(error, anthropic.NotFoundError):
        return ProviderError("ไม่พบโมเดล Claude ที่เลือก")
    if isinstance(error, anthropic.RateLimitError):
        return ProviderError("Claude ถูกจำกัดอัตราการเรียก ลองใหม่อีกครั้ง")
    if isinstance(error, anthropic.APIStatusError):
        return ProviderError(f"Claude ตอบกลับสถานะ {error.status_code}")
    if isinstance(error, anthropic.APIConnectionError):
        return ProviderError("เชื่อมต่อ Claude ไม่ได้ ตรวจอินเทอร์เน็ต")
    return ProviderError(str(error))


async def call_claude(api_key: str, model: str, system: str, user: str, max_tokens: int = 4096,
                      json_mode: bool = False, timeout: float = TIMEOUT) -> LLMResult:
    """json_mode ของ Claude บอกผ่าน prompt อย่างเดียว ผู้เรียกต้องแยก JSON ออกจากข้อความเอง"""
    started = time.perf_counter()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": "low"},
    }
    try:
        async with anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1) as client:
            try:
                if model in CLAUDE_FALLBACK_MODELS:
                    response = await client.beta.messages.create(
                        **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                    )
                else:
                    response = await client.messages.create(**kwargs)
            except anthropic.BadRequestError:
                # โมเดลรุ่นเก่าบางตัวไม่รับ effort หรือ fallbacks ลองใหม่แบบพื้นฐาน
                response = await client.messages.create(
                    model=model, max_tokens=max_tokens, system=system, messages=kwargs["messages"]
                )
    except anthropic.APIError as error:
        raise _claude_error(error) from error
    if response.stop_reason == "refusal":
        raise ProviderError("Claude ปฏิเสธคำขอนี้")
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
    if not text:
        raise ProviderError("Claude ไม่ได้ส่งข้อความกลับมา")
    return LLMResult(
        text=text,
        provider="claude",
        model=response.model,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def list_claude_models(api_key: str) -> list[str]:
    try:
        async with anthropic.AsyncAnthropic(api_key=api_key, timeout=15.0, max_retries=0) as client:
            return [model.id async for model in client.models.list(limit=100)]
    except anthropic.APIError as error:
        raise _claude_error(error) from error


def _gemini_model(model: str) -> str:
    return model.removeprefix("models/")


async def _post_gemini(url: str, body: dict, api_key: str, timeout: float = TIMEOUT) -> httpx.Response:
    """ส่งคำขอหนึ่งครั้ง ถ้า Google ตอบว่าคิวเต็มชั่วคราว (429, 500, 503) รอสั้น ๆ แล้วลองอีกครั้งเดียว"""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=body, headers={"x-goog-api-key": api_key})
        except httpx.HTTPError as error:
            raise ProviderError("เชื่อมต่อ Gemini ไม่ได้ หรือรอนานเกินไป") from error
        if response.status_code not in (429, 500, 503) or attempt == 1:
            return response
        await asyncio.sleep(1.0)
    return response


async def call_gemini(api_key: str, model: str, system: str, user: str, max_tokens: int = 1024,
                      json_mode: bool = False, timeout: float = TIMEOUT, backup_models: tuple[str, ...] = ()) -> LLMResult:
    """backup_models: รุ่นที่ลองต่อเมื่อรุ่นหลักรับงานไม่ไหว (ใช้ตอนสร้าง Item Bank ซึ่งยาวและพลาดไม่ได้)"""
    for candidate in [model, *[m for m in backup_models if m != model]]:
        try:
            return await _call_gemini_once(api_key, candidate, system, user, max_tokens, json_mode, timeout)
        except ProviderBusy as error:
            busy = error
    raise busy


async def _call_gemini_once(api_key: str, model: str, system: str, user: str, max_tokens: int,
                            json_mode: bool, timeout: float) -> LLMResult:
    started = time.perf_counter()
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # คำใบ้ยาวแค่ 2–3 ประโยค ให้โมเดลคิดน้อยที่สุด: ลดโทเคนที่ใช้คิดจากหลายร้อยเหลือศูนย์และตอบเร็วขึ้น
        "generationConfig": {"maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingLevel": "minimal"}},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    url = f"{GEMINI_BASE}/models/{_gemini_model(model)}:generateContent"
    response = await _post_gemini(url, body, api_key, timeout)
    if response.status_code == 400 and "thinking" in response.text.lower():
        # โมเดลรุ่นที่ไม่รองรับการตั้งระดับการคิด: ส่งใหม่แบบไม่ตั้ง
        body["generationConfig"].pop("thinkingConfig")
        response = await _post_gemini(url, body, api_key, timeout)
    if response.status_code in (400, 401, 403):
        message = response.json().get("error", {}).get("message", "") if response.content else ""
        raise ProviderError(f"Gemini ไม่รับคำขอ: {message[:120] or response.status_code}")
    if response.status_code == 404:
        raise ProviderError("ไม่พบโมเดล Gemini ที่เลือก")
    if response.status_code in (429, 503):
        raise ProviderBusy("Gemini มีผู้ใช้มากชั่วคราว ลองโมเดลอื่นหรือรอสักครู่")
    if response.status_code >= 300:
        raise ProviderError(f"Gemini ตอบกลับสถานะ {response.status_code}")
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "ไม่มีคำตอบ")
        raise ProviderError(f"Gemini ไม่ได้ตอบ: {reason}")
    if candidates[0].get("finishReason") == "MAX_TOKENS":
        # คำตอบถูกตัดกลางประโยค ไม่ส่งให้นักเรียน ใช้คำใบ้ต้นฉบับแทน
        raise ProviderError("คำตอบของ Gemini ถูกตัดเพราะเกินจำนวนโทเคน")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise ProviderError("Gemini ไม่ได้ส่งข้อความกลับมา")
    usage = data.get("usageMetadata") or {}
    return LLMResult(
        text=text,
        provider="gemini",
        model=data.get("modelVersion") or _gemini_model(model),
        tokens_in=usage.get("promptTokenCount", 0),
        tokens_out=usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def list_gemini_models(api_key: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{GEMINI_BASE}/models", params={"pageSize": 200},
                                        headers={"x-goog-api-key": api_key})
    except httpx.HTTPError as error:
        raise ProviderError("เชื่อมต่อ Gemini ไม่ได้ ตรวจอินเทอร์เน็ต") from error
    if response.status_code >= 300:
        raise ProviderError("API key ของ Gemini ไม่ถูกต้อง" if response.status_code in (400, 401, 403)
                            else f"Gemini ตอบกลับสถานะ {response.status_code}")
    models = response.json().get("models", [])
    return [
        _gemini_model(m["name"]) for m in models
        if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m.get("name", "")
    ]
