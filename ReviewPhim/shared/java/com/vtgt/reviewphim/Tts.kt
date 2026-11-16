package com.vtgt.reviewphim

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.File
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class TtsMissing(msg: String) : Exception(msg)

/** Giọng đọc tiếng Việt có sẵn trong máy (Google / Samsung TTS) - miễn phí, đọc được không cần mạng. */
class Tts(private val ctx: Context) {
    private var tts: TextToSpeech? = null
    private var engineUsed = ""
    private val pending = ConcurrentHashMap<String, CompletableDeferred<Boolean>>()

    suspend fun get(engine: String = ""): TextToSpeech = withContext(Dispatchers.Main) {
        tts?.let { if (engine == engineUsed) return@withContext it else it.shutdown() }
        val t = suspendCancellableCoroutine<TextToSpeech> { cont ->
            var ref: TextToSpeech? = null
            val listener = TextToSpeech.OnInitListener { st ->
                val r = ref
                if (st == TextToSpeech.SUCCESS && r != null) cont.resume(r)
                else cont.resumeWithException(TtsMissing("Không mở được bộ đọc giọng nói của máy."))
            }
            ref = if (engine.isBlank()) TextToSpeech(ctx, listener) else TextToSpeech(ctx, listener, engine)
        }
        val ok = t.setLanguage(Locale("vi", "VN"))
        if (ok == TextToSpeech.LANG_MISSING_DATA || ok == TextToSpeech.LANG_NOT_SUPPORTED) {
            throw TtsMissing("Máy chưa có giọng đọc tiếng Việt: vào Cài đặt app → 'Tải giọng tiếng Việt' (Google Speech Services).")
        }
        t.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) { id?.let { pending.remove(it)?.complete(true) } }
            @Deprecated("Deprecated in Java")
            override fun onError(id: String?) { id?.let { pending.remove(it)?.complete(false) } }
            override fun onError(id: String?, code: Int) { id?.let { pending.remove(it)?.complete(false) } }
        })
        tts = t
        engineUsed = engine
        t
    }

    suspend fun engines(): List<Pair<String, String>> = get().engines.map { it.name to it.label }

    /** Giọng tiếng Việt: (tên, mô tả). */
    suspend fun voices(engine: String = ""): List<Pair<String, String>> {
        val t = get(engine)
        val vs = withContext(Dispatchers.Main) { t.voices?.toList() ?: emptyList<Voice>() }
            .filter { it.locale.language == "vi" }
            .sortedWith(compareBy({ it.isNetworkConnectionRequired }, { it.name }))
        return vs.mapIndexed { i, v ->
            v.name to "Giọng ${i + 1} (${v.name.substringAfterLast("-x-", v.name).substringBefore('-')}" +
                (if (v.isNetworkConnectionRequired) ", cần mạng" else "") + ")"
        }
    }

    /** Đọc 1 câu ra file WAV. */
    suspend fun synth(text: String, out: File, voice: String, rate: Float, engine: String = ""): File {
        val t = get(engine)
        val id = UUID.randomUUID().toString()
        val done = CompletableDeferred<Boolean>()
        pending[id] = done
        withContext(Dispatchers.Main) {
            t.setSpeechRate(rate)
            if (voice.isNotBlank()) t.voices?.firstOrNull { it.name == voice }?.let { t.voice = it }
            val r = t.synthesizeToFile(text, Bundle(), out, id)
            if (r != TextToSpeech.SUCCESS) {
                pending.remove(id)
                throw TtsMissing("Bộ đọc giọng nói từ chối câu này.")
            }
        }
        val ok = withTimeout(90_000) { done.await() }
        if (!ok || !out.exists() || out.length() < 100) throw TtsMissing("Đọc giọng lỗi (thử chọn giọng khác ở Cài đặt).")
        return out
    }

    fun shutdown() {
        tts?.shutdown()
        tts = null
    }
}
