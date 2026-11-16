package com.vtgt.reviewphim.longvid

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.vtgt.reviewphim.Aspect
import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.Ff
import com.vtgt.reviewphim.Media
import com.vtgt.reviewphim.Prefs
import com.vtgt.reviewphim.Render
import com.vtgt.reviewphim.RenderSpec
import com.vtgt.reviewphim.manga.Slide
import com.vtgt.reviewphim.manga.Slides
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Video dài = nhiều phần dựng riêng rồi nối (không mã hóa lại): các phần phải cùng thông số để nối được.
 * Thử: 2 phần truyện audio (ảnh tĩnh, 5 khung/giây, bitrate thấp) + 2 phần phim (cắt cảnh, khung ngang 16:9).
 */
@RunWith(AndroidJUnit4::class)
class LongDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val dir = File(ctx.cacheDir, "ltest").apply { deleteRecursively(); mkdirs() }

    private suspend fun tone(f: File, sec: Int, hz: Int) =
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "sine=f=$hz:d=$sec", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", f.path))

    @Test
    fun audioStoryPartsConcat() = runBlocking {
        val (w, h) = Slides.size(false, 720)
        assertEquals(1280 to 720, w to h)
        val cover = File(dir, "cover.jpg")
        Bitmap.createBitmap(600, 900, Bitmap.Config.ARGB_8888).apply {
            Canvas(this).drawColor(Color.rgb(200, 60, 60))
            cover.outputStream().use { compress(Bitmap.CompressFormat.JPEG, 90, it) }
        }
        val parts = (1..2).map { k ->
            val card = Slides.titleCard("Vũ Động Càn Khôn", "Chương $k", w, h, File(dir, "card$k.jpg"))
            val fr = Slides.frame(cover, w, h, File(dir, "f$k.jpg")).first
            val vid = File(dir, "v$k.mp4")
            val cues = listOf(Cue(0.5, 10.0, "Lâm Động tỉnh dậy, nhìn quanh."), Cue(10.0, 40.0, "Hắn bước ra ngoài, trời đã sáng."))
            Slides.render(ctx, listOf(Slide(card, 5.0, false), Slide(fr, 40.0, false)), w, h, cues, false, "", vid,
                fps = 5, bitrate = 300_000, motion = false) {}
            val narr = File(dir, "n$k.wav")
            tone(narr, 45, 300 + k * 50)
            val aud = File(dir, "a$k.wav")
            Ff.mixRecap(ctx, narr, false, emptyList(), narr, 0.0, aud)
            val out = File(dir, "part$k.mp4")
            Ff.mux(ctx, vid, aud, out, "64k")
            val i = Media.probe(out)
            assertEquals(45.0, i.duration, 0.6)
            out
        }
        val size = parts.sumOf { it.length() }
        assertTrue("bitrate thấp: ${size / 1024} KB cho 90 giây", size < 6_000_000)
        val final = File(dir, "final.mp4")
        Ff.concat(ctx, parts, final)
        val fi = Media.probe(final)
        assertEquals(90.0, fi.duration, 1.2)
        assertEquals(w to h, fi.width to fi.height)
        assertTrue(fi.hasAudio)
        // giải mã được khung ở phần 2 (nối đúng)
        val m = android.media.MediaMetadataRetriever()
        m.setDataSource(final.path)
        val b = m.getFrameAtTime(70_000_000L, android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
        m.release()
        assertTrue("có hình ở phút thứ 2", b != null && Color.red(b.getPixel(w / 2, h / 2)) > 120)
    }

    @Test
    fun filmPartsConcat() = runBlocking {
        val parts = (1..2).map { k ->
            val src = File(dir, "ep$k.mp4")
            Ff.run(ctx, listOf("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=12", "-f", "lavfi", "-i", "sine=f=440:d=12",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src.path))
            val info = Media.probe(src)
            val clips = listOf(1.0 to 4.0, 6.0 to 9.0)
            val vid = File(dir, "fv$k.mp4")
            Render.video(ctx, RenderSpec(src, info, clips, Aspect.HORIZONTAL, 540, null, 0.8f to 0.95f,
                listOf(Cue(0.0, 3.0, "Tập $k")), "", hook = if (k == 1) "Cả bộ phim" else ""), vid, 1_000_000) {}
            assertEquals(960 to 540, Media.probe(vid).let { it.width to it.height })
            val narr = File(dir, "fn$k.wav")
            tone(narr, 6, 500)
            val aud = File(dir, "fa$k.wav")
            Ff.mixRecap(ctx, src, true, clips, narr, 0.12, aud)
            val out = File(dir, "fpart$k.mp4")
            Ff.mux(ctx, vid, aud, out, "96k")
            out
        }
        val final = File(dir, "ffinal.mp4")
        Ff.concat(ctx, parts, final)
        val fi = Media.probe(final)
        assertEquals(12.0, fi.duration, 0.8)
        assertEquals(960 to 540, fi.width to fi.height)
    }

    @Test
    fun promptsOnDevice() {
        val prefs = Prefs(ctx)
        val t = LongPrompts.translate("Vũ Động", "Chương 1", "林动睁开眼。", prefs, "Trước đó: Lâm Động bị thương.")
        assertTrue(t.contains("林动睁开眼。") && t.contains("Lâm Động bị thương") && t.contains("Dịch ĐỦ"))
        val r = LongPrompts.retell("Vũ Động", "Chương 2", "Văn bản", 3000, "hap_dan", prefs, "")
        assertTrue(r.contains("khoảng 3000 ký tự") && r.endsWith("Văn bản") && !r.contains("NỘI DUNG NGAY TRƯỚC"))
    }
}
