@file:OptIn(ExperimentalMaterial3Api::class)

package com.vtgt.reviewphim.longvid

import android.content.Intent
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vtgt.reviewphim.Ai
import com.vtgt.reviewphim.BuildConfig
import com.vtgt.reviewphim.Choice
import com.vtgt.reviewphim.Hint
import com.vtgt.reviewphim.ManualDialog
import com.vtgt.reviewphim.Muted
import com.vtgt.reviewphim.Prompts
import com.vtgt.reviewphim.Section
import com.vtgt.reviewphim.Toggle
import com.vtgt.reviewphim.Advanced
import com.vtgt.reviewphim.VieNeu
import com.vtgt.reviewphim.VoiceStudio
import kotlinx.coroutines.launch

@Composable
fun LongScreen(vm: LongVM, embedded: Boolean = false) {
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("📦 Dự án", "📋 Tiến độ")
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        TabRow(selectedTabIndex = tab) {
            tabs.forEachIndexed { i, t -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }) }
        }
        Box(Modifier.weight(1f)) {
            androidx.compose.animation.Crossfade(tab, label = "tab") { t -> if (t == 0) ProjectTab(vm) else ProgressTab(vm) }
        }
        @Suppress("UNUSED_VARIABLE") val rv = vm.rev
        val started = vm.project?.parts?.any { it.state > 0 } == true
        com.vtgt.reviewphim.ProgressPanel(vm.busy, vm.status, vm.progress, vm.apiWaiting, vm.logs, vm.result,
            if (started) "▶ TIẾP TỤC LÀM VIDEO DÀI" else "⚡ LÀM VIDEO DÀI", vm.project?.parts?.isNotEmpty() == true,
            vm::start, vm::cancel, vm::skipToManual, eta = vm.eta, stopLabel = "⏸ Dừng")
    }
    vm.ask?.let { ManualDialog(it, vm::answerManual, vm::cancel) }
}

// ==================================================================== tab Dự án
@Composable
private fun ProjectTab(vm: LongVM) {
    @Suppress("UNUSED_VARIABLE") val r = vm.rev   // vẽ lại khi dự án đổi
    var newBox by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
        Section("Dự án", 1, vm.project != null) {
            if (vm.projects.isNotEmpty()) {
                Choice("Dự án đang làm", vm.project?.dir?.name ?: "", vm.projects.map {
                    it.dir.name to "${kindIcon(it.kind)} ${it.title} (${it.doneParts}/${it.parts.size})"
                }) { n -> vm.projects.firstOrNull { it.dir.name == n }?.let(vm::openProject) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { newBox = true }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("➕ Dự án mới") }
                if (vm.project != null) {
                    var confirm by remember { mutableStateOf(false) }
                    OutlinedButton(onClick = { if (confirm) { vm.deleteProject(); confirm = false } else confirm = true }, enabled = !vm.busy) {
                        Text(if (confirm) "Bấm lần nữa để xóa" else "🗑 Xóa dự án")
                    }
                }
            }
            vm.project?.let { p ->
                var t by remember(p.dir.name) { mutableStateOf(p.title) }
                OutlinedTextField(t, { t = it; vm.edit { title = it } }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Tên truyện / phim (giúp AI gọi đúng tên nhân vật)") })
                Hint("${kindIcon(p.kind)} ${when (p.kind) { "novel" -> "Truyện audio (truyện chữ)"; "manga" -> "Tóm tắt cả bộ truyện tranh"; else -> "Tóm tắt cả bộ phim nhiều tập" }} · " +
                    vm.summary(p))
            }
        }
        vm.project?.let { p ->
            Section("Nội dung (${p.parts.size} ${if (p.kind == "film") "tập" else "chương"})", 2, p.parts.isNotEmpty()) { AddContent(vm, p) }
            Section("Cách làm", 3) { HowSection(vm, p) }
            Section("Giọng đọc", 4) { VoicePicker(vm) }
        }
        if (vm.project == null) Section("Bắt đầu") {
            Hint("Tạo dự án: truyện audio dài (đọc nguyên văn hoặc AI kể lại cả bộ tiểu thuyết / light novel / web novel), " +
                "tóm tắt cả bộ truyện tranh, hoặc review cả bộ phim nhiều tập. App làm từng chương / tập rồi ghép thành video dài " +
                "tới 10 tiếng; tắt app giữa chừng vẫn làm tiếp được.")
        }
        Spacer(Modifier.height(12.dp))
    }
    if (newBox) NewProjectDialog(vm) { newBox = false }
}

