package com.vtgt.reviewphim

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sin

class VieNeuTest {
    @Test
    fun fbankMatchesKaldi() {
        // cùng tín hiệu thử như fbank_ref.py; giá trị chuẩn tính bằng kaldi-native-fbank
        val wav = FloatArray(16000) {
            val t = it / 16000.0
            (0.3 * sin(2 * PI * 220 * t) + 0.1 * sin(2 * PI * 1234 * t) + 0.05 * sin(2 * PI * 3500 * t * t)).toFloat()
        }
        val fb = Fbank.compute(wav, meanNorm = false)
        assertEquals(98, fb.size)
        val ref = JSONObject(javaClass.classLoader!!.getResource("fbank_ref.json")!!.readText())
        val rows = ref.getJSONArray("rows")
        val vals = ref.getJSONArray("values")
        var worst = 0.0
        for (k in 0 until rows.length()) {
            val r = rows.getInt(k)
            val v = vals.getJSONArray(k)
            for (b in 0 until 80) worst = maxOf(worst, abs(fb[r][b] - v.getDouble(b)))
        }
        assertTrue("fbank lệch kaldi: $worst", worst < 5e-3)
        val norm = Fbank.compute(wav, meanNorm = true)
        assertEquals(ref.getDouble("mean_row7"), norm[7].average(), 1e-3)
    }

    @Test
    fun fftIsCorrect() {
        val re = DoubleArray(8) { if (it == 1) 1.0 else 0.0 }
        val im = DoubleArray(8)
        Fbank.fft(re, im)
        for (k in 0 until 8) {  // FFT của xung tại 1: e^{-2πik/8}
            assertEquals(kotlin.math.cos(2 * PI * k / 8), re[k], 1e-9)
            assertEquals(-sin(2 * PI * k / 8), im[k], 1e-9)
        }
    }

    @Test
    fun npz() {
        val f = File(javaClass.classLoader!!.getResource("t.npz")!!.toURI())
        val z = Npy.npz(f)
        assertEquals(listOf(0f, 1f, 2f, 3f), z.getValue("null_spk").data.toList())
        assertEquals(0.5f, z.getValue("latent_scale").data[0])
        assertEquals(listOf(2, 3), z.getValue("null_style").shape.toList())
    }

    @Test
    fun chunksAndTrim() {
        val c = VieNeu.chunks("Câu một ngắn. Câu hai cũng ngắn!\nĐoạn mới " + "rất dài ".repeat(40))
        assertTrue(c.all { it.first.length <= 140 })
        assertEquals("Câu một ngắn. Câu hai cũng ngắn!", c[0].first)
        assertEquals(0.7, c[0].second, 1e-9)                       // hết đoạn: nghỉ dài
        val w = FloatArray(24000) { if (it in 6000..18000) 0.5f else 0f }
        val t = VieNeu.trimAndFade(w)
        assertTrue("cắt im lặng hai đầu: ${t.size}", t.size in 12000..14000)
        assertEquals(0f, t[0], 1e-6f)                              // fade ở mép
    }
}
