@file:OptIn(ExperimentalMaterial3Api::class)

package com.vtgt.reviewphim.manga

import android.content.Intent
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
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
fun MangaScreen(vm: MangaVM, embedded: Boolean = false) {
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("📚 Làm video", "✏️ Kịch bản")
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        TabRow(selectedTabIndex = tab) {
            tabs.forEachIndexed { i, t -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }) }
        }
        Box(Modifier.weight(1f)) {
            androidx.compose.animation.Crossfade(tab, label = "tab") { t -> if (t == 0) MakeTab(vm) else ScriptTab(vm) }
        }
        com.vtgt.reviewphim.ProgressPanel(vm.busy, vm.status, vm.progress, vm.apiWaiting, vm.logs, vm.result,
            "⚡ LÀM VIDEO TÓM TẮT", vm.book != null, vm::makeVideo, vm::cancel, vm::skipToManual)
    }
    vm.ask?.let { ManualDialog(it, vm::answerManual, vm::cancel) }
}

// ==================================================================== tab Làm video
@Composable
private fun MakeTab(vm: MangaVM) {
    val pickImages = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { if (it.isNotEmpty()) vm.openImages(it) }
    val pickTree = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { it?.let(vm::openTree) }
    val pickFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::openFile) }
    val pickIllus = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { if (it.isNotEmpty()) vm.addIllus(it) }
    val pickBgm = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let { u -> vm.setBgm(u) } }
    var paste by remember { mutableStateOf(false) }
    var linkBox by remember { mutableStateOf(false) }
    var gallery by remember { mutableStateOf(false) }
    var browser by remember { mutableStateOf<String?>(null) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
        Section("Truyện", 1, vm.book != null) {
            Hint("Manga / manhwa / manhua hoặc light novel / tiểu thuyết: chọn 1 cách đưa truyện vào.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                com.vtgt.reviewphim.Tile("🔗", "Link", !vm.busy, Modifier.weight(1f), primary = true) { linkBox = true }
                com.vtgt.reviewphim.Tile("🖼", "Ảnh trang", !vm.busy, Modifier.weight(1f)) { pickImages.launch("image/*") }
                com.vtgt.reviewphim.Tile("📁", "Thư mục", !vm.busy, Modifier.weight(1f)) { pickTree.launch(null) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                com.vtgt.reviewphim.Tile("📦", "CBZ·PDF·EPUB", !vm.busy, Modifier.weight(1f)) { pickFile.launch(arrayOf("*/*")) }
                com.vtgt.reviewphim.Tile("📋", "Dán chữ", !vm.busy, Modifier.weight(1f)) { paste = true }
                com.vtgt.reviewphim.Tile("🌐", "Trình duyệt", !vm.busy, Modifier.weight(1f)) { browser = "" }
            }
            Choice("Kiểu truyện tranh", vm.layout, listOf("auto" to "Tự nhận",
                "page" to "Theo trang (manga, manhua, comic)",
                "webtoon" to "Cuộn dọc (manhwa, webtoon) - nối & cắt lại theo khung")) { vm.layout = it; vm.save("m_layout", it) }
            vm.book?.let { b ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    vm.cover?.let {
                        Image(it.asImageBitmap(), null, Modifier.width(72.dp).heightIn(max = 110.dp), contentScale = ContentScale.Fit)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(if (b.manga) "📚 Truyện tranh · ${b.pages.size} trang/khúc" else
                            "📖 Truyện chữ · ${b.text.length} ký tự · ${b.illus.size} ảnh minh họa", fontSize = 14.sp)
                        if (vm.items.isNotEmpty()) Hint("Đã đọc: ${vm.items.size} dòng diễn biến")
                    }
                }
                OutlinedTextField(vm.title, { vm.title = it }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Tên truyện (giúp AI gọi đúng tên nhân vật)") })
                if (b.manga) OutlinedButton(onClick = { gallery = true }, modifier = Modifier.fillMaxWidth()) {
                    Text("👁 Xem trước ${b.pages.size} trang đã tải (xóa trang thừa / quảng cáo)")
                }
                if (!b.manga && b.illus.isNotEmpty()) OutlinedButton(onClick = { gallery = true }, modifier = Modifier.fillMaxWidth()) {
                    Text("👁 Xem ${b.illus.size} ảnh minh họa")
                }
                if (!b.manga) OutlinedButton(onClick = { pickIllus.launch("image/*") }, enabled = !vm.busy) {
                    Text("🖼 Thêm ảnh bìa / minh họa")
                }
            }
        }
        Section("Video", 2) {
            Choice("Độ dài video", vm.targetSec, listOf(60 to "1 phút", 180 to "3 phút", 300 to "5 phút", 600 to "10 phút",
                900 to "15 phút", 1200 to "20 phút", 1800 to "30 phút")) { vm.targetSec = it; vm.save("m_target", "$it") }
            Choice("Văn phong", vm.style, Prompts.STYLES.map { it.key to it.value }) { vm.style = it; vm.save("m_style", it) }
            Choice("Khung hình", vm.vertical, listOf(true to "Dọc 9:16 (TikTok, Shorts, Reels)", false to "Ngang 16:9 (YouTube)")) {
                vm.vertical = it; vm.prefs.setBool("m_vertical", it)
            }
            Advanced("⚙ Tùy chọn thêm: khung tranh, phụ đề, nhạc nền, chất lượng") {
            Choice("Chất lượng", vm.quality, listOf(540 to "540p (nhanh nhất)", 720 to "720p HD", 1080 to "1080p Full HD")) {
                vm.quality = it; vm.save("m_quality", "$it")
            }
            Toggle("Chiếu lần lượt từng khung tranh (truyện theo trang)", vm.panelZoom) {
                vm.panelZoom = it; vm.prefs.setBool("m_panels", it)
            }
            if (vm.panelZoom) Choice("Thứ tự khung trong 1 hàng", vm.rtl, listOf(true to "Phải → trái (manga Nhật)",
                false to "Trái → phải (manhua, manhwa, comic)")) { vm.rtl = it; vm.prefs.setBool("m_rtl", it) }
            Toggle("Phụ đề karaoke (chữ đổi màu theo giọng đọc)", vm.karaoke) { vm.karaoke = it; vm.prefs.setBool("karaoke", it) }
            Toggle("Tiêu đề lớn ở đầu video (hook)", vm.hookTitle) { vm.hookTitle = it; vm.prefs.setBool("hook_title", it) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("🎵 Nhạc nền: " + vm.bgmName.ifBlank { "không có" }, modifier = Modifier.weight(1f), fontSize = 14.sp)
                OutlinedButton(onClick = { pickBgm.launch("audio/*") }, enabled = !vm.busy) { Text("Chọn") }
                if (vm.bgmName.isNotBlank()) TextButton(onClick = { vm.setBgm(null) }) { Text("✖") }
            }
            if (vm.bgmName.isNotBlank()) {
                var bv by remember { mutableStateOf(vm.prefs.num("bgm_vol", 0.25f)) }
                Hint("Âm lượng nhạc nền: ${(bv * 100).toInt()}% (tự nhỏ lại khi có giọng đọc)")
                Slider(bv, { bv = it; vm.prefs.setNum("bgm_vol", it) }, valueRange = 0.05f..0.6f)
            }
            }
            Advanced("📚 Tên nhân vật đúng ngay từ đầu (MyAnimeList)") {
            var q by remember { mutableStateOf("") }
            Hint("Gõ tên truyện (tiếng Anh / Nhật, vd: Solo Leveling) → lấy danh sách nhân vật chính thức từ MyAnimeList.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(q, { q = it }, Modifier.weight(1f), singleLine = true, label = { Text("Tên truyện") })
                Button(onClick = { vm.findCast(q) }, enabled = !vm.busy && q.isNotBlank()) { Text("🔍") }
            }
            if (vm.castInfo.isNotBlank()) Row(verticalAlignment = Alignment.CenterVertically) {
                Text("📚 ${vm.castInfo}", modifier = Modifier.weight(1f), fontSize = 13.sp)
                TextButton(onClick = vm::clearCast) { Text("✖") }
            }
                    }
        }
        Section("Giọng đọc", 3) { VoicePicker(vm) }
        Section("📋 Các bước sẽ làm") {
            vm.plan().forEachIndexed { k, (t, manual) ->
                Text("${k + 1}. $t", fontSize = 14.sp, color = if (manual) Color(0xFFFFD54F) else MaterialTheme.colorScheme.onSurface)
            }
            Hint("🖐 = bước bạn làm tay: app chép sẵn yêu cầu (và ảnh), bạn gửi sang Gemini / DeepSeek rồi dán câu trả lời lại. " +
                "Có key Gemini (miễn phí) thì app tự làm hết.")
        }
        Spacer(Modifier.height(12.dp))
    }
    if (paste) PasteDialog(vm) { paste = false }
    if (linkBox) LinkDialog(vm, { linkBox = false }) { u -> browser = u }
    vm.book?.let { b ->
        if (gallery) {
            if (b.manga) PageGallery(b.title, b.pages, vm.busy, onDelete = vm::deletePages) { gallery = false }
            else PageGallery(b.title, b.illus.mapIndexed { i, il -> Page(il.file, 0, 0, "Ảnh ${i + 1}") }, vm.busy,
                onDelete = vm::deleteIllus) { gallery = false }
        }
    }
    browser?.let { BrowserDialog(vm, it) { browser = null } }
}

