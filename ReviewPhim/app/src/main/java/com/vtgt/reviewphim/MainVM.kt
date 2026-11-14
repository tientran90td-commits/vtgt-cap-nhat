package com.vtgt.reviewphim

import android.app.Application
import android.content.ContentValues
import android.graphics.Bitmap
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

class MainVM(app: Application) : AndroidViewModel(app) {
    private val ctx get() = getApplication<Application>()
    val prefs = Prefs(app)
    val tts = Tts(app)
    val updater = Updater(app)

    // ---- video & dữ liệu
    var video by mutableStateOf<File?>(null)
    var title by mutableStateOf("")
    var info by mutableStateOf<VInfo?>(null)
    var preview by mutableStateOf<Bitmap?>(null)
    var lines by mutableStateOf<List<Line>>(emptyList())        // lời gốc (+ bản dịch khi ở chế độ dịch)
    var recapTitle by mutableStateOf("")
    var segs by mutableStateOf<List<Seg>>(emptyList())          // kịch bản review

    // ---- lựa chọn (nhớ lại lần sau)
    var mode by mutableStateOf(prefs.str("mode", "recap"))       // recap | translate
    var stt by mutableStateOf(prefs.str("stt", "whisper"))       // whisper | ocr | srt
    var aspect by mutableStateOf(Aspect.valueOf(prefs.str("aspect", Aspect.VERTICAL_FIT.name)))
    var quality by mutableStateOf(prefs.str("quality", "720").toInt())
    var targetSec by mutableStateOf(prefs.str("target", "180").toInt())
    var style by mutableStateOf(prefs.str("style", "hap_dan"))
    var output by mutableStateOf(prefs.str("output", "dub_sub"))  // dub_sub | sub | dub
    var cover by mutableStateOf(prefs.bool("cover", true))
    var bandTop by mutableFloatStateOf(prefs.num("band_top", 0.80f))
    var bandBottom by mutableFloatStateOf(prefs.num("band_bottom", 0.96f))
    var voice by mutableStateOf(prefs.str("voice"))
    var rate by mutableFloatStateOf(prefs.num("rate", 1.1f))
    var multiShot by mutableStateOf(prefs.bool("multi_shot", true))
    var karaoke by mutableStateOf(prefs.bool("karaoke", true))
    var hookTitle by mutableStateOf(prefs.bool("hook_title", true))
    var bgmName by mutableStateOf(prefs.str("bgm_name"))

    // ---- tiến trình
    val logs = mutableStateListOf<String>()
    var progress by mutableFloatStateOf(0f)
    var status by mutableStateOf("")
    var busy by mutableStateOf(false)
    var result by mutableStateOf<Uri?>(null)
    var update by mutableStateOf<Updater.Release?>(null)
    var manualPrompt by mutableStateOf<String?>(null)
    private var manualReply: CompletableDeferred<String?>? = null
    private var job: Job? = null

    private val work get() = File(ctx.filesDir, "work").apply { mkdirs() }

    fun save(k: String, v: String) = prefs.set(k, v)

    fun log(m: String) {
        val t = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        viewModelScope.launch(Dispatchers.Main) {
            logs.add("[$t] $m")
            if (logs.size > 300) logs.removeAt(0)
        }
    }

    private fun prog(p: Float, s: String? = null) {
        viewModelScope.launch(Dispatchers.Main) {
            progress = p.coerceIn(0f, 1f)
            if (s != null) status = s
        }
    }

