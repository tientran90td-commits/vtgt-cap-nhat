package com.vtgt.reviewphim.longvid

import android.app.Application
import android.content.ContentValues
import android.net.Uri
import android.os.Environment
import android.os.StatFs
import android.provider.MediaStore
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vtgt.reviewphim.Ai
import com.vtgt.reviewphim.Aspect
import com.vtgt.reviewphim.CPS
import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.Download
import com.vtgt.reviewphim.Ff
import com.vtgt.reviewphim.KeepAliveService
import com.vtgt.reviewphim.Line
import com.vtgt.reviewphim.ManualAsk
import com.vtgt.reviewphim.Media
import com.vtgt.reviewphim.Prefs
import com.vtgt.reviewphim.Prompts
import com.vtgt.reviewphim.RETRY_API
import com.vtgt.reviewphim.Render
import com.vtgt.reviewphim.RenderSpec
import com.vtgt.reviewphim.Seg
import com.vtgt.reviewphim.Shots
import com.vtgt.reviewphim.Stt
import com.vtgt.reviewphim.Tts
import com.vtgt.reviewphim.Updater
import com.vtgt.reviewphim.VInfo
import com.vtgt.reviewphim.VieNeu
import com.vtgt.reviewphim.VieNeuTts
import com.vtgt.reviewphim.VoiceStudio
import com.vtgt.reviewphim.Watch
import com.vtgt.reviewphim.Wav
import com.vtgt.reviewphim.fmtTime
import com.vtgt.reviewphim.manga.Book
import com.vtgt.reviewphim.manga.Books
import com.vtgt.reviewphim.manga.Item
import com.vtgt.reviewphim.manga.Page
import com.vtgt.reviewphim.manga.PageSheet
import com.vtgt.reviewphim.manga.Panels
import com.vtgt.reviewphim.manga.Slide
import com.vtgt.reviewphim.manga.Slides
import com.vtgt.reviewphim.manga.Story
import com.vtgt.reviewphim.manga.Web
import com.vtgt.reviewphim.parseTimed
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
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

/** Mức chất lượng cho video dài: số điểm ảnh cạnh ngắn, khung hình/giây, bitrate hình, bitrate tiếng. */
data class Preset(val short: Int, val fps: Int, val vbit: Int, val abit: String, val motion: Boolean) {
    /** Dung lượng ước tính (byte) cho [sec] giây. */
    fun bytes(sec: Double) = (vbit + abit.removeSuffix("k").toInt() * 1000) / 8.0 * sec
}

class LongVM(app: Application) : AndroidViewModel(app) {
    private val ctx get() = getApplication<Application>()
    val prefs = Prefs(app)
    val tts = Tts(app)
    val vieneu = VieNeuTts(app)
    val updater = Updater(app)
    var vnVoices by mutableStateOf<List<String>>(emptyList())
    var vnReady by mutableStateOf(false)