@Composable
private fun PasteDialog(vm: MangaVM, close: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = close, title = { Text("📋 Dán truyện chữ") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Tên truyện") })
            OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().heightIn(min = 160.dp, max = 320.dp),
                label = { Text("Nội dung (một hay nhiều chương)") })
            Hint("${text.length} ký tự")
        }
    }, confirmButton = {
        Button(onClick = { vm.pasteText(text, name); close() }, enabled = text.isNotBlank()) { Text("Dùng") }
    }, dismissButton = { TextButton(onClick = close) { Text("Hủy") } })
}

@Composable
private fun VoicePicker(vm: MangaVM) {
    val ctx = LocalContext.current
    var voices by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    var err by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        try {
            voices = vm.tts.voices(vm.prefs.str("tts_engine"))
            err = if (voices.isEmpty()) "Máy chưa có giọng tiếng Việt - vào Cài đặt → Tải giọng tiếng Việt." else ""
        } catch (e: Exception) {
            err = e.message ?: "Không mở được giọng đọc"
        }
        vm.refreshVieNeu()
    }
    var src by remember { mutableStateOf(vm.prefs.str("tts_src", "device")) }
    Choice("Nguồn giọng đọc", src, listOf("device" to "📱 Giọng có sẵn trong máy (offline)",
        "vieneu" to "🦜 VieNeu AI ngay trên máy + nhân bản giọng (offline)",
        "voicestudio" to "🎙 VoiceStudio trên máy tính")) { src = it; vm.prefs.set("tts_src", it) }
    when (src) {
        "vieneu" -> {
            if (!vm.vnReady) {
                Hint("Giọng AI tiếng Việt VieNeu-TTS chạy ngay trên điện thoại (~450 MB, tải một lần).")
                Button(onClick = vm::downloadVieNeu, enabled = !vm.busy) { Text("⬇ Tải giọng AI VieNeu") }
            }
            var v by remember { mutableStateOf(vm.prefs.str("vn_voice", "Minh Quân")) }
            if (vm.vnVoices.isNotEmpty()) Choice("Giọng VieNeu", v, vm.vnVoices.map { it to it }) { v = it; vm.prefs.set("vn_voice", it) }
            var fast by remember { mutableStateOf(vm.prefs.bool("vn_fast", false)) }
            Toggle("Đọc nhanh hơn (8 bước, hơi kém tự nhiên)", fast) { fast = it; vm.prefs.setBool("vn_fast", it) }
            var name by remember { mutableStateOf("") }
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let { u -> vm.cloneVoice(name, uri = u) } }
            Text("🎙 Nhân bản giọng", fontWeight = FontWeight.SemiBold)
            Hint("Chọn file ghi âm / video 8-15 giây có giọng người đó (nói rõ, yên tĩnh). Chỉ nhân bản giọng của bạn hoặc người đã đồng ý.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(name, { name = it }, Modifier.weight(1f), singleLine = true, label = { Text("Tên giọng mới") })
                OutlinedButton(onClick = { pick.launch("*/*") }, enabled = !vm.busy) { Text("📂 Chọn file") }
            }
            vm.vnVoices.filter { it in VieNeu.userVoices(ctx) }.forEach { n ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("🎙 $n", modifier = Modifier.weight(1f), fontSize = 14.sp)
                    TextButton(onClick = { vm.deleteVoice(n) }) { Text("Xóa") }
                }
            }
        }
        "voicestudio" -> {
            var vs by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
            var vsErr by remember { mutableStateOf("") }
            var vsVoice by remember { mutableStateOf(vm.prefs.str("vs_voice")) }
            LaunchedEffect(Unit) {
                try {
                    vs = VoiceStudio.voices(vm.prefs); vsErr = ""
                } catch (e: Exception) {
                    vsErr = e.message ?: "Không kết nối được VoiceStudio"
                }
            }
            if (vs.isNotEmpty()) Choice("Giọng VoiceStudio", vsVoice, vs) { vsVoice = it; vm.prefs.set("vs_voice", it) }
            if (vsErr.isNotEmpty()) Text("$vsErr (nhập địa chỉ ở Cài đặt)", color = Color(0xFFFF8A80), fontSize = 13.sp)
        }
        else -> {
            if (voices.isNotEmpty()) Choice("Giọng đọc (tiếng Việt có sẵn trong máy)", vm.voice, listOf("" to "Mặc định của máy") + voices) {
                vm.voice = it; vm.save("voice", it)
            }
            if (err.isNotEmpty()) Text(err, color = Color(0xFFFF8A80), fontSize = 13.sp)
        }
    }
    Hint("Tốc độ đọc: ${"%.2f".format(vm.rate)}x")
    Slider(vm.rate, { vm.rate = it; vm.prefs.setNum("rate", it) }, valueRange = 0.8f..1.6f)
    OutlinedButton(onClick = vm::previewVoice, enabled = !vm.busy) { Text("🔊 Nghe thử") }
}

