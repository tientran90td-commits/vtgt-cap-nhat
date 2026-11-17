package com.vtgt.reviewphim

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class AiError(msg: String) : Exception(msg)

/** Hỏi AI online qua API chính thức (chuẩn OpenAI). Không có key nào -> người dùng dán tay qua DeepSeek web. */
object Ai {
    data class Prov(val id: String, val name: String, val base: String, val models: List<String>, val keyUrl: String,
                    val note: String)

    val PROVS = listOf(
        Prov("deepseek", "DeepSeek", "https://api.deepseek.com/v1", listOf("deepseek-chat"),
            "https://platform.deepseek.com/api_keys", "dịch tiếng Trung rất tốt, giá rẻ (phải nạp tiền)"),
        Prov("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
            listOf("auto", "gemini-2.5-flash"), "https://aistudio.google.com/apikey", "có gói miễn phí"),
        Prov("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", listOf("auto"),
            "https://openrouter.ai/keys", "tự dùng DeepSeek miễn phí"),
        Prov("groq", "Groq", "https://api.groq.com/openai/v1", listOf("openai/gpt-oss-120b", "llama-3.3-70b-versatile"),
            "https://console.groq.com/keys", "miễn phí, rất nhanh - cũng dùng để nghe lời thoại"),
        Prov("openai", "OpenAI", "https://api.openai.com/v1", listOf("auto", "gpt-4o-mini"),
            "https://platform.openai.com/api-keys", "trả phí"),
    )

    /**
     * Máy chủ AI riêng (chuẩn OpenAI): LiteLLM proxy (tự thử lại, xoay nhiều key, chuyển AI dự phòng),
     * Ollama / LM Studio / llama.cpp trên máy tính nhà... Có địa chỉ thì dùng trước tiên.
     */
    val CUSTOM = Prov("custom", "Máy chủ AI riêng", "", listOf("auto"), "https://docs.litellm.ai/docs/simple_proxy",
        "LiteLLM / Ollama / LM Studio")

    /** "192.168.1.10:4000" -> "http://192.168.1.10:4000/v1". */
    fun customBase(prefs: Prefs): String = normBase(prefs.str("custom_url"))

    fun normBase(raw: String): String {
        var u = raw.trim().trimEnd('/')
        if (u.isEmpty()) return ""
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://$u"
        if (!Regex("/v\\d+(beta)?(/openai)?$").containsMatchIn(u) && !u.endsWith("/api")) u += "/v1"
        return u
    }

    private fun base(p: Prov, prefs: Prefs) = if (p.id == "custom") customBase(prefs) else p.base

    private fun keysOf(p: Prov, prefs: Prefs): List<String> =
        if (p.id == "custom") prefs.keys("custom").ifEmpty { listOf(prefs.str("key_custom").trim().ifEmpty { "sk-none" }) } else prefs.keys(p.id)

