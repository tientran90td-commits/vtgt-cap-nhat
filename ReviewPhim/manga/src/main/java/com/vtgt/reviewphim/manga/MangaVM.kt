package com.vtgt.reviewphim.manga

import android.app.Application
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vtgt.reviewphim.Ai
import com.vtgt.reviewphim.CPS
import com.vtgt.reviewphim.Cast
import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.Ff
import com.vtgt.reviewphim.KeepAliveService
import com.vtgt.reviewphim.ManualAsk
import com.vtgt.reviewphim.Prefs
import com.vtgt.reviewphim.Prompts
import com.vtgt.reviewphim.RETRY_API
import com.vtgt.reviewphim.Seg
import com.vtgt.reviewphim.Tts
import com.vtgt.reviewphim.Updater
import com.vtgt.reviewphim.VieNeu
import com.vtgt.reviewphim.VieNeuTts
import com.vtgt.reviewphim.VoiceStudio
import com.vtgt.reviewphim.Wav
import com.vtgt.reviewphim.splitCues
import com.vtgt.reviewphim.toSrt
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

class MangaVM(app: Application) : AndroidViewModel(app) {
    private val ctx get() = getApplication<Application>()
    val prefs = Prefs(app)
    val tts = Tts(app)
    val vieneu = VieNeuTts(app)
    val updater = Updater(app)
    var vnVoices by mutableStateOf<List<String>>(emptyList())
    var vnReady by mutableStateOf(false)

    // ---- truyện & kịch bản
    var book by mutableStateOf<Book?>(null)
    var title by mutableStateOf("")
    var cover by mutableStateOf<Bitmap?>(null)
    var items by mutableStateOf<List<Item>>(emptyList())     // diễn biến (AI đọc tranh / tóm tắt)
    var segs by mutableStateOf<List<Seg>>(emptyList())        // kịch bản
    var recapTitle by mutableStateOf("")

    // ---- lựa chọn
    var targetSec by mutableStateOf(prefs.str("m_target", "300").toInt())
    var style by mutableStateOf(prefs.str("m_style", "hap_dan"))
    var vertical by mutableStateOf(prefs.bool("m_vertical", true))
    var quality by mutableStateOf(prefs.str("m_quality", "720").toInt())
    var karaoke by mutableStateOf(prefs.bool("karaoke", true))
    var hookTitle by mutableStateOf(prefs.bool("hook_title", true))
    var bgmName by mutableStateOf(prefs.str("m_bgm_name"))
    var voice by mutableStateOf(prefs.str("voice"))
    var rate by mutableFloatStateOf(prefs.num("rate", 1.1f))
    var layout by mutableStateOf(prefs.str("m_layout", "auto"))   // auto | page | webtoon
    var rtl by mutableStateOf(prefs.bool("m_rtl", true))          // thứ tự khung: phải -> trái (manga Nhật)
    var panelZoom by mutableStateOf(prefs.bool("m_panels", true)) // chiếu lần lượt từng khung tranh

    // ---- tiến trình
    val logs = mutableStateListOf<String>()
    var progress by mutableFloatStateOf(0f)
    var status by mutableStateOf("")
    var busy by mutableStateOf(false)
    var result by mutableStateOf<Uri?>(null)
    var update by mutableStateOf<Updater.Release?>(null)
    var ask by mutableStateOf<ManualAsk?>(null)
    var apiWaiting by mutableStateOf(false)
    private var manualReply: CompletableDeferred<String?>? = null
    private val manualLock = kotlinx.coroutines.sync.Mutex()
    @Volatile
    private var apiDown = false
    @Volatile
    private var skipApi = false
    private var job: Job? = null

    private val work get() = File(ctx.filesDir, "work").apply { mkdirs() }
    private val bookDir get() = File(ctx.filesDir, "book")

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

    fun cancel() {
        job?.cancel()
        manualReply?.complete(null)
    }

    // ================================================================ nhập truyện
    private suspend fun setBook(b: Book) {
        val first = b.pages.firstOrNull()?.file ?: b.cover
        val bmp = first?.let { withContext(Dispatchers.IO) { BitmapFactory.decodeFile(it.path, BitmapFactory.Options().apply { inSampleSize = 4 }) } }
        withContext(Dispatchers.Main) {
            book = b
            title = b.title
            cover = bmp
            items = emptyList()
            segs = emptyList()
            recapTitle = ""
            result = null
        }
        if (b.manga) log("📚 ${b.title}: ${b.pages.size} ${if (b.webtoon) "khúc (truyện cuộn dọc, đã nối lại và cắt đúng khoảng trắng giữa các khung)" else "trang"}.")
        else log("📖 ${b.title}: ${b.text.length} ký tự, ${b.illus.size} ảnh minh họa${if (b.cover != null) ", có ảnh bìa" else ""}.")
    }