// ==================================================================== thanh dưới
// ==================================================================== tab Kịch bản
@Composable
private fun ScriptTab(vm: MangaVM) {
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::renderOnly, enabled = !vm.busy && vm.segs.isNotEmpty(), modifier = Modifier.weight(1f)) {
                Text("🎬 Xuất lại từ kịch bản này")
            }
            OutlinedButton(onClick = { vm.resetScript(); vm.makeVideo() }, enabled = !vm.busy && vm.items.isNotEmpty()) { Text("🔄 Viết lại") }
        }
        if (vm.segs.isEmpty()) {
            Box(Modifier.padding(16.dp)) {
                Hint(if (vm.items.isEmpty()) "Chưa có kịch bản - bấm ⚡ LÀM VIDEO TÓM TẮT. Sau đó sửa chữ ở đây rồi Xuất lại."
                else "AI đã đọc ${vm.items.size} dòng diễn biến. Bấm ⚡ để viết kịch bản.")
            }
            return@Column
        }
        var t by remember(vm.recapTitle) { mutableStateOf(vm.recapTitle) }
        OutlinedTextField(t, { t = it; vm.recapTitle = it }, Modifier.fillMaxWidth().padding(horizontal = 12.dp), label = { Text("Tiêu đề") })
        if (vm.book?.manga == true) Box(Modifier.padding(horizontal = 12.dp)) {
            Hint("[#12] / [#12.3] cuối câu = câu đó chiếu trang dòng 12 / khung 3 của trang đó (khớp giọng với tranh, không được đọc lên). Sửa số để đổi tranh.")
        }
        LazyColumn(Modifier.fillMaxSize().imePadding()) {
            itemsIndexed(vm.segs, key = { i, s -> "$i-${s.start}" }) { i, s ->
                var text by remember(s) { mutableStateOf(s.text) }
                val a = s.start.toInt()
                val b = if (s.end > s.start) s.end.toInt() - 1 else a
                val where = vm.items.getOrNull(a)?.label?.let { la -> vm.items.getOrNull(b)?.label?.let { lb -> if (la == lb) la else "$la – $lb" } } ?: ""
                Column(Modifier.padding(horizontal = 12.dp, vertical = 4.dp)) {
                    Hint("Đoạn ${i + 1}${if (where.isNotEmpty()) " · $where" else ""}")
                    OutlinedTextField(text, { text = it; s.text = it }, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

// ==================================================================== tab Cài đặt
