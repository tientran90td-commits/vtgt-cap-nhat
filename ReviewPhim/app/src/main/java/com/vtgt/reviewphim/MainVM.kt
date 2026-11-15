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
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

/**
 * Một bước bạn làm tay thay cho gọi API: chép yêu cầu -> dán sang AI (DeepSeek / Gemini) -> dán câu trả lời lại.
 * target: "deepseek" | "gemini"; file: file cần gửi kèm (âm thanh cho Gemini nghe).
 */
data class ManualAsk(val step: String, val target: String, val prompt: String, val note: String = "",
                     val file: Uri? = null, val fileName: String = "", val canApi: Boolean = false)

const val RETRY_API = "\u0000api"

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
    var ask by mutableStateOf<ManualAsk?>(null)                  // bước đang chờ bạn làm tay (chép / dán)
    private var manualReply: CompletableDeferred<String?>? = null
    private val manualLock = kotlinx.coroutines.sync.Mutex()
    @Volatile
    private var apiDown = false                                   // API vừa lỗi trong lần làm này -> các bước sau làm tay luôn
    var dlHelp by mutableStateOf<String?>(null)                   // link tải không được -> hướng dẫn tải tay
    var apiWaiting by mutableStateOf(false)                       // đang chờ API trả lời -> hiện nút "Làm tay ngay"
    @Volatile
    private var skipApi = false

    /** Bạn bấm "🖐 Làm tay ngay" trong lúc chờ API. */
    fun skipToManual() {
        skipApi = true
    }
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
        withContext(Dispatchers.Main) { dlHelp = null }
        val (f, t) = try {
            Download.fetch(ctx, prefs, u, File(work, "dl").apply { deleteRecursively() }, ::log) {
                prog(it, "Đang tải video ${(it * 100).toInt()}%")
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            withContext(Dispatchers.Main) { dlHelp = u }  // hiện cách tải tay
            throw IllegalStateException("Không tải được link này - làm tay: xem hướng dẫn ở mục 1. (${e.message?.lines()?.firstOrNull()})")
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
        val l = parseSubs(text)
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

    /** Các bước sẽ làm, bước nào bạn phải làm tay (🖐) - hiện trước khi bấm làm. */
    fun plan(): List<Pair<String, Boolean>> {
        val out = mutableListOf<Pair<String, Boolean>>()
        val aiManual = Ai.manual(prefs)
        val groq = prefs.key("groq").isNotBlank() || prefs.key("openai").isNotBlank()
        out += if (lines.isNotEmpty()) "Lời gốc: đã có ${lines.size} câu" to false else when (stt) {
            "ocr" -> "Lời gốc: máy tự đọc phụ đề trên hình" to false
            "srt" -> "Lời gốc: từ file .srt bạn chọn" to false
            "gemini" -> "Lời gốc: 🖐 đưa file âm thanh cho Gemini nghe, dán lại (${geminiParts()} lần)" to true
            else -> if (groq) "Lời gốc: Groq nghe tự động (lỗi thì chuyển sang 🖐 nhờ Gemini)" to false
            else "Lời gốc: 🖐 chưa có key Groq → đưa file âm thanh cho Gemini nghe, dán lại" to true
        }
        val n = if (mode == "recap") 1 else maxOf(1, (lines.size + 119) / 120)
        val what = if (mode == "recap") "Viết kịch bản review" else "Dịch"
        out += when {
            mode == "recap" && segs.isNotEmpty() -> "$what: đã có kịch bản" to false
            mode == "translate" && lines.isNotEmpty() && lines.none { it.vi.isBlank() } -> "$what: đã dịch xong" to false
            aiManual -> "$what: 🖐 chép yêu cầu sang DeepSeek, dán câu trả lời lại (~$n lần)" to true
            else -> "$what: AI tự động (lỗi thì chuyển sang 🖐 DeepSeek)" to false
        }
        out += "Giọng đọc, dựng video, lưu vào Thư viện: máy tự làm" to false
        return out
    }

    private fun geminiParts(): Int = maxOf(1, ((info?.duration ?: 0.0) / GEMINI_PART + 0.999).toInt())

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
        apiDown = false
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
                ask = null
                if (keepAlive) KeepAliveService.stop(ctx)
            }
        }
    }

    // ================================================================ AI (API hoặc dán tay)
    /**
     * Hỏi AI: có key thì gọi API; API lỗi (hết tiền, quá tải, mất mạng...) thì KHÔNG dừng mà chuyển ngay sang
     * làm tay (chép yêu cầu sang DeepSeek). inline = false: để người gọi gom các phần lỗi lại làm tay 1 lần.
     */
    private suspend fun askAi(step: String, prompt: String, inline: Boolean = true): String {
        while (true) {
            if (!Ai.manual(prefs) && !apiDown) {
                try {
                    return callApi(step, prompt)
                } catch (e: SkipApi) {
                    apiDown = true
                    log("🖐 Bạn chọn làm tay - bỏ qua API.")
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    apiDown = true
                    log("⚠ API lỗi (${e.message?.take(120)}) → chuyển sang 🖐 làm tay: chép yêu cầu sang DeepSeek.")
                    if (!inline) throw e
                }
            }
            val r = askManual(ManualAsk(step, "deepseek", prompt, canApi = Ai.chain(prefs).isNotEmpty()))
            if (r != RETRY_API) return r
            apiDown = false  // bạn bấm "Thử lại API"
        }
    }

    private class SkipApi : Exception()

    /** Gọi API chạy riêng; trong lúc chờ hiện số giây + nút "Làm tay ngay" (bấm là bỏ chờ ngay, không treo). */
    private suspend fun callApi(step: String, prompt: String): String {
        skipApi = false
        withContext(Dispatchers.Main) { apiWaiting = true }
        val call = viewModelScope.async(Dispatchers.IO) {
            Ai.chat(prefs, "Bạn là trợ lý biên tập video tiếng Việt. Làm đúng yêu cầu, chỉ trả lời JSON.", prompt, ::log)
        }
        val t0 = System.currentTimeMillis()
        try {
            while (!call.isCompleted) {
                if (skipApi) {
                    call.cancel()
                    throw SkipApi()
                }
                kotlinx.coroutines.delay(300)
                val s = (System.currentTimeMillis() - t0) / 1000
                prog(progress, "⏳ $step: chờ AI trả lời ${s}s... (lâu quá thì bấm 🖐 Làm tay ngay)")
            }
            return call.await()
        } catch (e: CancellationException) {
            call.cancel()
            throw e
        } finally {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.Main) { apiWaiting = false }
        }
    }

    private suspend fun askManual(a: ManualAsk): String = manualLock.withLock {
        val d = CompletableDeferred<String?>()
        manualReply = d
        withContext(Dispatchers.Main) { ask = a }
        log("🖐 ${a.step}: chép yêu cầu → dán sang ${if (a.target == "gemini") "Gemini" else "DeepSeek"} → dán câu trả lời lại.")
        val r = d.await()
        withContext(Dispatchers.Main) { ask = null }
        r ?: throw CancellationException("Đã hủy")
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
            "gemini" -> geminiTranscript(v, i)
            else -> if (prefs.key("groq").isBlank() && prefs.key("openai").isBlank()) {
                log("Chưa có key Groq → 🖐 nhờ Gemini nghe lời thoại (không cần key).")
                geminiTranscript(v, i)
            } else try {
                Stt.whisper(ctx, prefs, v, i, ::log) { prog(it * 0.3f, "Nghe lời thoại ${(it * 100).toInt()}%") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                log("⚠ Groq lỗi (${e.message?.take(120)}) → chuyển sang 🖐 nhờ Gemini nghe lời thoại.")
                geminiTranscript(v, i)
            }
        }
        if (l.isEmpty()) throw IllegalStateException(
            if (stt == "ocr") "Không đọc được chữ nào: chỉnh lại vùng phụ đề cho đúng chỗ chữ." else "Không nghe được lời thoại nào.")
        withContext(Dispatchers.Main) { lines = l }
        log("Lời gốc: ${l.size} câu.")
    }

    /** Lời gốc không cần API: lưu file âm thanh nhỏ vào Download, bạn đưa cho Gemini nghe rồi dán phụ đề lại. */
    private suspend fun geminiTranscript(v: File, i: VInfo): List<Line> {
        if (!i.hasAudio) throw IllegalStateException("Video không có tiếng - chọn 'Đọc phụ đề trên hình'.")
        val n = geminiParts()
        val out = mutableListOf<Line>()
        for (k in 0 until n) {
            val off = k * GEMINI_PART
            val mp3 = File(ctx.cacheDir, "gemini_$k.mp3")
            prog(0.3f * k / n, "Chuẩn bị file âm thanh ${k + 1}/$n")
            Ff.speechAudio(ctx, v, mp3, off, if (n > 1) GEMINI_PART else 0.0)
            val name = (title.take(50) + if (n > 1) " - phần ${k + 1}" else "").replace(Regex("[\\\\/:*?\"<>|]"), " ") + ".mp3"
            val uri = saveToDownloads(mp3, name)
            mp3.delete()
            val mins = (minOf(GEMINI_PART, i.duration - off) / 60).toInt() + 1
            var got = emptyList<Line>()
            while (got.isEmpty()) {
                val r = askManual(ManualAsk("Lời gốc ${if (n > 1) "phần ${k + 1}/$n" else ""}".trim(), "gemini",
                    Prompts.transcribe(title, k + 1, n, mins),
                    "Gửi kèm file \"$name\" (đã lưu ở Download/ReviewPhim) cho Gemini.", uri, name))
                got = parseTimed(r, off)
                if (got.isEmpty()) log("Không đọc được phụ đề trong câu trả lời - cần dạng SRT (00:00:01,000 --> ...). Dán lại.")
            }
            out += got
            log("Gemini chép được ${got.size} câu (phần ${k + 1}/$n).")
        }
        return Stt.cleanLines(out.sortedBy { it.start })
    }

    private suspend fun saveToDownloads(f: File, name: String): Uri = withContext(Dispatchers.IO) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, "audio/mpeg")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/ReviewPhim")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val r = ctx.contentResolver
        val uri = r.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IllegalStateException("Không lưu được file âm thanh vào Download.")
        r.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
        values.clear()
        values.put(MediaStore.Downloads.IS_PENDING, 0)
        r.update(uri, values, null, null)
        uri
    }

    /** Bộ nhớ tên riêng: tên AI đã dùng được lưu vào bảng tên -> tập sau cùng bộ phim dùng đúng tên đó. */
    private fun rememberNames(reply: String) {
        val n = synchronized(prefs) { Prompts.learnNames(prefs, Prompts.parseNames(reply)) }
        if (n > 0) log("🧠 Nhớ thêm $n tên riêng (sửa ở Cài đặt → Tên riêng).")
    }

    var castInfo by mutableStateOf(prefs.str("cast_title").let { if (it.isBlank()) "" else "$it: ${prefs.str("cast").split(", ").size} nhân vật" })

    /** Lấy danh sách nhân vật chính thức từ MyAnimeList (Jikan, không cần key) - ý tưởng từ Aniflow. */
    fun findCast(query: String) = launchTask("Tìm nhân vật") {
        val f = Cast.lookup(query) ?: throw IllegalStateException("Không tìm thấy \"$query\" trên MyAnimeList - thử tên tiếng Anh / Nhật.")
        prefs.set("cast", f.names.joinToString(", "))
        prefs.set("cast_title", f.title)
        withContext(Dispatchers.Main) { castInfo = "${f.title}: ${f.names.size} nhân vật" }
        log("📚 ${f.title}: ${f.names.take(8).joinToString(", ")}${if (f.names.size > 8) "..." else ""}")
    }

    fun clearCast() {
        prefs.set("cast", "")
        prefs.set("cast_title", "")
        castInfo = ""
    }

    private suspend fun writeRecap(i: VInfo) {
        prog(0.32f, "AI viết kịch bản review...")
        log("AI viết kịch bản review ~${targetSec / 60} phút...")
        val prompt = Prompts.recap(title, i.duration, lines, min(targetSec, (i.duration * 0.9).toInt().coerceAtLeast(30)),
            style, prefs)
        var last: Exception? = null
        repeat(2) {
            try {
                val reply = askAi("Viết kịch bản review", prompt)
                val (t, s) = Prompts.parseRecap(reply, i.duration, lines)
                rememberNames(reply)
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
        var first = cur.none { it.vi.isNotBlank() }
        for (round in 0 until 4) {
            val manual = Ai.manual(prefs) || apiDown  // API lỗi ở vòng trước -> vòng này làm tay, mỗi lần 120 câu
            val miss = cur.indices.filter { cur[it].vi.isBlank() && !cur[it].text.matches(Regex("[♪\\s\\p{Punct}]*")) }
            if (miss.isEmpty()) break
            if (round > 0) log("Dịch lại ${miss.size} câu bị sót...")
            val size = if (manual) 120 else 30
            val parts = miss.chunked(size)
            if (manual) {
                for ((k, p) in parts.withIndex()) {
                    log("Phần ${k + 1}/${parts.size}: ${p.size} câu")
                    val reply = askAi("Dịch phần ${k + 1}/${parts.size} (${p.size} câu)",
                        Prompts.translate(title, cur, p, prefs, first))
                    val got = Prompts.parseLines(reply, p)
                    rememberNames(reply)
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
                                val reply = askAi("Dịch", Prompts.translate(title, cur, p, prefs, true), inline = false)
                                val got = Prompts.parseLines(reply, p)
                                rememberNames(reply)
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
        if (!Ai.manual(prefs) && !apiDown && output != "sub") {
            for (round in 0 until 2) {
                val long = cur.indices.filter { cur[it].vi.length > maxChars(cur, it) * 1.3 }
                if (long.isEmpty()) break
                log("⚡ Tối ưu thuyết minh: rút gọn ${long.size} câu đọc quá nhanh (vòng ${round + 1})...")
                for (p in long.chunked(30)) {
                    try {
                        val got = Prompts.parseLines(askAi("Rút gọn câu dài", Prompts.shorten(cur, p, 1.0 - 0.1 * round),
                            inline = false), p)
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

    companion object {
        const val GEMINI_PART = 20 * 60.0  // mỗi file gửi Gemini tối đa 20 phút (câu trả lời không bị cắt giữa chừng)
    }

    private suspend fun coroutineScopeAll(tasks: List<suspend () -> Unit>) =
        kotlinx.coroutines.coroutineScope { tasks.map { t -> async { t() } }.awaitAll() }

    @Volatile
    private var vsDown = false

    /** Giọng đọc: VoiceStudio trên máy tính (nếu chọn và kết nối được), không thì giọng có sẵn của máy. */
    private suspend fun speak(text: String, out: File, r: Float): File {
        if (VoiceStudio.enabled(prefs) && !vsDown) {
            try {
                return VoiceStudio.synth(prefs, text, out, r)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                vsDown = true
                log("⚠ VoiceStudio lỗi (${e.message?.take(120)}) → dùng giọng có sẵn của máy cho phần còn lại.")
            }
        }
        return tts.synth(text, out, voice, r, prefs.str("tts_engine"))
    }

    /** Kiểm tra VoiceStudio trước khi đọc cả video (để không lẫn 2 giọng). */
    private suspend fun checkVoiceStudio() {
        vsDown = false
        if (!VoiceStudio.enabled(prefs)) return
        try {
            VoiceStudio.voices(prefs)
            log("🎙 Giọng VoiceStudio (${VoiceStudio.url(prefs)}): ${prefs.str("vs_voice").ifBlank { "mặc định" }}")
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            vsDown = true
            log("⚠ ${e.message} → dùng giọng có sẵn của máy.")
        }
    }

    private suspend fun renderRecap(v: File, i: VInfo) {
        checkVoiceStudio()
        val dir = File(ctx.cacheDir, "tts").apply { deleteRecursively(); mkdirs() }
        val narr = File(work, "narration.wav")
        val clips = mutableListOf<Pair<Double, Double>>()
        val cues = mutableListOf<Cue>()
        val maxChars = if (aspect == Aspect.SOURCE && i.width > i.height) 44 else 30
        log("Đọc giọng ${segs.size} đoạn...")
        var shotsUsed = 0
        Wav.Writer(narr).use { w ->
            var t = 0.0
            val order = segs.drop(1).sortedBy { it.start }  // các đoạn kể theo thời gian (đoạn 0 là hook)
            for ((k, s) in segs.withIndex()) {
                prog(0.4f + 0.3f * k / segs.size, "Đọc giọng ${k + 1}/${segs.size}")
                val wav = speak(s.text, File(dir, "s$k.wav"), rate)
                val pcm = Wav.read(wav)
                val dur = pcm.seconds + 0.35
                // khoảng hình của đoạn kể: đúng thời gian các câu thoại AI chỉ ra (#from - #to)
                val a0 = s.start.coerceIn(0.0, max(0.0, i.duration - 1.0))
                val b0 = (if (s.end > s.start) s.end else s.start + dur).coerceIn(a0, i.duration)
                val idx = order.indexOf(s)
                val lo = if (idx > 0) order[idx - 1].let { p -> if (p.end > p.start) p.end else p.start } else 0.0
                val hi = order.getOrNull(idx + 1)?.start ?: i.duration
                val (wl, wh) = min(lo, a0) to max(hi, b0)
                val pieces = if (multiShot) {
                    val from = max(wl, a0 - dur)
                    val to = min(wh, b0 + dur)
                    val sh = Shots.shots(Shots.analyze(ctx, v, from, to - from), to)
                    val extra = s.reuse.flatMap { (ra, rb) ->
                        val e2 = min(i.duration, min(rb, ra + 15.0))
                        if (e2 - ra < 1.0) emptyList() else Shots.shots(Shots.analyze(ctx, v, ra, e2 - ra), e2)
                    }
                    Shots.planIn(sh, a0, b0, dur, wl, min(wh, i.duration), extra)
                } else listOf(min(a0, max(0.0, i.duration - dur)) to dur)
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
            checkVoiceStudio()
            val dir = File(ctx.cacheDir, "tts").apply { deleteRecursively(); mkdirs() }
            dubFile = File(work, "dub.wav")
            val ls = lines
            var late = 0
            log("Đọc giọng thuyết minh ${ls.count { it.vi.isNotBlank() }} câu...")
            Wav.Writer(dubFile).use { w ->
                for ((k, l) in ls.withIndex()) {
                    if (l.vi.isBlank()) continue
                    prog(0.65f * k / ls.size + 0.05f, "Đọc giọng ${k + 1}/${ls.size}")
                    // thời gian còn lại tới câu sau, tính cả phần câu trước đọc lố -> đọc nhanh hơn để không trễ dồn
                    val at = max(l.start, w.seconds)
                    val nextStart = ls.getOrNull(k + 1)?.start ?: (l.end + 1.5)
                    val slot = max(0.6, min(nextStart, max(l.end, at) + 1.5) - at)
                    var r = rate
                    var pcm = Wav.read(speak(l.vi, File(dir, "l$k.wav"), r))
                    if (pcm.seconds > slot * 1.03 && r < rate * 1.5f) {
                        r = (rate * min(1.5, pcm.seconds / slot * 1.03)).toFloat()
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
        checkVoiceStudio()
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