    private fun freshDir(): File = bookDir.apply { deleteRecursively(); mkdirs() }

    fun openImages(uris: List<Uri>) = launchTask("Mở ảnh truyện") {
        if (uris.isEmpty()) return@launchTask
        val pages = Books.fromImages(ctx, uris, freshDir(), layout) { prog(it, "Đọc ảnh ${(it * 100).toInt()}%") }
        setBook(Book("manga", Books.titleOf(Books.displayName(ctx, uris.first())).replace(Regex("\\s*\\d+$"), ""), pages))
    }

    fun openTree(uri: Uri) = launchTask("Mở thư mục truyện") {
        val (t, pages) = Books.fromTree(ctx, uri, freshDir(), layout) { prog(it, "Đọc ảnh ${(it * 100).toInt()}%") }
        setBook(Book("manga", t, pages))
    }

    /** File: CBZ / ZIP (ảnh), PDF, EPUB, TXT. */
    fun openFile(uri: Uri) = launchTask("Mở file truyện") {
        val name = Books.displayName(ctx, uri)
        val ext = name.substringAfterLast('.', "").lowercase()
        val src = File(ctx.cacheDir, "nhap.$ext")
        withContext(Dispatchers.IO) {
            ctx.contentResolver.openInputStream(uri)?.use { i -> src.outputStream().use { i.copyTo(it) } }
                ?: throw IllegalStateException("Không đọc được file.")
        }
        val dir = freshDir()
        val t = Books.titleOf(name)
        val b = when (ext) {
            "cbz", "zip" -> Book("manga", t, Books.fromZip(src, dir, layout) { prog(it, "Giải nén trang ${(it * 100).toInt()}%") })
            "pdf" -> Book("manga", t, Books.fromPdf(src, dir) { prog(it, "Đọc PDF ${(it * 100).toInt()}%") })
            "epub" -> Books.fromEpub(src, dir) { prog(it, "Đọc EPUB ${(it * 100).toInt()}%") }
            "txt", "md", "text" -> Book("novel", t, text = withContext(Dispatchers.IO) { Books.readText(src.readBytes()) }.trim())
            else -> if (Books.isImage(name)) Book("manga", t, Books.fromImages(ctx, listOf(uri), dir, layout) {})
            else throw IllegalStateException("Chưa hỗ trợ file .$ext - dùng ảnh, CBZ/ZIP, PDF, EPUB hoặc TXT.")
        }
        src.delete()
        if (!b.manga && b.text.isBlank()) throw IllegalStateException("File không có chữ.")
        setBook(b)
    }

    /** Dán chữ (chương truyện chép từ web...). Ảnh minh họa / bìa thêm sau bằng nút Thêm ảnh. */
    fun pasteText(text: String, name: String) = launchTask("Dán truyện chữ") {
        if (text.isBlank()) throw IllegalStateException("Chưa có chữ.")
        freshDir()
        setBook(Book("novel", name.ifBlank { "Truyện" }, text = text.trim()))
    }

    /** Light novel: thêm ảnh bìa / ảnh minh họa (rải đều theo truyện). */
    fun addIllus(uris: List<Uri>) = launchTask("Thêm ảnh minh họa") {
        val b = book ?: throw IllegalStateException("Mở truyện chữ trước.")
        val pages = Books.fromImages(ctx, uris, File(bookDir, "illus_${System.currentTimeMillis()}")) {}
        val n = pages.size
        val add = pages.mapIndexed { k, p -> Illus((b.text.length.toLong() * k / max(1, n)).toInt(), p.file) }
        val nb = b.copy(illus = (b.illus + add).sortedBy { it.pos }, cover = b.cover ?: pages.first().file)
        withContext(Dispatchers.Main) {
            book = nb
            if (cover == null) cover = BitmapFactory.decodeFile(nb.cover!!.path, BitmapFactory.Options().apply { inSampleSize = 4 })
        }
        log("🖼 Thêm ${pages.size} ảnh minh họa (tổng ${nb.illus.size}).")
    }