private fun kindIcon(k: String) = when (k) {
    "novel" -> "📖"
    "manga" -> "📚"
    else -> "🎬"
}

@Composable
private fun NewProjectDialog(vm: LongVM, close: () -> Unit) {
    var kind by remember { mutableStateOf("novel") }
    var title by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = close, title = { Text("➕ Dự án video dài") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Choice("Loại video", kind, listOf("novel" to "📖 Truyện audio dài (tiểu thuyết, light novel, web novel)",
                "manga" to "📚 Tóm tắt cả bộ truyện tranh (manga / manhwa / manhua)",
                "film" to "🎬 Review / tóm tắt cả bộ phim nhiều tập")) { kind = it }
            OutlinedTextField(title, { title = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Tên truyện / phim") })
        }
    }, confirmButton = { Button(onClick = { vm.newProject(kind, title); close() }) { Text("Tạo") } },
        dismissButton = { TextButton(onClick = close) { Text("Hủy") } })
}

@Composable
private fun AddContent(vm: LongVM, p: Project) {
    var link by remember { mutableStateOf("") }
    var n by remember { mutableStateOf(vm.prefs.str("l_chapters", "50").toInt()) }
    var paste by remember { mutableStateOf(false) }
    when (p.kind) {
        "novel" -> {
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { if (it.isNotEmpty()) vm.importNovelFile(it) }
            val cover = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let(vm::setCover) }
            Hint("EPUB (tự chia chương theo mục lục, lấy ảnh minh họa + bìa), TXT (tự chia theo dòng \"Chương ...\"), dán chữ, hoặc link chương đầu.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { pick.launch(arrayOf("*/*")) }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("📂 EPUB / TXT") }
                OutlinedButton(onClick = { paste = true }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("📋 Dán chữ") }
            }
            OutlinedButton(onClick = { cover.launch("image/*") }, enabled = !vm.busy) {
                Text(if (p.cover.isBlank()) "🖼 Chọn ảnh bìa" else "🖼 Đổi ảnh bìa")
            }
            LinkRow(vm, link, { link = it }, n, { n = it }) { vm.importNovelLink(link, n) }
        }
        "manga" -> {
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { if (it.isNotEmpty()) vm.importMangaFiles(it) }
            Hint("Nhiều file CBZ / ZIP / PDF (mỗi file 1 chương), hoặc ảnh các trang (1 chương), hoặc link chương đầu.")
            Button(onClick = { pick.launch(arrayOf("*/*")) }, enabled = !vm.busy, modifier = Modifier.fillMaxWidth()) { Text("📂 CBZ / ZIP / PDF / ảnh") }
            var layout by remember { mutableStateOf(vm.prefs.str("m_layout", "auto")) }
            Choice("Kiểu truyện", layout, listOf("auto" to "Tự nhận", "page" to "Theo trang (manga, manhua)",
                "webtoon" to "Cuộn dọc (manhwa, webtoon)")) { layout = it; vm.save("m_layout", it) }
            LinkRow(vm, link, { link = it }, n, { n = it }) { vm.importMangaLink(link, n) }
        }
        else -> {
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { if (it.isNotEmpty()) vm.importFilmFiles(it) }
            Hint("Chọn nhiều tập phim (xếp theo tên file), hoặc dán link từng tập (mỗi dòng 1 link - YouTube, TikTok, Bilibili...).")
            Button(onClick = { pick.launch("video/*") }, enabled = !vm.busy, modifier = Modifier.fillMaxWidth()) { Text("🎬 Chọn các tập phim") }
            OutlinedTextField(link, { link = it }, Modifier.fillMaxWidth().heightIn(min = 80.dp), label = { Text("Link các tập (mỗi dòng 1 link)") })
            OutlinedButton(onClick = { vm.importFilmLinks(link); link = "" }, enabled = !vm.busy && link.contains("http")) { Text("⬇ Tải các tập") }
        }
    }
    if (p.parts.isNotEmpty()) Hint("Đã có ${p.parts.size} ${if (p.kind == "film") "tập" else "chương"} - xem / xóa / làm lại ở tab 📋 Tiến độ.")
    if (paste) {
        var name by remember { mutableStateOf("") }
        var text by remember { mutableStateOf("") }
        AlertDialog(onDismissRequest = { paste = false }, title = { Text("📋 Dán truyện") }, text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Tên chương (nếu dán 1 chương)") })
                OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().heightIn(min = 160.dp, max = 320.dp),
                    label = { Text("Nội dung (nhiều chương thì tự chia theo dòng \"Chương ...\")") })
                Hint("${text.length} ký tự")
            }
        }, confirmButton = { Button(onClick = { vm.importNovelText(text, name); paste = false }, enabled = text.isNotBlank()) { Text("Thêm") } },
            dismissButton = { TextButton(onClick = { paste = false }) { Text("Hủy") } })
    }
}

