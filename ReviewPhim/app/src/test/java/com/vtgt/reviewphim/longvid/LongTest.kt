package com.vtgt.reviewphim.longvid

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

class LongTest {
    @Test
    fun splitChapters() {
        val text = "Lời tựa ngắn.\nChương 1: Khởi đầu\nLâm Động tỉnh dậy.\nHắn đi ra ngoài.\n\nChương 2 - Viên đá\nViên đá phát sáng.\n" +
            "Phần lớn mọi người không tin.\nCHƯƠNG 3\nKết thúc."
        val ch = Text.chapters(text)
        assertEquals(listOf("Chương 1: Khởi đầu", "Chương 2 - Viên đá", "CHƯƠNG 3"), ch.map { it.first })
        assertTrue("dòng 'Phần lớn...' không phải tiêu đề", ch[1].second.contains("Phần lớn mọi người"))
        assertEquals("Kết thúc.", ch[2].second)
        val zh = Text.chapters("第一章 林动\n林动睁开眼。\n第二章 石符\n石符发光。")
        assertEquals(listOf("第一章 林动", "第二章 石符"), zh.map { it.first })
        assertTrue(Text.CHAPTER.containsMatchIn("Quyển 2 - Chương 15: Đại chiến"))
        assertTrue(!Text.CHAPTER.containsMatchIn("Hồi lâu sau hắn mới nói"))
        assertTrue(!Text.CHAPTER.containsMatchIn("Chương cuối cùng của đời người"))
        // không có tiêu đề chương: chia đều
        val plain = (1..40).joinToString("\n") { "Đoạn $it " + "chữ ".repeat(100) }
        val parts = Text.chapters(plain, 5000)
        assertTrue(parts.size in 3..6)
        assertEquals("Phần 1", parts[0].first)
    }

    @Test
    fun language() {
        assertTrue(Text.isVietnamese("Lâm Động tỉnh dậy, nhìn quanh căn phòng tối om. Hắn nhớ lại những chuyện đã xảy ra."))
        assertTrue(!Text.isVietnamese("Lin Dong woke up and looked around the dark room. He remembered what had happened."))
        assertTrue(!Text.isVietnamese("林动睁开眼睛，看着四周漆黑的房间。他想起了发生的事情。"))
        assertTrue(!Text.isVietnamese("임동은 눈을 떴다. 어두운 방을 둘러보았다."))
    }

    @Test
    fun speakChunks() {
        val t = "Câu một ngắn. Câu hai cũng ngắn! " + "Một câu rất dài, " + "có nhiều vế, ".repeat(30) + "kết thúc.\n\nĐoạn mới."
        val c = Text.speakChunks(t, 120)
        assertTrue(c.all { it.length <= 121 })
        assertEquals("Câu một ngắn. Câu hai cũng ngắn!", c[0])
        assertEquals("Đoạn mới.", c.last())
        assertEquals(t.replace(Regex("\\s+"), ""), c.joinToString("").replace(Regex("\\s+"), ""))
        assertTrue(Text.speakChunks("***\n---").isEmpty())
    }

    @Test
    fun projectSaveLoadBudget() {
        val dir = Files.createTempDirectory("lp").toFile()
        val p = Project(dir).apply { kind = "novel"; title = "Vũ Động"; mode = "retell"; targetMin = 60 }
        val a = p.newPart("Chương 1", 3000.0)
        val b = p.newPart("Chương 2", 9000.0)
        assertTrue(java.io.File(dir, "parts/${a.id}").isDirectory && a.id != b.id)
        b.state = 2
        b.dur = 125.5
        p.memory = "Lâm Động nhặt được viên đá."
        p.save()
        val q = Project.load(dir)!!
        assertEquals("Vũ Động", q.title)
        assertEquals(listOf("Chương 1", "Chương 2"), q.parts.map { it.name })
        assertEquals(2, q.parts[1].state)
        assertEquals(1, q.doneParts)
        assertEquals(125.5, q.totalDur, 1e-9)
        assertEquals(900, q.budget(0))          // 60 phút chia theo số ký tự: 1/4
        assertEquals(2700, q.budget(1))
        assertEquals(3600.0, q.estimate(), 1e-9)
        q.mode = "verbatim"
        assertEquals(12000 / com.vtgt.reviewphim.CPS, q.estimate(), 1e-6)
        // phần mới không trùng thư mục phần cũ đã xóa
        q.parts.removeAt(0)
        val c = q.newPart("Chương 3", 100.0)
        assertTrue(c.id != b.id)
        assertEquals("00:00 Chương 2\n02:05 Chương 3", Text.chapterList(q.parts))
        assertEquals("1:02:03", Text.stamp(3723.0))
        dir.deleteRecursively()
    }

    @Test
    fun presetsAndClean() {
        val eco = Preset(720, 5, 300_000, "64k", false)
        assertEquals(0.164, eco.bytes(3600.0) / 1e9, 0.01)      // truyện audio ~0.16 GB / giờ
        assertEquals("Lâm Động bước vào.", LongPrompts.clean("Bản dịch:\nLâm Động bước vào."))
        assertEquals("Câu 1.\nCâu 2.", LongPrompts.clean("```\nCâu 1.\nCâu 2.\n```"))
        assertTrue(LongPrompts.context("").isEmpty() && LongPrompts.context("abc").contains("abc"))
    }
}
