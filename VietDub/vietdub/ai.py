"""Kết nối AI dịch thuật: Gemini, Claude, OpenAI, Groq, OpenRouter, DeepSeek, Ollama (offline).

An toàn & nhanh:
- mỗi lần gọi chạy ở luồng phụ: cứ 15 giây báo "AI vẫn đang viết", bấm Hủy là dừng ngay;
- quá WAIT_LIMIT giây không trả lời -> coi là treo; lỗi / quá tải / treo -> tự chuyển AI khác đã có key;
- giảm "suy nghĩ" của model đời mới (dịch không cần suy luận sâu) -> nhanh gấp nhiều lần;
- đọc JSON chắc chắn, câu trả lời bị cắt giữa chừng vẫn giữ được các đoạn hoàn chỉnh.
"""
from __future__ import annotations

import json
import re
import threading
import time

import requests

from .config import Settings
from .media import Cancelled

PROVIDERS = {
    "auto": {"name": "⚡ Tự chọn (online nếu có key, không thì AI trên máy)", "key": None, "default": "",
             "models": [""], "max_chars": 24_000},
    "gemini": {"name": "Google Gemini (có gói miễn phí)", "key": "gemini", "default": "auto",
               "models": ["auto"], "max_chars": 600_000},
    "claude": {"name": "Anthropic Claude", "key": "claude", "default": "claude-opus-5-5",
               "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], "max_chars": 500_000},
    "openai": {"name": "OpenAI (ChatGPT API)", "key": "openai", "default": "auto", "models": ["auto"],
               "base": "https://api.openai.com/v1", "max_chars": 300_000},
    "groq": {"name": "Groq (rất nhanh, có gói miễn phí)", "key": "groq", "default": "openai/gpt-oss-120b",
             "models": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"], "base": "https://api.groq.com/openai/v1",
             "max_chars": 60_000},
    "openrouter": {"name": "OpenRouter (có DeepSeek miễn phí)", "key": "openrouter", "default": "auto",
                   "models": ["auto"], "base": "https://openrouter.ai/api/v1", "max_chars": 300_000},
    "deepseek": {"name": "DeepSeek", "key": "deepseek", "default": "deepseek-chat", "models": ["deepseek-chat"],
                 "base": "https://api.deepseek.com/v1", "max_chars": 150_000},
    "ollama": {"name": "Ollama - AI chạy trên máy (miễn phí)", "key": None, "default": "qwen2.5:7b",
               "models": ["qwen2.5:7b", "qwen2.5:3b", "gemma3:4b", "llama3.1:8b"], "max_chars": 24_000},
    "none": {"name": "Không dùng AI (tự cắt cảnh nổi bật)", "key": None, "default": "", "models": [""],
             "max_chars": 0},
}
FALLBACK_ORDER = ["gemini", "groq", "claude", "openai", "openrouter", "deepseek"]
WAIT_LIMIT = 300.0
HEARTBEAT = 15.0


class AIError(RuntimeError):
    pass


class _Retry(Exception):
    def __init__(self, msg: str, delay: float = 5.0):
        super().__init__(msg)
        self.delay = delay


_RESOLVED: dict = {}
_NO_THINK: set = set()
USED: dict = {}                    # AI nào đã thực sự trả lời trong lần dịch này (để cảnh báo chất lượng)
OLLAMA_OVERRIDE: str | None = None  # model trên máy hợp ngôn ngữ gốc hơn (vd Qwen cho phim Trung)

# model trên máy dịch kém tiếng Trung / Nhật / Hàn (chủ yếu học tiếng Anh)
_WEAK_CJK = ("llama", "gemma", "mistral", "phi")
CJK_LOCAL = "qwen2.5:7b"


# ------------------------------------------------------------------ tiện ích
def _check(r: requests.Response, name: str) -> dict:
    low = r.text.lower() if r.status_code == 429 else ""
    # hết tiền (OpenAI: insufficient_quota) / hết lượt cả ngày (Gemini: ...PerDay) -> thử lại vô ích, sang AI khác ngay;
    # còn giới hạn theo phút (PerMinute) thì vẫn chờ rồi thử lại
    if "insufficient_quota" in low or ("perday" in low and "perminute" not in low):
        raise AIError(f"{name}: hết hạn mức (gói miễn phí hết lượt hôm nay hoặc tài khoản hết tiền) - "
                      "nạp thêm / đợi sang ngày / dùng key AI khác.")
    if r.status_code in (429, 500, 502, 503, 504, 529):
        delay = 5.0
        m = re.search(r'retry(?:Delay|-after)"?\s*[:=]\s*"?(\d+)', r.text, re.I)
        if m:
            delay = min(60.0, float(m.group(1)))
        elif r.headers.get("retry-after", "").isdigit():
            delay = min(60.0, float(r.headers["retry-after"]))
        raise _Retry(f"{name} bận / quá tải (HTTP {r.status_code})", delay)
    if r.status_code == 402:
        raise AIError(f"{name}: tài khoản API hết tiền (HTTP 402) - nạp thêm hoặc dùng key AI khác.")
    if r.status_code in (401, 403):
        raise AIError(f"{name}: API key sai hoặc không có quyền (HTTP {r.status_code}).")
    if r.status_code >= 400:
        raise AIError(f"{name} lỗi HTTP {r.status_code}: {r.text[:400]}")
    try:
        return r.json()
    except ValueError as e:
        raise AIError(f"{name} trả về không phải JSON: {r.text[:200]}") from e


def extract_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    s, e = t.find("{"), t.rfind("}")
    if s == -1:
        raise AIError("AI không trả về JSON.\n" + (text or "")[:300])
    for cand in (t[s:e + 1], re.sub(r",\s*([\]}])", r"\1", t[s:e + 1])):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    got = _salvage(t[s:])
    if got is not None:
        return got
    raise AIError("Không đọc được JSON từ AI.\n" + (text or "")[:300])


def _salvage(t: str):
    """Câu trả lời bị cắt giữa chừng: giữ các đoạn hoàn chỉnh trước chỗ bị cắt."""
    ends = [m.start() for m in re.finditer(r"\}", t)][::-1][:300]
    for pos in ends:
        for tail in ("]}", "]}]}", "}]}"):
            try:
                d = json.loads(re.sub(r",\s*([\]}])", r"\1", t[:pos + 1] + tail))
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict) and d.get("segments"):
                return d
    return None