@Composable
private fun LinkRow(vm: LongVM, link: String, setLink: (String) -> Unit, n: Int, setN: (Int) -> Unit, go: () -> Unit) {
    OutlinedTextField(link, setLink, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Link chương đầu") })
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) {
            Choice("Số chương lấy liên tiếp", n, listOf(10, 20, 50, 100, 200, 500, 1000).map { it to "$it chương" }) {
                setN(it); vm.save("l_chapters", "$it")
            }
        }
        Button(onClick = go, enabled = !vm.busy && link.startsWith("http")) { Text("📥 Lấy") }
    }
}

@Composable
private fun HowSection(vm: LongVM, p: Project) {
    if (p.kind == "novel") {
        Choice("Cách đọc", p.mode, listOf("verbatim" to "Đọc nguyên văn (truyện nước ngoài thì AI dịch trước)",
            "retell" to "AI kể lại rút gọn theo độ dài bạn chọn")) { m -> vm.edit { mode = m } }
        if (p.mode == "verbatim") Hint("Truyện tiếng Việt đọc thẳng, không cần AI. Độ dài video theo độ dài truyện (~${Text.stamp(p.estimate())}).")
    }
    if (p.kind != "novel" || p.mode == "retell") {
        Choice("Độ dài cả video", p.targetMin, listOf(30, 60, 90, 120, 180, 240, 300, 360, 480, 600).map {
            it to (if (it < 60) "$it phút" else "${it / 60} giờ${if (it % 60 > 0) " ${it % 60} phút" else ""}")
        }) { m -> vm.edit { targetMin = m } }
        Choice("Văn phong", vm.style, Prompts.STYLES.map { it.key to it.value }) { vm.style = it; vm.save("l_style", it) }
    }
    Choice("Khung hình", vm.vertical, listOf(false to "Ngang 16:9 (YouTube - nên dùng cho video dài)", true to "Dọc 9:16")) {
        vm.vertical = it; vm.prefs.setBool("l_vertical", it)
    }
    Choice("Chất lượng / dung lượng", vm.quality, listOf(
        "eco" to "Tiết kiệm - file nhỏ (truyện audio ~0.15 GB/giờ)",
        "std" to "Chuẩn 720p",
        "hd" to "Nét 1080p (file lớn, dựng lâu)")) { vm.quality = it; vm.save("l_quality", it) }
    Hint("Ước tính: ${vm.summary(p)}")
    Advanced("⚙ Tùy chọn thêm: phụ đề, khung tranh, xuất, nhạc nền") {
    Toggle("Phụ đề karaoke (chữ đổi màu theo giọng đọc)", vm.karaoke) { vm.karaoke = it; vm.prefs.setBool("l_karaoke", it) }
    if (p.kind == "manga") {
        Toggle("Chiếu lần lượt từng khung tranh", vm.panelZoom) { vm.panelZoom = it; vm.prefs.setBool("m_panels", it) }
        if (vm.panelZoom) Choice("Thứ tự khung", vm.rtl, listOf(true to "Phải → trái (manga Nhật)", false to "Trái → phải (manhua, manhwa)")) {
            vm.rtl = it; vm.prefs.setBool("m_rtl", it)
        }
    }
    if (p.kind == "film") Toggle("👁 AI xem hình mỗi tập (cần key Gemini / OpenRouter...)", vm.watch) { vm.watch = it; vm.prefs.setBool("l_watch", it) }
    Choice("Xuất", vm.exportMode, listOf("one" to "Ghép thành 1 video dài", "parts" to "Lưu từng chương / tập thành video riêng")) {
        vm.exportMode = it; vm.save("l_export", it)
    }
    val pickBgm = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let { u -> vm.setBgm(u) } }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("🎵 Nhạc nền: " + vm.bgmName.ifBlank { "không có" }, modifier = Modifier.weight(1f), fontSize = 14.sp)
        OutlinedButton(onClick = { pickBgm.launch("audio/*") }, enabled = !vm.busy) { Text("Chọn") }
        if (vm.bgmName.isNotBlank()) TextButton(onClick = { vm.setBgm(null) }) { Text("✖") }
    }
    }
}

