@file:OptIn(ExperimentalMaterial3Api::class)

package com.vtgt.reviewphim

import android.content.Intent
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch

private val Muted = Color(0xFF9A9AB0)

@Composable
fun AppScreen(vm: MainVM) {
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("🎬 Làm video", "✏️ Kịch bản", "⚙️ Cài đặt")
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("ReviewPhim AI", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("v${BuildConfig.VERSION_NAME}", color = Muted, fontSize = 12.sp)
        }
        UpdateBanner(vm)
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
    vm.manualPrompt?.let { ManualDialog(it, vm) }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            content()
        }
    }
}

@Composable
private fun <T> Choice(label: String, value: T, options: List<Pair<T, String>>, onPick: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        Text(label, color = Muted, fontSize = 12.sp)
        Box {
            OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
                Text(options.firstOrNull { it.first == value }?.second ?: "Chọn...", modifier = Modifier.weight(1f))
                Text("▾")
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { (v, t) ->
                    DropdownMenuItem(text = { Text(t) }, onClick = { open = false; onPick(v) })
                }
            }
        }
    }
}

@Composable
private fun Hint(text: String) = Text(text, color = Muted, fontSize = 12.sp)

@Composable
private fun Toggle(text: String, value: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(value, onChange)
        Text(text, fontSize = 14.sp)
    }
}