def _watch(fn, name: str, log, cancel, limit: float | None = None):
    """Chạy lời gọi mạng ở luồng phụ: báo tiến độ, bấm Hủy dừng ngay, quá WAIT_LIMIT coi như treo."""
    box: dict = {}

    def target():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["e"] = e
    th = threading.Thread(target=target, daemon=True)
    t0 = time.time()
    th.start()
    beat = HEARTBEAT
    while th.is_alive():
        th.join(0.4)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        el = time.time() - t0
        if th.is_alive() and el >= beat:
            beat += HEARTBEAT
            if log:
                log(f"⏳ {name} vẫn đang viết... {int(el)}s")
        if th.is_alive() and el > (limit or WAIT_LIMIT):
            raise _Retry(f"{name} không trả lời sau {int(limit or WAIT_LIMIT)} giây", 0)
    if "e" in box:
        raise box["e"]
    return box.get("v")


# ------------------------------------------------------------------ chọn model
def list_models(provider: str, settings: Settings) -> list[str]:
    if provider == "gemini":
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": settings.key("gemini"), "pageSize": 200}, timeout=30,
                         proxies=settings.proxies())
        data = _check(r, "Gemini")
        return [m["name"].split("/", 1)[1] for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]
    if provider == "claude":
        return PROVIDERS["claude"]["models"]
    if provider == "ollama":
        ok, ms = ollama_status(settings)
        return ms or list(OLLAMA_MODELS)
    if provider == "none":
        return [""]
    base = _base(provider, settings)
    headers = {"Authorization": f"Bearer {settings.key(PROVIDERS[provider]['key'] or '')}"} \
        if PROVIDERS[provider]["key"] else {}
    r = requests.get(f"{base}/models", headers=headers, timeout=30, proxies=settings.proxies())
    data = _check(r, PROVIDERS[provider]["name"])
    return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))