@Composable
private fun VoicePicker(vm: LongVM) {
    val ctx = LocalContext.current
    var voices by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    LaunchedEffect(Unit) {
        voices = try { vm.tts.voices(vm.prefs.str("tts_engine")) } catch (e: Exception) { emptyList() }
        vm.refreshVieNeu()
    }
    var src by remember { mutableStateOf(vm.prefs.str("tts_src", "device")) }
    Choice("Nguồn giọng đọc", src, listOf("device" to "📱 Giọng có sẵn trong máy (nhanh nhất cho video dài)",
        "vieneu" to "🦜 VieNeu AI ngay trên máy + nhân bản giọng (hay hơn, chậm hơn)",
        "voicestudio" to "🎙 VoiceStudio trên máy tính")) { src = it; vm.prefs.set("tts_src", it) }
    when (src) {
        "vieneu" -> {
            if (!vm.vnReady) Button(onClick = vm::downloadVieNeu, enabled = !vm.busy) { Text("⬇ Tải giọng AI VieNeu (~450 MB)") }
            var v by remember { mutableStateOf(vm.prefs.str("vn_voice", "Minh Quân")) }
            if (vm.vnVoices.isNotEmpty()) Choice("Giọng VieNeu", v, vm.vnVoices.map { it to it }) { v = it; vm.prefs.set("vn_voice", it) }
            var fast by remember { mutableStateOf(vm.prefs.bool("vn_fast", true)) }
            Toggle("Đọc nhanh hơn (nên bật cho video dài)", fast) { fast = it; vm.prefs.setBool("vn_fast", it) }
            var name by remember { mutableStateOf("") }
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let { u -> vm.cloneVoice(name, u) } }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(name, { name = it }, Modifier.weight(1f), singleLine = true, label = { Text("Tên giọng nhân bản") })
                OutlinedButton(onClick = { pick.launch("*/*") }, enabled = !vm.busy) { Text("📂 File mẫu") }
            }
            Hint("File ghi âm 8-15 giây giọng của bạn / người đã đồng ý.")
            vm.vnVoices.filter { it in VieNeu.userVoices(ctx) }.forEach { n ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("🎙 $n", modifier = Modifier.weight(1f), fontSize = 14.sp)
                    TextButton(onClick = { vm.deleteVoice(n) }) { Text("Xóa") }
                }
            }
        }
        "voicestudio" -> {
            var vs by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
            var vsVoice by remember { mutableStateOf(vm.prefs.str("vs_voice")) }
            LaunchedEffect(Unit) { vs = try { VoiceStudio.voices(vm.prefs) } catch (e: Exception) { emptyList() } }
            if (vs.isNotEmpty()) Choice("Giọng VoiceStudio", vsVoice, vs) { vsVoice = it; vm.prefs.set("vs_voice", it) }
            else Hint("Nhập địa chỉ VoiceStudio ở Cài đặt.")
        }
        else -> if (voices.isNotEmpty()) Choice("Giọng đọc", vm.voice, listOf("" to "Mặc định của máy") + voices) {
            vm.voice = it; vm.save("voice", it)
        }
    }
    Hint("Tốc độ đọc: ${"%.2f".format(vm.rate)}x")
    Slider(vm.rate, { vm.rate = it; vm.prefs.setNum("rate", it) }, valueRange = 0.8f..1.6f)
    OutlinedButton(onClick = vm::previewVoice, enabled = !vm.busy) { Text("🔊 Nghe thử") }
}