    // ================================================================ chọn / tải video
    fun openVideo(uri: Uri) = launchTask("Mở video") {
        val name = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) it.getString(0) else null
        } ?: "video.mp4"
        val dst = File(work, "input.mp4")
        withContext(Dispatchers.IO) {
            ctx.contentResolver.openInputStream(uri)?.use { i -> dst.outputStream().use { o -> i.copyTo(o) } }
                ?: throw IllegalStateException("Không đọc được video đã chọn.")
        }
        setVideo(dst, name.substringBeforeLast('.'))
    }

    fun download(url: String) = launchTask("Tải video") {
        val u = Download.findUrl(url) ?: throw IllegalArgumentException("Không thấy link trong nội dung dán.")
        log("Tải: $u")
        val (f, t) = Download.fetch(ctx, prefs, u, File(work, "dl").apply { deleteRecursively() }, ::log) {
            prog(it, "Đang tải video ${(it * 100).toInt()}%")
        }
        setVideo(f, t)
    }

    private suspend fun setVideo(f: File, name: String) {
        val i = withContext(Dispatchers.IO) { Media.probe(f) }
        val pv = withContext(Dispatchers.IO) { Media.frame(f, i.duration * 0.3) }
        withContext(Dispatchers.Main) {
            video = f
            title = name
            info = i
            preview = pv
            lines = emptyList()
            segs = emptyList()
            recapTitle = ""
            result = null
        }
        log("Video: $name - ${fmtTime(i.duration)}, ${i.width}x${i.height}${if (i.hasAudio) "" else ", không có tiếng"}")
    }

    fun loadSrt(uri: Uri) = launchTask("Đọc phụ đề") {
        val text = withContext(Dispatchers.IO) {
            ctx.contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
        }
        val l = parseSrt(text)
        if (l.isEmpty()) throw IllegalArgumentException("File phụ đề không có câu nào.")
        withContext(Dispatchers.Main) { lines = l; segs = emptyList() }
        log("Phụ đề: ${l.size} câu.")
    }

    fun setBgm(uri: Uri?) = launchTask("Nhạc nền") {
        val f = File(work, "bgm.audio")
        if (uri == null) {
            f.delete()
            prefs.set("bgm_name", "")
            withContext(Dispatchers.Main) { bgmName = "" }
            return@launchTask
        }
        val name = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) it.getString(0) else null
        } ?: "nhạc"
        withContext(Dispatchers.IO) {
            ctx.contentResolver.openInputStream(uri)?.use { i -> f.outputStream().use { o -> i.copyTo(o) } }
        }
        prefs.set("bgm_name", name)
        withContext(Dispatchers.Main) { bgmName = name }
    }

    // ================================================================ chạy
    fun cancel() {
        job?.cancel()
        manualReply?.complete(null)
    }

    fun resetScript() {
        lines = if (mode == "translate") lines.map { it.copy(vi = "") } else lines
        segs = emptyList()
        recapTitle = ""
    }

    fun resetAll() {
        lines = emptyList()
        resetScript()
    }

    /** Làm từ đầu tới cuối; bước nào đã có (lời gốc, kịch bản đã sửa) thì dùng lại. */
    fun makeVideo() = launchTask("Làm video", keepAlive = true) {
        val v = video ?: throw IllegalStateException("Chọn video hoặc dán link trước.")
        val i = info!!
        if (lines.isEmpty()) transcript(v, i)
        if (mode == "recap") {
            if (segs.isEmpty()) writeRecap(i)
            renderRecap(v, i)
        } else {
            if (lines.any { it.vi.isBlank() }) translate()
            renderTranslate(v, i)
        }
    }

    /** Chỉ dựng lại video từ kịch bản / bản dịch hiện có (sau khi sửa tay). */
    fun renderOnly() = launchTask("Xuất lại video", keepAlive = true) {
        val v = video ?: throw IllegalStateException("Chưa có video.")
        if (mode == "recap") {
            if (segs.isEmpty()) throw IllegalStateException("Chưa có kịch bản.")
            renderRecap(v, info!!)
        } else {
            if (lines.isEmpty()) throw IllegalStateException("Chưa có bản dịch.")
            renderTranslate(v, info!!)
        }
    }

    private fun launchTask(name: String, keepAlive: Boolean = false, block: suspend () -> Unit) {
        if (busy) return
        busy = true
        progress = 0f
        status = "⏳ $name..."
        if (keepAlive) KeepAliveService.start(ctx, name)
        job = viewModelScope.launch(Dispatchers.Default) {
            try {
                block()
                status = "✅ $name - xong"
                progress = 1f
            } catch (e: CancellationException) {
                status = "Đã hủy"
                log("⏹ Đã hủy.")
            } catch (e: Exception) {
                status = "❌ ${e.message?.lines()?.firstOrNull() ?: e.javaClass.simpleName}"
                log("❌ $name: ${e.message ?: e}")
            } finally {
                busy = false
                manualPrompt = null
                if (keepAlive) KeepAliveService.stop(ctx)
            }
        }
    }

    // ================================================================ AI (API hoặc dán tay)
    private suspend fun ask(prompt: String): String {
        if (Ai.manual(prefs)) {
            val d = CompletableDeferred<String?>()
            manualReply = d
            withContext(Dispatchers.Main) { manualPrompt = prompt }
            log("🐋 Chép yêu cầu → dán vào DeepSeek → dán câu trả lời lại vào app.")
            val r = d.await()
            withContext(Dispatchers.Main) { manualPrompt = null }
            return r ?: throw CancellationException("Đã hủy")
        }
        return Ai.chat(prefs, "Bạn là trợ lý biên tập video tiếng Việt. Làm đúng yêu cầu, chỉ trả lời JSON.", prompt, ::log)
    }

    fun answerManual(text: String?) {
        manualReply?.complete(text)
    }

    // ================================================================ các bước
    private suspend fun transcript(v: File, i: VInfo) {
        prog(0f, "Lấy lời gốc...")
        val l = when (stt) {
            "ocr" -> {
                log("Đọc phụ đề trên hình (vùng ${(bandTop * 100).toInt()}–${(bandBottom * 100).toInt()}% chiều cao)...")
                Stt.ocr(v, i, bandTop, bandBottom, ::log) { prog(it * 0.3f, "Đọc chữ trên hình ${(it * 100).toInt()}%") }
            }
            "srt" -> throw IllegalStateException("Chọn file phụ đề .srt trước.")
            else -> Stt.whisper(ctx, prefs, v, i, ::log) { prog(it * 0.3f, "Nghe lời thoại ${(it * 100).toInt()}%") }
        }
        if (l.isEmpty()) throw IllegalStateException(
            if (stt == "ocr") "Không đọc được chữ nào: chỉnh lại vùng phụ đề cho đúng chỗ chữ." else "Không nghe được lời thoại nào.")
        withContext(Dispatchers.Main) { lines = l }
        log("Lời gốc: ${l.size} câu.")
    }

    private suspend fun writeRecap(i: VInfo) {
        prog(0.32f, "AI viết kịch bản review...")
        log("AI viết kịch bản review ~${targetSec / 60} phút...")
        val prompt = Prompts.recap(title, i.duration, lines, min(targetSec, (i.duration * 0.9).toInt().coerceAtLeast(30)),
            style, prefs)
        var last: Exception? = null
        repeat(2) {
            try {
                val (t, s) = Prompts.parseRecap(ask(prompt), i.duration)
                withContext(Dispatchers.Main) {
                    recapTitle = t.ifBlank { title }
                    segs = s
                }
                log("Kịch bản: \"$recapTitle\" - ${s.size} đoạn, ${s.sumOf { it.text.length }} ký tự.")
                return
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                last = e
                log("Kịch bản lỗi (${e.message?.take(100)}) - thử lại...")
            }
        }
        throw IllegalStateException("AI không viết được kịch bản: ${last?.message}")
    }

    private suspend fun translate() {
        val cur = lines.map { it.copy() }
        val todo = cur.indices.filter { cur[it].vi.isBlank() }
        prog(0.32f, "Dịch ${todo.size} câu...")
        val manual = Ai.manual(prefs)
        var first = cur.none { it.vi.isNotBlank() }
        for (round in 0 until 3) {
            val miss = cur.indices.filter { cur[it].vi.isBlank() && !cur[it].text.matches(Regex("[♪\\s\\p{Punct}]*")) }
            if (miss.isEmpty()) break
            if (round > 0) log("Dịch lại ${miss.size} câu bị sót...")
            val size = if (manual) 120 else 30
            val parts = miss.chunked(size)
            if (manual) {
                for ((k, p) in parts.withIndex()) {
                    log("Phần ${k + 1}/${parts.size}: ${p.size} câu")
                    val got = Prompts.parseLines(ask(Prompts.translate(title, cur, p, prefs, first)), p)
                    first = false
                    got.forEach { (j, v) -> cur[j].vi = v }
                    prog(0.32f + 0.3f * cur.count { it.vi.isNotBlank() } / cur.size)
                }
            } else {
                val sem = Semaphore(3)
                val done = java.util.concurrent.atomic.AtomicInteger()
                coroutineScopeAll(parts.map { p ->
                    suspend {
                        sem.withPermit {
                            try {
                                val got = Prompts.parseLines(ask(Prompts.translate(title, cur, p, prefs, true)), p)
                                synchronized(cur) { got.forEach { (j, v) -> cur[j].vi = v } }
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                log("Lô ${p.first() + 1}-${p.last() + 1} lỗi: ${e.message?.take(120)}")
                            }
                            val d = done.incrementAndGet()
                            prog(0.32f + 0.3f * d / parts.size, "Dịch ${min(cur.size, d * size)}/${cur.size} câu")
                        }
                    }
                })
            }
        }
        // câu đọc quá nhanh -> AI rút gọn (chỉ khi dùng API; dán tay thì giọng đọc tự nói nhanh hơn chút)
        if (!manual && output != "sub") {
            for (round in 0 until 2) {
                val long = cur.indices.filter { cur[it].vi.length > maxChars(cur, it) * 1.3 }
                if (long.isEmpty()) break
                log("⚡ Tối ưu thuyết minh: rút gọn ${long.size} câu đọc quá nhanh (vòng ${round + 1})...")
                for (p in long.chunked(30)) {
                    try {
                        val got = Prompts.parseLines(ask(Prompts.shorten(cur, p, 1.0 - 0.1 * round)), p)
                        got.forEach { (j, v) -> if (v.isNotBlank() && v.length < cur[j].vi.length) cur[j].vi = v }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        log("Rút gọn lỗi: ${e.message?.take(100)}")
                    }
                }
            }
        }
        withContext(Dispatchers.Main) { lines = cur }
        val left = cur.count { it.vi.isBlank() }
        log("Đã dịch ${cur.size - left}/${cur.size} câu." + if (left > 0) " Câu còn thiếu sửa tay ở tab Kịch bản." else "")
    }

    private suspend fun coroutineScopeAll(tasks: List<suspend () -> Unit>) =
        kotlinx.coroutines.coroutineScope { tasks.map { t -> async { t() } }.awaitAll() }

    private suspend fun speak(text: String, out: File, r: Float): File =
        tts.synth(text, out, voice, r, prefs.str("tts_engine"))

    private suspend fun renderRecap(v: File, i: VInfo) {
        val dir = File(ctx.cacheDir, "tts").apply { deleteRecursively(); mkdirs() }
        val narr = File(work, "narration.wav")
        val clips = mutableListOf<Pair<Double, Double>>()
        val cues = mutableListOf<Cue>()
        val maxChars = if (aspect == Aspect.SOURCE && i.width > i.height) 44 else 30
        log("Đọc giọng ${segs.size} đoạn...")
        var shotsUsed = 0
        Wav.Writer(narr).use { w ->
            var t = 0.0
            var usedEnd = 0.0
            val starts = segs.map { it.start }
            for ((k, s) in segs.withIndex()) {
                prog(0.4f + 0.3f * k / segs.size, "Đọc giọng ${k + 1}/${segs.size}")
                val wav = speak(s.text, File(dir, "s$k.wav"), rate)
                val pcm = Wav.read(wav)
                val dur = pcm.seconds + 0.35
                var start = s.start
                if (k > 0 && start < usedEnd) start = usedEnd  // không chiếu lại cảnh vừa dùng
                start = start.coerceIn(0.0, max(0.0, i.duration - dur - 0.5))
                // ghép nhiều cảnh ngắn bắt đầu ở điểm cắt cảnh, bỏ cảnh đen (cửa sổ tới đoạn kể sau)
                val pieces = if (multiShot) {
                    val nxt = starts.drop(k + 1).firstOrNull { it > start + dur }
                    val win = minOf(maxOf(dur + 2.0, minOf(dur * 3.0, (nxt ?: (start + dur * 3.0)) - start, 45.0)),
                        i.duration - start)
                    val sh = Shots.shots(Shots.analyze(ctx, v, start - 0.5, win + 0.5), start + win)
                    Shots.plan(sh, start, dur, i.duration)
                } else listOf(start to dur)
                if (k > 0) usedEnd = pieces.maxOf { it.first + it.second }
                w.silenceTo(t + 0.15)
                w.write(pcm)
                cues += splitCues(s.text, t + 0.15, pcm.seconds, maxChars)
                for ((a, d) in pieces) clips += a to min(i.duration, a + d)
                shotsUsed += pieces.size
                t += pieces.sumOf { (a, d) -> min(i.duration, a + d) - a }
                w.silenceTo(t)
            }
        }
        log("Ghép ${segs.size} đoạn lời kể từ $shotsUsed cảnh.")
        val bgm = File(work, "bgm.audio").takeIf { it.exists() && bgmName.isNotBlank() }
        val name = recapTitle.ifBlank { title }
        finish(v, i, clips, cues, name, hook = if (hookTitle) name else "") { mixed ->
            Ff.mixRecap(ctx, v, i.hasAudio, clips, narr, prefs.num("bg_vol", 0.12f).toDouble(), mixed, bgm,
                prefs.num("bgm_vol", 0.25f).toDouble())
        }
    }

    private suspend fun renderTranslate(v: File, i: VInfo) {
        val dub = output != "sub"
        val subs = output != "dub"
        var dubFile: File? = null
        if (dub) {
            val dir = File(ctx.cacheDir, "tts").apply { deleteRecursively(); mkdirs() }
            dubFile = File(work, "dub.wav")
            val ls = lines
            var late = 0
            log("Đọc giọng thuyết minh ${ls.count { it.vi.isNotBlank() }} câu...")
            Wav.Writer(dubFile).use { w ->
                for ((k, l) in ls.withIndex()) {
                    if (l.vi.isBlank()) continue
                    prog(0.65f * k / ls.size + 0.05f, "Đọc giọng ${k + 1}/${ls.size}")
                    val slot = maxChars(ls, k) / CPS
                    var r = rate
                    var pcm = Wav.read(speak(l.vi, File(dir, "l$k.wav"), r))
                    if (pcm.seconds > slot * 1.05 && r < rate * 1.35f) {
                        r = (rate * min(1.35, pcm.seconds / slot)).toFloat()
                        pcm = Wav.read(speak(l.vi, File(dir, "l$k.wav"), r))
                    }
                    if (w.seconds > l.start + 0.3) late++
                    w.silenceTo(l.start)
                    w.write(pcm)
                }
                w.silenceTo(i.duration)
            }
            if (late > 0) log("$late câu đọc trễ một chút so với hình (câu dịch dài).")
        }
        val maxChars = if (aspect == Aspect.SOURCE && i.width > i.height) 44 else 30
        val cues = if (subs) lines.filter { it.vi.isNotBlank() }.flatMap {
            splitCues(it.vi, it.start, it.end - it.start, maxChars * 2)
        } else emptyList()
        finish(v, i, null, cues, title) { mixed ->
            if (!i.hasAudio && dubFile == null) Wav.silence(mixed, i.duration)
            else Ff.mixDub(ctx, v, i.hasAudio, dubFile, if (dub) prefs.num("orig_vol", 0.35f).toDouble() else 1.0, mixed)
        }
    }

    /** Dựng hình + trộn tiếng + ghép + lưu vào thư viện ảnh. */
    private suspend fun finish(v: File, i: VInfo, clips: List<Pair<Double, Double>>?, cues: List<Cue>, name: String,
                               hook: String = "", mixAudio: suspend (File) -> Unit) {
        val vid = File(work, "video_only.mp4")
        val aud = File(work, "audio.wav")
        val out = File(work, "final.mp4")
        log("Trộn âm thanh...")
        prog(0.72f, "Trộn âm thanh")
        mixAudio(aud)
        val sp = spec(v, i, clips, cues, name, hook)
        log("Dựng hình ${Render.outSize(sp).let { "${it.first}x${it.second}" }}...")
        Render.video(ctx, sp, vid) { prog(0.75f + 0.22f * it, "Dựng video ${(it * 100).toInt()}%") }
        prog(0.97f, "Ghép tiếng")
        Ff.mux(ctx, vid, aud, out)
        File(work, "final.srt").writeText(toSrt(cues))
        val uri = saveToGallery(out, name)
        vid.delete()
        aud.delete()
        withContext(Dispatchers.Main) { result = uri }
        log("✅ Xong! Video đã lưu vào Thư viện ảnh → Movies/ReviewPhim.")
    }

    private fun spec(v: File, i: VInfo, clips: List<Pair<Double, Double>>?, cues: List<Cue>, name: String, hook: String) =
        RenderSpec(v, i, clips, aspect, quality, if (cover) bandTop to bandBottom else null, bandTop to bandBottom, cues, name,
            karaoke = karaoke && mode == "recap", hook = hook)

    private suspend fun saveToGallery(f: File, name: String): Uri = withContext(Dispatchers.IO) {
        val safe = name.replace(Regex("[\\\\/:*?\"<>|\\n]"), " ").trim().take(80).ifBlank { "ReviewPhim" }
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "$safe.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/ReviewPhim")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val r = ctx.contentResolver
        val uri = r.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values)
            ?: throw IllegalStateException("Không lưu được vào thư viện ảnh.")
        r.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
        values.clear()
        values.put(MediaStore.Video.Media.IS_PENDING, 0)
        r.update(uri, values, null, null)
        uri
    }

    // ================================================================ nghe thử
    fun previewVoice() = launchTask("Nghe thử giọng") {
        val f = speak("Xin chào, đây là giọng đọc review phim của bạn. Chúc bạn có video thật nhiều lượt xem!",
            File(ctx.cacheDir, "preview.wav"), rate)
        withContext(Dispatchers.Main) {
            android.media.MediaPlayer().apply {
                setDataSource(f.absolutePath)
                setOnCompletionListener { it.release() }
                prepare()
                start()
            }
        }
    }

    override fun onCleared() {
        tts.shutdown()
        super.onCleared()
    }
}
