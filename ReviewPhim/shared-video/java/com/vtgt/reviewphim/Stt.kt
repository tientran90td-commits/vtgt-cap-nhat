package com.vtgt.reviewphim

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.abs
import kotlin.math.min

/** Lấy lời gốc: nghe lời thoại (Groq Whisper, miễn phí) hoặc đọc phụ đề cứng trên hình (ML Kit, không cần mạng). */
object Stt {
    /** Groq / OpenAI Whisper. Video dài được cắt từng đoạn 20 phút (giới hạn 25 MB mỗi lần gửi). */
    suspend fun whisper(ctx: Context, prefs: Prefs, src: File, info: VInfo, log: (String) -> Unit,
                        progress: (Float) -> Unit): List<Line> {
        val (base, key, model) = when {
            prefs.key("groq").isNotBlank() -> Triple("https://api.groq.com/openai/v1", prefs.key("groq"), "whisper-large-v3")
            prefs.key("openai").isNotBlank() -> Triple("https://api.openai.com/v1", prefs.key("openai"), "whisper-1")
            else -> throw AiError("Nghe lời thoại cần key Groq (miễn phí, console.groq.com) - nhập ở Cài đặt. " +
                "Hoặc chọn 'Đọc phụ đề trên hình' nếu video có phụ đề cứng.")
        }
        if (!info.hasAudio) throw AiError("Video không có tiếng - hãy chọn 'Đọc phụ đề trên hình'.")
        val chunk = 20 * 60.0
        val n = maxOf(1, Math.ceil(info.duration / chunk).toInt())
        val out = mutableListOf<Line>()
        val lang = prefs.str("src_lang", "")
        for (k in 0 until n) {
            currentCoroutineContext().ensureActive()
            val off = k * chunk
            val mp3 = File(ctx.cacheDir, "speech_$k.mp3")
            log("Nghe lời thoại ${k + 1}/$n...")
            Ff.speechAudio(ctx, src, mp3, off, if (n > 1) chunk else 0.0)
            val segs = withContext(Dispatchers.IO) {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("file", mp3.name, mp3.asRequestBody("audio/mpeg".toMediaType()))
                    .addFormDataPart("model", model)
                    .addFormDataPart("response_format", "verbose_json")
                    .apply { if (lang.isNotEmpty()) addFormDataPart("language", lang) }
                    .build()
                val req = Request.Builder().url("$base/audio/transcriptions").header("Authorization", "Bearer $key")
                    .post(body).build()
                Ai.http.newCall(req).execute().use { r ->
                    val text = r.body?.string() ?: ""
                    if (!r.isSuccessful) throw AiError("Nghe lời thoại lỗi HTTP ${r.code}: ${text.take(200)}")
                    JSONObject(text).optJSONArray("segments")
                }
            }
            mp3.delete()
            if (segs != null) for (i in 0 until segs.length()) {
                val s = segs.getJSONObject(i)
                val t = s.optString("text").trim()
                if (t.isEmpty() || s.optDouble("no_speech_prob", 0.0) > 0.8) continue
                out.add(Line(off + s.optDouble("start"), off + s.optDouble("end"), t))
            }
            progress((k + 1f) / n)
        }
        return cleanLines(out)
    }

    /** Bỏ câu rác hay gặp của Whisper (lặp lại, "subscribe"...). */
    fun cleanLines(lines: List<Line>): List<Line> {
        val junk = Regex("(?i)(subtitles? by|字幕|請不吝點贊|订阅|subscribe|amara\\.org|thanks for watching)")
        val out = mutableListOf<Line>()
        for (l in lines) {
            if (junk.containsMatchIn(l.text) && l.text.length < 40) continue
            if (out.isNotEmpty() && out.last().text == l.text && l.start - out.last().end < 1.0) {
                out[out.size - 1] = out.last().copy(end = l.end)
                continue
            }
            out.add(l)
        }
        return out
    }

