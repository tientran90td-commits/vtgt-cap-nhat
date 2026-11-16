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
    fun assSubtitles() {
        val ass = """
[Script Info]
Title: test
[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,{\an8}一护推开{\i1}宫殿{\i0}大门\N第二行
Dialogue: 1,0:00:01.50,0:00:03.00,Default,,0,0,0,,一护推开宫殿大门 第二行
Dialogue: 0,0:00:05.00,0:00:07.00,OP_Romaji,,0,0,0,,{\k20}ka{\k30}ze
Dialogue: 0,0:00:08.00,0:00:09.00,Signs,,0,0,0,,{\pos(10,10)}Biển hiệu
Dialogue: 0,0:00:10.00,0:00:12.00,Default,,0,0,0,,前方, 正是友哈巴赫
""".trimIndent()
        val l = parseSubs(ass)
        assertEquals(listOf("一护推开宫殿大门 第二行", "前方, 正是友哈巴赫"), l.map { it.text })  // bỏ OP/ED, biển hiệu, lớp trùng
        assertEquals(1.5, l[0].start, 1e-6)
        assertEquals(12.0, l[1].end, 1e-6)
        // .vtt thiếu giờ
        val vtt = parseSubs("WEBVTT\n\n00:01.000 --> 00:03.500\nXin chào\n\n01:02:03.000 --> 01:02:04.000\nHai")
        assertEquals(listOf(1.0, 3723.0), vtt.map { it.start })
    }

    @Test
    fun nameMemoryAndCast() {
        val n = Prompts.parseNames("{\"lines\": {\"1\": \"a\"}, \"names\": {\"一护\": \"Ichigo\", \"友哈巴赫\": \"Yhwach\", " +
            "\"x\": \"x\", \"灵压\": \"灵压\"}}")
        assertEquals(mapOf("一护" to "Ichigo", "友哈巴赫" to "Yhwach"), n)   // bỏ tên chưa dịch / giống hệt
        assertTrue(Prompts.parseNames("không phải json").isEmpty())
        assertEquals("Kurosaki Ichigo", Cast.malName("Kurosaki, Ichigo"))
        assertEquals("Yhwach", Cast.malName("Yhwach"))
    }

    @Test
    fun geminiReply() {
        // Gemini trả SRT (có chữ thừa trước / sau) -> cộng thời điểm bắt đầu của phần
        val srt = parseTimed("Đây là phụ đề:\n```srt\n1\n00:00:01,000 --> 00:00:02,500\n一护推开宫殿大门。\n\n" +
            "2\n00:00:03,000 --> 00:00:04,000\n前方正是友哈巴赫\n```", 1200.0)
        assertEquals(2, srt.size)
        assertEquals(1201.0, srt[0].start, 1e-6)
        assertEquals("前方正是友哈巴赫", srt[1].text)
        // hoặc từng dòng có mốc [mm:ss]
        val ts = parseTimed("[00:05] Câu một\n[01:02.5] Câu hai\n1:00:03 - Câu ba")
        assertEquals(listOf(5.0, 62.5, 3603.0), ts.map { it.start })
        assertEquals(13.0, ts[0].end, 1e-6)                                  // mỗi câu tối đa 8 giây
        assertEquals("Câu ba", ts[2].text)
        assertTrue(parseTimed("không có mốc thời gian").isEmpty())
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
    fun recapAnchoredToDialogue() {
        val lines = (0 until 40).map { Line(it * 10.0, it * 10.0 + 4.0, "câu $it") }
        val t = transcriptIds(lines)
        assertTrue(t.startsWith("#1 [00:00] câu 0\n#2 [00:10] câu 1"))
        val long = transcriptIds((0 until 3000).map { Line(it * 2.0, it * 2.0 + 1.5, "câu thoại khá dài số $it để thử") }, 20000)
        assertTrue(long.length <= 20000 && long.startsWith("#1-"))                     // phim dài: gộp khối câu
        // AI chỉ ra đoạn kể ứng với câu #31-#34 (hook) và #3-#5 -> đúng thời gian các câu đó
        val (_, segs) = Prompts.parseRecap("{\"segments\":[{\"from\":31,\"to\":34,\"text\":\"hook\"}," +
            "{\"from\":3,\"to\":5,\"text\":\"mở đầu\"}]}", 400.0, lines)
        assertEquals(300.0, segs[0].start, 1e-6)
        assertEquals(334.0, segs[0].end, 1e-6)
        assertEquals(20.0, segs[1].start, 1e-6)
        assertEquals(44.0, segs[1].end, 1e-6)
    }

    @Test
    fun planInStaysInsideRange() {
        // cảnh mỗi 5 giây, cảnh 30-35 tối
        val sh = (0 until 20).map { Shots.Shot(it * 5.0, it * 5.0 + 5.0, if (it == 6) 5.0 else 100.0) }
        val p = Shots.planIn(sh, 20.0, 44.0, 9.0, 10.0, 60.0)
        assertEquals(9.0, p.sumOf { it.second }, 1e-6)
        assertTrue("trong khoảng câu thoại: $p", p.all { (a, d) -> a >= 20.0 - 1e-6 && a + d <= 44.0 + 1e-6 })
        assertTrue("bỏ cảnh tối: $p", p.none { (a, d) -> a < 35.0 && a + d > 30.0 })
        assertTrue("rải đều, không dồn đầu khoảng: $p", p.last().first >= 30.0)
        // khoảng câu thoại ngắn hơn lời kể: nới ra nhưng không vượt đoạn trước / sau
        val q = Shots.planIn(sh, 50.0, 52.0, 8.0, 48.0, 60.0)
        assertEquals(8.0, q.sumOf { it.second }, 1e-6)
        assertTrue("chỉ nới tối đa 2 giây mỗi bên: $q", q.all { (a, d) -> a >= 48.0 - 1e-6 && a + d <= 54.0 + 1e-6 })
        // đoạn thoại chỉ có 1 cảnh sáng: dùng lại cảnh đó (lượt sau lấy phần khác), không lan sang cảnh tối / xa
        val sh2 = listOf(Shots.Shot(96.0, 99.0, 10.0), Shots.Shot(99.0, 103.0, 100.0), Shots.Shot(103.0, 110.0, 10.0))
        val c = Shots.planIn(sh2, 100.0, 102.0, 6.0, 95.0, 110.0)
        assertEquals(listOf(99.0 to 3.6, 100.0 to 2.4), c.map { (a, d) -> a to Math.round(d * 10) / 10.0 })
        // AI gợi ý dùng lại cảnh ở chỗ khác
        val r = Shots.planIn(sh2, 100.0, 102.0, 6.0, 95.0, 110.0, listOf(Shots.Shot(10.0, 14.0, 100.0)))
        assertEquals(listOf(99.0 to 3.0, 10.0 to 3.0), r)
        val (_, rs) = Prompts.parseRecap("{\"segments\":[{\"from\":2,\"to\":2,\"text\":\"a\",\"reuse\":[1,99]}]}", 100.0,
            listOf(Line(10.0, 12.0, "x"), Line(20.0, 22.0, "y")))
        assertEquals(listOf(9.5 to 12.5), rs[0].reuse)                       // câu không tồn tại bị bỏ
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

    @Test
    fun watchParse() {
        val reply = """
            Dưới đây là diễn biến:
            00:05-00:20 | Luffy lao tới đấm bay gã mặc giáp đen
            **00:24** - Cô gái tóc đỏ rút kiếm
            [01:02 - 01:10] Hai bên giao chiến, cháy nổ khắp nơi
            09:59 | mốc bịa ngoài khoảng ảnh
            00:30 | x
        """.trimIndent()
        val sc = Watch.parse(reply, 0.0, 70.0, 2.0)
        assertEquals(listOf(5.0, 24.0, 62.0), sc.map { it.start })
        assertEquals(20.0, sc[0].end, 1e-9)
        assertEquals("Cô gái tóc đỏ rút kiếm", sc[1].text)
        assertEquals(44.0, sc[1].end, 1e-9)                      // không có mốc cuối: tới cảnh sau, tối đa 20 giây
        assertEquals(70.0, sc[2].end, 1e-9)
        assertEquals(3723.0, Watch.parseClock("1:02:03"), 1e-9)
        // lời thoại + hình xếp theo thời gian, dòng hình có nhãn [HÌNH]
        val tl = Watch.timeline(listOf(Line(10.0, 12.0, "你好"), Line(30.0, 31.0, "走")), sc)
        assertEquals(listOf(5.0, 10.0, 24.0, 30.0, 62.0), tl.map { it.start })
        assertTrue(tl[0].text.startsWith(Watch.TAG))
        assertEquals(listOf(Line(1.0, 2.0, "a")), Watch.timeline(listOf(Line(1.0, 2.0, "a")), emptyList()))
        // kịch bản neo vào dòng hình (cảnh hành động không thoại) lấy đúng thời gian cảnh đó
        val (_, segs) = Prompts.parseRecap("{\"segments\":[{\"from\":3,\"to\":3,\"text\":\"Cô gái rút kiếm.\"}]}", 100.0, tl)
        assertEquals(24.0, segs[0].start, 1e-9)
        assertEquals(44.0, segs[0].end, 1e-9)
        // phim càng dài chụp càng thưa
        assertEquals(2.0, Watch.step(600.0), 1e-9)
        assertEquals(12.0, Watch.step(3 * 3600.0), 1e-9)
        assertTrue(Watch.estimateSheets(7200.0) in 15..30)
        assertEquals(256 to 144, Watch.cellSize(1920, 1080))
        assertEquals(144 to 256, Watch.cellSize(1080, 1920))
    }

    @Test
    fun openRouterVisionModel() {
        val ids = listOf("deepseek/deepseek-chat-v3.1:free", "google/gemma-3-27b-it:free", "meta-llama/llama-4-maverick:free",
            "qwen/qwen2.5-vl-72b-instruct:free", "openai/gpt-4o")
        assertEquals("qwen/qwen2.5-vl-72b-instruct:free", Ai.openRouterVision(ids))
        assertEquals("google/gemma-3-27b-it:free", Ai.openRouterVision(listOf("google/gemma-3-27b-it:free", "x/y:free")))
        assertNull(Ai.openRouterVision(listOf("deepseek/deepseek-chat-v3.1:free")))
    }

    @Test
    fun customAiBase() {
        assertEquals("http://192.168.1.10:4000/v1", Ai.normBase("192.168.1.10:4000"))
        assertEquals("http://x:11434/v1", Ai.normBase("http://x:11434/"))
        assertEquals("https://p.com/v1", Ai.normBase("https://p.com/v1"))
        assertEquals("https://g.com/v1beta/openai", Ai.normBase("https://g.com/v1beta/openai"))
        assertEquals("", Ai.normBase("  "))
    }
}