    fun setBgm(uri: Uri?) = launchTask("Nhạc nền") {
        val f = File(work, "bgm.audio")
        if (uri == null) {
            f.delete()
            prefs.set("m_bgm_name", "")
            withContext(Dispatchers.Main) { bgmName = "" }
            return@launchTask
        }
        withContext(Dispatchers.IO) { ctx.contentResolver.openInputStream(uri)?.use { i -> f.outputStream().use { i.copyTo(it) } } }
        val n = Books.displayName(ctx, uri)
        prefs.set("m_bgm_name", n)
        withContext(Dispatchers.Main) { bgmName = n }
    }

    // ================================================================ các bước
    fun plan(): List<Pair<String, Boolean>> {
        val b = book ?: return listOf("Mở truyện trước (ảnh / thư mục / CBZ / PDF / EPUB / TXT)" to false)
        val out = mutableListOf<Pair<String, Boolean>>()
        val vision = !Ai.manual(prefs) && Ai.visionChain(prefs).isNotEmpty()
        out += when {
            items.isNotEmpty() -> "Đọc truyện: đã có ${items.size} dòng diễn biến" to false
            b.manga && vision -> "Đọc tranh: AI xem ${b.pages.size} trang (${sheetCount(b, 3)} lần gửi; lỗi thì 🖐 gửi cho Gemini)" to false
            b.manga -> "Đọc tranh: 🖐 gửi ảnh trang cho Gemini, dán lại (~${sheetCount(b, 10)} lần)" to true
            b.text.length <= SHORT -> "Đọc truyện: truyện ngắn, không cần tóm tắt trước" to false
            Ai.manual(prefs) -> "Tóm tắt từng phần: 🖐 chép sang DeepSeek, dán lại (~${Books.chunks(b.text, MANUAL_CHUNK).size} lần)" to true
            else -> "Tóm tắt từng phần: AI tự động (${Books.chunks(b.text, API_CHUNK).size} phần; lỗi thì 🖐 DeepSeek)" to false
        }
        out += when {
            segs.isNotEmpty() -> "Kịch bản: đã có" to false
            Ai.manual(prefs) -> "Viết kịch bản: 🖐 chép sang DeepSeek, dán lại (1 lần)" to true
            else -> "Viết kịch bản: AI tự động (lỗi thì 🖐 DeepSeek)" to false
        }
        out += "Giọng đọc, dựng video, lưu vào Thư viện: máy tự làm" to false
        return out
    }

    private fun sheetCount(b: Book, per: Int) = ((b.pages.size + Story.PER_SHEET - 1) / Story.PER_SHEET + per - 1) / per

    fun resetScript() {
        segs = emptyList()
        recapTitle = ""
    }

    fun resetAll() {
        items = emptyList()
        resetScript()
    }

    fun makeVideo() = launchTask("Làm video", keepAlive = true) {
        val b = book ?: throw IllegalStateException("Mở truyện trước.")
        if (items.isEmpty()) {
            if (b.manga) readManga(b) else readNovel(b)
        }
        if (segs.isEmpty()) writeScript(b)
        render(b)
    }

    fun renderOnly() = launchTask("Xuất lại video", keepAlive = true) {
        val b = book ?: throw IllegalStateException("Chưa có truyện.")
        if (segs.isEmpty()) throw IllegalStateException("Chưa có kịch bản.")
        render(b)
    }

    // ================================================================ AI (API hoặc làm tay)
    private class SkipApi : Exception()

    fun skipToManual() {
        skipApi = true
    }