    /** Lượt key đang dùng của mỗi AI (xoay vòng). */
    private val keyAt = mutableMapOf<String, Int>()

    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(100, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .callTimeout(120, TimeUnit.SECONDS)   // 1 lần gọi tối đa 2 phút (Gemini quá tải từng treo 4 phút mới báo 503)
        .build()

    /** Tổng thời gian chờ API cho 1 yêu cầu (mọi AI, mọi lần thử); quá thì chuyển sang làm tay. */
    const val BUDGET_MS = 150_000L

    private val resolved = mutableMapOf<String, String>()
    private val JSON_TYPE = "application/json".toMediaType()

    fun chain(prefs: Prefs): List<Prov> =
        (if (customBase(prefs).isNotEmpty()) listOf(CUSTOM) else emptyList()) + PROVS.filter { prefs.keys(it.id).isNotEmpty() }

    fun manual(prefs: Prefs): Boolean = prefs.str("ai", "auto") == "manual" || chain(prefs).isEmpty()

    /** Gửi 1 yêu cầu theo thứ tự các AI có key; AI hỏng / hết tiền / hết lượt -> sang AI kế tiếp. */
    /** AI nhìn được ảnh (DeepSeek không nhìn được ảnh). */
    fun visionChain(prefs: Prefs): List<Prov> = chain(prefs).filter { it.id != "deepseek" && (it.id != "custom" || prefs.str("custom_vmodel") != "-") }

    suspend fun chat(prefs: Prefs, system: String, user: String, log: (String) -> Unit, json: Boolean = true,
                     images: List<java.io.File> = emptyList()): String {
        val provs = if (images.isEmpty()) chain(prefs) else visionChain(prefs)
        if (provs.isEmpty()) throw AiError(if (images.isEmpty()) "Chưa nhập key AI nào (mục Cài đặt)."
            else "Chưa có key AI nhìn được ảnh (Gemini / OpenRouter / Groq / OpenAI).")
        var last: Exception? = null
        val t00 = System.currentTimeMillis()
        for ((i, p) in provs.withIndex()) {
            if (System.currentTimeMillis() - t00 > BUDGET_MS) break
            if (i > 0) log("🔀 Chuyển sang ${p.name} (vì: ${last?.message?.take(140)})")
            val ks = keysOf(p, prefs)
            val start = (keyAt[p.id] ?: 0) % ks.size
            var tried = 0          // số key đã thử của AI này
            var waits = 0          // số lần đã chờ để thử lại (chờ tăng dần như tenacity)
            while (tried < ks.size && System.currentTimeMillis() - t00 <= BUDGET_MS) {
                val ki = (start + tried) % ks.size
                try {
                    val model = if (images.isEmpty()) model(p, prefs, ks[ki]) else visionModel(p, prefs, ks[ki])
                    val t0 = System.currentTimeMillis()
                    val (out, used) = call(p, model, ks[ki], system, user, json, images, base(p, prefs))
                    keyAt[p.id] = ki
                    record(prefs, p.id, used.first, used.second)
                    log("AI ${p.name}${if (ks.size > 1) " (key ${ki + 1}/${ks.size})" else ""} ($model) trả lời sau ${(System.currentTimeMillis() - t0) / 1000}s")
                    return out
                } catch (e: CancellationException) {
                    throw e
                } catch (e: RetryLater) {
                    last = e
                    if (tried + 1 < ks.size) {               // còn key khác: đổi key ngay, khỏi chờ
                        log("${e.message} → đổi sang key ${(ki + 1) % ks.size + 1}/${ks.size}")
                        keyAt[p.id] = (ki + 1) % ks.size
                        tried++
                        continue
                    }
                    val left = BUDGET_MS - (System.currentTimeMillis() - t00)
                    val ms = backoff(waits, e.waitSec)
                    if (waits >= 3 || ms > left - 5000) break
                    waits++
                    log("${e.message} - thử lại sau ${ms / 1000}s (lần $waits/3)")
                    delay(ms)
                    tried = 0
                } catch (e: KeyError) {                      // key hết tiền / hết lượt / sai: sang key kế
                    last = e
                    if (tried + 1 < ks.size) log("${e.message} → đổi sang key ${(ki + 1) % ks.size + 1}/${ks.size}")
                    keyAt[p.id] = (ki + 1) % ks.size
                    tried++
                } catch (e: IOException) {
                    last = AiError("${p.name}: ${if (e is java.io.InterruptedIOException) "chờ quá lâu không trả lời" else "lỗi mạng / không kết nối được"}")
                    if (waits >= 2 || p.id == "custom") break
                    waits++
                    delay(backoff(waits, 0))
                } catch (e: Exception) {
                    last = e
                    break
                }
            }
        }
        throw AiError("Không AI nào trả lời được: ${last?.message}")
    }

    private class RetryLater(msg: String, val waitSec: Int) : Exception(msg)

    /** Thống kê dùng AI trong ngày (số lần gọi, token gửi / nhận) theo từng AI - cách BatchLLM theo dõi chi phí. */
    @Synchronized
    private fun record(prefs: Prefs, id: String, tin: Long, tout: Long) {
        val day = java.text.SimpleDateFormat("yyyyMMdd", java.util.Locale.US).format(java.util.Date())
        if (prefs.str("use_day") != day) {
            (PROVS + CUSTOM).forEach { prefs.set("use_${it.id}", "") }
            prefs.set("use_day", day)
        }
        val v = prefs.str("use_$id").split(';').mapNotNull { it.toLongOrNull() }.let { if (it.size == 3) it else listOf(0L, 0L, 0L) }
        prefs.set("use_$id", "${v[0] + 1};${v[1] + tin};${v[2] + tout}")
    }

    /** "Hôm nay: Gemini 120 lần · 350k token..." */
    fun usageText(prefs: Prefs): String {
        val day = java.text.SimpleDateFormat("yyyyMMdd", java.util.Locale.US).format(java.util.Date())
        if (prefs.str("use_day") != day) return "Hôm nay chưa gọi AI nào."
        val rows = (listOf(CUSTOM) + PROVS).mapNotNull { p ->
            val v = prefs.str("use_${p.id}").split(';').mapNotNull { it.toLongOrNull() }
            if (v.size != 3 || v[0] == 0L) null else "${p.name}: ${v[0]} lần · ${fmtTok(v[1] + v[2])} token (gửi ${fmtTok(v[1])}, nhận ${fmtTok(v[2])})"
        }
        return if (rows.isEmpty()) "Hôm nay chưa gọi AI nào." else "Hôm nay:\n" + rows.joinToString("\n")
    }

    fun fmtTok(n: Long): String = when {
        n >= 1_000_000 -> "%.1fM".format(java.util.Locale.US, n / 1e6)
        n >= 1_000 -> "${n / 1000}k"
        else -> "$n"
    }

    /**
     * Thời gian chờ trước lần thử lại thứ [n] (0..): tăng dần 2 → 4 → 8 giây + ngẫu nhiên tới 1 giây (cách tenacity
     * "wait_exponential + jitter"); AI báo phải chờ bao lâu ([asked] giây, header Retry-After) thì chờ đủ (tối đa 30 giây).
     */
    fun backoff(n: Int, asked: Int, rnd: kotlin.random.Random = kotlin.random.Random): Long {
        val exp = (2000L shl n.coerceIn(0, 4)).coerceAtMost(16_000L)
        val want = if (asked > 0) maxOf(exp, asked.coerceAtMost(30) * 1000L) else exp
        return want + rnd.nextLong(0, 1000)
    }

    /** Lỗi do key (hết tiền, hết lượt, sai key): đổi key khác của cùng AI. */
    private class KeyError(msg: String) : Exception(msg)

    private suspend fun call(p: Prov, model: String, key: String, system: String, user: String, json: Boolean,
                             images: List<java.io.File>, base: String): Pair<String, Pair<Long, Long>> =
        withContext(Dispatchers.IO) {
            val content: Any = if (images.isEmpty()) user else JSONArray().apply {
                put(JSONObject().put("type", "text").put("text", user))
                for (f in images) put(JSONObject().put("type", "image_url").put("image_url", JSONObject()
                    .put("url", "data:image/jpeg;base64," + android.util.Base64.encodeToString(f.readBytes(), android.util.Base64.NO_WRAP))))
            }
            val body = JSONObject()
                .put("model", model)
                .put("temperature", if (images.isEmpty()) 0.7 else 0.3)
                .put("messages", JSONArray()
                    .put(JSONObject().put("role", "system").put("content", system))
                    .put(JSONObject().put("role", "user").put("content", content)))
            if (json) body.put("response_format", JSONObject().put("type", "json_object"))
            if (model.startsWith("openai/gpt-oss")) body.put("reasoning_effort", "low")
            var (code, text, after) = post("$base/chat/completions", key, body)
            if (code == 400 && json && text.contains("response_format")) {
                body.remove("response_format")
                val r = post("$base/chat/completions", key, body)
                code = r.first
                text = r.second
                after = r.third
            }
            check(p, code, text, after)
            val o = JSONObject(text)
            val msg = o.getJSONArray("choices").getJSONObject(0).getJSONObject("message")
            val content = msg.optString("content", "")
            // token đã dùng (AI báo trong "usage"; không có thì ước tính ~4 ký tự / token)
            val u = o.optJSONObject("usage")
            val tin = u?.optLong("prompt_tokens", -1)?.takeIf { it >= 0 } ?: ((system.length + user.length) / 4L + images.size * 1000L)
            val tout = u?.optLong("completion_tokens", -1)?.takeIf { it >= 0 } ?: (content.length / 4L)
            content to (tin to tout)
        }

    /** (mã HTTP, nội dung, số giây AI yêu cầu chờ - header Retry-After). */
    private fun post(url: String, key: String, body: JSONObject): Triple<Int, String, Int?> {
        val req = Request.Builder().url(url)
            .header("Authorization", "Bearer $key")
            .header("X-Title", "ReviewPhim AI")
            .post(body.toString().toRequestBody(JSON_TYPE))
            .build()
        http.newCall(req).execute().use { r ->
            return Triple(r.code, r.body?.string() ?: "", r.header("Retry-After")?.trim()?.toDoubleOrNull()?.toInt())
        }
    }

    private fun check(p: Prov, code: Int, text: String, after: Int? = null) {
        if (code in 200..299) return
        val low = text.lowercase()
        when {
            code == 402 || "insufficient_quota" in low || "insufficient balance" in low ->
                throw KeyError("${p.name}: tài khoản API hết tiền / hết hạn mức")
            code == 401 || code == 403 -> throw KeyError("${p.name}: key sai hoặc không có quyền (HTTP $code)")
            code == 429 && ("perday" in low || "per day" in low) -> throw KeyError("${p.name}: hết lượt miễn phí hôm nay")
            code == 429 || code >= 500 -> {
                val wait = after ?: Regex("retry[^0-9]{0,12}(\\d+)", RegexOption.IGNORE_CASE).find(text)?.groupValues?.get(1)
                    ?.toIntOrNull()?.coerceIn(3, 60) ?: 0
                throw RetryLater("${p.name} đang bận (HTTP $code)", wait)
            }
            code == 404 || (code == 400 && "model" in low) -> {
                resolved.remove(p.id)
                throw AiError("${p.name}: model không dùng được (HTTP $code)")
            }
            else -> throw AiError("${p.name} lỗi HTTP $code: ${text.take(200)}")
        }
    }

    /** Model: tự chọn model mới, hợp việc dịch (Gemini Flash, GPT mini, DeepSeek miễn phí trên OpenRouter). */
    private suspend fun model(p: Prov, prefs: Prefs, key: String): String {
        if (p.id == "custom") prefs.str("custom_model").trim().takeIf { it.isNotEmpty() }?.let { return it }
        resolved[p.id]?.let { return it }
        val first = p.models.first()
        if (first != "auto") return first.also { resolved[p.id] = it }
        val ids = try {
            listModels(base(p, prefs), key)
        } catch (e: Exception) {
            emptyList()
        }
        val pick = when (p.id) {
            "gemini" -> ids.map { it.removePrefix("models/") }
                .filter { it.startsWith("gemini") && "flash" in it && listOf("lite", "image", "tts", "live", "audio", "exp", "preview").none { b -> b in it } }
                .maxByOrNull { version(it) }
            "openai" -> ids.filter { Regex("^gpt-\\d").containsMatchIn(it) && "mini" in it &&
                listOf("audio", "realtime", "search", "transcribe", "tts", "nano").none { b -> b in it } &&
                !Regex("-\\d{4}-\\d{2}-\\d{2}$").containsMatchIn(it) }.maxByOrNull { version(it) }
            "openrouter" -> openRouterFree(ids)
            "custom" -> ids.firstOrNull() ?: throw AiError("Máy chủ AI riêng: chưa có model nào - nhập tên model ở Cài đặt.")
            else -> null
        } ?: p.models.getOrNull(1) ?: "deepseek/deepseek-chat"
        resolved[p.id] = pick
        return pick
    }

    /** Model nhìn được ảnh: Gemini Flash, GPT mini, Llama 4 trên Groq, model miễn phí có thị giác trên OpenRouter. */
    private suspend fun visionModel(p: Prov, prefs: Prefs, key: String): String = when (p.id) {
        "groq" -> "meta-llama/llama-4-scout-17b-16e-instruct"
        "openrouter" -> resolved["openrouter-vision"] ?: (openRouterVision(try {
            listModels(base(p, prefs), key)
        } catch (e: Exception) {
            emptyList()
        }) ?: "google/gemma-3-27b-it:free").also { resolved["openrouter-vision"] = it }
        "custom" -> prefs.str("custom_vmodel").trim().takeIf { it.isNotEmpty() } ?: model(p, prefs, key)
        else -> model(p, prefs, key)
    }

    /** Kiểm tra máy chủ AI riêng: danh sách model. */
    suspend fun testCustom(prefs: Prefs): List<String> {
        val b = customBase(prefs)
        if (b.isEmpty()) throw AiError("Chưa nhập địa chỉ.")
        return listModels(b, keysOf(CUSTOM, prefs).first())
    }

    fun openRouterVision(ids: List<String>): String? {
        val free = ids.filter { it.endsWith(":free") }
        for (fam in listOf("google/gemini", "qwen2.5-vl|qwen3-vl|qwen-vl", "llama-4", "gemma-3", "mistral-small-3")) {
            val r = Regex(fam)
            free.filter { r.containsMatchIn(it.lowercase()) && "thinking" !in it }.maxByOrNull { version(it.substringAfter('/')) }?.let { return it }
        }
        return null
    }

    private fun version(s: String): Double =
        Regex("(\\d+)(?:\\.(\\d+))?").find(s)?.let { it.groupValues[1].toDouble() + (it.groupValues[2].toDoubleOrNull() ?: 0.0) / 10 } ?: 0.0

    /** Ưu tiên DeepSeek miễn phí (bản thường, không phải R1 suy nghĩ lâu), rồi Qwen miễn phí. */
    fun openRouterFree(ids: List<String>): String? {
        val free = ids.filter { it.endsWith(":free") }
        for (fam in listOf("deepseek", "qwen")) {
            val c = free.filter { fam in it.lowercase() }
            val fast = c.filter { !Regex("r1|distill|think|coder|math|-vl").containsMatchIn(it.lowercase()) }
            (fast.ifEmpty { c }).maxByOrNull { version(it.substringAfter('/')) }?.let { return it }
        }
        return null
    }

    private suspend fun listModels(base: String, key: String): List<String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("$base/models").header("Authorization", "Bearer $key").build()
        http.newCall(req).execute().use { r ->
            val arr = JSONObject(r.body?.string() ?: "{}").optJSONArray("data") ?: JSONArray()
            (0 until arr.length()).map { arr.getJSONObject(it).optString("id") }.filter { it.isNotEmpty() }
        }
    }
}