    /** Đọc phụ đề cứng trong vùng [top, bottom] (tỉ lệ chiều cao). Chỉ chạy OCR khi vùng chữ đổi hình. */
    suspend fun ocr(src: File, info: VInfo, top: Float, bottom: Float, log: (String) -> Unit,
                    progress: (Float) -> Unit): List<Line> = withContext(Dispatchers.Default) {
        val rec = TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build())
        val mmr = MediaMetadataRetriever()
        mmr.setDataSource(src.absolutePath)
        val w = min(960, info.width)
        val h = (w.toDouble() * info.height / info.width).toInt()
        val step = 0.5
        val out = mutableListOf<Line>()
        var prevSig: IntArray? = null
        var prevText = ""
        var curText = ""
        var curStart = 0.0
        var t = 0.0
        var ocrCount = 0
        fun close(at: Double) {
            if (curText.isNotEmpty() && at - curStart >= 0.4) out.add(Line(curStart, at, curText))
            curText = ""
        }
        try {
            while (t < info.duration) {
                currentCoroutineContext().ensureActive()
                val frame = mmr.getScaledFrameAtTime((t * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST, w, h)
                if (frame != null) {
                    val y0 = (top * frame.height).toInt().coerceIn(0, frame.height - 2)
                    val y1 = (bottom * frame.height).toInt().coerceIn(y0 + 2, frame.height)
                    val band = Bitmap.createBitmap(frame, 0, y0, frame.width, y1 - y0)
                    val sig = signature(band)
                    val text = if (prevSig != null && diff(sig, prevSig) < 4.0) prevText else {
                        ocrCount++
                        clean(recognize(rec, band))
                    }
                    prevSig = sig
                    prevText = text
                    if (text != curText) {
                        if (text.isNotEmpty() && curText.isNotEmpty() && similarity(norm(text), norm(curText)) > 0.75) {
                            if (text.length > curText.length) curText = text // cùng câu, OCR lần này đọc đủ hơn
                        } else {
                            close(t)
                            curText = text
                            curStart = t
                        }
                    }
                    band.recycle()
                    frame.recycle()
                }
                t += step
                progress((t / info.duration).toFloat().coerceAtMost(1f))
            }
            close(info.duration)
        } finally {
            mmr.release()
            rec.close()
        }
        log("Đọc chữ trên hình: ${out.size} câu (OCR $ocrCount khung hình).")
        out
    }

    private fun norm(s: String) = s.replace(Regex("[\\s\\p{Punct}，。！？、：；“”‘’（）《》…]"), "")

    private fun clean(s: String): String {
        val t = s.replace("\n", " ").replace(Regex("\\s+"), " ").trim()
        val meaningful = t.count { it.isLetter() }
        return if (meaningful < 2) "" else t
    }

    private suspend fun recognize(rec: com.google.mlkit.vision.text.TextRecognizer, bmp: Bitmap): String =
        suspendCancellableCoroutine { cont ->
            rec.process(InputImage.fromBitmap(bmp, 0))
                .addOnSuccessListener { cont.resume(it.text) }
                .addOnFailureListener { cont.resumeWithException(it) }
        }

    /** Dấu vân tay nhỏ của vùng chữ (độ sáng 48x12 ô) để biết chữ có đổi không. */
    private fun signature(b: Bitmap): IntArray {
        val s = Bitmap.createScaledBitmap(b, 48, 12, true)
        val px = IntArray(48 * 12)
        s.getPixels(px, 0, 48, 0, 0, 48, 12)
        if (s != b) s.recycle()
        return IntArray(px.size) { val c = px[it]; ((c shr 16 and 255) + (c shr 8 and 255) + (c and 255)) / 3 }
    }

    private fun diff(a: IntArray, b: IntArray): Double {
        var s = 0L
        for (i in a.indices) s += abs(a[i] - b[i])
        return s.toDouble() / a.size
    }
}