    private suspend fun callApi(step: String, prompt: String, json: Boolean, images: List<File> = emptyList()): String {
        skipApi = false
        withContext(Dispatchers.Main) { apiWaiting = true }
        val call = viewModelScope.async(Dispatchers.IO) {
            val sys = if (images.isNotEmpty()) "Bạn đọc truyện tranh và tả lại bằng tiếng Việt, đúng định dạng được yêu cầu."
            else if (json) "Bạn là trợ lý biên tập video tiếng Việt. Làm đúng yêu cầu, chỉ trả lời JSON."
            else "Bạn là trợ lý tóm tắt truyện tiếng Việt. Làm đúng định dạng được yêu cầu."
            Ai.chat(prefs, sys, prompt, ::log, json = json && images.isEmpty(), images = images)
        }
        val t0 = System.currentTimeMillis()
        try {
            while (!call.isCompleted) {
                if (skipApi) {
                    call.cancel()
                    throw SkipApi()
                }
                kotlinx.coroutines.delay(300)
                prog(progress, "⏳ $step: chờ AI ${(System.currentTimeMillis() - t0) / 1000}s... (lâu quá thì bấm 🖐 Làm tay ngay)")
            }
            return call.await()
        } catch (e: CancellationException) {
            call.cancel()
            throw e
        } finally {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.Main) { apiWaiting = false }
        }
    }

    /** Hỏi AI chữ: API lỗi thì chuyển sang 🖐 chép sang DeepSeek. */
    private suspend fun askAi(step: String, prompt: String, json: Boolean): String {
        while (true) {
            if (!Ai.manual(prefs) && !apiDown) {
                try {
                    return callApi(step, prompt, json)
                } catch (e: SkipApi) {
                    apiDown = true
                    log("🖐 Bạn chọn làm tay - bỏ qua API.")
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    apiDown = true
                    log("⚠ API lỗi (${e.message?.take(120)}) → 🖐 làm tay: chép yêu cầu sang DeepSeek.")
                }
            }
            val r = askManual(ManualAsk(step, "deepseek", prompt, canApi = Ai.chain(prefs).isNotEmpty()))
            if (r != RETRY_API) return r
            apiDown = false
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

    // ================================================================ đọc truyện tranh
    private suspend fun readManga(b: Book) {
        prog(0.02f, "Chuẩn bị ảnh trang cho AI đọc...")
        val dir = File(ctx.cacheDir, "doc").apply { deleteRecursively(); mkdirs() }
        val sheets = withContext(Dispatchers.Default) { Story.sheets(b.pages, dir) }
        val useApi = !Ai.manual(prefs) && Ai.visionChain(prefs).isNotEmpty()
        val groups = sheets.chunked(if (useApi) 3 else 10)
        val notes = HashMap<Int, String>()
        log("👁 AI đọc ${b.pages.size} trang (${sheets.size} ảnh ghép, ${groups.size} lần gửi).")
        for ((k, g) in groups.withIndex()) {
            val first = g.first().pages.first() + 1
            val last = g.last().pages.last() + 1
            val step = "Đọc tranh ${if (groups.size > 1) "phần ${k + 1}/${groups.size}" else ""}".trim()
            val prompt = Story.readPages(title, k + 1, groups.size, g.size, first, last, prefs,
                notes.keys.sorted().takeLast(8).mapNotNull { notes[it] })
            var got = emptyMap<Int, String>()
            if (useApi && !apiDown) {
                try {
                    got = Story.parsePages(callApi(step, prompt, false, g.map { it.file }), first, last)
                    if (got.isEmpty()) log("⚠ AI không đọc được trang nào ở phần ${k + 1} → 🖐 gửi cho Gemini.")
                } catch (e: SkipApi) {
                    apiDown = true
                    log("🖐 Bạn chọn làm tay - bỏ qua API.")
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    apiDown = true
                    log("⚠ AI đọc tranh lỗi (${e.message?.take(120)}) → 🖐 gửi ảnh cho Gemini.")
                }
            }
            if (got.isEmpty()) got = readManual(g, step, prompt, first, last)
            notes.putAll(got)
            prog(0.05f + 0.3f * (k + 1) / groups.size, "Đọc tranh ${k + 1}/${groups.size}")
            log("👁 P$first–P$last: đọc được ${got.size} trang.")
        }
        dir.deleteRecursively()
        val its = b.pages.indices.mapNotNull { i -> notes[i + 1]?.let { Item(it, page = i, label = b.pages[i].label) } }
        if (its.isEmpty()) throw IllegalStateException("AI chưa đọc được trang nào.")
        withContext(Dispatchers.Main) { items = its }
        log("📚 Diễn biến: ${its.size}/${b.pages.size} trang có nội dung.")
    }

    /** 🖐 Lưu ảnh vào Download/MangaRecap, gửi cho Gemini cùng yêu cầu, dán câu trả lời lại. */
    private suspend fun readManual(g: List<PageSheet>, step: String, prompt: String, first: Int, last: Int): Map<Int, String> {
        val base = title.take(40).replace(Regex("[\\\\/:*?\"<>|]"), " ").trim()
        val uris = g.map { s -> saveToDownloads(s.file, "$base ${s.file.name}", "image/jpeg") }
        try {
            while (true) {
                val r = askManual(ManualAsk(step, "gemini", prompt,
                    "Gửi kèm ${g.size} ảnh trang (P$first–P$last, đã lưu ở Download/MangaRecap) cho Gemini - nút 📤 gửi cả ảnh lẫn yêu cầu.",
                    uris, "${g.size} ảnh trang", canApi = Ai.visionChain(prefs).isNotEmpty(), mime = "image/jpeg"))
                if (r == RETRY_API) {
                    try {
                        apiDown = false
                        val got = Story.parsePages(callApi(step, prompt, false, g.map { it.file }), first, last)
                        if (got.isNotEmpty()) return got
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        apiDown = true
                        log("⚠ Vẫn lỗi (${e.message?.take(100)}).")
                    }
                    continue
                }
                val got = Story.parsePages(r, first, last)
                if (got.isNotEmpty()) return got
                log("Không thấy dòng nào dạng \"P12 | ...\" - dán lại câu trả lời của Gemini.")
            }
        } finally {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.IO) {
                uris.forEach { runCatching { ctx.contentResolver.delete(it, null, null) } }
            }
        }
    }

    // ================================================================ đọc light novel
    private suspend fun readNovel(b: Book) {
        val text = b.text
        if (text.length <= SHORT) {
            val its = Story.rawItems(text, 500).mapIndexed { k, it -> it.copy(label = "đoạn ${k + 1}") }
            withContext(Dispatchers.Main) { items = its }
            log("📖 Truyện ngắn (${text.length} ký tự) → ${its.size} đoạn, viết kịch bản thẳng.")
            return
        }
        val parts = Books.chunks(text, if (Ai.manual(prefs)) MANUAL_CHUNK else API_CHUNK)
        log("📖 ${text.length} ký tự → tóm tắt ${parts.size} phần.")
        val out = mutableListOf<Item>()
        for ((k, p) in parts.withIndex()) {
            val (start, body) = p
            var notes = emptyList<String>()
            var tries = 0
            while (notes.isEmpty() && tries < 3) {
                tries++
                val r = askAi("Tóm tắt phần ${k + 1}/${parts.size}",
                    Story.novelNotes(title, k + 1, parts.size, body, prefs, out.takeLast(6).map { it.text }), json = false)
                notes = Story.parseNotes(r)
                if (notes.isEmpty()) log("Không thấy ý nào dạng \"- ...\" trong câu trả lời - thử lại.")
            }
            notes.forEachIndexed { j, n ->
                out += Item(n, pos = start + ((j + 0.5) / notes.size * body.length).toInt(), label = "phần ${k + 1}")
            }
            prog(0.05f + 0.3f * (k + 1) / parts.size, "Tóm tắt ${k + 1}/${parts.size}")
        }
        if (out.isEmpty()) throw IllegalStateException("Chưa tóm tắt được phần nào.")
        withContext(Dispatchers.Main) { items = out }
        log("📖 Diễn biến: ${out.size} ý.")
    }

    // ================================================================ kịch bản
    private suspend fun writeScript(b: Book) {
        prog(0.36f, "AI viết kịch bản...")
        val content = items.sumOf { it.text.length }
        val target = min(targetSec, max(45, (content / CPS * 0.9).toInt()))
        if (target < targetSec) log("Truyện ngắn → video khoảng ${target / 60} phút ${target % 60} giây.")
        val prompt = Story.script(title, b.manga, items, target, style, prefs)
        var last: Exception? = null
        repeat(2) {
            try {
                val reply = askAi("Viết kịch bản", prompt, json = true)
                val (t, s) = Prompts.parseRecap(reply, items.size.toDouble(), Story.asLines(items))
                val n = synchronized(prefs) { Prompts.learnNames(prefs, Prompts.parseNames(reply)) }
                if (n > 0) log("🧠 Nhớ thêm $n tên riêng.")
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

    // ================================================================ giọng đọc
    @Volatile
    private var vnDown = false
    @Volatile
    private var vsDown = false

    private suspend fun speak(text: String, out: File, r: Float): File {
        if (prefs.str("tts_src") == "vieneu" && !vnDown) {
            try {
                return vieneu.synth(text, prefs.str("vn_voice", "Minh Quân"), out, r / 1.1f * 1.05f,
                    if (prefs.bool("vn_fast", false)) 8 else 16)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                vnDown = true
                log("⚠ VieNeu lỗi (${e.message?.take(120)}) → dùng giọng có sẵn của máy cho phần còn lại.")
            }
        }
        if (prefs.str("tts_src") == "voicestudio" && VoiceStudio.enabled(prefs) && !vsDown) {
            try {
                return VoiceStudio.synth(prefs, text, out, r)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                vsDown = true
                log("⚠ VoiceStudio lỗi (${e.message?.take(120)}) → dùng giọng có sẵn của máy.")
            }
        }
        return tts.synth(text, out, voice, r, prefs.str("tts_engine"))
    }

    private suspend fun checkVoices() {
        vnDown = false
        vsDown = false
        if (prefs.str("tts_src") == "vieneu") {
            try {
                vieneu.ensure(clone = false, log = ::log) { p, s -> prog(progress, "$s (${(p * 100).toInt()}%)") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                vnDown = true
                log("⚠ Không chuẩn bị được giọng VieNeu (${e.message?.take(120)}) → dùng giọng có sẵn của máy.")
            }
        }
    }

    fun refreshVieNeu() {
        vnVoices = try {
            VieNeu.allVoices(ctx).keys.toList()
        } catch (e: Exception) {
            emptyList()
        }
        vnReady = VieNeu.ready(ctx)
    }

    fun downloadVieNeu() = launchTask("Tải giọng AI VieNeu", keepAlive = true) {
        vieneu.ensure(clone = true, log = ::log) { p, s -> prog(p, s) }
        withContext(Dispatchers.Main) { refreshVieNeu() }
    }

    fun cloneVoice(name: String, uri: Uri? = null, file: File? = null) = launchTask("Nhân bản giọng", keepAlive = true) {
        vieneu.ensure(clone = true, log = ::log) { p, s -> prog(p * 0.8f, s) }
        val src = file ?: File(ctx.cacheDir, "clone_src").also { f ->
            withContext(Dispatchers.IO) {
                ctx.contentResolver.openInputStream(uri!!)?.use { i -> f.outputStream().use { o -> i.copyTo(o) } }
                    ?: throw IllegalStateException("Không đọc được file giọng mẫu.")
            }
        }
        prog(0.85f, "Nhân bản giọng...")
        val v = vieneu.clone(name.trim().ifBlank { "Giọng của tôi" }, src, ::log)
        prefs.set("vn_voice", v.name)
        withContext(Dispatchers.Main) { refreshVieNeu() }
        log("✅ Đã nhân bản giọng \"${v.name}\".")
    }

    fun deleteVoice(name: String) {
        VieNeu.deleteVoice(ctx, name)
        if (prefs.str("vn_voice") == name) prefs.set("vn_voice", "")
        refreshVieNeu()
    }

    fun previewVoice() = launchTask("Nghe thử giọng") {
        checkVoices()
        val f = speak("Xin chào, đây là giọng kể chuyện của bạn. Hôm nay chúng ta cùng tóm tắt một bộ truyện thật hay!",
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

    // ================================================================ dựng video
    private suspend fun render(b: Book) {
        checkVoices()
        val (w, h) = Slides.size(vertical, quality)
        val ttsDir = File(ctx.cacheDir, "tts").apply { deleteRecursively(); mkdirs() }
        val frames = File(ctx.cacheDir, "frames").apply { deleteRecursively(); mkdirs() }
        val narr = File(work, "narration.wav")
        val slides = mutableListOf<Slide>()
        val cues = mutableListOf<Cue>()
        val made = HashMap<String, Pair<File, Boolean>>()
        val panelDir = File(frames, "khung").apply { mkdirs() }
        val panelsOf = HashMap<String, List<File>>()
        val zoom = b.manga && !b.webtoon && panelZoom
        var nPanels = 0
        val maxChars = if (vertical) 30 else 44
        val name = recapTitle.ifBlank { title }
        log("Đọc giọng ${segs.size} đoạn, dựng ${w}x$h...")
        Wav.Writer(narr).use { wr ->
            var t = 0.0
            for ((k, s) in segs.withIndex()) {
                prog(0.4f + 0.3f * k / segs.size, "Đọc giọng ${k + 1}/${segs.size}")
                val pcm = Wav.read(speak(s.text, File(ttsDir, "s$k.wav"), rate))
                val dur = pcm.seconds + 0.35
                val a = s.start.toInt()
                val e = if (s.end > s.start) s.end.toInt() else a + 1
                var files = Story.visuals(b, items, a, e)
                if (files.isEmpty()) {
                    files = listOf(made.getOrPut("card") {
                        Slides.titleCard(name, if (b.manga) "" else "Light novel", w, h, File(frames, "card.jpg")) to false
                    }.first)
                }
                if (zoom) {  // chiếu lần lượt từng khung tranh của các trang (thứ tự đọc)
                    files = files.flatMap { pg ->
                        panelsOf.getOrPut(pg.path) {
                            withContext(Dispatchers.Default) {
                                try {
                                    Panels.crops(pg, rtl, panelDir, "p${panelsOf.size}")
                                } catch (e: Exception) {
                                    listOf(pg)
                                }
                            }.also { if (it.size > 1) nPanels += it.size }
                        }
                    }
                }
                for ((f, d) in Story.share(files, dur, if (zoom) 1.6 else 2.2)) {
                    val (img, scroll) = made.getOrPut(f.path) {
                        withContext(Dispatchers.Default) {
                            if (f.parentFile == frames) f to false else Slides.frame(f, w, h, File(frames, "f${made.size}.jpg"))
                        }
                    }
                    slides += Slide(img, d, scroll)
                }
                wr.silenceTo(t + 0.15)
                wr.write(pcm)
                cues += splitCues(s.text, t + 0.15, pcm.seconds, maxChars)
                t += dur
                wr.silenceTo(t)
            }
        }
        log("Ghép ${segs.size} đoạn lời kể với ${slides.size} cảnh (${made.size} ảnh${if (nPanels > 0) ", tách được $nPanels khung tranh" else ""}).")
        val aud = File(work, "audio.wav")
        val vid = File(work, "video_only.mp4")
        val out = File(work, "final.mp4")
        prog(0.72f, "Trộn âm thanh")
        val bgm = File(work, "bgm.audio").takeIf { it.exists() && bgmName.isNotBlank() }
        Ff.mixRecap(ctx, narr, false, emptyList(), narr, 0.0, aud, bgm, prefs.num("bgm_vol", 0.25f).toDouble())
        Slides.render(ctx, slides, w, h, cues, karaoke, if (hookTitle) name else "", vid) {
            prog(0.75f + 0.22f * it, "Dựng video ${(it * 100).toInt()}%")
        }
        prog(0.97f, "Ghép tiếng")
        Ff.mux(ctx, vid, aud, out)
        File(work, "final.srt").writeText(toSrt(cues))
        val uri = saveToGallery(out, name)
        vid.delete()
        aud.delete()
        frames.deleteRecursively()
        withContext(Dispatchers.Main) { result = uri }
        log("✅ Xong! Video đã lưu vào Thư viện ảnh → Movies/MangaRecap.")
    }

    private suspend fun saveToDownloads(f: File, name: String, mime: String): Uri = withContext(Dispatchers.IO) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/MangaRecap")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val r = ctx.contentResolver
        val uri = r.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IllegalStateException("Không lưu được ảnh vào Download.")
        r.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
        values.clear()
        values.put(MediaStore.Downloads.IS_PENDING, 0)
        r.update(uri, values, null, null)
        uri
    }

    private suspend fun saveToGallery(f: File, name: String): Uri = withContext(Dispatchers.IO) {
        val safe = name.replace(Regex("[\\\\/:*?\"<>|\\n]"), " ").trim().take(80).ifBlank { "MangaRecap" }
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "$safe.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/MangaRecap")
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

    // ================================================================ tên nhân vật (MyAnimeList)
    var castInfo by mutableStateOf(prefs.str("cast_title").let { if (it.isBlank()) "" else "$it: ${prefs.str("cast").split(", ").size} nhân vật" })

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

    override fun onCleared() {
        tts.shutdown()
        vieneu.close()
        super.onCleared()
    }

    companion object {
        const val SHORT = 16000          // truyện ngắn hơn thì viết kịch bản thẳng từ văn bản
        const val API_CHUNK = 14000      // mỗi phần gửi API tóm tắt
        const val MANUAL_CHUNK = 28000   // làm tay: phần lớn hơn để ít lần chép / dán
    }
}
