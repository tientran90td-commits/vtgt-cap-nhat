package com.vtgt.reviewphim

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import com.yausername.ffmpeg.FFmpeg
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Định dạng số cho ffmpeg: luôn dấu chấm thập phân, không theo ngôn ngữ máy (tiếng Việt dùng dấu phẩy). */
fun String.num(vararg args: Any?): String = String.format(java.util.Locale.US, this, *args)

data class VInfo(val duration: Double, val width: Int, val height: Int, val hasAudio: Boolean)

object Media {
    fun probe(f: File): VInfo {
        val m = MediaMetadataRetriever()
        try {
            m.setDataSource(f.absolutePath)
            val dur = (m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toDoubleOrNull() ?: 0.0) / 1000
            var w = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            var h = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
            val rot = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            if (rot == 90 || rot == 270) {
                val t = w; w = h; h = t
            }
            val audio = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_AUDIO) == "yes"
            if (w <= 0 || h <= 0 || dur <= 0) throw IllegalArgumentException("Không đọc được video (file hỏng hoặc không phải video).")
            return VInfo(dur, w, h, audio)
        } finally {
            m.release()
        }
    }

    /** Ảnh một khung hình (thu nhỏ) để xem trước / đặt vùng phụ đề. */
    fun frame(f: File, sec: Double, maxW: Int = 720): Bitmap? {
        val m = MediaMetadataRetriever()
        return try {
            m.setDataSource(f.absolutePath)
            val info = probe(f)
            val w = min(maxW, info.width)
            val h = (w.toDouble() * info.height / info.width).roundToInt()
            m.getScaledFrameAtTime((sec * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST_SYNC, w, h)
        } catch (e: Exception) {
            null
        } finally {
            m.release()
        }
    }
}

/** ffmpeg đi kèm thư viện youtubedl-android (có x264, mp3lame, bộ lọc âm thanh). */
object Ff {
    @Volatile
    private var ready = false

    fun init(ctx: Context) {
        if (ready) return
        FFmpeg.getInstance().init(ctx.applicationContext)
        ready = true
    }

    suspend fun run(ctx: Context, args: List<String>, onLine: (String) -> Unit = {}) = withContext(Dispatchers.IO) {
        init(ctx)
        val bin = File(ctx.applicationInfo.nativeLibraryDir, "libffmpeg.so")
        val lib = File(ctx.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/usr/lib")
        val pb = ProcessBuilder(listOf(bin.absolutePath, "-hide_banner", "-nostdin", "-y") + args)
            .redirectErrorStream(true)
        pb.environment()["LD_LIBRARY_PATH"] = lib.absolutePath
        val pr = pb.start()
        val job = currentCoroutineContext()[Job]
        val handle = job?.invokeOnCompletion { if (pr.isAlive) pr.destroy() }
        val tail = ArrayDeque<String>()
        try {
            pr.inputStream.bufferedReader().forEachLine {
                onLine(it)
                tail.addLast(it)
                if (tail.size > 40) tail.removeFirst()
            }
            val code = pr.waitFor()
            currentCoroutineContext().ensureActive()
            if (code != 0) {
                val why = tail.lastOrNull { it.isNotBlank() && !it.startsWith("  ") }?.trim() ?: "không rõ"
                throw RuntimeException("ffmpeg lỗi: $why (mã $code)\n" + tail.takeLast(10).joinToString("\n"))
            }
        } finally {
            handle?.dispose()
            if (pr.isAlive) pr.destroy()
        }
    }

    /** Âm thanh nhỏ gọn để gửi nhận dạng giọng nói (mono 16 kHz, mp3 32 kbps ~ 0.24 MB/phút). */
    suspend fun speechAudio(ctx: Context, src: File, out: File, start: Double = 0.0, dur: Double = 0.0) {
        val a = mutableListOf<String>()
        if (start > 0) a += listOf("-ss", "%.3f".num(start))
        a += listOf("-i", src.absolutePath)
        if (dur > 0) a += listOf("-t", "%.3f".num(dur))
        a += listOf("-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", out.absolutePath)
        run(ctx, a)
    }

    /** Thuyết minh: tiếng gốc nhỏ lại (tự nhỏ thêm khi có giọng đọc) + giọng đọc -> WAV. */
    suspend fun mixDub(ctx: Context, src: File, hasAudio: Boolean, dub: File?, origVol: Double, out: File) {
        val fmt = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
        val a = mutableListOf("-i", src.absolutePath)
        if (dub != null) a += listOf("-i", dub.absolutePath)
        val graph = when {
            !hasAudio && dub != null -> "[1:a]$fmt[a]"
            dub == null -> "[0:a]$fmt,volume=%.2f[a]".num(origVol)
            origVol <= 0.0 -> "[1:a]$fmt[a]"
            else -> "[1:a]$fmt,asplit=2[sc][d];[0:a]$fmt,volume=%.2f[o];".num(origVol) +
                "[o][sc]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=350[duck];" +
                "[duck][d]amix=inputs=2:duration=first:normalize=0[a]"
        }
        a += listOf("-filter_complex", graph, "-map", "[a]", "-vn", "-c:a", "pcm_s16le", out.absolutePath)
        run(ctx, a)
    }

    /** Review: âm thanh gốc của các cảnh đã chọn (rất nhỏ, làm nền) + lời kể -> WAV. */
    suspend fun mixRecap(ctx: Context, src: File, hasAudio: Boolean, clips: List<Pair<Double, Double>>, narr: File,
                         bgVol: Double, out: File, bgm: File? = null, bgmVol: Double = 0.25) {
        val fmt = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
        val a = mutableListOf("-i", src.absolutePath, "-i", narr.absolutePath)
        if (bgm != null) a += listOf("-stream_loop", "-1", "-i", bgm.absolutePath)
        // nhạc nền (lặp cho đủ dài), tự nhỏ lại khi có giọng đọc
        val music = if (bgm == null) "" else
            "[2:a]$fmt,volume=%.2f[m];[n]asplit=2[nv][nsc];[m][nsc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[md];".num(bgmVol)
        val graph = if (!hasAudio || bgVol <= 0.0) {
            "[1:a]$fmt[n];" + music + (if (bgm == null) "[n]anull[a]" else "[nv][md]amix=inputs=2:duration=first:normalize=0[a]")
        } else {
            val sb = StringBuilder()
            clips.forEachIndexed { i, (s, e) ->
                sb.append("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,$fmt[c$i];".num(s, e))
            }
            clips.indices.forEach { sb.append("[c$it]") }
            sb.append("concat=n=${clips.size}:v=0:a=1,volume=%.2f[bg];".num(bgVol))
            sb.append("[1:a]$fmt[n];").append(music)
            sb.append(if (bgm == null) "[n][bg]amix=inputs=2:duration=first:normalize=0[a]"
            else "[nv][bg][md]amix=inputs=3:duration=first:normalize=0[a]")
            sb.toString()
        }
        a += listOf("-filter_complex", graph, "-map", "[a]", "-vn", "-c:a", "pcm_s16le", out.absolutePath)
        run(ctx, a)
    }

    /** Ghép hình (đã dựng) + tiếng -> mp4 xem được trên mọi máy. */
    suspend fun mux(ctx: Context, video: File, audio: File, out: File) {
        val base = listOf("-i", video.absolutePath, "-i", audio.absolutePath, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-shortest", "-movflags", "+faststart")
        try {
            run(ctx, base + listOf("-c:a", "aac", "-b:a", "160k", out.absolutePath))
        } catch (e: RuntimeException) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            run(ctx, base + listOf("-c:a", "libmp3lame", "-b:a", "160k", out.absolutePath))
        }
    }
}

/** Âm thanh PCM 16-bit mono. */
class Pcm(val rate: Int, val data: ShortArray) {
    val seconds: Double get() = data.size.toDouble() / rate
}

object Wav {
    fun read(f: File): Pcm {
        val b = ByteBuffer.wrap(f.readBytes()).order(ByteOrder.LITTLE_ENDIAN)
        if (b.limit() < 44 || b.getInt(0) != 0x46464952) throw IllegalArgumentException("Không phải file WAV: ${f.name}")
        var pos = 12
        var channels = 1
        var rate = 22050
        var bits = 16
        while (pos + 8 <= b.limit()) {
            val id = b.getInt(pos)
            val size = b.getInt(pos + 4)
            val body = pos + 8
            if (id == 0x20746d66) { // "fmt "
                channels = b.getShort(body + 2).toInt()
                rate = b.getInt(body + 4)
                bits = b.getShort(body + 14).toInt()
            } else if (id == 0x61746164) { // "data"
                if (bits != 16) throw IllegalArgumentException("WAV $bits-bit chưa hỗ trợ")
                val len = min(size, b.limit() - body) / 2 / channels
                val out = ShortArray(len)
                for (i in 0 until len) {
                    var s = 0
                    for (c in 0 until channels) s += b.getShort(body + (i * channels + c) * 2)
                    out[i] = (s / channels).toShort()
                }
                return Pcm(rate, out)
            }
            pos = body + size + (size and 1)
        }
        throw IllegalArgumentException("WAV không có dữ liệu: ${f.name}")
    }

