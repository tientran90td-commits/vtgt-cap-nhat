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
import com.vtgt.reviewphim.VieNeu
import com.vtgt.reviewphim.VoiceStudio
import kotlinx.coroutines.launch

@Composable
fun MangaScreen(vm: MangaVM, embedded: Boolean = false) {
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("📚 Làm video", "✏️ Kịch bản", "⚙️ Cài đặt")
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        if (!embedded) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("MangaRecap AI", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(8.dp))
                Text("v${BuildConfig.VERSION_NAME}", color = Muted, fontSize = 12.sp)
            }
            UpdateBanner(vm)
        }
        TabRow(selectedTabIndex = tab) {
            tabs.forEachIndexed { i, t -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }) }
        }
        Box(Modifier.weight(1f)) {
            when (tab) {
                0 -> MakeTab(vm)
                1 -> ScriptTab(vm)
                else -> SettingsTab(vm)
            }
        }
        BottomBar(vm)
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
        Section("1. Truyện") {
            Hint("Truyện tranh (manga / manhwa / manhua): dán link chương, chọn ảnh các trang, cả thư mục, hoặc file CBZ / ZIP / PDF. " +
                "Light novel / tiểu thuyết: dán link chương, file EPUB / TXT hoặc dán chữ. Trang manhwa dài được tự nối / cắt theo khung tranh.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { pickImages.launch("image/*") }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("🖼 Ảnh trang") }
                Button(onClick = { pickTree.launch(null) }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("📁 Thư mục") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { pickFile.launch(arrayOf("*/*")) }, enabled = !vm.busy, modifier = Modifier.weight(1f)) {
                    Text("📦 CBZ/PDF/EPUB/TXT")
                }
                OutlinedButton(onClick = { paste = true }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("📋 Dán chữ") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { linkBox = true }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("🔗 Lấy từ link") }
                OutlinedButton(onClick = { browser = "" }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("🌐 Trình duyệt") }
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
        Section("Tên nhân vật đúng ngay từ đầu") {
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
        Section("2. Video") {
            Choice("Độ dài video", vm.targetSec, listOf(60 to "1 phút", 180 to "3 phút", 300 to "5 phút", 600 to "10 phút",
                900 to "15 phút", 1200 to "20 phút", 1800 to "30 phút")) { vm.targetSec = it; vm.save("m_target", "$it") }
            Choice("Văn phong", vm.style, Prompts.STYLES.map { it.key to it.value }) { vm.style = it; vm.save("m_style", it) }
            Choice("Khung hình", vm.vertical, listOf(true to "Dọc 9:16 (TikTok, Shorts, Reels)", false to "Ngang 16:9 (YouTube)")) {
                vm.vertical = it; vm.prefs.setBool("m_vertical", it)
            }
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
        Section("3. Giọng đọc") { VoicePicker(vm) }
        Section("Các bước sẽ làm") {
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
@Composable
private fun BottomBar(vm: MangaVM) {
    val ctx = LocalContext.current
    var showLog by remember { mutableStateOf(false) }
    Surface(color = MaterialTheme.colorScheme.surfaceVariant) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (vm.busy || vm.status.isNotEmpty()) {
                LinearProgressIndicator(progress = { vm.progress }, modifier = Modifier.fillMaxWidth())
                Text(vm.status, fontSize = 13.sp, maxLines = 2)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (vm.busy && vm.apiWaiting) Button(onClick = vm::skipToManual, modifier = Modifier.weight(1f)) { Text("🖐 Làm tay ngay") }
                if (vm.busy) {
                    Button(onClick = vm::cancel, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)),
                        modifier = Modifier.weight(if (vm.apiWaiting) 0.6f else 1f)) { Text("⏹ Hủy") }
                } else {
                    Button(onClick = vm::makeVideo, enabled = vm.book != null, modifier = Modifier.weight(1f).height(52.dp)) {
                        Text("⚡ LÀM VIDEO TÓM TẮT", fontWeight = FontWeight.Bold)
                    }
                }
                OutlinedButton(onClick = { showLog = !showLog }) { Text(if (showLog) "Ẩn log" else "Log") }
            }
            vm.result?.let { uri ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "video/mp4").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                    }, modifier = Modifier.weight(1f)) { Text("▶ Xem video") }
                    OutlinedButton(onClick = {
                        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("video/mp4")
                            .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Chia sẻ video"))
                    }, modifier = Modifier.weight(1f)) { Text("📤 Chia sẻ") }
                }
            }
            if (showLog) {
                val st = rememberLazyListState()
                LaunchedEffect(vm.logs.size) { if (vm.logs.isNotEmpty()) st.animateScrollToItem(vm.logs.size - 1) }
                SelectionContainer {
                    LazyColumn(Modifier.fillMaxWidth().heightIn(max = 220.dp), state = st) {
                        itemsIndexed(vm.logs) { _, l -> Text(l, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = Muted) }
                    }
                }
            }
        }
    }
}

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
@Composable
private fun SettingsTab(vm: MangaVM) {
    val ctx = LocalContext.current
    val uri = LocalUriHandler.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 6.dp).imePadding()) {
        Section("AI đọc truyện & viết kịch bản") {
            var ai by remember { mutableStateOf(vm.prefs.str("ai", "auto")) }
            Choice("Dùng", ai, listOf("manual" to "🖐 Làm tay: gửi sang Gemini / DeepSeek (miễn phí)",
                "auto" to "⚡ API tự động (lỗi thì tự chuyển sang làm tay)")) { ai = it; vm.prefs.set("ai", it) }
            Hint("Đọc tranh cần AI nhìn được ảnh: Gemini (miễn phí, khuyên dùng), OpenRouter, Groq hoặc OpenAI. " +
                "DeepSeek chỉ dùng cho tóm tắt chữ / viết kịch bản. Key chỉ lưu trong máy này.")
            Ai.PROVS.forEach { p ->
                var k by remember { mutableStateOf(vm.prefs.str("key_${p.id}")) }
                OutlinedTextField(k, { k = it.trim(); vm.prefs.set("key_${p.id}", k) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("${p.name} key - ${p.note}") }, visualTransformation = PasswordVisualTransformation())
                TextButton(onClick = { uri.openUri(p.keyUrl) }) { Text("Lấy key ${p.name} ↗") }
            }
            Hint("Mỗi AI nhập được nhiều key, cách nhau dấu phẩy: key này quá tải / hết lượt thì app tự đổi sang key kế.")
            com.vtgt.reviewphim.CustomAiSection(vm.prefs)
        }
        Section("Tên riêng") {
            var g by remember { mutableStateOf(vm.prefs.str("glossary")) }
            OutlinedTextField(g, { g = it; vm.prefs.set("glossary", it) }, Modifier.fillMaxWidth().heightIn(min = 90.dp),
                label = { Text("Tên riêng AI luôn dùng (mỗi dòng: gốc = Việt)") }, placeholder = { Text("성진우 = Sung Jin-Woo\n林动 = Lâm Động") })
            Hint("Tên AI đã dùng được tự nhớ thêm vào đây cho các tập sau.")
        }
        Section("🎙 VoiceStudio trên máy tính (tùy chọn)") {
            var u by remember { mutableStateOf(vm.prefs.str("vs_url")) }
            OutlinedTextField(u, { u = it.trim(); vm.prefs.set("vs_url", u) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Địa chỉ máy tính (vd 192.168.1.10:3900)") })
            var pin by remember { mutableStateOf(vm.prefs.str("vs_pin")) }
            OutlinedTextField(pin, { pin = it.trim(); vm.prefs.set("vs_pin", pin) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Mã PIN Network share (nếu có)") })
        }
        Section("Giọng đọc của máy") {
            var engines by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
            LaunchedEffect(Unit) { engines = try { vm.tts.engines() } catch (e: Exception) { emptyList() } }
            var eng by remember { mutableStateOf(vm.prefs.str("tts_engine")) }
            if (engines.isNotEmpty()) Choice("Bộ đọc", eng, listOf("" to "Mặc định của máy") + engines) {
                eng = it; vm.prefs.set("tts_engine", it); vm.voice = ""; vm.save("voice", "")
            }
            OutlinedButton(onClick = {
                runCatching { ctx.startActivity(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                    .onFailure { uri.openUri("https://play.google.com/store/apps/details?id=com.google.android.tts") }
            }) { Text("⬇ Tải giọng tiếng Việt") }
        }
        Section("Cập nhật") {
            val scope = rememberCoroutineScope()
            var msg by remember { mutableStateOf("") }
            Button(onClick = {
                scope.launch {
                    msg = "Đang kiểm tra..."
                    val r = runCatching { vm.updater.check() }.getOrNull()
                    vm.update = r
                    msg = when {
                        r == null -> "Không kiểm tra được (cần mạng)."
                        vm.updater.newer(r) -> "Có bản mới: ${r.name} - bấm nút Cập nhật ở trên cùng."
                        else -> "Đang dùng bản mới nhất."
                    }
                }
            }) { Text("🔄 Kiểm tra bản mới") }
            if (msg.isNotEmpty()) Hint(msg)
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun UpdateBanner(vm: MangaVM) {
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { vm.update = runCatching { vm.updater.check() }.getOrNull() }
    val r = vm.update
    if (!vm.updater.newer(r) || r == null) return
    var p by remember { mutableStateOf(-1f) }
    Row(Modifier.fillMaxWidth().background(Color(0xFF2E7D32)).padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(if (p < 0) "Có bản mới ${r.name}" else "Đang tải ${(p * 100).toInt()}%", modifier = Modifier.weight(1f))
        TextButton(onClick = {
            scope.launch {
                try {
                    p = 0f
                    vm.updater.install(vm.updater.download(r) { p = it })
                } catch (e: Exception) {
                    vm.log("Cập nhật lỗi: ${e.message}")
                } finally {
                    p = -1f
                }
            }
        }, enabled = p < 0) { Text("Cập nhật", color = Color.White) }
    }
}