// ==================================================================== tab Làm video
@Composable
private fun MakeTab(vm: MainVM) {
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let(vm::openVideo) }
    val pickSrt = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let(vm::loadSrt) }
    val pickBgm = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { it?.let { u -> vm.setBgm(u) } }
    var link by remember { mutableStateOf("") }
    val clip = LocalClipboardManager.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
        Section("1. Video gốc") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { pick.launch("video/*") }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("📂 Chọn video") }
            }
            OutlinedTextField(link, { link = it }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("hoặc dán link TikTok / YouTube / Douyin") })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { clip.getText()?.text?.let { link = it } }) { Text("📋 Dán") }
                Button(onClick = { vm.download(link) }, enabled = !vm.busy && link.isNotBlank(), modifier = Modifier.weight(1f)) {
                    Text("⬇ Tải video")
                }
            }
            Hint("Mẹo: trong TikTok / YouTube bấm Chia sẻ → ReviewPhim AI để tải luôn.")
            vm.info?.let { i ->
                Text(vm.title, fontWeight = FontWeight.SemiBold, maxLines = 2)
                Hint("${fmtTime(i.duration)} · ${i.width}x${i.height}${if (i.hasAudio) "" else " · không có tiếng"}" +
                    if (vm.lines.isNotEmpty()) " · lời gốc ${vm.lines.size} câu" else "")
            }
        }
        Section("2. Làm gì?") {
            Choice("Chế độ", vm.mode, listOf(
                "recap" to "🎬 Review / tóm tắt phim thành video ngắn",
                "translate" to "🌐 Dịch nguyên video sang tiếng Việt",
            )) { vm.mode = it; vm.save("mode", it) }
            if (vm.mode == "recap") {
                Choice("Độ dài video review", vm.targetSec, listOf(60 to "1 phút", 120 to "2 phút", 180 to "3 phút",
                    300 to "5 phút", 600 to "10 phút", 900 to "15 phút")) { vm.targetSec = it; vm.save("target", "$it") }
                Choice("Văn phong", vm.style, Prompts.STYLES.map { it.key to it.value }) { vm.style = it; vm.save("style", it) }
                Toggle("Ghép nhiều cảnh ngắn theo điểm cắt cảnh (bỏ cảnh đen)", vm.multiShot) {
                    vm.multiShot = it; vm.prefs.setBool("multi_shot", it)
                }
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
            } else {
                Choice("Xuất ra", vm.output, listOf("dub_sub" to "Thuyết minh + Vietsub", "sub" to "Chỉ Vietsub (giữ tiếng gốc)",
                    "dub" to "Chỉ thuyết minh")) { vm.output = it; vm.save("output", it) }
            }
        }
        Section("3. Lời gốc của video") {
            Choice("Lấy lời gốc bằng", vm.stt, listOf(
                "whisper" to "🎧 Nghe lời thoại (Groq - miễn phí, cần key)",
                "ocr" to "🔤 Đọc phụ đề cứng trên hình (không cần mạng)",
                "srt" to "📄 File phụ đề .srt",
            )) { vm.stt = it; vm.save("stt", it); vm.lines = emptyList() }
            if (vm.stt == "srt") OutlinedButton(onClick = { pickSrt.launch("*/*") }, enabled = !vm.busy) { Text("Chọn file .srt") }
            if (vm.stt == "ocr") Hint("Đọc chữ Trung + Latin. Kéo 2 thanh dưới để khung vàng ôm đúng dòng phụ đề.")
            BandEditor(vm)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(vm.cover, { vm.cover = it; vm.prefs.setBool("cover", it) })
                Text("Che phụ đề gốc (phụ đề Việt hiện đúng chỗ đó)")
            }
        }
        Section("4. Khung hình & giọng đọc") {
            Choice("Khung hình", vm.aspect, Aspect.entries.map { it to it.label }) { vm.aspect = it; vm.save("aspect", it.name) }
            Choice("Chất lượng", vm.quality, listOf(540 to "540p (nhanh nhất)", 720 to "720p HD", 1080 to "1080p Full HD")) {
                vm.quality = it; vm.save("quality", "$it")
            }
            VoicePicker(vm)
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun BandEditor(vm: MainVM) {
    val bmp = vm.preview ?: return
    Box(Modifier.fillMaxWidth().aspectRatio(bmp.width.toFloat() / bmp.height)) {
        Image(bmp.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.FillBounds)
        Canvas(Modifier.fillMaxSize()) {
            val top = vm.bandTop * size.height
            val bottom = vm.bandBottom * size.height
            drawRect(Color(0x55FFD54F), Offset(0f, top), Size(size.width, bottom - top))
            drawRect(Color(0xFFFFD54F), Offset(0f, top), Size(size.width, bottom - top), style = Stroke(4f))
        }
    }
    Hint("Mép trên vùng phụ đề: ${(vm.bandTop * 100).toInt()}%")
    Slider(vm.bandTop, { vm.bandTop = it.coerceAtMost(vm.bandBottom - 0.03f); vm.prefs.setNum("band_top", vm.bandTop) }, valueRange = 0f..1f)
    Hint("Mép dưới: ${(vm.bandBottom * 100).toInt()}%")
    Slider(vm.bandBottom, { vm.bandBottom = it.coerceAtLeast(vm.bandTop + 0.03f); vm.prefs.setNum("band_bottom", vm.bandBottom) }, valueRange = 0f..1f)
}

@Composable
private fun VoicePicker(vm: MainVM) {
    var voices by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    var err by remember { mutableStateOf("") }
    val engine = vm.prefs.str("tts_engine")
    LaunchedEffect(engine) {
        try {
            voices = vm.tts.voices(engine)
            err = if (voices.isEmpty()) "Máy chưa có giọng tiếng Việt - vào Cài đặt → Tải giọng tiếng Việt." else ""
        } catch (e: Exception) {
            err = e.message ?: "Không mở được giọng đọc"
        }
    }
    if (voices.isNotEmpty()) {
        Choice("Giọng đọc (tiếng Việt có sẵn trong máy)", vm.voice, listOf("" to "Mặc định của máy") + voices) {
            vm.voice = it; vm.save("voice", it)
        }
    }
    if (err.isNotEmpty()) Text(err, color = Color(0xFFFF8A80), fontSize = 13.sp)
    Hint("Tốc độ đọc: ${"%.2f".format(vm.rate)}x")
    Slider(vm.rate, { vm.rate = it; vm.prefs.setNum("rate", it) }, valueRange = 0.8f..1.6f)
    OutlinedButton(onClick = vm::previewVoice, enabled = !vm.busy) { Text("🔊 Nghe thử") }
}

// ==================================================================== thanh dưới: nút làm + tiến độ + log
@Composable
private fun BottomBar(vm: MainVM) {
    val ctx = LocalContext.current
    var showLog by remember { mutableStateOf(false) }
    Surface(color = MaterialTheme.colorScheme.surfaceVariant) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (vm.busy || vm.status.isNotEmpty()) {
                LinearProgressIndicator(progress = { vm.progress }, modifier = Modifier.fillMaxWidth())
                Text(vm.status, fontSize = 13.sp, maxLines = 2)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (vm.busy) {
                    Button(onClick = vm::cancel, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)),
                        modifier = Modifier.weight(1f)) { Text("⏹ Hủy") }
                } else {
                    Button(onClick = vm::makeVideo, enabled = vm.video != null, modifier = Modifier.weight(1f).height(52.dp)) {
                        Text(if (vm.mode == "recap") "⚡ LÀM VIDEO REVIEW" else "⚡ VIỆT HÓA VIDEO", fontWeight = FontWeight.Bold)
                    }
                }
                OutlinedButton(onClick = { showLog = !showLog }) { Text(if (showLog) "Ẩn log" else "Log") }
            }
            vm.result?.let { uri ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "video/mp4")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
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
private fun ScriptTab(vm: MainVM) {
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::renderOnly, enabled = !vm.busy && (vm.segs.isNotEmpty() || vm.lines.any { it.vi.isNotBlank() }),
                modifier = Modifier.weight(1f)) { Text("🎬 Xuất lại từ kịch bản này") }
            OutlinedButton(onClick = { vm.resetScript(); vm.makeVideo() }, enabled = !vm.busy && vm.lines.isNotEmpty()) {
                Text("🔄 AI viết lại")
            }
        }
        if (vm.mode == "recap") {
            if (vm.segs.isEmpty()) {
                Hint("Chưa có kịch bản - bấm ⚡ LÀM VIDEO REVIEW. Sau đó sửa chữ ở đây rồi Xuất lại.")
                return@Column
            }
            var t by remember(vm.recapTitle) { mutableStateOf(vm.recapTitle) }
            OutlinedTextField(t, { t = it; vm.recapTitle = it }, Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                label = { Text("Tiêu đề") })
            LazyColumn(Modifier.fillMaxSize().imePadding()) {
                itemsIndexed(vm.segs, key = { i, s -> "$i-${s.start}" }) { i, s ->
                    var text by remember(s) { mutableStateOf(s.text) }
                    Column(Modifier.padding(horizontal = 12.dp, vertical = 4.dp)) {
                        Hint("Đoạn ${i + 1} · cảnh từ ${fmtTime(s.start)}")
                        OutlinedTextField(text, { text = it; s.text = it }, Modifier.fillMaxWidth())
                    }
                }
            }
        } else {
            if (vm.lines.isEmpty()) {
                Hint("Chưa có lời gốc - bấm ⚡ VIỆT HÓA VIDEO.")
                return@Column
            }
            LazyColumn(Modifier.fillMaxSize().imePadding()) {
                itemsIndexed(vm.lines, key = { i, l -> "$i-${l.start}" }) { i, l ->
                    var text by remember(l) { mutableStateOf(l.vi) }
                    Column(Modifier.padding(horizontal = 12.dp, vertical = 4.dp)) {
                        Hint("${i + 1} · ${fmtTime(l.start)} · ${l.text}")
                        OutlinedTextField(text, { text = it; l.vi = it }, Modifier.fillMaxWidth(),
                            placeholder = { Text("(chưa dịch)") })
                    }
                }
            }
        }
    }
}

