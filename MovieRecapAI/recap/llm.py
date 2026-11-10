"""Kết nối các AI viết kịch bản (LLM).

- Claude (Anthropic): dùng SDK chính thức `anthropic`.
- Gemini: REST API generativelanguage.googleapis.com.
- OpenAI, Groq, DeepSeek, OpenRouter, xAI Grok, Mistral, Qwen, Ollama, LM Studio
  và mọi dịch vụ "OpenAI-compatible": REST /chat/completions.
"""
from __future__ import annotations

import json
import re
import time

import requests

from .config import Settings

# id -> thông tin nhà cung cấp
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "name": "Google Gemini",
        "kind": "gemini",
        "key": "gemini_key",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview"],
        "url_help": "https://aistudio.google.com/apikey",
        "note": "Có gói miễn phí, ngữ cảnh 1 triệu token - rất hợp với phim dài.",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "kind": "anthropic",
        "key": "anthropic_key",
        "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        "url_help": "https://console.anthropic.com/settings/keys",
        "note": "Viết kịch bản tự nhiên, ngữ cảnh 1 triệu token.",
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "kind": "openai",
        "key": "openai_key",
        "base_key": "openai_base",
        "base": "https://api.openai.com/v1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini"],
        "url_help": "https://platform.openai.com/api-keys",
    },
    "groq": {
        "name": "Groq (Llama, Qwen... siêu nhanh)",
        "kind": "openai",
        "key": "groq_key",
        "base": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "qwen/qwen3-32b", "llama-3.1-8b-instant"],
        "url_help": "https://console.groq.com/keys",
        "note": "Miễn phí có giới hạn; ngữ cảnh nhỏ hơn - app tự chia nhỏ transcript.",
        "max_chars": 60000,
    },
    "deepseek": {
        "name": "DeepSeek",
        "kind": "openai",
        "key": "deepseek_key",
        "base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "url_help": "https://platform.deepseek.com/api_keys",
        "max_chars": 150000,
    },
    "openrouter": {
        "name": "OpenRouter (hàng trăm model)",
        "kind": "openai",
        "key": "openrouter_key",
        "base": "https://openrouter.ai/api/v1",
        "models": ["google/gemini-2.5-flash", "anthropic/claude-sonnet-5-5", "openai/gpt-4.1-mini",
                   "deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct:free"],
        "url_help": "https://openrouter.ai/keys",
    },
    "xai": {
        "name": "xAI Grok",
        "kind": "openai",
        "key": "xai_key",
        "base": "https://api.x.ai/v1",
        "models": ["grok-4", "grok-3-mini"],
        "url_help": "https://console.x.ai",
    },
    "mistral": {
        "name": "Mistral AI",
        "kind": "openai",
        "key": "mistral_key",
        "base": "https://api.mistral.ai/v1",
        "models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        "url_help": "https://console.mistral.ai/api-keys",
    },
    "qwen": {
        "name": "Alibaba Qwen (DashScope)",
        "kind": "openai",
        "key": "qwen_key",
        "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "url_help": "https://bailian.console.alibabacloud.com/",
    },
    "ollama": {
        "name": "Ollama (chạy offline trên máy)",
        "kind": "openai",
        "key": None,
        "base_key": "ollama_url",
        "base": "http://localhost:11434/v1",
        "models": ["qwen2.5:14b", "llama3.1:8b", "gemma3:12b", "qwen3:8b"],
        "url_help": "https://ollama.com/download",
        "note": "Miễn phí, không cần mạng. Cần máy mạnh (GPU).",
        "max_chars": 24000,
    },
    "lmstudio": {
        "name": "LM Studio (offline)",
        "kind": "openai",
        "key": None,
        "base_key": "lmstudio_url",
        "base": "http://localhost:1234/v1",
        "models": ["local-model"],
        "url_help": "https://lmstudio.ai",
        "max_chars": 24000,
    },
    "custom": {
        "name": "Tùy chỉnh (OpenAI-compatible)",
        "kind": "openai",
        "key": "custom_key",
        "base_key": "custom_base",
        "base": "",
        "models": [],
        "url_help": "",
    },
    "none": {
        "name": "Không dùng AI (tự chọn đoạn theo thoại)",
        "kind": "none",
        "key": None,
        "models": ["-"],
    },
}


