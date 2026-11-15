package com.vtgt.reviewphim

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.math.exp
import kotlin.math.sqrt

/**
 * VieNeu-TTS chạy trên máy ảo, so với VieNeu bản Python (dữ liệu chuẩn do scripts/vieneu_ref.py tạo trong CI):
 * âm vị (sea-g2p qua JNI) giống hệt, log(giây) giống, giọng nhân bản giống (cosine), đọc câu ra tiếng.
 */
@RunWith(AndroidJUnit4::class)
class VieNeuDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val testAssets = InstrumentationRegistry.getInstrumentation().context.assets

    private fun cos(a: FloatArray, b: List<Double>): Double {
        var d = 0.0; var na = 0.0; var nb = 0.0
        for (i in a.indices) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i] }
        return d / sqrt(na * nb)
    }

    @Test
    fun vieneuOnDevice() = runBlocking {
        val names = testAssets.list("")?.toList() ?: emptyList()
        assumeTrue("không có dữ liệu chuẩn VieNeu (chỉ có trong CI)", "vieneu_ref.json" in names)
        val ref = JSONObject(testAssets.open("vieneu_ref.json").bufferedReader().readText())
        val dir = VieNeu.dir(ctx)
        val bin = File(dir, "sea_g2p.bin")
        if (bin.length() == 0L) testAssets.open("sea_g2p.bin").use { i -> bin.outputStream().use { i.copyTo(it) } }
        // tải mô hình từ Hugging Face (đường thật của app)
        VieNeu.download(ctx, clone = true, log = { Log.i("VieNeuTest", it) }) { _, s -> Log.i("VieNeuTest", s) }
        assertTrue(VieNeu.ready(ctx, clone = true))

        // 1. âm vị: sea-g2p (Rust qua JNI) giống hệt bản Python
        val g2p = SeaG2p(bin.path)
        val texts = ref.getJSONArray("texts")
        val phs = ref.getJSONArray("phonemes")
        for (i in 0 until texts.length()) assertEquals(phs.getString(i), g2p.phonemize(texts.getString(i), true))

        // 2. id + thời lượng dự đoán giống bản Python
        val eng = NanoEngine(dir)
        val ph0 = phs.getString(0)
        val ids = ref.getJSONArray("ids")
        assertEquals((0 until ids.length()).map { ids.getLong(it) }, eng.ids(ph0).toList())
        val voice = VieNeu.presets(ctx).getValue("Minh Quân")
        val logS = eng.logSeconds(ph0, voice)
        assertEquals(ref.getDouble("log_s"), logS, 1e-3)

        // 3. đọc câu: ra tiếng, dài đúng thời lượng dự đoán
        val t0 = System.currentTimeMillis()
        val wav = eng.infer(ph0, voice, steps = 8)
        val secs = wav.size / 24000.0
        val took = (System.currentTimeMillis() - t0) / 1000.0
        Log.i("VieNeuTest", "đọc ${"%.2f".format(secs)} s mất ${"%.1f".format(took)} s (RTF ${"%.2f".format(took / secs)})")
        assertTrue("không có NaN", wav.none { it.isNaN() })
        var e = 0.0
        for (x in wav) e += x * x
        val rms = sqrt(e / wav.size)
        assertTrue("có tiếng (rms=$rms)", rms > 0.01)
        assertTrue("dài ~ ${exp(logS)} s, được $secs s", secs > exp(logS) * 0.5 && secs < exp(logS) + 1.0)

        // 4. nhân bản giọng từ file mẫu: x-vector + style gần như trùng bản Python
        val src = File(ctx.cacheDir, "clone_ref.wav")
        testAssets.open("clone_ref.wav").use { i -> src.outputStream().use { i.copyTo(it) } }
        val w16 = File(ctx.cacheDir, "c16.wav")
        val w24 = File(ctx.cacheDir, "c24.wav")
        Ff.run(ctx, listOf("-i", src.path, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", w16.path))
        Ff.run(ctx, listOf("-i", src.path, "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", w24.path))
        val a = Wav.read(w16)
        val b = Wav.read(w24)
        val cv = eng.cloneVoice("thử", FloatArray(a.data.size) { a.data[it] / 32768f }, FloatArray(b.data.size) { b.data[it] / 32768f })
        val refSpk = ref.getJSONArray("clone_spk").let { j -> (0 until j.length()).map { j.getDouble(it) } }
        val cs = cos(cv.spk, refSpk)
        Log.i("VieNeuTest", "x-vector cosine = $cs")
        assertTrue("x-vector giống bản Python (cos=$cs)", cs > 0.97)
        val shape = ref.getJSONArray("clone_style_shape")
        assertEquals(shape.getInt(0), cv.styleRows)
        val row0 = ref.getJSONArray("clone_style_row0").let { j -> (0 until j.length()).map { j.getDouble(it) } }
        val cst = cos(cv.style.copyOf(row0.size), row0)
        Log.i("VieNeuTest", "style cosine = $cst")
        assertTrue("style giống bản Python (cos=$cst)", cst > 0.9)
        eng.close()

        // 5. đường dùng trong app: nhân bản (có lọc im lặng / chuẩn hóa âm lượng) rồi đọc bằng giọng đó
        val tts = VieNeuTts(ctx)
        val v = tts.clone("Giọng thử", src) { Log.i("VieNeuTest", it) }
        assertTrue("Giọng thử" in VieNeu.allVoices(ctx))
        val out = File(ctx.cacheDir, "vn.wav")
        tts.synth(texts.getString(1), v.name, out, 1f, steps = 8)
        assertTrue("đọc bằng giọng nhân bản: ${Wav.duration(out)} s", Wav.duration(out) > 1.5)
        tts.close()
        VieNeu.deleteVoice(ctx, "Giọng thử")
        g2p.close()
    }
}
