"""Kết nối các AI viết kịch bản (LLM).

- Claude (Anthropic): dùng SDK chính thức `anthropic`.
- Gemini: REST API generativelanguage.googleapis.com.
- OpenAI, Groq, DeepSeek, OpenRouter, xAI Grok, Mistral, Qwen, Ollama, LM Studio
  và mọi dịch vụ "OpenAI-compatible": REST /chat/completions.
"""
from __future__ import annotations

import json
import re
import threading
import time

import requests

from .config import Settings

# id -> thông tin nhà cung cấp
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "name": "Google Gemini",
        "kind": "gemini",
        "key": "gemini_key",
        # "auto": app tự lấy danh sách model của tài khoản và chọn bản Flash mới nhất còn dùng được
        "models": ["auto", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
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
    "web": {
        "name": "🌐 Dùng bản WEB miễn phí (ChatGPT / Gemini / Claude... copy & dán)",
        "kind": "web",
        "key": None,
        "models": ["aistudio", "chatgpt", "gemini", "claude", "deepseek", "grok", "copilot"],
        "max_chars": 60000,
        "note": "Không cần API key. App copy sẵn câu lệnh & mở trang web, bạn dán vào rồi dán câu trả lời lại vào app. "
                "Khuyên dùng 'aistudio' (Google AI Studio: miễn phí, đọc được phim rất dài).",
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


class ModelNotFound(LLMError):
    """Model không tồn tại / đã ngừng / tài khoản không được dùng -> có thể tự đổi sang model khác."""


class QuotaError(LLMError):
    """Hết tiền / hết hạn mức ngày - thử lại vô ích, nên đổi sang AI khác."""


class TooLarge(LLMError):
    """Yêu cầu dài quá hạn mức token/phút của tài khoản -> cần chia nhỏ transcript."""

    def __init__(self, msg: str, limit_tokens: int = 0):
        super().__init__(msg)
        self.limit_tokens = limit_tokens


class RateLimited(LLMError):
    """Đã thử lại nhiều lần nhưng nhà cung cấp vẫn báo quá tải."""


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


_RESOLVED: dict[tuple[str, str], str] = {}  # (provider, model gốc) -> model thực dùng (trong phiên chạy)


def _version_key(name: str) -> tuple:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", name.split("/")[-1])[:3]]
    stable = 0 if re.search(r"preview|exp|experimental|latest-preview", name) else 1
    return (*(nums + [0, 0, 0])[:3], stable, -len(name))


_SKIP_WORDS = ("tts", "image", "embedding", "embed", "live", "audio", "vision-only", "aqa", "learnlm", "thinking-exp",
               "robotics", "computer-use", "veo", "imagen", "native-audio", "guard", "whisper", "moderation",
               "realtime", "transcribe", "search")


def pick_model(pid: str, old: str, candidates: list[str], kind: str = "text") -> str | None:
    """Chọn model thay thế gần giống `old` nhất (cùng dòng flash/pro/lite/mini...) và mới nhất."""
    old_l = (old or "").lower()
    pool = []
    for c in candidates:
        cl = c.lower()
        if kind == "tts":
            if "tts" not in cl:
                continue
        elif any(w in cl for w in _SKIP_WORDS):
            continue
        if pid == "gemini" and not cl.startswith("gemini"):
            continue
        pool.append(c)
    if not pool:
        return None
    families = ["flash-lite", "flash", "pro", "mini", "nano", "haiku", "sonnet", "opus", "turbo"]
    fam = next((f for f in families if f in old_l), "flash" if pid == "gemini" else None)
    same = [c for c in pool if fam and fam in c.lower() and (fam != "flash" or "lite" not in c.lower())]
    return sorted(same or pool, key=_version_key, reverse=True)[0]


def resolve_model(pid: str, model: str, settings: Settings, log=None, error: str = "", kind: str = "text") -> str:
    """'auto' -> model mới nhất phù hợp; khi model bị báo không tồn tại -> model thay thế (ưu tiên model
    mà chính nhà cung cấp gợi ý trong thông báo lỗi)."""
    key = (pid, model or "auto", kind)
    if not error and key in _RESOLVED:
        return _RESOLVED[key]
    if model and model != "auto" and not error:
        return model
    suggested = next((x for x in re.findall(r"models/([a-z0-9][\w.\-]*[a-z0-9])", error or "")
                      if x != model and (kind != "tts" or "tts" in x)), None)
    try:
        cands = list_models(pid, settings)
    except Exception:  # noqa: BLE001
        cands = []
    if suggested and (not cands or suggested in cands):
        new = suggested
    else:
        new = pick_model(pid, model, [c for c in cands if c != model], kind) or suggested
    if not new:
        if model == "auto":
            new = next((x for x in PROVIDERS[pid]["models"] if x != "auto"), model)
        else:
            raise LLMError(f"Model '{model}' không dùng được và không tìm được model thay thế. "
                           "Bấm 🔄 cạnh ô Model ở Bước 2 để chọn model khác.")
    _RESOLVED[key] = new
    if log and new != model:
        log(f"🔁 Dùng model {new}" + (f" thay cho '{model}' (model cũ đã ngừng hoặc không dùng được)."
                                        if model not in ("", "auto") else " (tự chọn bản mới nhất)."), level="warn")
    return new


FALLBACK_ORDER = ["gemini", "anthropic", "openai", "openrouter", "deepseek", "xai", "mistral", "qwen", "groq"]
_DEAD: dict[str, str] = {}  # nhà cung cấp đã hết tiền/hạn mức trong phiên này -> bỏ qua luôn


def fallback_providers(pid: str, settings: Settings) -> list[str]:
    """Các AI khác mà người dùng đã nhập key (dùng khi AI chính hết tiền/quá tải)."""
    out = []
    for p in FALLBACK_ORDER:
        if p == pid or p in _DEAD:
            continue
        k = PROVIDERS[p].get("key")
        if k and (settings.get("api", k) or "").strip():
            out.append(p)
    return out


# ---- Hủy & theo dõi khi chờ AI trả lời
_tls = threading.local()
WAIT_LIMIT = 300.0   # 1 lần gọi AI quá 5 phút -> coi như treo, chuyển AI khác (hoặc thử lại nếu không có AI khác)
HEARTBEAT = 20.0


def set_cancel(ev) -> None:
    """Gắn sự kiện Hủy của tác vụ đang chạy (theo luồng) - để bấm Hủy dừng ngay cả khi đang chờ AI."""
    _tls.cancel = ev


def _cancel_ev():
    return getattr(_tls, "cancel", None)


def _watch(fn, name: str, log):
    """Chạy lời gọi mạng ở luồng phụ: báo 'vẫn đang viết' định kỳ, bấm Hủy là dừng, quá lâu thì báo treo."""
    from .ffmpeg_utils import Cancelled

    box: dict = {}

    def run():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["e"] = e
    th = threading.Thread(target=run, daemon=True)
    t0 = time.time()
    th.start()
    ev = _cancel_ev()
    next_beat = HEARTBEAT
    while th.is_alive():
        th.join(0.5)
        if ev is not None and ev.is_set():
            raise Cancelled()
        el = time.time() - t0
        if el >= next_beat and th.is_alive():
            next_beat += HEARTBEAT
            if log:
                log(f"⏳ {name} vẫn đang viết... {int(el)}s (bấm Hủy nếu muốn dừng)")
        if el > WAIT_LIMIT and th.is_alive():
            raise _Retryable(f"{name} không trả lời sau {int(WAIT_LIMIT)} giây", delay=0)
    if "e" in box:
        raise box["e"]
    return box.get("v")


def model_fits(pid: str, model: str) -> bool:
    """Tên model có hợp với nhà cung cấp không (vd chọn Gemini mà ô model còn ghi model của Groq)."""
    m = (model or "").strip().lower()
    if m in ("", "auto") or pid not in PROVIDERS:
        return True
    kind = PROVIDERS[pid].get("kind")
    if kind == "gemini":
        return m.startswith(("gemini", "gemma", "learnlm", "models/"))
    if kind == "anthropic":
        return m.startswith("claude")
    if pid == "openai":
        return "/" not in m and not m.startswith(("gemini", "claude", "llama", "mixtral", "qwen", "deepseek"))
    return True


def chat(pid: str, model: str, system: str, user: str, settings: Settings, json_mode: bool = True,
         max_tokens: int = 32000, log=None, images: list[tuple[str, bytes]] | None = None) -> str:
    """Gửi 1 yêu cầu, trả về văn bản trả lời. Tự thử lại khi lỗi mạng/quá tải.
    - Model đã ngừng -> tự chuyển model mới.
    - Hết tiền / quá tải kéo dài -> tự chuyển sang AI khác mà bạn đã nhập key (nếu bật)."""
    if not model_fits(pid, model):
        if log:
            log(f"Model '{model}' không thuộc {PROVIDERS[pid]['name']} - tự chọn model phù hợp.", level="warn")
        model = "auto"
    if pid in _DEAD and settings.get("script", "auto_fallback", True):
        alts = fallback_providers(pid, settings)
        if alts:
            pid, model = alts[0], "auto" if alts[0] == "gemini" else PROVIDERS[alts[0]]["models"][0]
    try:
        return _chat_model(pid, model, system, user, settings, json_mode, max_tokens, log, images)
    except (QuotaError, RateLimited) as e:
        if isinstance(e, QuotaError):
            _DEAD[pid] = str(e)
        if not settings.get("script", "auto_fallback", True):
            raise
        alts = fallback_providers(pid, settings)
        if not alts:
            raise LLMError(f"{e}\n\n👉 Nhập thêm key của AI khác (vd Gemini miễn phí) ở mục 🔑 API & Cài đặt - "
                           "app sẽ tự chuyển sang khi AI này lỗi.") from e
        last = e
        for alt in alts:
            alt_model = "auto" if alt == "gemini" else PROVIDERS[alt]["models"][0]
            if log:
                log(f"🔀 {PROVIDERS[pid]['name']} không dùng được ({str(e).splitlines()[0][:120]}) "
                    f"-> tự chuyển sang {PROVIDERS[alt]['name']}.", level="warn")
            try:
                return _chat_model(alt, alt_model, system, user, settings, json_mode, max_tokens, log, images)
            except (QuotaError, RateLimited, ModelNotFound) as e2:
                if isinstance(e2, QuotaError):
                    _DEAD[alt] = str(e2)
                last = e2
            except TooLarge:
                raise
            except LLMError as e2:
                last = e2
        raise LLMError(f"Tất cả AI đều lỗi. Lỗi cuối: {last}") from e


def _chat_model(pid, model, system, user, settings, json_mode, max_tokens, log, images) -> str:
    if PROVIDERS[pid]["kind"] not in ("none", "web") and (model in ("", "auto") or (pid, model, "text") in _RESOLVED):
        model = resolve_model(pid, model, settings, log)
    try:
        return _chat_once(pid, model, system, user, settings, json_mode, max_tokens, log, images)
    except ModelNotFound as e:
        new = resolve_model(pid, model, settings, log, error=str(e) or "not found")
        if new == model:
            raise
        _RESOLVED[(pid, model, "text")] = new
        if settings.get("script", "provider") == pid and settings.get("script", "model") in (model, "auto", ""):
            if settings.get("script", "model") != "auto":
                settings.set("script", "model", new)
                settings.save()
        return _chat_once(pid, new, system, user, settings, json_mode, max_tokens, log, images)


# ---- Chế độ WEB: giao diện đăng ký 1 hàm "cầu nối" hiện hộp thoại copy & dán cho người dùng
WEB_SITES = {
    "aistudio": ("Google AI Studio (miễn phí, ngữ cảnh 1 triệu token)", "https://aistudio.google.com/prompts/new_chat"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
    "gemini": ("Gemini", "https://gemini.google.com/app"),
    "claude": ("Claude", "https://claude.ai/new"),
    "deepseek": ("DeepSeek", "https://chat.deepseek.com/"),
    "grok": ("Grok", "https://grok.com/"),
    "copilot": ("Microsoft Copilot", "https://copilot.microsoft.com/"),
}
WEB_BRIDGE = None  # callable(site, prompt, json_mode) -> str ; do giao diện gán


def web_prompt(system: str, user: str, json_mode: bool) -> str:
    tail = ("\n\nQUAN TRỌNG: Chỉ trả lời bằng MỘT khối JSON hợp lệ theo đúng cấu trúc yêu cầu ở trên, "
            "không giải thích thêm, không cắt ngắn." if json_mode else "")
    return f"{system.strip()}\n\n{user.strip()}{tail}"


def _chat_once(pid, model, system, user, settings, json_mode, max_tokens, log, images) -> str:
    kind = PROVIDERS[pid]["kind"]
    if kind == "web":
        if WEB_BRIDGE is None:
            raise LLMError("Chế độ dùng bản web chỉ chạy trong giao diện app.")
        if log:
            log(f"🌐 Chờ bạn dán câu trả lời từ {WEB_SITES.get(model, (model,))[0]}...")
        return WEB_BRIDGE(model, web_prompt(system, user, json_mode), json_mode)
    last_err: Exception | None = None
    attempts = 6
    stalls = 0
    name = PROVIDERS[pid]["name"]
    for attempt in range(attempts):
        try:
            if kind == "anthropic":
                return _watch(lambda: _chat_anthropic(model, system, user, settings, max_tokens, log, images), name, log)
            if kind == "gemini":
                t0 = time.time()
                out = _watch(lambda: _chat_gemini(model, system, user, settings, json_mode, max_tokens, images),
                             name, log)
                u = LAST_USAGE or {}
                if log and u:
                    log(f"AI trả lời sau {time.time() - t0:.0f}s · {u.get('candidatesTokenCount', 0):,} token"
                        + (f" (+{u['thoughtsTokenCount']:,} token suy nghĩ)" if u.get("thoughtsTokenCount") else "")
                        + f" · {model}")
                return out
            if kind == "openai":
                return _watch(lambda: _chat_openai(pid, model, system, user, settings, json_mode, max_tokens, images),
                              name, log)
            raise LLMError("Nhà cung cấp không hỗ trợ chat")
        except LLMError:
            raise
        except _Retryable as e:
            last_err = e
            if "không trả lời sau" in str(e):
                stalls += 1
                # có AI khác (đã nhập key) -> chuyển ngay sau 1 lần treo; không có thì thử lại thêm 1 lần
                has_alt = bool(fallback_providers(pid, settings)) and settings.get("script", "auto_fallback", True)
                if stalls >= (1 if has_alt else 2):
                    break
            if attempt == attempts - 1:
                break
            wait = min(65.0, max(getattr(e, "delay", 0.0) + 1, 2 ** (attempt + 1)))
            if log:
                log(f"AI bận/quá tải ({e}). Thử lại sau {wait:.0f}s ({attempt + 1}/{attempts - 1})...", level="warn")
            _sleep(wait)
        except requests.RequestException as e:
            last_err = e
            if isinstance(e, requests.Timeout):
                stalls += 1
                if stalls >= 2:
                    last_err = _Retryable(f"{name} không trả lời (hết thời gian chờ)")
                    break
            wait = 2 ** (attempt + 1)
            if log:
                log(f"Lỗi mạng ({e}). Thử lại sau {wait}s...", level="warn")
            _sleep(wait)
    if isinstance(last_err, _Retryable):
        raise RateLimited(f"{PROVIDERS[pid]['name']} đang quá tải / giới hạn tốc độ ({last_err}). "
                          "Hãy thử lại sau ít phút hoặc dùng AI khác.")
    raise LLMError(f"Gọi AI thất bại: {last_err}")


def _sleep(sec: float) -> None:
    """Chờ nhưng vẫn dừng ngay khi bấm Hủy."""
    from .ffmpeg_utils import Cancelled

    ev = _cancel_ev()
    if ev is None:
        time.sleep(sec)
        return
    end = time.time() + sec
    while time.time() < end:
        if ev is not None and ev.is_set():
            raise Cancelled()
        time.sleep(min(0.5, max(0.0, end - time.time())))


class _Retryable(Exception):
    def __init__(self, msg: str = "", delay: float = 0.0):
        super().__init__(msg)
        self.delay = delay


QUOTA_HELP = {
    "OpenAI (ChatGPT)": "Tài khoản OpenAI hết tiền hoặc chưa nạp tiền (API tính phí riêng, khác gói ChatGPT Plus). "
                        "Nạp tại platform.openai.com/settings/organization/billing",
    "Google Gemini": "Đã dùng hết lượt miễn phí trong ngày của Gemini. Đợi sang ngày mới, bật tính phí, "
                     "hoặc dùng AI khác.",
    "Anthropic Claude": "Tài khoản Anthropic hết tín dụng. Nạp tại console.anthropic.com/settings/billing",
}


def classify_limit(status: int, body: str, name: str, retry_after: str | None = None):
    """Phân loại lỗi 429/413: hết tiền (QuotaError) / yêu cầu quá lớn (TooLarge) / quá tải tạm thời (_Retryable)."""
    low = (body or "").lower()
    if "insufficient_quota" in low or "credit balance" in low or "billing_hard_limit" in low or \
            "perday" in low or "per day" in low or "requests per day" in low or "(rpd)" in low:
        help_ = QUOTA_HELP.get(name, "Tài khoản đã hết tiền/hết hạn mức của dịch vụ này.")
        raise QuotaError(f"{name}: {help_}\nChi tiết: {body[:300]}")
    if "request too large" in low or status == 413 or ("tokens per min" in low and "requested" in low):
        m = re.search(r"limit[\s:]*([\d,]+)", body or "", re.I)
        lim = int(m.group(1).replace(",", "")) if m else 0
        raise TooLarge(f"{name}: yêu cầu dài quá hạn mức token/phút của tài khoản (giới hạn {lim or '?'} token).", lim)
    delay = 0.0
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = 0.0
    m = re.search(r'"?retryDelay"?\s*[:=]\s*"?(\d+(?:\.\d+)?)s', body or "") or \
        re.search(r"(?:try again|retry) in (\d+(?:\.\d+)?)\s*s", body or "", re.I)
    if m:
        delay = max(delay, float(m.group(1)))
    raise _Retryable(f"HTTP {status}", delay)


def _check(resp: requests.Response, name: str) -> dict:
    if resp.status_code in (429, 413):
        classify_limit(resp.status_code, resp.text[:2000], name, resp.headers.get("retry-after"))
    if resp.status_code in (500, 502, 503, 504, 529):
        raise _Retryable(f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        txt = str(detail)
        low = txt.lower()
        if resp.status_code == 404 or "model_not_found" in low or "model_decommissioned" in low or \
                "no longer available" in low or "does not exist" in low or "is not found for api version" in low or \
                ("model" in low and ("not found" in low or "deprecated" in low or "decommissioned" in low)):
            raise ModelNotFound(f"{name}: model không dùng được ({resp.status_code}): {txt[:600]}")
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
    effort = openai_effort(model, _thinking_level(settings))
    if effort:
        body["reasoning_effort"] = effort
    timeout = 900 if pid in ("ollama", "lmstudio") else 600
    r = _session(settings).post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if effort and r.status_code == 400 and "reasoning" in (r.text or "").lower():
        _NO_THINK.add(model)
        body.pop("reasoning_effort", None)
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


# ---- Mức "suy nghĩ" của AI: model đời mới (Gemini 2.5+/3, GPT-5, o-series, gpt-oss) mặc định suy nghĩ rất lâu
# trước khi viết. Viết kịch bản recap không cần suy luận sâu -> mặc định "low" nhanh gấp nhiều lần.
THINKING = {"low": "⚡ Nhanh (khuyên dùng)", "auto": "Mặc định của model", "high": "🧠 Kỹ (chậm, viết sâu hơn)"}
_NO_THINK: set = set()  # model không nhận tham số suy nghĩ
LAST_USAGE: dict = {}   # số token của lần gọi gần nhất (để ghi nhật ký)


def _thinking_level(settings) -> str:
    v = (settings.get("script", "thinking") or "low") if settings is not None else "low"
    return v if v in THINKING else "low"


def gemini_thinking(model: str, level: str) -> dict | None:
    if level == "auto" or model in _NO_THINK:
        return None
    m = re.match(r"gemini-(\d+)(?:\.(\d+))?", model or "")
    if not m:
        return None
    major, minor = int(m.group(1)), int(m.group(2) or 0)
    if major >= 3:
        return {"thinkingLevel": "low" if level == "low" else "high"}
    if (major, minor) >= (2, 5):
        if "pro" in model:  # bản pro không tắt hẳn được
            return {"thinkingBudget": 128 if level == "low" else -1}
        return {"thinkingBudget": 0 if level == "low" else -1}
    return None


def openai_effort(model: str, level: str) -> str | None:
    if level == "auto" or model in _NO_THINK:
        return None
    if re.match(r"^(openai/)?(o\d|gpt-5|gpt-oss)", (model or "").lower()):
        return "low" if level == "low" else "high"
    return None


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
    think = gemini_thinking(model, _thinking_level(settings))
    if think:
        body["generationConfig"]["thinkingConfig"] = think
    r = _session(settings).post(url, params={"key": key}, json=body, timeout=(20, WAIT_LIMIT + 30))
    if think and r.status_code == 400 and "think" in (r.text or "").lower():
        _NO_THINK.add(model)  # model không hỗ trợ -> gửi lại không kèm
        body["generationConfig"].pop("thinkingConfig", None)
        r = _session(settings).post(url, params={"key": key}, json=body, timeout=(20, WAIT_LIMIT + 30))
    data = _check(r, "Gemini")
    global LAST_USAGE
    LAST_USAGE = data.get("usageMetadata") or {}
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
        raise ModelNotFound(f"Claude: không tìm thấy model '{model}'.") from e
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e.message).lower():
            raise QuotaError(f"Anthropic Claude: {QUOTA_HELP['Anthropic Claude']}") from e
        raise LLMError(f"Claude: yêu cầu không hợp lệ: {e.message}") from e
    except anthropic.RateLimitError as e:
        classify_limit(429, str(e.message), "Anthropic Claude", e.response.headers.get("retry-after"))
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
    if kind in ("none", "web"):
        return list(p["models"])
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
            got = _salvage(text[text.find("{"):])
            if got is not None:
                return got
            raise LLMError(f"Không đọc được JSON từ AI: {e}\n{text[:500]}") from e


def _salvage(t: str):
    """Câu trả lời bị cắt giữa chừng (hết giới hạn độ dài): giữ lại mọi đoạn hoàn chỉnh trước chỗ bị cắt."""
    ends = [m.start() for m in re.finditer(r"\}", t)][::-1][:300]
    for pos in ends:
        head = t[:pos + 1]
        for tail in ("]}", "]}]}", "}]}", "]}}"):
            try:
                d = json.loads(re.sub(r",\s*([\]}])", r"\1", head + tail))
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict) and (d.get("segments") or d.get("frames") or len(d) > 1):
                return d
    return None