// ==================================================================== dán tay qua DeepSeek web
@Composable
private fun ManualDialog(prompt: String, vm: MainVM) {
    val clip = LocalClipboardManager.current
    val uri = LocalUriHandler.current
    var reply by remember(prompt) { mutableStateOf("") }
    var copied by remember(prompt) { mutableStateOf(false) }
    Dialog(onDismissRequest = {}, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().padding(12.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("🐋 Nhờ DeepSeek (miễn phí)", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text("1. Bấm Chép yêu cầu  2. Mở DeepSeek, dán vào ô chat, gửi  3. Bấm nút chép dưới câu trả lời của DeepSeek, " +
                    "quay lại đây bấm Dán & dùng. Nên dùng cùng 1 cuộc trò chuyện cho các phần của cùng video.", fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { clip.setText(AnnotatedString(prompt)); copied = true }, modifier = Modifier.weight(1f)) {
                        Text(if (copied) "✅ Đã chép" else "📋 Chép yêu cầu")
                    }
                    OutlinedButton(onClick = { uri.openUri("https://chat.deepseek.com") }, modifier = Modifier.weight(1f)) {
                        Text("🌐 Mở DeepSeek")
                    }
                }
                Hint("Yêu cầu (${prompt.length} ký tự): " + prompt.take(300).replace("\n", " ") + "...")
                OutlinedTextField(reply, { reply = it }, Modifier.fillMaxWidth().heightIn(min = 120.dp, max = 260.dp),
                    label = { Text("Câu trả lời của DeepSeek") })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { clip.getText()?.text?.let { reply = it } }, modifier = Modifier.weight(1f)) {
                        Text("📋 Dán")
                    }
                    Button(onClick = { vm.answerManual(reply) }, enabled = reply.contains("{") || reply.contains("|"),
                        modifier = Modifier.weight(1f)) { Text("✅ Dùng") }
                }
                TextButton(onClick = { vm.cancel() }) { Text("Hủy") }
            }
        }
    }
}

