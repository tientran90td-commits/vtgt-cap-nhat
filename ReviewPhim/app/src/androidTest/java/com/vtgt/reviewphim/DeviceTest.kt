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
            // chữ phụ đề trắng, hoặc vàng khi karaoke đã đọc tới
            if ((c shr 16 and 255) > 200 && (c shr 8 and 255) > 180) bright++
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
        // máy để tiếng Việt (dấu phẩy thập phân) - lỗi ffmpeg 234 từng xảy ra chỉ ở máy người dùng
        java.util.Locale.setDefault(java.util.Locale("vi", "VN"))
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
            listOf(Cue(2.5, 3.5, "MMMMMMMM")), "Tiêu đề thử", karaoke = true, hook = "HOOK HOOK")
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
        val yellow = yellowRatio(frameAt(vid, 1.5), 0.0f, top)
        assertTrue("tiêu đề vàng ở khung trên (yellow=$yellow)", yellow > 0.0005)
        // tiêu đề hook lớn giữa màn hình trong 2.6 giây đầu, sau đó tắt
        val hookOn = yellowRatio(frameAt(vid, 1.0), 0.37f, 0.47f)
        val hookOff = yellowRatio(frameAt(vid, 3.5), 0.37f, 0.47f)
        assertTrue("hook phải hiện ở giây 1 (on=$hookOn)", hookOn > 0.003)
        assertTrue("hook phải tắt ở giây 3.5 (off=$hookOff)", hookOff < 0.0005)

        // trộn tiếng nền + lời kể, ghép -> mp4 có tiếng
        val mixed = File(dir, "a.wav")
        Ff.mixRecap(ctx, src, true, clips, narr, 0.12, mixed)
        assertEquals(4.0, Wav.duration(mixed), 0.15)
        // nhạc nền ngắn hơn video: lặp lại cho đủ, tự nhỏ khi có giọng đọc
        val bgm = File(dir, "bgm.mp3")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "sine=f=660:d=1.5", "-c:a", "libmp3lame", bgm.absolutePath))
        Ff.mixRecap(ctx, src, true, clips, narr, 0.12, mixed, bgm, 0.3)
        assertEquals(4.0, Wav.duration(mixed), 0.15)
        Ff.mixRecap(ctx, src, false, clips, narr, 0.12, mixed, bgm, 0.3)
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
        assertEquals(8.0, Wav.duration(m2), 0.35)  // âm thanh aac + -shortest có thể hụt ~0.25 giây
        Render.video(ctx, RenderSpec(src, info, null, Aspect.SOURCE, 360, null, 0.8f to 0.95f,
            listOf(Cue(0.0, 8.0, "Phụ đề tiếng Việt")), ""), vid) {}
        assertEquals(8.0, Media.probe(vid).duration, 0.3)
    }

    @Test
    fun shotDetectionOnDevice() = runBlocking {
        // video đổi màu (đổi cảnh) mỗi 2 giây, giây 4-6 màn hình đen
        val src = File(dir, "cuts.mp4")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=10",
            "-vf", "hue=H=floor(t/2)*PI/2,drawbox=c=black:t=fill:enable='between(t,4,6)'",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", src.absolutePath))
        val frames = Shots.analyze(ctx, src, 0.0, 10.0)
        assertTrue("phải đọc được khung (${frames.size})", frames.size > 40)
        val sh = Shots.shots(frames, 10.0)
        // đổi sắc màu (độ sáng gần như giữ nguyên) không tính là cắt cảnh; vào / ra màn hình đen thì có
        assertTrue("phải thấy các lần cắt cảnh (${sh.size})", sh.size >= 3)
        assertTrue("phải nhận ra cảnh đen: $sh", sh.any { it.y < Shots.DARK_Y && it.a in 3.5..4.5 })
        val p = Shots.plan(sh, 0.5, 5.0, 10.0)
        assertTrue("không lấy cảnh đen: $p", p.none { (a, d) -> a < 5.9 && a + d > 4.1 })
        assertEquals(5.0, p.sumOf { it.second }, 0.05)
    }

    @Test
    fun watchSheetsOnDevice() = runBlocking {
        // 60 giây: đổi cảnh mỗi 6 giây, giây 12-24 màn hình đen (không được chụp)
        val src = File(dir, "watch.mp4")
        Ff.run(ctx, listOf("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=60",
            "-vf", "hue=H=floor(t/6)*PI/3,drawbox=c=black:t=fill:enable='between(t,12,24)'",
            "-c:v", "libx264", "-g", "50", "-pix_fmt", "yuv420p", src.absolutePath))
        val i = Media.probe(src)
        val out = File(dir, "watch").apply { deleteRecursively() }
        val sheets = Watch.sheets(src, i, out) {}
        val times = sheets.flatMap { it.times }
        assertTrue("phải chụp được khung: $times", times.size >= 6)
        assertTrue("không chụp cảnh đen: $times", times.none { it in 12.5..23.5 })
        assertEquals(times.sorted(), times)
        assertTrue(sheets.all { it.file.length() > 5000 && it.times.size <= Watch.GRID * Watch.GRID })
        val bmp = android.graphics.BitmapFactory.decodeFile(sheets[0].file.path)
        assertEquals(Watch.GRID * 256 + (Watch.GRID - 1) * 4, bmp.width)
        // kịch bản có mô tả hình: yêu cầu gửi AI phải dặn kể cả cảnh không thoại
        val tl = Watch.timeline(listOf(Line(1.0, 2.0, "hello")), listOf(Line(13.0, 20.0, "Hai người đánh nhau")))
        val pr = Prompts.recap("Phim", 60.0, tl, 60, "hap_dan", Prefs(ctx))
        assertTrue(pr.contains("#2 [00:13] [HÌNH] Hai người đánh nhau"))
        assertTrue(pr.contains("KHÔNG bỏ qua các cảnh hành động"))
        val w = Prompts.watch("Phim", 1, 1, 0.0, 60.0, sheets.size, listOf(Line(1.0, 2.0, "hello")), Prefs(ctx))
        assertTrue(w.contains("mm:ss-mm:ss | mô tả") && w.contains("[00:01] hello"))
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