// ==================================================================== tab Tiến độ
@Composable
private fun ProgressTab(vm: LongVM) {
    @Suppress("UNUSED_VARIABLE") val r = vm.rev
    val p = vm.project
    var gallery by remember { mutableStateOf<Part?>(null) }
    gallery?.let { pt ->
        if (p != null) com.vtgt.reviewphim.manga.PageGallery("${p.title} - ${pt.name}", vm.pagesOf(p, pt), vm.busy,
            onDelete = { vm.deletePages(pt, it) }) { gallery = null }
    }
    Column(Modifier.fillMaxSize()) {
        if (p == null) {
            Box(Modifier.padding(16.dp)) { Hint("Chưa có dự án - tạo ở tab 📦 Dự án.") }
            return@Column
        }
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("${p.doneParts}/${p.parts.size} phần xong · video đã có ${Text.stamp(p.totalDur)}", fontWeight = FontWeight.SemiBold)
            if (vm.eta.isNotBlank()) Hint("⏱ ${vm.eta}")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = vm::export, enabled = !vm.busy && p.doneParts > 0, modifier = Modifier.weight(1f)) { Text("📤 Xuất phần đã xong") }
                OutlinedButton(onClick = vm::cleanup, enabled = !vm.busy && p.doneParts > 0) { Text("🗑 Dọn file tạm") }
            }
            Hint("Video dài làm lâu (đọc giọng + dựng từng phần): cứ để máy cắm sạc. Tắt app / dừng giữa chừng thì bấm ▶ Tiếp tục, app làm tiếp từ phần dở.")
        }
        LazyColumn(Modifier.fillMaxSize()) {
            itemsIndexed(p.parts, key = { _, pt -> pt.id }) { i, pt ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(when (pt.state) { 2 -> "✅"; 1 -> "📝"; else -> "○" }, modifier = Modifier.width(28.dp))
                    Column(Modifier.weight(1f)) {
                        Text("${i + 1}. ${pt.name}", fontSize = 14.sp, maxLines = 1)
                        val extra = when {
                            pt.error.isNotBlank() -> "❌ ${pt.error.take(120)}"
                            pt.state >= 2 -> Text.stamp(pt.dur)
                            pt.state == 1 -> "đã có lời đọc / kịch bản"
                            else -> when (p.kind) { "novel" -> "${pt.weight.toInt()} ký tự"; "manga" -> "${pt.weight.toInt()} trang"; else -> Text.stamp(pt.weight) }
                        }
                        Text(extra, fontSize = 12.sp, color = if (pt.error.isNotBlank()) Color(0xFFFF8A80) else Muted, maxLines = 2)
                    }
                    if (p.kind == "manga") TextButton(onClick = { gallery = pt }) { Text("👁") }
                    if (!vm.busy) {
                        if (pt.state > 0) TextButton(onClick = { vm.redoPart(pt) }) { Text("↻") }
                        TextButton(onClick = { vm.removePart(pt) }) { Text("✖") }
                    }
                }
            }
        }
    }
}

// ==================================================================== thanh dưới
// ==================================================================== tab Cài đặt
