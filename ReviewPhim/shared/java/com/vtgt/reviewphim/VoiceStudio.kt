package com.vtgt.reviewphim

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit

/**
 * Giọng đọc từ VoiceStudio (github.com/debpalash/VoiceStudio, AGPL-3.0) chạy trên máy tính cùng wifi: app chỉ gọi
 * API chuẩn OpenAI của nó (POST /v1/audio/speech), không chứa code VoiceStudio. Dùng được giọng nhân bản của bạn.
 * Trên máy tính: mở VoiceStudio → bật Network share (lấy mã PIN), hoặc chạy backend với --host 0.0.0.0.
 */
object VoiceStudio {
    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS).readTimeout(90, TimeUnit.SECONDS).callTimeout(120, TimeUnit.SECONDS).build()

    fun url(prefs: Prefs): String {
        var u = prefs.str("vs_url").trim().trimEnd('/')
        if (u.isNotEmpty() && !u.startsWith("http")) u = "http://$u"
        if (u.isNotEmpty() && Regex(":\\d+$").find(u.substringAfter("://")) == null) u += ":3900"
        return u
    }

    fun enabled(prefs: Prefs) = prefs.str("tts_src") == "voicestudio" && url(prefs).isNotEmpty()

    private fun req(prefs: Prefs, path: String): Request.Builder {
        val b = Request.Builder().url(url(prefs) + path)
        prefs.str("vs_key").trim().takeIf { it.isNotEmpty() }?.let { b.header("Authorization", "Bearer $it") }
        prefs.str("vs_pin").trim().takeIf { it.isNotEmpty() }?.let { b.header("X-OmniVoice-Pin", it) }
        return b
    }

    /** Danh sách giọng (cả giọng nhân bản): (id, tên). Ném lỗi dễ hiểu nếu không kết nối được. */
    suspend fun voices(prefs: Prefs): List<Pair<String, String>> = withContext(Dispatchers.IO) {
        if (url(prefs).isEmpty()) throw IllegalStateException("Chưa nhập địa chỉ VoiceStudio (vd 192.168.1.10).")
        try {
            http.newCall(req(prefs, "/v1/audio/voices").build()).execute().use { r ->
                val body = r.body?.string() ?: ""
                if (r.code == 401 || r.code == 403) throw IllegalStateException("VoiceStudio từ chối: nhập đúng mã PIN / key.")
                if (!r.isSuccessful) throw IllegalStateException("VoiceStudio lỗi HTTP ${r.code}")
                val t = body.trim()
                val arr = if (t.startsWith("[")) JSONArray(t) else JSONObject(t).optJSONArray("voices") ?: JSONObject(t).optJSONArray("data") ?: JSONArray()
                (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.map { o ->
                    val id = o.optString("voice_id").ifBlank { o.optString("id") }
                    id to o.optString("name").ifBlank { id }
                }.filter { it.first.isNotBlank() }
            }
        } catch (e: java.io.IOException) {
            throw IllegalStateException("Không kết nối được VoiceStudio ở ${url(prefs)}: máy tính phải bật VoiceStudio, " +
                "bật Network share và cùng wifi với điện thoại.")
        }
    }

    /** Đọc 1 câu -> WAV 24 kHz 16-bit mono (xin dạng pcm thô rồi tự ghi đầu WAV). */
    suspend fun synth(prefs: Prefs, text: String, out: File, speed: Float): File = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("model", prefs.str("vs_model").ifBlank { "omnivoice" })
            .put("input", text)
            .put("voice", prefs.str("vs_voice").ifBlank { "alloy" })
            .put("response_format", "pcm")
            .put("speed", speed.toDouble())
            .put("language", "vi")
        val r = req(prefs, "/v1/audio/speech").post(body.toString().toRequestBody("application/json".toMediaType())).build()
        http.newCall(r).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("VoiceStudio lỗi HTTP ${resp.code}: ${resp.body?.string()?.take(160)}")
            val bytes = resp.body?.bytes() ?: ByteArray(0)
            if (bytes.size < 200) throw IllegalStateException("VoiceStudio trả về âm thanh rỗng")
            val n = bytes.size / 2
            val bb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            Wav.Writer(out).use { w -> w.write(Pcm(24000, ShortArray(n) { bb.getShort(it * 2) })) }
        }
        out
    }
}