def openrouter_models(settings: Settings) -> list[dict]:
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=30, proxies=settings.proxies())
    return _check(r, "OpenRouter").get("data", [])


def _free(m: dict) -> bool:
    pr = m.get("pricing") or {}
    return str(m.get("id", "")).endswith(":free") or (str(pr.get("prompt")) in ("0", "0.0")
                                                      and str(pr.get("completion")) in ("0", "0.0"))


def pick_openrouter(models: list[dict]) -> str | None:
    """Ưu tiên DeepSeek MIỄN PHÍ (dịch tiếng Trung rất tốt), rồi Qwen miễn phí. Bỏ bản 'suy nghĩ lâu' (R1, distill)
    nếu có bản thường, vì dịch không cần và chậm hơn nhiều."""
    free = [m for m in models if _free(m) and m.get("id")]
    for fam in ("deepseek", "qwen"):
        cands = [m for m in free if fam in m["id"].lower()]
        fast = [m for m in cands if not re.search(r"r1|distill|think|coder|math|vl\b|-vl", m["id"].lower())]
        cands = fast or cands
        if cands:
            return max(cands, key=lambda m: (m.get("created") or 0, _ver(m["id"].split("/")[-1])))["id"]
    return None


def _ver(name: str) -> tuple:
    m = re.search(r"(\d+)(?:\.(\d+))?", name)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def pick_gemini(models: list[str]) -> str | None:
    bad = ("lite", "image", "tts", "audio", "live", "embed", "vision", "learnlm", "aqa", "gemma", "robotics",
           "computer", "native", "exp")
    flash = [m for m in models if m.startswith("gemini") and "flash" in m and not any(b in m for b in bad)]
    if not flash:
        return None
    return max(flash, key=lambda m: (_ver(m), "preview" not in m, -len(m)))


def pick_openai(models: list[str]) -> str | None:
    bad = ("audio", "realtime", "image", "tts", "transcribe", "search", "embedding", "instruct", "codex", "nano")
    cands = [m for m in models if re.match(r"^(gpt-\d|o\d)", m) and not any(b in m for b in bad)
             and not re.search(r"-\d{4}-\d{2}-\d{2}$", m)]
    if not cands:
        return None
    mini = [m for m in cands if "mini" in m]
    return max(mini or cands, key=lambda m: (_ver(m.replace("gpt-", "")), -len(m)))


def resolve_model(provider: str, settings: Settings, log=None) -> str:
    if provider == "ollama":
        return OLLAMA_OVERRIDE or (settings.get("ai", "ollama_model") or PROVIDERS["ollama"]["default"]).strip()
    model = (settings.get("ai", "model") or "auto").strip() if settings.get("ai", "provider") == provider else "auto"
    if model and model != "auto" and model_fits(provider, model):
        return model
    if provider in _RESOLVED:
        return _RESOLVED[provider]
    new = PROVIDERS[provider]["default"]
    if provider in ("gemini", "openai"):
        try:
            ms = list_models(provider, settings)
            new = (pick_gemini(ms) if provider == "gemini" else pick_openai(ms)) or new
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"Không lấy được danh sách model ({e}).", "warn")
        if new == "auto":
            new = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"
    if provider == "openrouter":
        try:
            new = pick_openrouter(openrouter_models(settings)) or "google/gemini-2.5-flash"
        except Exception as e:  # noqa: BLE001
            new = "google/gemini-2.5-flash"
            if log:
                log(f"Không lấy được danh sách model OpenRouter ({e}).", "warn")
    _RESOLVED[provider] = new
    if log:
        log(f"AI {PROVIDERS[provider]['name']}: dùng model {new}")
    return new


def model_fits(provider: str, model: str) -> bool:
    m = (model or "").lower()
    if m in ("", "auto"):
        return True
    if provider == "gemini":
        return m.startswith(("gemini", "gemma"))
    if provider == "claude":
        return m.startswith("claude")
    if provider == "openai":
        return "/" not in m and not m.startswith(("gemini", "claude", "llama", "qwen", "deepseek"))
    return True


def _base(provider: str, settings: Settings) -> str:
    if provider == "ollama":
        return (settings.get("ai", "ollama_url") or "http://localhost:11434/v1").rstrip("/")
    return PROVIDERS[provider]["base"]


