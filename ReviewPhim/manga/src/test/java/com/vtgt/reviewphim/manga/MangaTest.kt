package com.vtgt.reviewphim.manga

import com.vtgt.reviewphim.Prompts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class MangaTest {
    @Test
    fun naturalOrder() {
        val names = listOf("ch1_p10.jpg", "ch1_p2.jpg", "ch1_p1.jpg", "ch2_p1.jpg", "ch1_p02b.jpg")
        assertEquals(listOf("ch1_p1.jpg", "ch1_p2.jpg", "ch1_p02b.jpg", "ch1_p10.jpg", "ch2_p1.jpg"), names.sortedWith(Books.natural))
        assertTrue(Books.isImage("a/B.WEBP") && !Books.isImage("x.txt"))
    }

    @Test
    fun webtoonCuts() {
        // dải 800 x 5000: khoảng trắng cao 80 điểm ảnh quanh y = 1150, 2350, 3500
        val blank = setOf(1150, 2350, 3500)
        val ys = Books.cuts(800, 5000) { y -> if (blank.any { kotlin.math.abs(it - y) <= 40 }) 0.0 else 60.0 }
        assertEquals(0, ys.first())
        assertEquals(5000, ys.last())
        assertTrue("cắt giữa khoảng trắng: $ys", ys.drop(1).dropLast(1).all { y -> blank.any { kotlin.math.abs(it - y) <= 30 } })
        assertTrue("mỗi khúc không quá 2 lần chiều rộng: $ys", ys.zipWithNext().all { (a, b) -> b - a <= 1600 })
        // trang thường không cắt
        assertEquals(listOf(0, 1100), Books.cuts(800, 1100) { 50.0 })
        // không có khoảng trắng: vẫn cắt, mỗi khúc ≤ 2 lần rộng
        val ys2 = Books.cuts(700, 6000) { 40.0 }
        assertTrue(ys2.zipWithNext().all { (a, b) -> b - a in 1..1400 })
        assertEquals(0.0, Books.rowBlank(IntArray(10) { 0xFFFFFFFF.toInt() }), 1e-9)
        assertTrue(Books.rowBlank(IntArray(10) { if (it % 2 == 0) 0xFF000000.toInt() else 0xFFFFFFFF.toInt() }) > 100)
    }

    @Test
    fun htmlAndText() {
        val t = Books.htmlToText("""<html><head><title>x</title><style>p{}</style></head><body><h1>Chương 1</h1>
            <p>Lâm&nbsp;Động bước vào &quot;hang&quot;.</p><p><img src="../Images/a.jpg" alt=""/></p><p>Hết&#33;</p></body></html>""")
        assertEquals("Chương 1\nLâm Động bước vào \"hang\".\n\u0001../Images/a.jpg\u0001\nHết!", t)
        assertEquals("Xin chào", Books.readText(byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + "Xin chào".toByteArray()))
        assertEquals("林动", Books.readText("林动".toByteArray(charset("GB18030"))))
        val text = (1..50).joinToString("\n") { "Đoạn $it " + "chữ ".repeat(30) }
        val ch = Books.chunks(text, 1000)
        assertTrue(ch.size in 5..12)
        assertEquals(0, ch.first().first)
        assertTrue("cắt ở cuối đoạn", ch.all { (s, c) -> text.substring(s).startsWith(c) && c.endsWith("chữ") })
        assertEquals(text.replace("\n", "").length.toDouble(), ch.sumOf { it.second.replace("\n", "").length }.toDouble(), 50.0)
    }

    @Test
    fun parseAnswers() {
        val r = """
            Đây là diễn biến:
            P1 | Bìa truyện (bỏ qua)
            **P2** | Jin-Woo bước vào hầm ngục, nói "Lại là cấp E sao?"
            P3: Bức tượng khổng lồ mở mắt
            Trang 4 - Mọi người hoảng loạn bỏ chạy
            P9 | ngoài khoảng
            P3 | thêm chi tiết
        """.trimIndent()
        val m = Story.parsePages(r, 1, 4)
        assertEquals(setOf(2, 3, 4), m.keys)
        assertEquals("Bức tượng khổng lồ mở mắt thêm chi tiết", m[3])
        assertTrue(m[2]!!.startsWith("Jin-Woo"))
        val notes = Story.parseNotes("Tóm tắt:\n- Lâm Động nhặt được viên đá bí ẩn ở hậu sơn.\n2. Hắn luyện thành công Thông Bối Quyền.\n- ngắn\nkết")
        assertEquals(listOf("Lâm Động nhặt được viên đá bí ẩn ở hậu sơn.", "Hắn luyện thành công Thông Bối Quyền."), notes)
        val raw = Story.rawItems("A".repeat(300) + "\n" + "B".repeat(300) + "\n" + "C".repeat(100), 500)
        assertEquals(2, raw.size)
        assertEquals(0, raw[0].pos)
        assertEquals(602, raw[1].pos)
    }

    @Test
    fun scriptMapsToPages() {
        val pages = (0 until 6).map { Page(File("p$it.jpg"), 800, 1100, "Trang ${it + 1}") }
        val book = Book("manga", "X", pages)
        // trang 2 không đọc được -> các dòng diễn biến là trang 1,3,4,5,6
        val items = listOf(0, 2, 3, 4, 5).map { Item("trang $it", page = it, label = pages[it].label) }
        val reply = "{\"title\":\"T\",\"segments\":[{\"from\":4,\"to\":5,\"text\":\"Hook.\"},{\"from\":1,\"to\":2,\"text\":\"Mở đầu.\"},{\"from\":3,\"to\":3,\"text\":\"Giữa.\"}]}"
        val (t, segs) = Prompts.parseRecap(reply, items.size.toDouble(), Story.asLines(items))
        assertEquals("T", t)
        assertEquals("Hook.", segs[0].text)
        fun pagesOf(i: Int) = Story.visuals(book, items, segs[i].start.toInt(), segs[i].end.toInt()).map { it.name }
        assertEquals(listOf("p4.jpg", "p5.jpg"), pagesOf(0))
        assertEquals(listOf("p0.jpg", "p2.jpg"), pagesOf(1))
        assertEquals(listOf("p3.jpg"), pagesOf(2))
    }

    @Test
    fun novelVisuals() {
        val cover = File("cover.jpg")
        val book = Book("novel", "LN", text = "x".repeat(10000), illus = listOf(Illus(3000, File("i1.jpg")), Illus(7000, File("i2.jpg"))), cover = cover)
        val items = (0 until 10).map { Item("ý $it", pos = it * 1000) }
        assertEquals(listOf("cover.jpg"), Story.visuals(book, items, 0, 2).map { it.name })      // trước ảnh đầu: ảnh bìa
        assertEquals(listOf("i1.jpg"), Story.visuals(book, items, 2, 4).map { it.name })         // ảnh nằm trong khoảng
        assertEquals(listOf("i1.jpg"), Story.visuals(book, items, 4, 6).map { it.name })         // ảnh gần nhất phía trước
        assertEquals(listOf("i2.jpg"), Story.visuals(book, items, 6, 10).map { it.name })
        val none = Book("novel", "LN", text = "abc")
        assertTrue(Story.visuals(none, items, 0, 1).isEmpty())
        // chia thời gian: mỗi ảnh ≥ 2.2 giây
        val fs = (0 until 10).map { File("$it.jpg") }
        val sh = Story.share(fs, 7.0)
        assertEquals(3, sh.size)
        assertEquals(7.0, sh.sumOf { it.second }, 1e-9)
        assertEquals(listOf("0.jpg", "3.jpg", "6.jpg"), sh.map { it.first.name })
        assertEquals(1, Story.share(fs.take(2), 1.0).size)
    }

    @Test
    fun panelsInReadingOrder() {
        val w = 300
        val h = 420
        val g = IntArray(w * h) { 255 }
        fun fill(l: Int, t: Int, r: Int, b: Int) { for (y in t until b) for (x in l until r) g[y * w + x] = 100 }
        fill(10, 10, 290, 140)    // khung trên, cả hàng
        fill(10, 150, 145, 290)   // hàng giữa: khung trái
        fill(155, 150, 290, 290)  // hàng giữa: khung phải
        fill(10, 300, 290, 410)   // khung dưới
        val top = Box(10, 10, 290, 140)
        val left = Box(10, 150, 145, 290)
        val right = Box(155, 150, 290, 290)
        val bottom = Box(10, 300, 290, 410)
        assertEquals(listOf(top, right, left, bottom), Panels.detect(g, w, h, rtl = true))   // manga Nhật: phải trước
        assertEquals(listOf(top, left, right, bottom), Panels.detect(g, w, h, rtl = false))
        // tranh tràn trang, không có rãnh: cả trang là 1 khung
        val art = IntArray(w * h) { (it * 37 % 200) }
        assertEquals(1, Panels.detect(art, w, h, true).size)
        // trang nền đen, khung sáng
        val dark = IntArray(w * h) { 10 }
        for (y in 20 until 200) for (x in 20 until 280) dark[y * w + x] = 220
        for (y in 220 until 400) for (x in 20 until 280) dark[y * w + x] = 220
        assertEquals(listOf(Box(20, 20, 280, 200), Box(20, 220, 280, 400)), Panels.detect(dark, w, h, true))
    }

    @Test
    fun webtoonDetection() {
        assertTrue(Books.looksWebtoon(List(5) { 720 to 1280 }))          // ảnh cắt sẵn cùng cỡ, dài hơn trang sách
        assertTrue(Books.looksWebtoon(listOf(800 to 1100, 800 to 5000)))  // có dải dài
        assertTrue(!Books.looksWebtoon(List(6) { 800 to 1150 }))         // trang manga
        assertTrue(!Books.looksWebtoon(listOf(700 to 1300, 800 to 1300, 900 to 1300)))
        assertTrue(!Books.looksWebtoon(emptyList()))
    }

    @Test
    fun webPages() {
        val base = "https://x.com/truyen/c1/"
        val html = """<html><head><script>var x=1</script></head><body><header><img src="/logo.png"></header>
            <div class="reading"><img src="data:image/gif;base64,AAA" data-src="https://cdn.x.com/c1/001.jpg">
            <img data-original="//cdn.x.com/c1/002.jpg" src="/loading.gif"><img src="003.webp" class="page"></div>
            <img src="/static/icon-fb.png"></body></html>"""
        assertEquals(listOf("https://cdn.x.com/c1/001.jpg", "https://cdn.x.com/c1/002.jpg", "https://x.com/truyen/c1/003.webp"),
            Web.images(html, base))
        // danh sách ảnh nằm trong script (JSON)
        val js = "<html><body><div id=r></div><script>var pages=[\"https:\\/\\/img.y.com\\/a\\/1.jpg\",\"https:\\/\\/img.y.com\\/a\\/2.jpg?t=1\"]</script></body></html>"
        assertEquals(listOf("https://img.y.com/a/1.jpg", "https://img.y.com/a/2.jpg?t=1"), Web.images(js, base))

        val chap = """<html><head><title>Vũ Động Càn Khôn - Chương 1</title></head><body>
            <div class="main-content"><div class="menu"><a href="/">Trang chủ</a></div>
            <h1>Chương 1: Viên đá</h1>
            <div id="chapter-c" class="chapter-c"><p>Lâm Động mở mắt.</p>Hắn nhìn quanh.<br>Trời đã sáng.<div class="ads">QC</div>${"<p>Lâm Động vận chuyển nguyên lực, cảm nhận viên đá đang phát sáng.</p>".repeat(10)}<p>Chương sau</p></div>
            <a href="/truyen/c0/">‹ Chương trước</a> <a class="btn" href="/truyen/c2/">Chương sau ›</a>
            <div class="comments"><p>hay quá</p></div></div></body></html>"""
        val t = Web.text(chap)
        assertTrue(t, t.startsWith("Lâm Động mở mắt.\nHắn nhìn quanh.\nTrời đã sáng."))
        assertTrue(t, !t.contains("Chương sau") && !t.contains("hay quá") && !t.contains("Trang chủ"))
        assertEquals("Chương 1: Viên đá", Web.title(chap))
        assertEquals("https://x.com/truyen/c2/", Web.next(chap, base))
        assertEquals("https://x.com/c/9", Web.next("<link rel=\"next\" href=\"/c/9\">", base))
        assertEquals(null, Web.next("<a href='/c/0'>Chương trước</a>", base))
        assertTrue(Web.decode("<meta charset=\"gbk\"><p>林动</p>".toByteArray(charset("GBK")), null).contains("林动"))
        assertTrue(Web.isImageUrl("https://a.b/1.JPG?x=1") && !Web.isImageUrl("https://a.b/chap-1"))
        assertEquals("https://a.b/x/y.jpg", Web.absolute("https://a.b/x/z.html", "y.jpg"))
    }

    @Test
    fun syncBeats() {
        val b = Sync.beats("Jin-Woo bước vào hầm ngục [#3.1]. Bức tượng bỗng mở mắt [#3.3]! Mọi người hoảng loạn. Hắn bị đâm. [#5]", 2, 5, 6)
        assertEquals(listOf(
            Sync.Beat("Jin-Woo bước vào hầm ngục.", 2, 0),
            Sync.Beat("Bức tượng bỗng mở mắt!", 2, 2),
            Sync.Beat("Mọi người hoảng loạn.", 2, -1),
            Sync.Beat("Hắn bị đâm.", 4, -1)), b)
        // ghi chú ngoài truyện bị bỏ qua, câu không ghi chú theo dòng đầu đoạn
        assertEquals(listOf(Sync.Beat("Câu A.", 1, -1), Sync.Beat("Câu B.", 1, -1)), Sync.beats("Câu A [#99]. Câu B.", 1, 2, 6))
        assertEquals(listOf(Sync.Beat("Không có ghi chú gì cả", 3, -1)), Sync.beats("Không có ghi chú gì cả", 3, 4, 6))
        assertEquals("A, B.", Sync.clean("A [#2.1], B [ #3 ] ."))
    }
}