    val root: File get() = File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "long").apply { mkdirs() }

    var project by mutableStateOf<Project?>(null)
    var rev by mutableIntStateOf(0)                    // tăng mỗi lần dự án đổi -> giao diện vẽ lại
    var projects by mutableStateOf<List<Project>>(emptyList())

    // ---- lựa chọn
    var style by mutableStateOf(prefs.str("l_style", "hap_dan"))
    var vertical by mutableStateOf(prefs.bool("l_vertical", false))
    var quality by mutableStateOf(prefs.str("l_quality", "eco"))     // eco | std | hd
    var karaoke by mutableStateOf(prefs.bool("l_karaoke", false))
    var panelZoom by mutableStateOf(prefs.bool("m_panels", true))
    var rtl by mutableStateOf(prefs.bool("m_rtl", true))
    var watch by mutableStateOf(prefs.bool("l_watch", true))
    var exportMode by mutableStateOf(prefs.str("l_export", "one"))    // one | parts
    var voice by mutableStateOf(prefs.str("voice"))
    var rate by mutableFloatStateOf(prefs.num("rate", 1.1f))
    var bgmName by mutableStateOf(prefs.str("l_bgm_name"))

    // ---- tiến trình
    val logs = mutableStateListOf<String>()
    var progress by mutableFloatStateOf(0f)
    var status by mutableStateOf("")
    var busy by mutableStateOf(false)
    var eta by mutableStateOf("")
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

    init {
        refreshProjects()
        prefs.str("l_last").takeIf { it.isNotBlank() }?.let { n -> projects.firstOrNull { it.dir.name == n }?.let { project = it } }
    }

    fun save(k: String, v: String) = prefs.set(k, v)

    fun log(m: String) {
        val t = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        viewModelScope.launch(Dispatchers.Main) {
            logs.add("[$t] $m")
            if (logs.size > 400) logs.removeAt(0)
        }
    }

    private fun prog(p: Float, s: String? = null) {
        viewModelScope.launch(Dispatchers.Main) {
            progress = p.coerceIn(0f, 1f)
            if (s != null) status = s
        }
    }

    private fun touch() {
        viewModelScope.launch(Dispatchers.Main) { rev++ }
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
                status = "⏸ Đã dừng - bấm ▶ Tiếp tục để làm tiếp từ chỗ dừng"
                log("⏸ Đã dừng.")
            } catch (e: Exception) {
                status = "❌ ${e.message?.lines()?.firstOrNull() ?: e.javaClass.simpleName}"
                log("❌ $name: ${e.message ?: e}")
            } finally {
                busy = false
                ask = null
                apiWaiting = false
                touch()
                if (keepAlive) KeepAliveService.stop(ctx)
            }
        }
    }

    fun cancel() {
        job?.cancel()
        manualReply?.complete(null)
    }

    // ================================================================ dự án
    fun refreshProjects() {
        projects = (root.listFiles()?.filter { File(it, "project.json").exists() } ?: emptyList())
            .mapNotNull { Project.load(it) }.sortedByDescending { it.created }
    }

    fun openProject(p: Project) {
        project = p
        prefs.set("l_last", p.dir.name)
        result = null
        touch()
    }

    fun newProject(kind: String, title: String) {
        val dir = File(root, "p" + System.currentTimeMillis())
        val p = Project(dir).apply { this.kind = kind; this.title = title.ifBlank { "Video dài" } }
        if (kind != "novel") p.mode = "retell"
        p.save()
        refreshProjects()
        openProject(p)
    }

    fun deleteProject() {
        val p = project ?: return
        if (busy) return
        p.dir.deleteRecursively()
        project = null
        prefs.set("l_last", "")
        refreshProjects()
    }

    fun edit(block: Project.() -> Unit) {
        val p = project ?: return
        p.block()
        p.save()
        touch()
    }

    fun removePart(part: Part) = edit {
        parts.remove(part)
        File(dir, "parts/${part.id}").deleteRecursively()
    }

    /** Làm lại 1 phần (đọc / viết lại + dựng lại). */
    fun redoPart(part: Part) = edit {
        part.state = 0
        part.error = ""
        part.dur = 0.0
        File(dir, "parts/${part.id}").listFiles()?.filter { it.name in setOf("vi.txt", "items.json", "script.json", "lines.json", "part.mp4", "part.srt") }
            ?.forEach { it.delete() }
    }

    private fun need(kind: String): Project {
        val p = project ?: throw IllegalStateException("Tạo hoặc chọn dự án trước.")
        if (p.kind != kind) throw IllegalStateException("Dự án này là ${kindName(p.kind)} - tạo dự án mới cho ${kindName(kind)}.")
        return p
    }

    fun kindName(k: String) = when (k) {
        "novel" -> "truyện chữ"
        "manga" -> "truyện tranh"
        else -> "phim"
    }

    private suspend fun copyIn(uri: Uri, out: File) = withContext(Dispatchers.IO) {
        out.parentFile?.mkdirs()
        ctx.contentResolver.openInputStream(uri)?.use { i -> out.outputStream().use { i.copyTo(it) } }
            ?: throw IllegalStateException("Không đọc được file.")
    }

    // ================================================================ nhập: truyện chữ
    private fun addChapters(p: Project, chapters: List<Pair<String, String>>, illus: List<Pair<Int, File>> = emptyList(),
                            positions: List<Int> = emptyList()) {
        for ((k, c) in chapters.withIndex()) {
            val part = p.newPart(c.first.ifBlank { "Chương ${p.parts.size + 1}" }, c.second.length.toDouble())
            val d = p.partDir(part)
            File(d, "src.txt").writeText(c.second)
            // ảnh minh họa nằm trong chương này (EPUB)
            if (positions.isNotEmpty()) {
                val a = positions[k]
                val b = positions.getOrNull(k + 1) ?: Int.MAX_VALUE
                val mine = illus.filter { it.first in a until b }
                if (mine.isNotEmpty()) File(d, "illus.txt").writeText(mine.joinToString("\n") { it.second.path })
            }
        }
        p.save()
        touch()
    }

    fun importNovelFile(uris: List<Uri>) = launchTask("Thêm truyện chữ") {
        val p = need("novel")
        for (uri in uris) {
            val name = Books.displayName(ctx, uri)
            val ext = name.substringAfterLast('.', "").lowercase()
            val src = File(ctx.cacheDir, "nhap.$ext")
            copyIn(uri, src)
            if (ext == "epub") {
                val b = Books.fromEpub(src, File(p.dir, "media")) { prog(it, "Đọc EPUB ${(it * 100).toInt()}%") }
                if (p.title.isBlank() || p.title == "Video dài") p.title = b.title
                if (p.cover.isBlank()) b.cover?.let { p.cover = it.path }
                // chương theo mục lục EPUB; chương quá ngắn (lời nói đầu, mục lục) gộp vào chương sau
                val marks = b.marks.ifEmpty { listOf(0 to "Phần 1") }
                val chs = mutableListOf<Pair<String, String>>()
                val pos = mutableListOf<Int>()
                for ((k, m) in marks.withIndex()) {
                    val end = marks.getOrNull(k + 1)?.first ?: b.text.length
                    val body = b.text.substring(m.first.coerceIn(0, b.text.length), end.coerceIn(m.first, b.text.length)).trim()
                    if (body.length < 300 && k < marks.size - 1) continue
                    // chương 1 file quá dài (EPUB không chia chương): tách theo tiêu đề chương trong chữ
                    val sub = if (body.length > 60000) Text.chapters(body) else listOf(m.second.ifBlank { "Chương ${chs.size + 1}" } to body)
                    for (s in sub) { chs += s; pos += m.first }
                }
                addChapters(p, chs, b.illus.map { it.pos to it.file }, pos)
                log("📖 ${b.title}: ${chs.size} chương, ${b.text.length} ký tự, ${b.illus.size} ảnh minh họa.")
            } else {
                val text = Books.readText(src.readBytes())
                val chs = Text.chapters(text)
                addChapters(p, chs)
                log("📖 $name: ${chs.size} chương, ${text.length} ký tự.")
            }
            src.delete()
        }
    }

    fun importNovelText(text: String, name: String) = launchTask("Dán truyện") {
        val p = need("novel")
        val chs = Text.chapters(text.trim())
        if (chs.size == 1 && name.isNotBlank()) addChapters(p, listOf(name to chs[0].second)) else addChapters(p, chs)
        log("📖 Thêm ${chs.size} chương (${text.length} ký tự).")
    }

    /** Link chương truyện chữ: lấy liên tiếp [n] chương theo nút "Chương sau" (mỗi chương 1 phần). */
    fun importNovelLink(url: String, n: Int) = launchTask("Lấy truyện chữ từ link", keepAlive = true) {
        val p = need("novel")
        var u: String? = url.trim()
        val seen = HashSet<String>()
        var k = 0
        while (u != null && k < n && seen.add(u)) {
            prog(k.toFloat() / n, "Lấy chương ${k + 1}/$n")
            val page = try {
                Web.page(u)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (k == 0) throw IllegalStateException("Không mở được link: ${e.message?.take(120)}")
                log("⚠ Dừng ở chương ${k + 1}: ${e.message?.take(100)}")
                break
            }
            if (page.text.length < 200) {
                if (k == 0) throw IllegalStateException("Không thấy chữ truyện trong trang (trang hiện chữ bằng JavaScript?). Thử chép tay rồi Dán chữ.")
                break
            }
            if (k == 0 && (p.title.isBlank() || p.title == "Video dài")) p.title = page.title.replace(Regex("(?i)\\s*[-–|:]?\\s*(chương|chapter|chap)\\s*\\d+.*$"), "").trim()
            addChapters(p, listOf(page.title.ifBlank { "Chương ${p.parts.size + 1}" } to page.text))
            k++
            u = page.next
        }
        log("📖 Đã lấy $k chương (tổng ${p.parts.size} phần).")
    }

    fun setCover(uri: Uri) = launchTask("Ảnh bìa") {
        val p = project ?: return@launchTask
        val f = File(p.dir, "media/cover_${System.currentTimeMillis()}.jpg")
        copyIn(uri, f)
        edit { cover = f.path }
    }

    // ================================================================ nhập: truyện tranh
    private fun addMangaChapter(p: Project, name: String, pages: List<Page>) {
        val part = p.newPart(name, pages.size.toDouble())
        val d = File(p.partDir(part), "pages").apply { mkdirs() }
        pages.forEachIndexed { i, pg -> pg.file.renameTo(File(d, "p%05d.jpg".format(i))) }
        File(p.partDir(part), "pages.json").writeText(JSONArray().apply {
            pages.forEachIndexed { i, pg -> put(JSONObject().put("w", pg.w).put("h", pg.h).put("label", pg.label).put("strip", pg.strip).put("f", "p%05d.jpg".format(i))) }
        }.toString())
        p.save()
        touch()
    }

    fun pagesOf(p: Project, part: Part): List<Page> {
        val d = p.partDir(part)
        val a = try { JSONArray(File(d, "pages.json").readText()) } catch (e: Exception) { JSONArray() }
        return (0 until a.length()).map { a.getJSONObject(it) }.map {
            Page(File(d, "pages/" + it.getString("f")), it.optInt("w"), it.optInt("h"), it.optString("label"), it.optBoolean("strip"))
        }
    }

    /** Nhiều file CBZ / ZIP / PDF: mỗi file 1 chương. Nhiều ảnh: 1 chương. */
    fun importMangaFiles(uris: List<Uri>) = launchTask("Thêm truyện tranh", keepAlive = true) {
        val p = need("manga")
        val layout = prefs.str("m_layout", "auto")
        val named = uris.map { it to Books.displayName(ctx, it) }.sortedWith { a, b -> Books.natural.compare(a.second, b.second) }
        val images = named.filter { Books.isImage(it.second) }
        if (images.isNotEmpty()) {
            val pages = Books.fromImages(ctx, images.map { it.first }, File(ctx.cacheDir, "nhap_pages").apply { deleteRecursively() }, layout) {
                prog(it, "Đọc ảnh ${(it * 100).toInt()}%")
            }
            addMangaChapter(p, "Chương ${p.parts.size + 1}", pages)
        }
        for ((k, nu) in named.filter { !Books.isImage(it.second) }.withIndex()) {
            val (uri, name) = nu
            val ext = name.substringAfterLast('.', "").lowercase()
            val src = File(ctx.cacheDir, "nhap.$ext")
            copyIn(uri, src)
            val tmp = File(ctx.cacheDir, "nhap_pages").apply { deleteRecursively() }
            val pages = when (ext) {
                "pdf" -> Books.fromPdf(src, tmp) { prog(it, "Chương ${k + 1}: đọc PDF ${(it * 100).toInt()}%") }
                else -> Books.fromZip(src, tmp, layout) { prog(it, "Chương ${k + 1}: giải nén ${(it * 100).toInt()}%") }
            }
            addMangaChapter(p, Books.titleOf(name), pages)
            src.delete()
            log("📚 ${Books.titleOf(name)}: ${pages.size} trang.")
        }
        if (p.title.isBlank() || p.title == "Video dài") edit { title = Books.titleOf(named.first().second).replace(Regex("\\s*\\d+$"), "") }
    }

    /** Link chương truyện tranh: lấy [n] chương liên tiếp (mỗi chương 1 phần). */
    fun importMangaLink(url: String, n: Int) = launchTask("Lấy truyện tranh từ link", keepAlive = true) {
        val p = need("manga")
        val layout = prefs.str("m_layout", "auto")
        var u: String? = url.trim()
        val seen = HashSet<String>()
        var k = 0
        while (u != null && k < n && seen.add(u)) {
            prog(k.toFloat() / n, "Lấy chương ${k + 1}/$n")
            val page = try {
                Web.page(u)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (k == 0) throw IllegalStateException("Không mở được link: ${e.message?.take(120)}")
                log("⚠ Dừng ở chương ${k + 1}: ${e.message?.take(100)}")
                break
            }
            if (page.images.size < 3) {
                if (k == 0) throw IllegalStateException("Không thấy ảnh truyện trong trang (trang tải ảnh bằng JavaScript?). Thử tải về CBZ / ảnh rồi thêm file.")
                break
            }
            val pages = Books.fromUrls(page.images.map { it to page.url }, File(ctx.cacheDir, "nhap_pages").apply { deleteRecursively() }, layout) {
                prog((k + it) / n, "Chương ${k + 1}/$n: tải ảnh ${(it * 100).toInt()}%")
            }
            if (k == 0 && (p.title.isBlank() || p.title == "Video dài")) p.title = page.title.replace(Regex("(?i)\\s*[-–|:]?\\s*(chương|chapter|chap|ch\\.)\\s*\\d+.*$"), "").trim()
            addMangaChapter(p, page.title.ifBlank { "Chương ${p.parts.size + 1}" }, pages)
            log("📚 ${page.title.take(60)}: ${pages.size} trang.")
            k++
            u = page.next
        }
    }

    // ================================================================ nhập: phim nhiều tập
    fun importFilmFiles(uris: List<Uri>) = launchTask("Thêm tập phim", keepAlive = true) {
        val p = need("film")
        val named = uris.map { it to Books.displayName(ctx, it) }.sortedWith { a, b -> Books.natural.compare(a.second, b.second) }
        for ((k, nu) in named.withIndex()) {
            prog(k.toFloat() / named.size, "Chép tập ${k + 1}/${named.size}")
            val part = p.newPart(Books.titleOf(nu.second), 0.0)
            val f = File(p.partDir(part), "video.mp4")
            copyIn(nu.first, f)
            val i = withContext(Dispatchers.IO) { Media.probe(f) }
            part.weight = i.duration
            p.save()
            touch()
            log("🎬 ${part.name}: ${fmtTime(i.duration)}")
        }
        if (p.title.isBlank() || p.title == "Video dài") edit { title = Books.titleOf(named.first().second).replace(Regex("(?i)\\s*(tập|ep|episode|e)?\\s*\\d+$"), "") }
    }

    /** Link tập phim (YouTube / TikTok / Bilibili...), mỗi dòng 1 link - tải bằng yt-dlp. */
    fun importFilmLinks(text: String) = launchTask("Tải tập phim", keepAlive = true) {
        val p = need("film")
        val links = text.lines().mapNotNull { Download.findUrl(it) }
        if (links.isEmpty()) throw IllegalStateException("Dán link tập phim, mỗi dòng 1 link.")
        for ((k, u) in links.withIndex()) {
            val tmp = File(ctx.cacheDir, "dl").apply { deleteRecursively() }
            val (f, t) = Download.fetch(ctx, prefs, u, tmp, ::log) { prog((k + it) / links.size, "Tải tập ${k + 1}/${links.size} ${(it * 100).toInt()}%") }
            val part = p.newPart(t.ifBlank { "Tập ${p.parts.size + 1}" }, 0.0)
            val dst = File(p.partDir(part), "video.mp4")
            if (!f.renameTo(dst)) { f.copyTo(dst, true); f.delete() }
            part.weight = Media.probe(dst).duration
            p.save()
            touch()
            log("🎬 ${part.name}: ${fmtTime(part.weight)}")
        }
        if (p.title.isBlank() || p.title == "Video dài") edit { title = parts.first().name }
    }

    fun setBgm(uri: Uri?) = launchTask("Nhạc nền") {
        val f = File(root, "bgm.audio")
        if (uri == null) {
            f.delete()
            prefs.set("l_bgm_name", "")
            withContext(Dispatchers.Main) { bgmName = "" }
            return@launchTask
        }
        copyIn(uri, f)
        val n = Books.displayName(ctx, uri)
        prefs.set("l_bgm_name", n)
        withContext(Dispatchers.Main) { bgmName = n }
    }

    // ================================================================ chất lượng / ước tính
    fun preset(p: Project): Preset = when (p.kind) {
        "novel" -> when (quality) {
            "hd" -> Preset(1080, 24, 2_000_000, "128k", true)
            "std" -> Preset(720, 15, 700_000, "96k", true)
            else -> Preset(720, 5, 300_000, "64k", false)
        }
        "manga" -> when (quality) {
            "hd" -> Preset(1080, 30, 3_000_000, "128k", true)
            "std" -> Preset(720, 24, 1_500_000, "96k", true)
            else -> Preset(720, 12, 700_000, "64k", true)
        }
        else -> when (quality) {
            "hd" -> Preset(1080, 30, 4_000_000, "128k", true)
            "std" -> Preset(720, 30, 2_000_000, "128k", true)
            else -> Preset(540, 24, 1_000_000, "96k", true)
        }
    }

    fun summary(p: Project): String {
        val sec = p.estimate()
        val gb = preset(p).bytes(sec) / 1e9
        return "${p.parts.size} phần · video khoảng ${Text.stamp(sec)} · ~${"%.1f".format(gb)} GB"
    }

    private fun freeGb(): Double = try { StatFs(root.path).availableBytes / 1e9 } catch (e: Exception) { 99.0 }

    // ================================================================ AI (API / làm tay)
    private class SkipApi : Exception()

    fun skipToManual() {
        skipApi = true
    }

    private suspend fun callApi(step: String, prompt: String, json: Boolean, images: List<File> = emptyList()): String {
        skipApi = false
        withContext(Dispatchers.Main) { apiWaiting = true }
        val call = viewModelScope.async(Dispatchers.IO) {
            val sys = when {
                images.isNotEmpty() -> "Bạn xem ảnh và tả lại bằng tiếng Việt, đúng định dạng được yêu cầu."
                json -> "Bạn là trợ lý biên tập video tiếng Việt. Làm đúng yêu cầu, chỉ trả lời JSON."
                else -> "Bạn là biên tập viên truyện audio tiếng Việt. Làm đúng yêu cầu."
            }
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
                prog(progress, "⏳ $step: chờ AI ${(System.currentTimeMillis() - t0) / 1000}s...")
            }
            return call.await()
        } catch (e: CancellationException) {
            call.cancel()
            throw e
        } finally {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.Main) { apiWaiting = false }
        }
    }

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

    /** Gửi ảnh cho AI nhìn: API (Gemini...) hoặc 🖐 gửi ảnh cho Gemini. [parse] trả rỗng = chưa được. */
    private suspend fun <T> askVision(step: String, prompt: String, files: List<File>, manualNote: String,
                                      parse: (String) -> T, ok: (T) -> Boolean): T? {
        val useApi = !Ai.manual(prefs) && Ai.visionChain(prefs).isNotEmpty()
        if (useApi && !apiDown) {
            try {
                val r = parse(callApi(step, prompt, false, files))
                if (ok(r)) return r
            } catch (e: SkipApi) {
                apiDown = true
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                apiDown = true
                log("⚠ AI nhìn ảnh lỗi (${e.message?.take(120)}) → 🖐 gửi ảnh cho Gemini.")
            }
        }
        val uris = files.map { f -> saveToDownloads(f, f.name, "image/jpeg") }
        try {
            while (true) {
                val r = askManual(ManualAsk(step, "gemini", prompt, manualNote, uris, "${files.size} ảnh",
                    canApi = Ai.visionChain(prefs).isNotEmpty(), mime = "image/jpeg"))
                if (r == RETRY_API) {
                    apiDown = false
                    try {
                        val x = parse(callApi(step, prompt, false, files))
                        if (ok(x)) return x
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        apiDown = true
                        log("⚠ Vẫn lỗi (${e.message?.take(100)}).")
                    }
                    continue
                }
                val x = parse(r)
                if (ok(x)) return x
                log("Không đọc được câu trả lời - dán lại câu trả lời của Gemini.")
            }
        } finally {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.IO) {
                uris.forEach { runCatching { ctx.contentResolver.delete(it, null, null) } }
            }
        }
    }

    private suspend fun askManual(a: ManualAsk): String = manualLock.withLock {
        val d = CompletableDeferred<String?>()
        manualReply = d
        withContext(Dispatchers.Main) { ask = a }
        log("🖐 ${a.step}: chép yêu cầu → dán sang ${if (a.target == "gemini") "Gemini" else "DeepSeek"} → dán câu trả lời lại.")
        val r = d.await()
        withContext(Dispatchers.Main) { ask = null }
        r ?: throw CancellationException("Đã dừng")
    }

    fun answerManual(text: String?) {
        manualReply?.complete(text)
    }

    // ================================================================ làm video dài
    /** Làm lần lượt các phần chưa xong (dừng / tắt app vẫn làm tiếp được), rồi ghép thành video. */
    fun start() = launchTask("Làm video dài", keepAlive = true) {
        val p = project ?: throw IllegalStateException("Tạo hoặc chọn dự án trước.")
        if (p.parts.isEmpty()) throw IllegalStateException("Dự án chưa có chương / tập nào - thêm nội dung ở mục 2.")
        val pr = preset(p)
        val left = p.parts.filter { it.state < 2 }
        val need = pr.bytes(p.estimate()) * left.size / max(1, p.parts.size) * 1.3 / 1e9
        if (freeGb() < need + 1) log("⚠ Bộ nhớ còn ${"%.1f".format(freeGb())} GB, cần khoảng ${"%.1f".format(need + 1)} GB - có thể bị đầy giữa chừng.")
        checkVoices()
        val t0 = System.currentTimeMillis()
        var made = 0
        for ((i, part) in p.parts.withIndex()) {
            if (part.state >= 2) continue
            val base = i.toFloat() / p.parts.size
            fun sub(x: Float, s: String) = prog(base + x / p.parts.size, "Phần ${i + 1}/${p.parts.size} · ${part.name.take(40)}: $s")
            try {
                if (part.state == 0) {
                    when (p.kind) {
                        "novel" -> prepNovel(p, i, part, ::sub)
                        "manga" -> prepManga(p, i, part, ::sub)
                        else -> prepFilm(p, i, part, ::sub)
                    }
                    part.state = 1
                    part.error = ""
                    p.save()
                    touch()
                }
                when (p.kind) {
                    "novel" -> renderNovel(p, part, pr, ::sub)
                    "manga" -> renderManga(p, part, pr, ::sub)
                    else -> renderFilm(p, i, part, pr, ::sub)
                }
                part.dur = withContext(Dispatchers.IO) { Media.probe(File(p.partDir(part), "part.mp4")).duration }
                part.state = 2
                part.error = ""
                p.save()
                touch()
                made++
                val per = (System.currentTimeMillis() - t0) / 1000.0 / made
                val rest = p.parts.count { it.state < 2 }
                withContext(Dispatchers.Main) { eta = if (rest > 0) "Còn $rest phần · khoảng ${Text.stamp(per * rest)}" else "" }
                log("✅ ${part.name}: ${Text.stamp(part.dur)} (xong ${p.doneParts}/${p.parts.size}, video đã có ${Text.stamp(p.totalDur)})")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                part.error = e.message?.take(300) ?: e.javaClass.simpleName
                p.save()
                touch()
                throw IllegalStateException("${part.name}: ${part.error}")
            }
        }
        withContext(Dispatchers.Main) { eta = "" }
        exportAll(p)
    }

    /** Chỉ xuất (ghép) lại video từ các phần đã làm xong. */
    fun export() = launchTask("Xuất video dài", keepAlive = true) {
        val p = project ?: throw IllegalStateException("Chưa có dự án.")
        exportAll(p)
    }

    private suspend fun exportAll(p: Project) {
        val done = p.parts.filter { it.state >= 2 && File(p.partDir(it), "part.mp4").exists() }
        if (done.isEmpty()) throw IllegalStateException("Chưa có phần nào làm xong.")
        if (done.size < p.parts.size) log("⚠ Mới xong ${done.size}/${p.parts.size} phần - xuất các phần đã xong.")
        val safe = p.title.replace(Regex("[\\\\/:*?\"<>|\\n]"), " ").trim().take(70).ifBlank { "Video dài" }
        // mục lục chương + phụ đề cả video
        val toc = Text.chapterList(done)
        var off = 0.0
        val allCues = mutableListOf<Cue>()
        for (pt in done) {
            File(p.partDir(pt), "cues.json").takeIf { it.exists() }?.let { f ->
                val a = JSONArray(f.readText())
                for (k in 0 until a.length()) a.getJSONObject(k).let { o ->
                    allCues += Cue(o.getDouble("s") + off, o.getDouble("e") + off, o.getString("t"))
                }
            }
            off += pt.dur
        }
        val info = File(p.dir, "mo_ta.txt")
        info.writeText("${p.title}\n\nMục lục:\n$toc\n")
        saveToDownloads(info, "$safe - mục lục.txt", "text/plain")
        val srt = File(p.dir, "phu_de.srt")
        srt.writeText(toSrt(allCues))
        saveToDownloads(srt, "$safe.srt", "application/x-subrip")
        if (exportMode == "parts") {
            for ((k, pt) in done.withIndex()) {
                prog(k.toFloat() / done.size, "Lưu phần ${k + 1}/${done.size}")
                val u = saveToGallery(File(p.partDir(pt), "part.mp4"), "$safe - ${"%03d".format(k + 1)} ${pt.name.take(50)}")
                if (k == done.size - 1) withContext(Dispatchers.Main) { result = u }
            }
            log("✅ Đã lưu ${done.size} video vào Thư viện ảnh → Movies/LongRecap. Mục lục + phụ đề ở Download/LongRecap.")
            return
        }
        val total = done.sumOf { it.dur }
        val size = done.sumOf { File(p.partDir(it), "part.mp4").length() } / 1e9
        if (freeGb() < size * 2.1) throw IllegalStateException("Không đủ bộ nhớ để ghép (${"%.1f".format(size)} GB video, cần trống ~${"%.1f".format(size * 2.1)} GB). " +
            "Chọn 'Lưu từng phần riêng' ở mục Xuất, hoặc giải phóng bộ nhớ.")
        prog(0.1f, "Ghép ${done.size} phần (${Text.stamp(total)}, ${"%.1f".format(size)} GB)...")
        log("Ghép ${done.size} phần thành 1 video ${Text.stamp(total)}...")
        val out = File(p.dir, "final.mp4")
        Ff.concat(ctx, done.map { File(p.partDir(it), "part.mp4") }, out)
        prog(0.6f, "Lưu vào Thư viện ảnh...")
        val u = saveToGallery(out, safe)
        out.delete()
        withContext(Dispatchers.Main) { result = u }
        log("✅ Xong video ${Text.stamp(total)} → Thư viện ảnh / Movies/LongRecap. Mục lục chương (dán vào mô tả YouTube) + phụ đề .srt ở Download/LongRecap.")
    }

    /** Xóa file nguồn / phần đã dựng để lấy lại bộ nhớ (giữ dự án). */
    fun cleanup() = launchTask("Dọn bộ nhớ") {
        val p = project ?: return@launchTask
        var freed = 0L
        for (pt in p.parts) p.partDir(pt).walkBottomUp().filter { it.isFile && it.extension in setOf("mp4", "wav", "jpg") }.forEach {
            freed += it.length(); it.delete()
        }
        p.parts.forEach { if (it.state >= 2) it.state = 1 }
        p.save()
        touch()
        log("🗑 Đã xóa ${"%.2f".format(freed / 1e9)} GB file tạm (giữ lời đọc / kịch bản; dựng lại được nếu còn nguồn chữ).")
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
                log("⚠ VieNeu lỗi (${e.message?.take(120)}) → dùng giọng có sẵn của máy.")
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
                vieneu.ensure(clone = false, log = ::log) { pr, s -> prog(progress, "$s (${(pr * 100).toInt()}%)") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                vnDown = true
                log("⚠ Không chuẩn bị được giọng VieNeu (${e.message?.take(120)}) → dùng giọng có sẵn của máy.")
            }
        }
    }

    fun refreshVieNeu() {
        vnVoices = try { VieNeu.allVoices(ctx).keys.toList() } catch (e: Exception) { emptyList() }
        vnReady = VieNeu.ready(ctx)
    }

    fun downloadVieNeu() = launchTask("Tải giọng AI VieNeu", keepAlive = true) {
        vieneu.ensure(clone = true, log = ::log) { pr, s -> prog(pr, s) }
        withContext(Dispatchers.Main) { refreshVieNeu() }
    }

    fun cloneVoice(name: String, uri: Uri) = launchTask("Nhân bản giọng", keepAlive = true) {
        vieneu.ensure(clone = true, log = ::log) { pr, s -> prog(pr * 0.8f, s) }
        val src = File(ctx.cacheDir, "clone_src")
        copyIn(uri, src)
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
        val f = speak("Xin chào các bạn, chào mừng đến với kênh truyện audio. Chúc các bạn nghe truyện vui vẻ!",
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

    /** Đọc lời thoại [segs] (đã có thời gian) vào 1 file WAV, trả về phụ đề. */
    private fun saveCues(d: File, cues: List<Cue>) {
        File(d, "cues.json").writeText(JSONArray().apply { cues.forEach { put(JSONObject().put("s", it.start).put("e", it.end).put("t", it.text)) } }.toString())
        File(d, "part.srt").writeText(toSrt(cues))
    }

    private fun maxChars() = if (vertical) 30 else 44

    private fun size(pr: Preset) = Slides.size(vertical, pr.short)

    private suspend fun mixAndMux(d: File, narr: File, vid: File, pr: Preset, src: File? = null, hasAudio: Boolean = false,
                                  clips: List<Pair<Double, Double>> = emptyList()) {
        val aud = File(d, "audio.wav")
        val bgm = File(root, "bgm.audio").takeIf { it.exists() && bgmName.isNotBlank() }
        Ff.mixRecap(ctx, src ?: narr, src != null && hasAudio, clips, narr, prefs.num("bg_vol", 0.12f).toDouble(), aud, bgm,
            prefs.num("bgm_vol", 0.2f).toDouble())
        Ff.mux(ctx, vid, aud, File(d, "part.mp4"), pr.abit)
        aud.delete()
        narr.delete()
        vid.delete()
    }

    // ---------------------------------------------------------------- truyện chữ
    private suspend fun prepNovel(p: Project, i: Int, part: Part, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val src = File(d, "src.txt").readText()
        val out = when {
            p.mode == "retell" -> {
                sub(0.05f, "AI kể lại chương")
                val chars = (p.budget(i) * CPS).toInt()
                val r = askAi("Kể lại ${part.name}", LongPrompts.retell(p.title, part.name, src.take(60000), chars, style, prefs, p.memory), json = false)
                LongPrompts.clean(r)
            }
            Text.isVietnamese(src) -> src
            else -> {
                val chunks = Books.chunks(src, if (Ai.manual(prefs)) 12000 else 3500)
                val sb = StringBuilder()
                for ((k, c) in chunks.withIndex()) {
                    sub(0.05f + 0.3f * k / chunks.size, "Dịch ${k + 1}/${chunks.size}")
                    val r = askAi("Dịch ${part.name} (${k + 1}/${chunks.size})",
                        LongPrompts.translate(p.title, part.name, c.second, prefs, sb.takeLast(800).toString().ifBlank { p.memory }), json = false)
                    sb.append(LongPrompts.clean(r)).append("\n\n")
                }
                sb.toString().trim()
            }
        }
        if (out.length < 20) throw IllegalStateException("Lời đọc trống.")
        File(d, "vi.txt").writeText(out)
        p.memory = out.takeLast(1200)
    }

    private suspend fun renderNovel(p: Project, part: Part, pr: Preset, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val text = File(d, "vi.txt").readText()
        val chunks = Text.speakChunks(text)
        val tts = File(d, "tts").apply { deleteRecursively(); mkdirs() }
        val narr = File(d, "narration.wav")
        val cues = mutableListOf<Cue>()
        var t = 0.0
        Wav.Writer(narr).use { w ->
            w.silenceTo(0.6)
            t = 0.6
            for ((k, c) in chunks.withIndex()) {
                if (k % 5 == 0) sub(0.4f + 0.4f * k / chunks.size, "Đọc giọng ${k + 1}/${chunks.size}")
                val pcm = Wav.read(speak(c, File(tts, "c.wav"), rate))
                w.silenceTo(t)
                w.write(pcm)
                cues += splitCues(c, t, pcm.seconds, maxChars() * 2)
                t += pcm.seconds + if (c.endsWith(".") || c.endsWith("!") || c.endsWith("?") || c.endsWith("…")) 0.35 else 0.15
            }
            t += 1.0
            w.silenceTo(t)
        }
        tts.deleteRecursively()
        // hình: ảnh minh họa của chương (rải đều), không có thì ảnh bìa, không có thì khung tên truyện
        val (w, h) = size(pr)
        val frames = File(d, "frames").apply { deleteRecursively(); mkdirs() }
        val ill = File(d, "illus.txt").takeIf { it.exists() }?.readLines()?.map { File(it) }?.filter { it.exists() } ?: emptyList()
        val pics = ill.ifEmpty { listOfNotNull(File(p.cover).takeIf { p.cover.isNotBlank() && it.exists() }) }
        val slides = mutableListOf<Slide>()
        val card = Slides.titleCard(p.title, part.name, w, h, File(frames, "card.jpg"))
        if (pics.isEmpty()) slides += Slide(card, t, false) else {
            val first = min(6.0, t / 4)
            slides += Slide(card, first, false)
            val each = (t - first) / pics.size
            pics.forEachIndexed { k, f ->
                val (img, scroll) = Slides.frame(f, w, h, File(frames, "f$k.jpg"))
                slides += Slide(img, each, scroll)
            }
        }
        sub(0.85f, "Dựng hình ${Text.stamp(t)}")
        val vid = File(d, "video_only.mp4")
        Slides.render(ctx, slides, w, h, cues, karaoke, "", vid, pr.fps, pr.vbit, pr.motion) { sub(0.85f + 0.12f * it, "Dựng hình ${(it * 100).toInt()}%") }
        frames.deleteRecursively()
        saveCues(d, cues)
        mixAndMux(d, narr, vid, pr)
    }

    // ---------------------------------------------------------------- truyện tranh
    private suspend fun prepManga(p: Project, i: Int, part: Part, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val pages = pagesOf(p, part)
        if (pages.isEmpty()) throw IllegalStateException("Chương không có trang ảnh.")
        val sheets = withContext(Dispatchers.Default) { Story.sheets(pages, File(d, "doc").apply { deleteRecursively() }) }
        val groups = sheets.chunked(if (!Ai.manual(prefs) && Ai.visionChain(prefs).isNotEmpty()) 3 else 10)
        val notes = HashMap<Int, String>()
        for ((k, g) in groups.withIndex()) {
            sub(0.3f * k / groups.size, "AI đọc tranh ${k + 1}/${groups.size}")
            val first = g.first().pages.first() + 1
            val last = g.last().pages.last() + 1
            val prev = notes.keys.sorted().takeLast(8).mapNotNull { notes[it] }.ifEmpty { listOf(p.memory.takeLast(600)).filter { it.isNotBlank() } }
            val prompt = Story.readPages("${p.title} - ${part.name}", k + 1, groups.size, g.size, first, last, prefs, prev)
            val got = askVision("Đọc tranh ${part.name} (${k + 1}/${groups.size})", prompt, g.map { it.file },
                "Gửi kèm ${g.size} ảnh trang (P$first–P$last) cho Gemini - nút 📤 gửi cả ảnh lẫn yêu cầu.",
                { Story.parsePages(it, first, last) }, { it.isNotEmpty() }) ?: emptyMap()
            notes.putAll(got)
        }
        File(d, "doc").deleteRecursively()
        val items = pages.indices.mapNotNull { k -> notes[k + 1]?.let { Item(it, page = k, label = pages[k].label) } }
        if (items.isEmpty()) throw IllegalStateException("AI chưa đọc được trang nào.")
        File(d, "items.json").writeText(JSONArray().apply { items.forEach { put(JSONObject().put("t", it.text).put("p", it.page).put("l", it.label)) } }.toString())
        sub(0.35f, "AI viết lời kể")
        val target = min(p.budget(i), max(30, (items.sumOf { it.text.length } / CPS * 0.9).toInt()))
        val prompt = LongPrompts.context(p.memory) + Story.script("${p.title} - ${part.name}", true, items, target, style, prefs)
        val segs = scriptFrom(prompt, items.size.toDouble(), Story.asLines(items))
        saveSegs(d, segs)
        p.memory = segs.joinToString(" ") { it.text }.takeLast(1200)
    }

    private suspend fun scriptFrom(prompt: String, duration: Double, lines: List<Line>): List<Seg> {
        var last: Exception? = null
        repeat(2) {
            try {
                val reply = askAi("Viết kịch bản", prompt, json = true)
                val (_, s) = Prompts.parseRecap(reply, duration, lines)
                synchronized(prefs) { Prompts.learnNames(prefs, Prompts.parseNames(reply)) }
                return s
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                last = e
                log("Kịch bản lỗi (${e.message?.take(100)}) - thử lại...")
            }
        }
        throw IllegalStateException("AI không viết được kịch bản: ${last?.message}")
    }

    private fun saveSegs(d: File, segs: List<Seg>) {
        File(d, "script.json").writeText(JSONArray().apply {
            segs.forEach { s -> put(JSONObject().put("s", s.start).put("e", s.end).put("t", s.text)
                .put("r", JSONArray().apply { s.reuse.forEach { (a, b) -> put(JSONArray().put(a).put(b)) } })) }
        }.toString())
    }

    private fun loadSegs(d: File): List<Seg> {
        val a = JSONArray(File(d, "script.json").readText())
        return (0 until a.length()).map { a.getJSONObject(it) }.map { o ->
            val r = o.optJSONArray("r") ?: JSONArray()
            Seg(o.getDouble("s"), o.getString("t"), o.optDouble("e", -1.0),
                (0 until r.length()).map { k -> r.getJSONArray(k).let { it.getDouble(0) to it.getDouble(1) } })
        }
    }

    private suspend fun renderManga(p: Project, part: Part, pr: Preset, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val pages = pagesOf(p, part)
        val book = Book("manga", p.title, pages)
        val a = JSONArray(File(d, "items.json").readText())
        val items = (0 until a.length()).map { a.getJSONObject(it) }.map { Item(it.getString("t"), page = it.getInt("p"), label = it.optString("l")) }
        val segs = loadSegs(d)
        val (w, h) = size(pr)
        val tts = File(d, "tts").apply { deleteRecursively(); mkdirs() }
        val frames = File(d, "frames").apply { deleteRecursively(); mkdirs() }
        val narr = File(d, "narration.wav")
        val slides = mutableListOf<Slide>()
        val cues = mutableListOf<Cue>()
        val made = HashMap<String, Pair<File, Boolean>>()
        val panelsOf = HashMap<String, List<File>>()
        val zoom = !book.webtoon && panelZoom
        Wav.Writer(narr).use { wr ->
            var t = 0.0
            for ((k, s) in segs.withIndex()) {
                sub(0.4f + 0.4f * k / segs.size, "Đọc giọng ${k + 1}/${segs.size}")
                val pcm = Wav.read(speak(s.text, File(tts, "s$k.wav"), rate))
                val dur = pcm.seconds + 0.35
                val e = if (s.end > s.start) s.end.toInt() else s.start.toInt() + 1
                var files = Story.visuals(book, items, s.start.toInt(), e)
                if (zoom) files = files.flatMap { pg ->
                    panelsOf.getOrPut(pg.path) {
                        withContext(Dispatchers.Default) { try { Panels.crops(pg, rtl, File(frames, "khung"), "p${panelsOf.size}") } catch (x: Exception) { listOf(pg) } }
                    }
                }
                if (files.isEmpty()) files = listOf(Slides.titleCard(p.title, part.name, w, h, File(frames, "card.jpg")))
                for ((f, du) in Story.share(files, dur, if (zoom) 1.6 else 2.2)) {
                    val (img, scroll) = made.getOrPut(f.path) {
                        withContext(Dispatchers.Default) {
                            if (f.parentFile == frames) f to false else Slides.frame(f, w, h, File(frames, "f${made.size}.jpg"))
                        }
                    }
                    slides += Slide(img, du, scroll)
                }
                wr.silenceTo(t + 0.15)
                wr.write(pcm)
                cues += splitCues(s.text, t + 0.15, pcm.seconds, maxChars())
                t += dur
                wr.silenceTo(t)
            }
        }
        tts.deleteRecursively()
        val vid = File(d, "video_only.mp4")
        Slides.render(ctx, slides, w, h, cues, karaoke, "", vid, pr.fps, pr.vbit, pr.motion) { sub(0.85f + 0.12f * it, "Dựng hình ${(it * 100).toInt()}%") }
        frames.deleteRecursively()
        saveCues(d, cues)
        mixAndMux(d, narr, vid, pr)
    }

    // ---------------------------------------------------------------- phim nhiều tập
    private suspend fun prepFilm(p: Project, i: Int, part: Part, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val v = File(d, "video.mp4")
        val info = withContext(Dispatchers.IO) { Media.probe(v) }
        // lời thoại: Groq (có key) hoặc 🖐 nhờ Gemini nghe
        val linesFile = File(d, "lines.json")
        val lines: List<Line> = if (linesFile.exists()) readLines(linesFile) else {
            sub(0.05f, "Nghe lời thoại")
            val l = if (!info.hasAudio) emptyList() else if (prefs.key("groq").isNotBlank() || prefs.key("openai").isNotBlank()) try {
                Stt.whisper(ctx, prefs, v, info, ::log) { sub(0.05f + 0.15f * it, "Nghe lời thoại ${(it * 100).toInt()}%") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                log("⚠ Groq lỗi (${e.message?.take(100)}) → 🖐 nhờ Gemini nghe.")
                geminiTranscript(p, part, v, info)
            } else geminiTranscript(p, part, v, info)
            writeLines(linesFile, l)
            l
        }
        // xem hình (cảnh hành động không thoại) - chỉ khi có AI nhìn ảnh qua API (video dài: làm tay quá nhiều lần)
        var scenes = emptyList<Line>()
        if (watch && !Ai.manual(prefs) && Ai.visionChain(prefs).isNotEmpty() && !apiDown) {
            sub(0.2f, "AI xem hình")
            val dir = File(d, "watch").apply { deleteRecursively() }
            val sheets = Watch.sheets(v, info, dir) { sub(0.2f + 0.05f * it, "Chụp khung hình ${(it * 100).toInt()}%") }
            val st = Watch.step(info.duration)
            for ((k, g) in sheets.chunked(5).withIndex()) {
                val lo = g.first().times.first()
                val hi = g.last().times.last()
                val prompt = Prompts.watch("${p.title} - ${part.name}", k + 1, (sheets.size + 4) / 5, lo, hi, g.size,
                    lines.filter { it.end >= lo - 3 && it.start <= hi + 3 }, prefs)
                try {
                    scenes = scenes + Watch.parse(callApi("Xem hình ${part.name}", prompt, false, g.map { it.file }), lo, hi, st)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    log("⚠ Bỏ qua xem hình phần ${k + 1} (${e.message?.take(80)}).")
                    break
                }
            }
            dir.deleteRecursively()
        }
        val tl = Watch.timeline(lines, scenes)
        if (tl.isEmpty()) throw IllegalStateException("Tập này không có lời thoại / mô tả hình nào.")
        sub(0.3f, "AI viết kịch bản")
        val target = min(p.budget(i), (info.duration * 0.9).toInt().coerceAtLeast(30))
        val prompt = LongPrompts.context(p.memory) + Prompts.recap("${p.title} - ${part.name}", info.duration, tl, target, style, prefs)
        val segs = scriptFrom(prompt, info.duration, tl)
        saveSegs(d, segs)
        p.memory = segs.joinToString(" ") { it.text }.takeLast(1200)
    }

    private fun readLines(f: File): List<Line> {
        val a = JSONArray(f.readText())
        return (0 until a.length()).map { a.getJSONObject(it) }.map { Line(it.getDouble("s"), it.getDouble("e"), it.getString("t")) }
    }

    private fun writeLines(f: File, l: List<Line>) =
        f.writeText(JSONArray().apply { l.forEach { put(JSONObject().put("s", it.start).put("e", it.end).put("t", it.text)) } }.toString())

    private suspend fun geminiTranscript(p: Project, part: Part, v: File, i: VInfo): List<Line> {
        val partLen = 20 * 60.0
        val n = max(1, Math.ceil(i.duration / partLen).toInt())
        val out = mutableListOf<Line>()
        for (k in 0 until n) {
            val off = k * partLen
            val mp3 = File(ctx.cacheDir, "gemini_$k.mp3")
            Ff.speechAudio(ctx, v, mp3, off, if (n > 1) partLen else 0.0)
            val name = "${p.title.take(30)} ${part.name.take(30)}${if (n > 1) " phần ${k + 1}" else ""}".replace(Regex("[\\\\/:*?\"<>|]"), " ") + ".mp3"
            val uri = saveToDownloads(mp3, name, "audio/mpeg")
            mp3.delete()
            try {
                var got = emptyList<Line>()
                while (got.isEmpty()) {
                    val r = askManual(ManualAsk("Lời thoại ${part.name}${if (n > 1) " (${k + 1}/$n)" else ""}", "gemini",
                        Prompts.transcribe(p.title, k + 1, n, (min(partLen, i.duration - off) / 60).toInt() + 1),
                        "Gửi kèm file \"$name\" (Download/LongRecap) cho Gemini.", listOf(uri), name))
                    got = parseTimed(r, off)
                    if (got.isEmpty()) log("Cần phụ đề dạng SRT (00:00:01,000 --> ...). Dán lại.")
                }
                out += got
            } finally {
                runCatching { ctx.contentResolver.delete(uri, null, null) }
            }
        }
        return Stt.cleanLines(out.sortedBy { it.start })
    }

    private suspend fun renderFilm(p: Project, i: Int, part: Part, pr: Preset, sub: (Float, String) -> Unit) {
        val d = p.partDir(part)
        val v = File(d, "video.mp4")
        val info = withContext(Dispatchers.IO) { Media.probe(v) }
        val segs = loadSegs(d)
        val tts = File(d, "tts").apply { deleteRecursively(); mkdirs() }
        val narr = File(d, "narration.wav")
        val clips = mutableListOf<Pair<Double, Double>>()
        val cues = mutableListOf<Cue>()
        Wav.Writer(narr).use { w ->
            var t = 0.0
            val order = segs.drop(1).sortedBy { it.start }
            for ((k, s) in segs.withIndex()) {
                sub(0.4f + 0.35f * k / segs.size, "Đọc giọng ${k + 1}/${segs.size}")
                val pcm = Wav.read(speak(s.text, File(tts, "s$k.wav"), rate))
                val dur = pcm.seconds + 0.35
                val a0 = s.start.coerceIn(0.0, max(0.0, info.duration - 1.0))
                val b0 = (if (s.end > s.start) s.end else s.start + dur).coerceIn(a0, info.duration)
                val idx = order.indexOf(s)
                val lo = if (idx > 0) order[idx - 1].let { q -> if (q.end > q.start) q.end else q.start } else 0.0
                val hi = order.getOrNull(idx + 1)?.start ?: info.duration
                val (wl, wh) = min(lo, a0) to max(hi, b0)
                val from = max(wl, a0 - dur)
                val to = min(wh, b0 + dur)
                val pieces = try {
                    val sh = Shots.shots(Shots.analyze(ctx, v, from, to - from), to)
                    Shots.planIn(sh, a0, b0, dur, wl, min(wh, info.duration))
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    listOf(min(a0, max(0.0, info.duration - dur)) to dur)
                }
                w.silenceTo(t + 0.15)
                w.write(pcm)
                cues += splitCues(s.text, t + 0.15, pcm.seconds, maxChars())
                for ((a, du) in pieces) clips += a to min(info.duration, a + du)
                t += pieces.sumOf { (a, du) -> min(info.duration, a + du) - a }
                w.silenceTo(t)
            }
        }
        tts.deleteRecursively()
        val spec = RenderSpec(v, info, clips, if (vertical) Aspect.VERTICAL_FIT else Aspect.HORIZONTAL, pr.short, null, 0.8f to 0.95f,
            cues, "", karaoke = karaoke, hook = if (i == 0) p.title else "")
        val vid = File(d, "video_only.mp4")
        Render.video(ctx, spec, vid, pr.vbit) { sub(0.78f + 0.2f * it, "Dựng hình ${(it * 100).toInt()}%") }
        saveCues(d, cues)
        mixAndMux(d, narr, vid, pr, v, info.hasAudio, clips)
    }

    // ================================================================ lưu file
    private suspend fun saveToDownloads(f: File, name: String, mime: String): Uri = withContext(Dispatchers.IO) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/LongRecap")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val r = ctx.contentResolver
        val uri = r.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: throw IllegalStateException("Không lưu được vào Download.")
        r.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
        values.clear()
        values.put(MediaStore.Downloads.IS_PENDING, 0)
        r.update(uri, values, null, null)
        uri
    }

    private suspend fun saveToGallery(f: File, name: String): Uri = withContext(Dispatchers.IO) {
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "$name.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/LongRecap")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val r = ctx.contentResolver
        val uri = r.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: throw IllegalStateException("Không lưu được vào thư viện ảnh.")
        r.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o, 1 shl 20) } }
        values.clear()
        values.put(MediaStore.Video.Media.IS_PENDING, 0)
        r.update(uri, values, null, null)
        uri
    }

    override fun onCleared() {
        tts.shutdown()
        vieneu.close()
        super.onCleared()
    }
}