# ------------------------------------------------------------------ gọi từng nhà cung cấp
def _gemini(model, system, user, settings, json_mode, max_tokens):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.8}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    major, minor = _ver(model)
    think = None
    if model not in _NO_THINK and model.startswith("gemini"):
        if major >= 3:
            think = {"thinkingLevel": "low"}
        elif (major, minor) >= (2, 5):
            think = {"thinkingBudget": 128 if "pro" in model else 0}
    if think:
        body["generationConfig"]["thinkingConfig"] = think
    kw = dict(params={"key": settings.key("gemini")}, timeout=(20, WAIT_LIMIT + 30), proxies=settings.proxies())
    r = requests.post(url, json=body, **kw)
    if think and r.status_code == 400 and "think" in r.text.lower():
        _NO_THINK.add(model)
        body["generationConfig"].pop("thinkingConfig")
        r = requests.post(url, json=body, **kw)
    if r.status_code == 404:
        _RESOLVED.pop("gemini", None)
    data = _check(r, "Gemini")
    cands = data.get("candidates") or []
    if not cands:
        raise AIError(f"Gemini không trả kết quả: {data.get('promptFeedback', data)}")
    text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []) if not p.get("thought"))
    if not text:
        raise _Retry(f"Gemini trả về rỗng ({cands[0].get('finishReason')})", 3)
    return text


def _openai_like(provider, model, system, user, settings, json_mode, max_tokens):
    base = _base(provider, settings)
    headers = {"Content-Type": "application/json"}
    if PROVIDERS[provider]["key"]:
        headers["Authorization"] = f"Bearer {settings.key(PROVIDERS[provider]['key'])}"
    if provider == "openrouter":
        headers["X-Title"] = "VietDub Studio"
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode and provider != "ollama":
        body["response_format"] = {"type": "json_object"}
    if re.match(r"^(openai/)?(o\d|gpt-5|gpt-oss)", model.lower()) and model not in _NO_THINK:
        body["reasoning_effort"] = "low"
    url = f"{base}/chat/completions"
    kw = dict(headers=headers, timeout=(20, WAIT_LIMIT + 30), proxies=settings.proxies())
    r = requests.post(url, json=body, **kw)
    if r.status_code == 400 and ("reasoning" in r.text or "response_format" in r.text):
        _NO_THINK.add(model)
        body.pop("reasoning_effort", None)
        if "response_format" in r.text:
            body.pop("response_format", None)
        r = requests.post(url, json=body, **kw)
    data = _check(r, PROVIDERS[provider]["name"])
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise AIError(f"Phản hồi lạ: {str(data)[:300]}") from e