class LLMError(RuntimeError):
    pass


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    proxy = (settings.get("api", "proxy") or "").strip()
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def _base(pid: str, settings: Settings) -> str:
    p = PROVIDERS[pid]
    base = settings.get("api", p["base_key"]) if p.get("base_key") else ""
    return (base or p.get("base") or "").rstrip("/")


def _key(pid: str, settings: Settings) -> str:
    p = PROVIDERS[pid]
    return (settings.get("api", p["key"]) or "").strip() if p.get("key") else ""


def _require_key(pid: str, settings: Settings) -> str:
    k = _key(pid, settings)
    if PROVIDERS[pid].get("key") and not k:
        raise LLMError(f"Chưa nhập API key cho {PROVIDERS[pid]['name']} (mục 🔑 API & Cài đặt).")
    return k


def chat(pid: str, model: str, system: str, user: str, settings: Settings, json_mode: bool = True,
         max_tokens: int = 32000, log=None, images: list[tuple[str, bytes]] | None = None) -> str:
    """Gửi 1 yêu cầu, trả về văn bản trả lời. Tự thử lại khi lỗi mạng/quá tải."""
    kind = PROVIDERS[pid]["kind"]
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            if kind == "anthropic":
                return _chat_anthropic(model, system, user, settings, max_tokens, log, images)
            if kind == "gemini":
                return _chat_gemini(model, system, user, settings, json_mode, max_tokens, images)
            if kind == "openai":
                return _chat_openai(pid, model, system, user, settings, json_mode, max_tokens, images)
            raise LLMError("Nhà cung cấp không hỗ trợ chat")
        except LLMError:
            raise
        except _Retryable as e:
            last_err = e
            wait = 2 ** (attempt + 1)
            if log:
                log(f"AI bận/quá tải ({e}). Thử lại sau {wait}s...", level="warn")
            time.sleep(wait)
        except requests.RequestException as e:
            last_err = e
            wait = 2 ** (attempt + 1)
            if log:
                log(f"Lỗi mạng ({e}). Thử lại sau {wait}s...", level="warn")
            time.sleep(wait)
    raise LLMError(f"Gọi AI thất bại: {last_err}")


class _Retryable(Exception):
    pass


def _check(resp: requests.Response, name: str) -> dict:
    if resp.status_code in (429, 500, 502, 503, 504, 529):
        raise _Retryable(f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        if resp.status_code in (401, 403):
            raise LLMError(f"{name}: API key không hợp lệ hoặc không có quyền ({resp.status_code}). {detail}")
        raise LLMError(f"{name}: lỗi HTTP {resp.status_code}: {detail}")
    return resp.json()


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _chat_openai(pid, model, system, user, settings, json_mode, max_tokens, images=None) -> str:
    base = _base(pid, settings)
    if not base:
        raise LLMError("Chưa nhập Base URL cho nhà cung cấp tùy chỉnh.")
    key = _require_key(pid, settings)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if pid == "openrouter":
        headers["X-Title"] = "Movie Recap AI"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if images:
        parts = []
        for label, data in images:
            parts.append({"type": "text", "text": label})
            parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _b64(data)}})
        parts.append({"type": "text", "text": user})
        body["messages"][1]["content"] = parts
    if json_mode and pid not in ("ollama", "lmstudio", "custom"):
        body["response_format"] = {"type": "json_object"}
    timeout = 900 if pid in ("ollama", "lmstudio") else 600
    r = _session(settings).post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code == 400 and "response_format" in body:
        body.pop("response_format")
        r = _session(settings).post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    data = _check(r, PROVIDERS[pid]["name"])
    try:
        msg = data["choices"][0]["message"]
        return msg.get("content") or ""
    except (KeyError, IndexError):
        raise LLMError(f"Phản hồi lạ: {str(data)[:400]}")