    fun resample(p: Pcm, rate: Int): Pcm {
        if (p.rate == rate || p.data.isEmpty()) return p
        val n = (p.data.size.toLong() * rate / p.rate).toInt()
        val out = ShortArray(n)
        val step = p.rate.toDouble() / rate
        for (i in 0 until n) {
            val x = i * step
            val j = x.toInt()
            val f = x - j
            val a = p.data[min(j, p.data.size - 1)]
            val c = p.data[min(j + 1, p.data.size - 1)]
            out[i] = (a + (c - a) * f).roundToInt().toShort()
        }
        return Pcm(rate, out)
    }

    /** Ghi WAV tuần tự: đặt từng câu vào đúng thời điểm, không chồng lên nhau. */
    class Writer(private val f: File, val rate: Int = 24000) : AutoCloseable {
        private val out = f.outputStream().buffered(1 shl 16)
        var samples = 0L
            private set
        val seconds: Double get() = samples.toDouble() / rate

        init {
            out.write(ByteArray(44))
        }

        fun silenceTo(sec: Double) {
            val target = (sec * rate).toLong()
            val zero = ByteArray(8192)
            while (samples < target) {
                val n = min(4096L, target - samples).toInt()
                out.write(zero, 0, n * 2)
                samples += n
            }
        }

        fun write(p: Pcm) {
            val r = Wav.resample(p, rate)
            val buf = ByteBuffer.allocate(r.data.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (s in r.data) buf.putShort(s)
            out.write(buf.array())
            samples += r.data.size
        }

        override fun close() {
            out.flush()
            out.close()
            val dataLen = samples * 2
            RandomAccessFile(f, "rw").use { raf ->
                val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
                h.putInt(0x46464952).putInt((36 + dataLen).toInt()).putInt(0x45564157) // RIFF....WAVE
                h.putInt(0x20746d66).putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2)
                    .putShort(2).putShort(16)
                h.putInt(0x61746164).putInt(dataLen.toInt())
                raf.seek(0)
                raf.write(h.array())
            }
        }
    }

    fun duration(f: File): Double = read(f).seconds

    fun silence(f: File, sec: Double) = Writer(f).use { it.silenceTo(max(0.1, sec)) }
}