// ==================================================================== tab Cài đặt
@Composable
private fun SettingsTab(vm: MainVM) {
    val ctx = LocalContext.current
    val uri = LocalUriHandler.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 6.dp).imePadding()) {
        Section("AI viết kịch bản & dịch") {
            var ai by remember { mutableStateOf(vm.prefs.str("ai", "auto")) }
            Choice("Dùng", ai, listOf("auto" to "Tự động: AI có key (không có key thì dán tay)",
                "manual" to "🐋 Luôn dán tay qua DeepSeek web (miễn phí)")) { ai = it; vm.prefs.set("ai", it) }
            Hint("Key chỉ lưu trong máy này. Thứ tự dùng: DeepSeek → Gemini → OpenRouter → Groq → OpenAI; AI nào lỗi/hết tiền thì tự sang AI kế.")
            Ai.PROVS.forEach { p ->
                var k by remember { mutableStateOf(vm.prefs.key(p.id)) }
                OutlinedTextField(k, { k = it.trim(); vm.prefs.set("key_${p.id}", k) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("${p.name} key - ${p.note}") }, visualTransformation = PasswordVisualTransformation())
                TextButton(onClick = { uri.openUri(p.keyUrl) }) { Text("Lấy key ${p.name} ↗") }
            }
        }
        Section("Tên riêng & lời gốc") {
            var g by remember { mutableStateOf(vm.prefs.str("glossary")) }
            OutlinedTextField(g, { g = it; vm.prefs.set("glossary", it) }, Modifier.fillMaxWidth().heightIn(min = 90.dp),
                label = { Text("Tên riêng AI luôn dùng (mỗi dòng: gốc = Việt)") }, placeholder = { Text("一护 = Ichigo\n林动 = Lâm Động") })
            var lang by remember { mutableStateOf(vm.prefs.str("src_lang", "")) }
            Choice("Ngôn ngữ lời thoại (khi nghe bằng Groq)", lang, listOf("" to "Tự nhận", "zh" to "Tiếng Trung", "en" to "Tiếng Anh",
                "ja" to "Tiếng Nhật", "ko" to "Tiếng Hàn", "th" to "Tiếng Thái")) { lang = it; vm.prefs.set("src_lang", it) }
        }
        Section("Âm thanh") {
            var bg by remember { mutableStateOf(vm.prefs.num("bg_vol", 0.12f)) }
            Hint("Tiếng phim nền khi review: ${(bg * 100).toInt()}%")
            Slider(bg, { bg = it; vm.prefs.setNum("bg_vol", it) }, valueRange = 0f..0.5f)
            var ov by remember { mutableStateOf(vm.prefs.num("orig_vol", 0.35f)) }
            Hint("Tiếng gốc khi thuyết minh: ${(ov * 100).toInt()}% (tự nhỏ thêm lúc có giọng đọc)")
            Slider(ov, { ov = it; vm.prefs.setNum("orig_vol", it) }, valueRange = 0f..1f)
        }
        Section("Giọng đọc của máy") {
            Hint("App dùng giọng tiếng Việt có sẵn trong máy (Google Speech Services hay Samsung TTS), miễn phí, đọc được không cần mạng.")
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
            OutlinedButton(onClick = {
                runCatching { ctx.startActivity(Intent("com.android.settings.TTS_SETTINGS").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            }) { Text("Mở cài đặt giọng đọc của máy") }
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
private fun UpdateBanner(vm: MainVM) {
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
                    val f = vm.updater.download(r) { p = it }
                    vm.updater.install(f)
                } catch (e: Exception) {
                    vm.log("Cập nhật lỗi: ${e.message}")
                } finally {
                    p = -1f
                }
            }
        }, enabled = p < 0) { Text("CẬP NHẬT", color = Color.White, fontWeight = FontWeight.Bold) }
    }
}