def _chat_gemini(model, system, user, settings, json_mode, max_tokens, images=None) -> str:
    key = _require_key("gemini", settings)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [
            *[p for label, data in (images or []) for p in
              ({"text": label}, {"inlineData": {"mimeType": "image/jpeg", "data": _b64(data)}})],
            {"text": user}]}],
        "generationConfig": {"maxOutputTokens": min(max_tokens, 65536), "temperature": 0.8},
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
            for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                      "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
        ],
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    r = _session(settings).post(url, params={"key": key}, json=body, timeout=600)
    data = _check(r, "Gemini")
    cands = data.get("candidates") or []
    if not cands:
        raise LLMError(f"Gemini không trả kết quả: {data.get('promptFeedback', data)}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text:
        raise LLMError(f"Gemini trả về rỗng (finishReason={cands[0].get('finishReason')}).")
    return text


# Các model Claude hỗ trợ cơ chế tự chuyển model khi bị từ chối (server-side fallback)
_CLAUDE_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1")


def _chat_anthropic(model, system, user, settings, max_tokens, log, images=None) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("Thiếu thư viện 'anthropic'. Chạy: pip install anthropic") from e
    key = _require_key("anthropic", settings)
    kwargs = {}
    proxy = (settings.get("api", "proxy") or "").strip()
    if proxy:
        kwargs["http_client"] = anthropic.DefaultHttpxClient(proxy=proxy)
    client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=900, **kwargs)
    params = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user if not images else [
            *[b for label, data in images for b in
              ({"type": "text", "text": label},
               {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(data)}})],
            {"type": "text", "text": user}]}],
    )
    try:
        if model.startswith(_CLAUDE_FALLBACK_MODELS):
            # Bật fallback phía server: nếu model chính từ chối (vd. phim có cảnh bạo lực),
            # API tự chạy lại bằng model dự phòng phù hợp.
            with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            ) as stream:
                msg = stream.get_final_message()
        else:
            with client.messages.stream(**params) as stream:
                msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError("Claude: API key không hợp lệ.") from e
    except anthropic.PermissionDeniedError as e:
        raise LLMError(f"Claude: key không có quyền dùng model này ({e.message}).") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Claude: không tìm thấy model '{model}'.") from e
    except anthropic.BadRequestError as e:
        raise LLMError(f"Claude: yêu cầu không hợp lệ: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise _Retryable("rate limit") from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise _Retryable(f"HTTP {e.status_code}") from e
        raise LLMError(f"Claude lỗi {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise _Retryable("mất kết nối") from e
    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        raise LLMError(f"Claude từ chối yêu cầu (nhóm: {cat}). Hãy thử model/nhà cung cấp khác.")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    if msg.stop_reason == "max_tokens" and log:
        log("Cảnh báo: kịch bản bị cắt do đạt giới hạn độ dài.", level="warn")
    return text


def list_models(pid: str, settings: Settings) -> list[str]:
    """Lấy danh sách model trực tiếp từ nhà cung cấp."""
    p = PROVIDERS[pid]
    kind = p["kind"]
    s = _session(settings)
    if kind == "none":
        return ["-"]
    if kind == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=_require_key(pid, settings))
        return [m.id for m in client.models.list()]
    if kind == "gemini":
        r = s.get("https://generativelanguage.googleapis.com/v1beta/models",
                  params={"key": _require_key(pid, settings), "pageSize": 200}, timeout=30)
        data = _check(r, "Gemini")
        out = []
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                out.append(m["name"].split("/", 1)[-1])
        return out
    base = _base(pid, settings)
    key = _key(pid, settings)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = s.get(f"{base}/models", headers=headers, timeout=30)
    data = _check(r, p["name"])
    items = data.get("data", data.get("models", []))
    return sorted(m.get("id") or m.get("name") for m in items if isinstance(m, dict))


def test_provider(pid: str, model: str, settings: Settings) -> str:
    txt = chat(pid, model, "Reply with a JSON object.", 'Return {"ok": true}', settings, json_mode=True,
               max_tokens=2000)
    return txt.strip()[:200]


def extract_json(text: str) -> dict:
    """Lấy JSON từ câu trả lời của AI (bỏ ```json, chữ thừa, dấu phẩy thừa...)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("AI không trả về JSON hợp lệ.\n" + text[:500])
    t = t[start:end + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        fixed = re.sub(r",\s*([\]}])", r"\1", t)
        fixed = fixed.replace("“", '"').replace("”", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise LLMError(f"Không đọc được JSON từ AI: {e}\n{text[:500]}") from e
