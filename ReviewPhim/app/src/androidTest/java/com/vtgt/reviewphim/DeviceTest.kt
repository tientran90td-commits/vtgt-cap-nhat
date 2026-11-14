package com.vtgt.reviewphim

import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.math.PI
import kotlin.math.sin

/** Chạy trên máy ảo Android (GitHub Actions): ffmpeg, dựng hình Media3 + phụ đề, trộn tiếng, ghép. */
@RunWith(AndroidJUnit4::class)
class DeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val dir = File(ctx.cacheDir, "devtest").apply { deleteRecursively(); mkdirs() }

    private fun brightRatio(b: Bitmap, y0: Float, y1: Float): Double {
        var n = 0
        var bright = 0
        for (y in (b.height * y0).toInt() until (b.height * y1).toInt() step 2) for (x in 0 until b.width step 2) {
            val c = b.getPixel(x, y)
            if ((c shr 16 and 255) > 200 && (c shr 8 and 255) > 200 && (c and 255) > 200) bright++
            n++
        }
        return bright.toDouble() / n
    }

    private fun yellowRatio(b: Bitmap, y0: Float, y1: Float): Double {
        var n = 0
        var hit = 0
        for (y in (b.height * y0).toInt() until (b.height * y1).toInt() step 2) for (x in 0 until b.width step 2) {
            val c = b.getPixel(x, y)
            if ((c shr 16 and 255) > 180 && (c shr 8 and 255) > 140 && (c and 255) < 120) hit++
            n++
        }
        return hit.toDouble() / n
    }

    private fun frameAt(f: File, sec: Double): Bitmap {
        val m = MediaMetadataRetriever()
        m.setDataSource(f.absolutePath)
        val b = m.getFrameAtTime((sec * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST)!!
        m.release()
        return b
    }

    @Test
    fun fullPipeline() = runBlocking {
        // video thử: nền đen 640x360, 8 giây, có tiếng (ffmpeg đi kèm app, mã hóa x264)
        val src = File(dir, "src.mp4")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=8", "-f", "lavfi",
            "-i", "sine=f=330:d=8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src.absolutePath))
        val info = Media.probe(src)
        assertEquals(640, info.width)
        assertTrue(info.hasAudio && info.duration > 7.5)

        // lời kể giả (WAV ghi tuần tự) 4 giây
        val narr = File(dir, "narr.wav")
        val tone = ShortArray(24000) { (8000 * sin(2 * PI * 440 * it / 24000.0)).toInt().toShort() }
        Wav.Writer(narr).use { w ->
            w.silenceTo(0.5)
            w.write(Pcm(24000, tone))
            w.silenceTo(4.0)
        }
        assertEquals(4.0, Wav.duration(narr), 0.01)

        // 2 cảnh [1,3] + [5,7] -> 4 giây; phụ đề chữ trắng từ giây 2.5 tới 3.5 (rơi vào cảnh thứ 2)
        val clips = listOf(1.0 to 3.0, 5.0 to 7.0)
        val spec = RenderSpec(src, info, clips, Aspect.VERTICAL_FIT, 360, 0.80f to 0.96f, 0.80f to 0.96f,
            listOf(Cue(2.5, 3.5, "MMMMMMMM")), "Tiêu đề thử")
        val vid = File(dir, "v.mp4")
        Render.video(ctx, spec, vid) {}
        val vi = Media.probe(vid)
        assertEquals(360, vi.width)
        assertEquals(640, vi.height)
        assertEquals(4.0, vi.duration, 0.3)
        // vị trí phụ đề: dải 80-96% của khung gốc nằm giữa khung dọc
        val top = (640 - 202.5f) / 2 / 640
        val band0 = top + 0.80f * 202.5f / 640
        val band1 = top + 0.96f * 202.5f / 640
        val on = brightRatio(frameAt(vid, 3.0), band0, band1)
        val off = brightRatio(frameAt(vid, 1.5), band0, band1)
        assertTrue("phụ đề phải hiện ở giây 3 (on=$on)", on > 0.05)
        assertTrue("phụ đề không được hiện ở giây 1.5 (off=$off)", off < 0.01)
        assertTrue("tiêu đề vàng ở khung trên", yellowRatio(frameAt(vid, 1.5), 0.0f, top) > 0.01)

        // trộn tiếng nền + lời kể, ghép -> mp4 có tiếng
        val mixed = File(dir, "a.wav")
        Ff.mixRecap(ctx, src, true, clips, narr, 0.12, mixed)
        assertEquals(4.0, Wav.duration(mixed), 0.15)
        val out = File(dir, "final.mp4")
        Ff.mux(ctx, vid, mixed, out)
        val oi = Media.probe(out)
        assertTrue(oi.hasAudio)
        assertEquals(4.0, oi.duration, 0.3)

        // thuyết minh: tiếng gốc nhỏ lại + giọng đọc
        val dub = File(dir, "dub.wav")
        Wav.Writer(dub).use { w -> w.silenceTo(1.0); w.write(Pcm(24000, tone)); w.silenceTo(8.0) }
        val m2 = File(dir, "m2.wav")
        Ff.mixDub(ctx, src, true, dub, 0.35, m2)
        assertEquals(8.0, Wav.duration(m2), 0.2)
        Render.video(ctx, RenderSpec(src, info, null, Aspect.SOURCE, 360, null, 0.8f to 0.95f,
            listOf(Cue(0.0, 8.0, "Phụ đề tiếng Việt")), ""), vid) {}
        assertEquals(8.0, Media.probe(vid).duration, 0.3)
    }

    @Test
    fun speechAudioIsSmall() = runBlocking {
        val src = File(dir, "s.mp4")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "sine=f=200:d=60", "-c:a", "aac", src.absolutePath))
        val mp3 = File(dir, "s.mp3")
        Ff.speechAudio(ctx, src, mp3)
        assertTrue("1 phút ~ 0.24 MB (${mp3.length()})", mp3.length() in 100_000..400_000)
    }
}