def _claude(model, system, user, settings, json_mode, max_tokens):
    try:
        import anthropic
    except ImportError as e:
        raise AIError("Chưa cài thư viện Claude: pip install anthropic") from e
    kwargs = {}
    proxy = (settings.get("net", "proxy") or "").strip()
    if proxy:
        kwargs["http_client"] = anthropic.DefaultHttpxClient(proxy=proxy)
    client = anthropic.Anthropic(api_key=settings.key("claude"), timeout=WAIT_LIMIT + 30, max_retries=2, **kwargs)
    params = dict(model=model, max_tokens=min(max_tokens, 16000), system=system,
                  messages=[{"role": "user", "content": user}], output_config={"effort": "low"})
    try:
        try:  # server-side fallback: nếu model từ chối, API tự chạy lại trên model dự phòng phù hợp
            msg = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        except (TypeError, anthropic.BadRequestError):
            msg = client.messages.create(**params)
    except anthropic.AuthenticationError as e:
        raise AIError("Claude: API key sai.") from e
    except anthropic.RateLimitError as e:
        raise _Retry("Claude quá tải / hết hạn mức", 20) from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise _Retry(f"Claude lỗi máy chủ ({e.status_code})", 10) from e
        raise AIError(f"Claude lỗi: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise _Retry("Không kết nối được Claude", 5) from e
    if msg.stop_reason == "refusal":
        raise AIError("Claude từ chối yêu cầu này.")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# ------------------------------------------------------------------ Ollama (offline)
OLLAMA_MODELS = {
    "qwen2.5:7b": "Qwen2.5 7B - tiếng Việt tốt (khuyên dùng, ~4.7 GB)",
    "qwen2.5:3b": "Qwen2.5 3B - nhanh hơn, máy yếu (~1.9 GB)",
    "gemma3:4b": "Gemma 3 4B - đa ngôn ngữ (~3.3 GB)",
    "qwen2.5:14b": "Qwen2.5 14B - dịch hay hơn, cần máy mạnh, RAM 16 GB+ (~9 GB)",
    "llama3.1:8b": "Llama 3.1 8B - dịch tiếng Trung/Nhật/Hàn kém (~4.9 GB)",
}


def better_local_model(settings: Settings, lang: str, log=None) -> str | None:
    """Phim Trung/Nhật/Hàn mà đang chọn model trên máy yếu tiếng châu Á (Llama, Gemma...) -> dùng Qwen."""
    cur = (settings.get("ai", "ollama_model") or PROVIDERS["ollama"]["default"]).strip()
    if lang not in ("zh", "ja", "ko") or not cur.lower().startswith(_WEAK_CJK):
        return None
    if log:
        log(f"⚠ {cur} dịch tiếng Trung/Nhật/Hàn rất kém → lần này dùng {CJK_LOCAL} (giỏi tiếng Trung hơn; "
            "lần đầu tự tải ~4.7 GB). Đổi hẳn trong ⚙️ Cài đặt → Model AI trên máy.", "warn")
    return CJK_LOCAL


def ollama_url(settings: Settings) -> str:
    u = (settings.get("ai", "ollama_url") or "http://localhost:11434").rstrip("/")
    return u[:-3] if u.endswith("/v1") else u


def ollama_status(settings: Settings) -> tuple[bool, list[str]]:
    """(Ollama có đang chạy không, các model đã tải)."""
    try:
        r = requests.get(f"{ollama_url(settings)}/api/tags", timeout=5)
        if r.ok:
            return True, [m.get("name", "") for m in r.json().get("models", [])]
    except requests.RequestException:
        pass
    return False, []


def ollama_pull(model: str, settings: Settings, log, progress, cancel) -> None:
    """Tải model AI về máy (một lần)."""
    log(f"Tải model AI {model} về máy (một lần, vài GB)...")
    with requests.post(f"{ollama_url(settings)}/api/pull", json={"name": model, "stream": True}, stream=True,
                       timeout=(10, 600)) as r:
        if r.status_code >= 400:
            raise AIError(f"Tải model lỗi: {r.text[:200]}")
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if not line:
                continue
            d = json.loads(line)
            if d.get("error"):
                raise AIError(f"Tải model lỗi: {d['error']}")
            if d.get("total"):
                progress(d.get("completed", 0) / d["total"],
                         f"Tải {model}: {d.get('completed', 0) / 1e9:.1f}/{d['total'] / 1e9:.1f} GB")
    log(f"✅ Đã có model {model}.")


def prepare_ollama(settings: Settings, log=None, cancel=None) -> str:
    """Bảo đảm Ollama đang chạy và có model: tự mở Ollama, tự tải model nếu có mạng. Trả về tên model."""
    from . import hybrid

    model = resolve_model("ollama", settings)
    ok, models = hybrid.ensure_ollama(settings, log)
    if not ok:
        raise AIError("Chưa có Ollama (AI chạy trên máy): cài từ ollama.com (hoặc chạy install.bat) - "
                      "hoặc nhập API key AI online trong ⚙️ Cài đặt.")
    if not hybrid.ollama_has(models, model):
        if settings.mode != "offline" and hybrid.net_ok(settings):
            ollama_pull(model, settings, log or (lambda *_a, **_k: None), lambda *_a, **_k: None, cancel)
        else:
            raise AIError(f"Chưa tải model AI '{model}' về máy. Bấm '⬇ Tải model AI' trong ⚙️ Cài đặt (cần mạng 1 lần).")
    return model


def _ollama(model, system, user, settings, json_mode, max_tokens):
    n_ctx = int(min(32768, max(8192, (len(system) + len(user)) / 2.5 + max_tokens)))
    body = {"model": model, "stream": False, "options": {"num_ctx": n_ctx, "temperature": 0.7,
                                                         "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["format"] = "json"
    r = requests.post(f"{ollama_url(settings)}/api/chat", json=body, timeout=(10, 1800))
    if r.status_code >= 400:
        raise AIError(f"Ollama lỗi {r.status_code}: {r.text[:300]}")
    return (r.json().get("message") or {}).get("content", "")


def _call_once(provider, model, system, user, settings, json_mode, max_tokens):
    if provider == "ollama":
        return _ollama(model, system, user, settings, json_mode, max_tokens)
    if provider == "gemini":
        return _gemini(model, system, user, settings, json_mode, max_tokens)
    if provider == "claude":
        return _claude(model, system, user, settings, json_mode, max_tokens)
    return _openai_like(provider, model, system, user, settings, json_mode, max_tokens)


def available(provider: str, settings: Settings) -> bool:
    k = PROVIDERS[provider]["key"]
    return provider == "ollama" or bool(k and settings.key(k))


def max_chars(settings: Settings) -> int:
    from . import hybrid

    chain = hybrid.ai_chain(settings)
    return PROVIDERS[chain[0]]["max_chars"] if chain else 24_000


def chat(settings: Settings, system: str, user: str, json_mode: bool = True, max_tokens: int = 16000,
         log=None, cancel=None, provider: str | None = None) -> str:
    """Gửi 1 yêu cầu theo chuỗi dự phòng (online <-> trên máy); lỗi tạm thời thì thử lại, treo / hết lượt / mất
    mạng thì tự chuyển sang AI kế tiếp."""
    from . import hybrid

    if provider:
        chain = [provider]
    else:
        chain = hybrid.ai_chain(settings, log)
    if not chain:
        raise AIError("Đang chọn 'Không dùng AI'.")
    last: Exception | None = None
    for pi, prov in enumerate(chain):
        if PROVIDERS[prov]["key"] and not settings.key(PROVIDERS[prov]["key"]):
            last = AIError(f"Chưa nhập API key cho {PROVIDERS[prov]['name']} (mục ⚙️ Cài đặt).")
            continue
        name = PROVIDERS[prov]["name"]
        if pi and log:
            why = f" (vì: {str(last)[:160]})" if last else ""
            log(f"🔀 Chuyển sang {name}{why}.", "warn")
        try:
            model = prepare_ollama(settings, log, cancel) if prov == "ollama" else resolve_model(prov, settings, log)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            if log and pi + 1 < len(chain):
                log(f"{name}: {e}", "warn")
            continue
        for attempt in range(3):
            t0 = time.time()
            try:
                out = _watch(lambda: _call_once(prov, model, system, user, settings, json_mode, max_tokens),
                             name, log, cancel, limit=1800 if prov == "ollama" else WAIT_LIMIT)
                if log:
                    log(f"AI trả lời sau {time.time() - t0:.0f}s ({name} / {model}).")
                USED[prov] = USED.get(prov, 0) + 1
                return out
            except Cancelled:
                raise
            except AIError as e:  # key sai, model lỗi... -> thử AI khác (nếu có)
                last = e
                if log and pi + 1 < len(chain):
                    log(f"{name}: {e}", "warn")
                break
            except _Retry as e:
                last = e
                if "không trả lời" in str(e) or attempt == 2:
                    break  # treo -> sang AI khác luôn
                if log:
                    log(f"{e} - thử lại sau {e.delay:.0f}s...", "warn")
                if cancel is not None and cancel.wait(e.delay):
                    raise Cancelled()
            except requests.ConnectionError as e:  # mất mạng / dịch vụ không kết nối được -> sang AI kế tiếp ngay
                last = e
                if log and pi + 1 < len(chain):
                    log(f"{name}: không kết nối được.", "warn")
                break
            except requests.RequestException as e:
                last = e
                if attempt == 2:
                    break
                if cancel is not None and cancel.wait(3 * (attempt + 1)):
                    raise Cancelled()
    raise AIError(f"Không gọi được AI: {last}")
