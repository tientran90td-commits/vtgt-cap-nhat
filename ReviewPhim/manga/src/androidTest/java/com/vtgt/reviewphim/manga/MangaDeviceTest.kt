package com.vtgt.reviewphim.manga

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.media.MediaMetadataRetriever
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.Ff
import com.vtgt.reviewphim.Media
import com.vtgt.reviewphim.Prefs
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(AndroidJUnit4::class)
class MangaDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val dir = File(ctx.cacheDir, "mtest").apply { deleteRecursively(); mkdirs() }

    private fun jpg(f: File, w: Int, h: Int, draw: (Canvas) -> Unit): File {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        draw(Canvas(b))
        f.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 92, it) }
        b.recycle()
        return f
    }

    /** Dải webtoon: các khung tranh màu (có họa tiết) cách nhau bởi khoảng trắng. */
    private fun webtoon(f: File, w: Int, panels: List<Int>, gap: Int): File {
        val h = panels.sum() + gap * (panels.size + 1)
        return jpg(f, w, h) { c ->
            c.drawColor(Color.WHITE)
            var y = gap
            val p = Paint()
            for ((k, ph) in panels.withIndex()) {
                p.color = Color.HSVToColor(floatArrayOf(k * 70f % 360, 0.8f, 0.8f))
                c.drawRect(20f, y.toFloat(), w - 20f, (y + ph).toFloat(), p)
                p.color = Color.BLACK
                for (i in 0 until 12) c.drawCircle(40f + i * (w - 80) / 12f, y + ph / 2f, 10f, p)
                y += ph + gap
            }
        }
    }

    @Test
    fun webtoonSlicedAtGaps() {
        val src = webtoon(File(dir, "strip.jpg"), 720, listOf(900, 1000, 800, 1100), 80)
        val pages = Books.sliceFile(src, File(dir, "out"), "Trang 1", 0)
        assertTrue("phải cắt thành nhiều khúc: ${pages.map { it.h }}", pages.size >= 3)
        assertTrue(pages.all { it.h <= it.w * Books.MAX_RATIO + 2 })
        assertEquals(720 * 0 + pages.sumOf { it.h }, BitmapFactory.Options().apply { inJustDecodeBounds = true }
            .also { BitmapFactory.decodeFile(src.path, it) }.outHeight)
        // chỗ cắt nằm trên khoảng trắng: hàng đầu mỗi khúc (trừ khúc đầu) gần như trắng
        for (p in pages.drop(1)) {
            val b = BitmapFactory.decodeFile(p.file.path)
            val px = IntArray(b.width)
            b.getPixels(px, 0, b.width, 0, 0, b.width, 1)
            assertTrue("khúc ${p.label} bắt đầu ở khoảng trắng", Books.rowBlank(px) < 8.0 && Color.red(px[b.width / 2]) > 200)
        }
        assertEquals("Trang 1.1", pages[0].label)
    }

    @Test
    fun cbzAndEpub() = runBlocking {
        // CBZ: thứ tự trang theo số (2 trước 10)
        val cbz = File(dir, "t.cbz")
        ZipOutputStream(cbz.outputStream()).use { z ->
            for (n in listOf(10, 2, 1)) {
                z.putNextEntry(ZipEntry("chap/$n.jpg"))
                val f = jpg(File(dir, "z$n.jpg"), 400, 560) { it.drawColor(Color.rgb(n * 20, 100, 100)) }
                z.write(f.readBytes())
                z.closeEntry()
            }
        }
        val pages = Books.fromZip(cbz, File(dir, "cbz")) {}
        assertEquals(listOf("Trang 1", "Trang 2", "Trang 3"), pages.map { it.label })
        val firstRed = BitmapFactory.decodeFile(pages[0].file.path).getPixel(10, 10).let { Color.red(it) }
        assertTrue("trang đầu là 1.jpg (đỏ ~20): $firstRed", firstRed < 40)

        // EPUB: 2 chương theo spine + ảnh minh họa giữa 2 chương + ảnh bìa
        val epub = File(dir, "t.epub")
        val img = jpg(File(dir, "ill.jpg"), 600, 900) { it.drawColor(Color.BLUE) }
        ZipOutputStream(epub.outputStream()).use { z ->
            fun put(n: String, s: ByteArray) { z.putNextEntry(ZipEntry(n)); z.write(s); z.closeEntry() }
            put("mimetype", "application/epub+zip".toByteArray())
            put("META-INF/container.xml", """<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""".toByteArray())
            put("OEBPS/content.opf", """<package><metadata><dc:title>Thế Giới Võ Hồn</dc:title><meta name="cover" content="cov"/></metadata>
                <manifest><item id="c2" href="Text/c2.xhtml" media-type="application/xhtml+xml"/>
                <item id="c1" href="Text/c1.xhtml" media-type="application/xhtml+xml"/>
                <item id="cov" href="Images/ill.jpg" media-type="image/jpeg"/></manifest>
                <spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>""".toByteArray())
            put("OEBPS/Text/c1.xhtml", "<html><body><h2>Chương 1</h2><p>Lâm Động nhặt được viên đá.</p><p><img src=\"../Images/ill.jpg\"/></p></body></html>".toByteArray())
            put("OEBPS/Text/c2.xhtml", "<html><body><h2>Chương 2</h2><p>Hắn luyện thành công quyền pháp.</p></body></html>".toByteArray())
            put("OEBPS/Images/ill.jpg", img.readBytes())
        }
        val b = Books.fromEpub(epub, File(dir, "ep")) {}
        assertEquals("Thế Giới Võ Hồn", b.title)
        assertTrue(b.text.indexOf("Chương 1") < b.text.indexOf("Chương 2"))
        assertEquals(1, b.illus.size)
        assertTrue("ảnh nằm giữa 2 chương", b.illus[0].pos > b.text.indexOf("viên đá") && b.illus[0].pos <= b.text.indexOf("Chương 2"))
        assertTrue(b.cover != null && b.cover!!.length() > 0)
    }

    @Test
    fun slideshowScrollsTallPage() = runBlocking {
        val (w, h) = 360 to 640
        // trang dài: nửa trên đỏ, nửa dưới xanh -> cuộn: đầu cảnh thấy đỏ, cuối cảnh thấy xanh
        val tall = jpg(File(dir, "tall.jpg"), 720, 2400) { c ->
            val p = Paint()
            p.color = Color.RED; c.drawRect(0f, 0f, 720f, 1200f, p)
            p.color = Color.BLUE; c.drawRect(0f, 1200f, 720f, 2400f, p)
        }
        val normal = jpg(File(dir, "norm.jpg"), 700, 1000) { it.drawColor(Color.GREEN) }
        val (f1, s1) = Slides.frame(tall, w, h, File(dir, "f1.jpg"))
        val (f2, s2) = Slides.frame(normal, w, h, File(dir, "f2.jpg"))
        assertTrue("trang dài phải cuộn", s1)
        assertTrue("trang vừa khung không cuộn", !s2)
        val card = Slides.titleCard("Thế Giới Võ Hồn", "Light novel", w, h, File(dir, "card.jpg"))
        val vid = File(dir, "v.mp4")
        Slides.render(ctx, listOf(Slide(f1, 3.0, s1), Slide(f2, 2.0, s2), Slide(card, 1.0, false)), w, h,
            listOf(Cue(0.2, 2.5, "Phụ đề thử nghiệm")), karaoke = true, hook = "", out = vid) {}
        val info = Media.probe(vid)
        assertEquals(6.0, info.duration, 0.4)
        assertEquals(w to h, info.width to info.height)
        val m = MediaMetadataRetriever()
        m.setDataSource(vid.path)
        fun at(sec: Double): Int = m.getFrameAtTime((sec * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST)!!.getPixel(w / 2, h / 3)
        val start = at(0.15)
        val end = at(2.85)
        val mid = at(4.0)
        m.release()
        assertTrue("đầu cảnh thấy phần trên (đỏ): ${Integer.toHexString(start)}", Color.red(start) > 150 && Color.blue(start) < 100)
        assertTrue("cuối cảnh thấy phần dưới (xanh): ${Integer.toHexString(end)}", Color.blue(end) > 150 && Color.red(end) < 100)
        assertTrue("cảnh 2 màu xanh lá: ${Integer.toHexString(mid)}", Color.green(mid) > 150)

        // tiếng: chỉ có lời kể (+ không nhạc nền) rồi ghép vào hình
        val narr = File(dir, "n.wav")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "sine=f=300:d=6", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", narr.path))
        val aud = File(dir, "a.wav")
        Ff.mixRecap(ctx, narr, false, emptyList(), narr, 0.0, aud)
        val out = File(dir, "final.mp4")
        Ff.mux(ctx, vid, aud, out)
        val fi = Media.probe(out)
        assertTrue(fi.hasAudio)
        assertEquals(6.0, fi.duration, 0.5)
    }

    @Test
    fun scriptPromptHasPages() {
        val items = listOf(Item("Jin-Woo vào hầm ngục", page = 0, label = "Trang 1"), Item("Tượng mở mắt", page = 1, label = "Trang 2"))
        val p = Story.script("Solo Leveling", true, items, 120, "hap_dan", Prefs(ctx))
        assertTrue(p.contains("#1 [Trang 1] Jin-Woo vào hầm ngục") && p.contains("#2 [Trang 2] Tượng mở mắt"))
        val r = Story.readPages("Solo Leveling", 1, 2, 3, 1, 12, Prefs(ctx))
        assertTrue(r.contains("P1 ... P12") && r.contains("P12 |"))
        val n = Story.novelNotes("LN", 1, 3, "Văn bản", Prefs(ctx))
        assertTrue(n.contains("phần 1/3") && n.endsWith("Văn bản"))
    }
}
