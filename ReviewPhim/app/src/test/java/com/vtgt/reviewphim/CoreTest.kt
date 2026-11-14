package com.vtgt.reviewphim

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CoreTest {
    @Test
    fun numbersForFfmpegIgnoreLocale() {
        val old = java.util.Locale.getDefault()
        try {
            java.util.Locale.setDefault(java.util.Locale("vi", "VN"))
            assertEquals("12,500", "%.3f".format(12.5))           // định dạng thường theo máy: dấu phẩy
            assertEquals("atrim=start=12.500:end=13.250", "atrim=start=%.3f:end=%.3f".num(12.5, 13.25))
        } finally {
            java.util.Locale.setDefault(old)
        }
    }

    @Test
    fun srt() {
        val l = parseSrt("1\n00:00:01,000 --> 00:00:02,500\n<i>Xin chào</i>\nbạn\n\n2\n00:01:00.000 --> 00:01:02.000\n{\\an8}Hai\n")
        assertEquals(2, l.size)
        assertEquals("Xin chào bạn", l[0].text)
        assertEquals(60.0, l[1].start, 1e-6)
        assertEquals("Hai", l[1].text)
        assertTrue(toSrt(listOf(Cue(1.0, 2.5, "A"))).contains("00:00:01,000 --> 00:00:02,500"))
    }

    @Test
    fun chunks() {
        val text = "Ichigo đẩy cánh cửa cung điện. Phía trước, Yhwach ngồi trên ngai vàng, ánh mắt lạnh lùng nhìn xuống " +
            "kẻ thách thức trẻ tuổi đang tiến vào."
        val c = chunkText(text, 30)
        assertTrue(c.all { it.length <= 30 })
        assertEquals(text.replace(Regex("\\s+"), " "), c.joinToString(" "))
        val cues = splitCues(text, 10.0, 8.0, 30)
        assertEquals(10.0, cues.first().start, 1e-6)
        assertEquals(18.0, cues.last().end, 1e-6)
    }

    @Test
    fun json() {
        val j = extractJson("Đây là kết quả:\n```json\n{\"lines\": {\"1\": \"Một\", \"2\": \"Hai\",}}\n```")
        assertEquals("Một", j.getJSONObject("lines").getString("1"))
        val got = Prompts.parseLines("{\"lines\": {\"1\": \"Ichigo\", \"2\": \"还没\", \"3\": \"\", \"9\": \"lạc\"}}", listOf(0, 1, 2))
        assertEquals(mapOf(0 to "Ichigo", 2 to ""), got)                       // câu còn chữ Hán bị loại, id lạ bị bỏ
        assertEquals(mapOf(0 to "Một", 1 to "Hai"), Prompts.parseLines("1 | Một\n2. Hai", listOf(0, 1)))
        val (title, segs) = Prompts.parseRecap("{\"title\":\"T\",\"segments\":[{\"start\":80,\"text\":\"hook\"}," +
            "{\"start\":50,\"text\":\"b\"},{\"start\":5,\"text\":\"a\"},{\"start\":999,\"text\":\"c\"}]}", 100.0)
        assertEquals("T", title)
        assertEquals(listOf("hook", "a", "b", "c"), segs.map { it.text })   // đoạn hook giữ ở đầu, còn lại theo thời gian
        assertEquals(94.0, segs.last().start, 1e-6)                          // tránh 5% cuối (credit)
    }

    @Test
    fun transcriptAndChars() {
        val lines = (0 until 2000).map { Line(it * 3.0, it * 3.0 + 2.0, "câu thoại số $it khá dài để thử gộp") }
        val t = transcriptText(lines, 20000)
        assertTrue(t.length <= 20000)
        assertTrue(t.startsWith("[00:00]"))
        assertTrue(maxChars(lines, 0) >= (2.0 * CPS).toInt())
        assertTrue(similarity("一护推开宫殿大门", "一护推开宫殿大门。") > 0.8)
        assertTrue(similarity("一护推开宫殿大门", "前方正是友哈巴赫") < 0.3)
    }

    @Test
    fun shotsPlan() {
        // khung 6/giây: đổi cảnh ở 2.5, 2.9, 3.3, 9; cảnh 2.9-3.3 tối (cảnh đen)
        val lines = mutableListOf<String>()
        var t = 0.0
        while (t < 20.0) {
            val cut = listOf(2.5, 2.9, 3.3, 9.0).any { kotlin.math.abs(it - t) < 0.01 }
            val y = if (t >= 2.9 && t < 3.3) 10.0 else 100.0
            lines += "[Parsed_metadata_4 @ 0x0] frame:0 pts:0 pts_time:%.3f".num(t)
            lines += "[Parsed_metadata_4 @ 0x0] lavfi.signalstats.YAVG=$y"
            lines += "[Parsed_metadata_4 @ 0x0] lavfi.scd.score=${if (cut) 40.0 else 1.0}"
            t = Math.round((t + 0.1) * 10) / 10.0
        }
        val frames = Shots.parse(lines, 100.0)
        assertEquals(100.0, frames.first().t, 1e-6)                          // cộng thời điểm bắt đầu cửa sổ
        val sh = Shots.shots(frames.map { it.copy(t = it.t - 100.0) }, 20.0)
        assertEquals(5, sh.size)
        val p = Shots.plan(sh, 1.0, 7.0, 100.0)
        // bỏ cảnh quá ngắn (2.5-2.9) và cảnh đen (2.9-3.3); mỗi cảnh tối đa 3.6s; đủ 7 giây
        assertEquals(listOf(1.0 to 1.5, 3.3 to 3.6), p.take(2).map { (a, d) -> Math.round(a * 10) / 10.0 to Math.round(d * 10) / 10.0 })
        assertEquals(7.0, p.sumOf { it.second }, 1e-6)
        assertEquals(listOf(5.0 to 2.0), Shots.plan(emptyList(), 5.0, 2.0, 100.0))   // không dò được cảnh: 1 đoạn liền
    }

    @Test
    fun karaoke() {
        val s = "Ichigo đẩy cửa cung điện"
        assertEquals(0, Shots.karaokeChars(s, 0.0))
        assertEquals("Ichigo ", s.take(Shots.karaokeChars(s, 0.1)))         // đang đọc chữ đầu
        assertEquals(s.length, Shots.karaokeChars(s, 1.0))
        assertTrue(Shots.karaokeChars(s, 0.6) in 10 until s.length)
    }

    @Test
    fun openRouter() {
        val ids = listOf("google/gemini-2.5-flash", "deepseek/deepseek-r1:free", "deepseek/deepseek-chat-v3.1:free",
            "qwen/qwen3-235b-a22b:free")
        assertEquals("deepseek/deepseek-chat-v3.1:free", Ai.openRouterFree(ids))
        assertNull(Ai.openRouterFree(listOf("google/gemini-2.5-flash")))
    }
}
