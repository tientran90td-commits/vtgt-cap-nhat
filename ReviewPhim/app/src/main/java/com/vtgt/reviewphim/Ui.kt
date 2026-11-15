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
    vm.ask?.let { ManualDialog(it, vm) }
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
            vm.dlHelp?.let { bad ->
                val uh = LocalUriHandler.current
                Surface(color = Color(0x33FFB74D), shape = RoundedCornerShape(10.dp)) {
                    Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("🖐 Tải tay: link này app không tải được (trang chặn / cần đăng nhập).", fontWeight = FontWeight.SemiBold)
                        Text("1. Bấm Mở link → dùng nút Lưu / Tải video của app gốc (TikTok, Douyin...) hoặc trang tải video " +
                            "bạn hay dùng.\n2. Quay lại đây bấm 📂 Chọn video, chọn file vừa tải.", fontSize = 13.sp)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { runCatching { uh.openUri(bad) } }) { Text("🌐 Mở link") }
                            Button(onClick = { vm.dlHelp = null; pick.launch("video/*") }) { Text("📂 Chọn video") }
                        }
                    }
                }
            }
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
                Toggle("👁 AI xem hình cả video (kể cả cảnh hành động không có thoại)", vm.watch) {
                    vm.watch = it; vm.prefs.setBool("watch", it)
                }
                if (vm.watch) Hint("App chụp khung hình suốt video, ghép ảnh có mốc thời gian để AI (Gemini...) xem và tả lại diễn biến. " +
                    "Có key Gemini thì tự làm; không thì 🖐 gửi ảnh cho app Gemini rồi dán câu trả lời.")
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
        Section("Tên nhân vật đúng ngay từ đầu") {
            var q by remember { mutableStateOf("") }
            Hint("Gõ tên anime / phim (tiếng Anh hoặc Nhật, vd: Bleach) → app lấy danh sách nhân vật chính thức từ MyAnimeList " +
                "để AI gọi đúng tên. Tên AI đã dùng cũng được nhớ lại cho các tập sau.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(q, { q = it }, Modifier.weight(1f), singleLine = true, label = { Text("Tên anime / phim") })
                Button(onClick = { vm.findCast(q) }, enabled = !vm.busy && q.isNotBlank()) { Text("🔍") }
            }
            if (vm.castInfo.isNotBlank()) Row(verticalAlignment = Alignment.CenterVertically) {
                Text("📚 ${vm.castInfo}", modifier = Modifier.weight(1f), fontSize = 13.sp)
                TextButton(onClick = vm::clearCast) { Text("✖") }
            }
        }
        Section("3. Lời gốc của video") {
            Choice("Lấy lời gốc bằng", vm.stt, listOf(
                "whisper" to "🎧 Nghe lời thoại (Groq API; lỗi / không key → 🖐 nhờ Gemini)",
                "gemini" to "🖐 Nhờ Gemini nghe (làm tay, không cần key)",
                "ocr" to "🔤 Đọc phụ đề cứng trên hình (không cần mạng)",
                "srt" to "📄 File phụ đề (.srt / .ass / .vtt)",
            )) { vm.stt = it; vm.save("stt", it); vm.lines = emptyList() }
            if (vm.stt == "srt") OutlinedButton(onClick = { pickSrt.launch("*/*") }, enabled = !vm.busy) { Text("Chọn file phụ đề") }
            if (vm.stt == "ocr") Hint("Đọc chữ Trung + Latin. Kéo 2 thanh dưới để khung vàng ôm đúng dòng phụ đề.")
            BandEditor(vm)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(vm.cover, { vm.cover = it; vm.prefs.setBool("cover", it) })
                Text("Che phụ đề gốc (phụ đề Việt hiện đúng chỗ đó)")
            }
        }
        Section("Các bước sẽ làm") {
            vm.plan().forEachIndexed { k, (t, manual) ->
                Text("${k + 1}. $t", fontSize = 14.sp, color = if (manual) Color(0xFFFFD54F) else MaterialTheme.colorScheme.onSurface)
            }
            Hint("🖐 = bước bạn làm tay: app chép sẵn yêu cầu, bạn dán sang DeepSeek / Gemini rồi dán câu trả lời lại. " +
                "Không cần API, không lo lỗi hết tiền / quá tải.")
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
    var src by remember { mutableStateOf(vm.prefs.str("tts_src", "device")) }
    Choice("Nguồn giọng đọc", src, listOf("device" to "📱 Giọng có sẵn trong máy (offline)",
        "vieneu" to "🦜 VieNeu AI ngay trên máy + nhân bản giọng (offline)",
        "voicestudio" to "🎙 VoiceStudio trên máy tính (giọng AI / giọng nhân bản)")) { src = it; vm.prefs.set("tts_src", it) }
    if (src == "vieneu") {
        VieNeuPanel(vm)
    } else if (src == "voicestudio") {
        var vsVoices by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
        var vsErr by remember { mutableStateOf("") }
        var vsVoice by remember { mutableStateOf(vm.prefs.str("vs_voice")) }
        LaunchedEffect(Unit) {
            try {
                vsVoices = VoiceStudio.voices(vm.prefs); vsErr = ""
            } catch (e: Exception) {
                vsErr = e.message ?: "Không kết nối được VoiceStudio"
            }
        }
        if (vsVoices.isNotEmpty()) Choice("Giọng VoiceStudio", vsVoice, vsVoices) { vsVoice = it; vm.prefs.set("vs_voice", it) }
        if (vsErr.isNotEmpty()) Text("$vsErr (nhập địa chỉ ở Cài đặt → VoiceStudio)", color = Color(0xFFFF8A80), fontSize = 13.sp)
        Hint("Không kết nối được thì app tự dùng giọng có sẵn của máy.")
    } else if (voices.isNotEmpty()) {
        Choice("Giọng đọc (tiếng Việt có sẵn trong máy)", vm.voice, listOf("" to "Mặc định của máy") + voices) {
            vm.voice = it; vm.save("voice", it)
        }
    }
    if (err.isNotEmpty() && src == "device") Text(err, color = Color(0xFFFF8A80), fontSize = 13.sp)
    Hint("Tốc độ đọc: ${"%.2f".format(vm.rate)}x")
    Slider(vm.rate, { vm.rate = it; vm.prefs.setNum("rate", it) }, valueRange = 0.8f..1.6f)
    OutlinedButton(onClick = vm::previewVoice, enabled = !vm.busy) { Text("🔊 Nghe thử") }
}

@Composable
private fun VieNeuPanel(vm: MainVM) {
    val ctx = LocalContext.current
    LaunchedEffect(Unit) { vm.refreshVieNeu() }
    var voice by remember { mutableStateOf(vm.prefs.str("vn_voice", "Minh Quân")) }
    if (!vm.vnReady) {
        Hint("Giọng AI tiếng Việt VieNeu-TTS chạy ngay trên điện thoại, không cần mạng sau khi tải (~450 MB, một lần).")
        Button(onClick = vm::downloadVieNeu, enabled = !vm.busy) { Text("⬇ Tải giọng AI VieNeu") }
    }
    if (vm.vnVoices.isNotEmpty()) {
        Choice("Giọng VieNeu", voice, vm.vnVoices.map { it to it }) { voice = it; vm.prefs.set("vn_voice", it) }
    }
    var fast by remember { mutableStateOf(vm.prefs.bool("vn_fast", false)) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(fast, { fast = it; vm.prefs.setBool("vn_fast", it) })
        Text("Đọc nhanh hơn (8 bước, hơi kém tự nhiên)", fontSize = 14.sp)
    }
    // ---- nhân bản giọng
    var name by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    var secs by remember { mutableIntStateOf(0) }
    val rec = remember { mutableStateOf<android.media.MediaRecorder?>(null) }
    val recFile = remember { java.io.File(ctx.cacheDir, "giong_mau.m4a") }
    val pickAudio = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) {
        it?.let { u -> vm.cloneVoice(name, uri = u) }
    }
    val askMic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(recording) {
        secs = 0
        while (recording) {
            kotlinx.coroutines.delay(1000)
            secs++
            if (secs >= 20) recording = false.also { rec.value?.let { r -> runCatching { r.stop() }; r.release() }; rec.value = null }
        }
    }
    Text("🎙 Nhân bản giọng", fontWeight = FontWeight.SemiBold)
    Hint("Ghi âm 8-15 giây bạn đọc một đoạn bất kỳ (chỗ yên tĩnh, nói rõ), hoặc chọn file có giọng người đó. " +
        "Chỉ nhân bản giọng của bạn hoặc người đã đồng ý.")
    OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Tên giọng mới") })
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (!recording) {
            Button(onClick = {
                if (androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.RECORD_AUDIO) !=
                    android.content.pm.PackageManager.PERMISSION_GRANTED) {
                    askMic.launch(android.Manifest.permission.RECORD_AUDIO)
                    return@Button
                }
                val r = (if (android.os.Build.VERSION.SDK_INT >= 31) android.media.MediaRecorder(ctx)
                else @Suppress("DEPRECATION") android.media.MediaRecorder()).apply {
                    setAudioSource(android.media.MediaRecorder.AudioSource.MIC)
                    setOutputFormat(android.media.MediaRecorder.OutputFormat.MPEG_4)
                    setAudioEncoder(android.media.MediaRecorder.AudioEncoder.AAC)
                    setAudioSamplingRate(44100)
                    setAudioEncodingBitRate(128000)
                    setOutputFile(recFile.path)
                    prepare()
                    start()
                }
                rec.value = r
                recording = true
            }, enabled = !vm.busy, modifier = Modifier.weight(1f)) { Text("⏺ Ghi âm") }
        } else {
            Button(onClick = {
                rec.value?.let { r -> runCatching { r.stop() }; r.release() }
                rec.value = null
                recording = false
                vm.cloneVoice(name, file = recFile)
            }, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)), modifier = Modifier.weight(1f)) {
                Text("⏹ Dừng & nhân bản (${secs}s)")
            }
        }
        OutlinedButton(onClick = { pickAudio.launch("audio/*") }, enabled = !vm.busy && !recording, modifier = Modifier.weight(1f)) {
            Text("📂 Chọn file")
        }
    }
    val mine = vm.vnVoices.filter { it in VieNeu.userVoices(ctx) }
    mine.forEach { n ->
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("🎙 $n", modifier = Modifier.weight(1f), fontSize = 14.sp)
            TextButton(onClick = { vm.deleteVoice(n) }) { Text("Xóa") }
        }
    }
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
                if (vm.busy && vm.apiWaiting) {
                    Button(onClick = vm::skipToManual, modifier = Modifier.weight(1f)) { Text("🖐 Làm tay ngay") }
                }
                if (vm.busy) {
                    Button(onClick = vm::cancel, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)),
                        modifier = Modifier.weight(if (vm.apiWaiting) 0.6f else 1f)) { Text("⏹ Hủy") }
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
private fun ManualDialog(a: ManualAsk, vm: MainVM) {
    val clip = LocalClipboardManager.current
    val ctx = LocalContext.current
    val gemini = a.target == "gemini"
    val who = if (gemini) "Gemini" else "DeepSeek"
    var reply by remember(a) { mutableStateOf("") }
    var copied by remember(a) { mutableStateOf(false) }
    fun looksLikeAnswer(t: String) = t != a.prompt && (t.contains("{") || t.contains("-->") || Regex("\\d+:\\d{2}").containsMatchIn(t))
    // quay lại app sau khi chép câu trả lời: tự dán
    val owner = androidx.compose.ui.platform.LocalLifecycleOwner.current
    androidx.compose.runtime.DisposableEffect(owner, a) {
        val obs = androidx.lifecycle.LifecycleEventObserver { _, ev ->
            if (ev == androidx.lifecycle.Lifecycle.Event.ON_RESUME && reply.isBlank()) {
                clip.getText()?.text?.let { if (looksLikeAnswer(it)) reply = it }
            }
        }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }
    fun openApp() {
        val pkg = if (gemini) "com.google.android.apps.bard" else "com.deepseek.chat"
        val web = if (gemini) "https://gemini.google.com/app" else "https://chat.deepseek.com"
        val i = ctx.packageManager.getLaunchIntentForPackage(pkg)
            ?: Intent(Intent.ACTION_VIEW, android.net.Uri.parse(web))
        ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    Dialog(onDismissRequest = {}, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().padding(12.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("🖐 Làm tay: ${a.step}", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text(if (gemini) "1. Bấm Chép yêu cầu.  2. Bấm 📤 Gửi cho Gemini (hoặc mở Gemini, đính kèm " +
                    "\"${a.fileName}\" trong Download/ReviewPhim), dán yêu cầu, gửi.  3. Chép câu trả lời, quay lại đây - app tự dán, bấm Dùng."
                else "1. Bấm Chép yêu cầu.  2. Mở DeepSeek, dán vào ô chat, gửi (nên dùng chung 1 cuộc trò chuyện cho các phần của " +
                    "cùng video).  3. Bấm nút chép dưới câu trả lời, quay lại đây - app tự dán, bấm Dùng.", fontSize = 13.sp)
                if (a.note.isNotBlank()) Hint(a.note)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { clip.setText(AnnotatedString(a.prompt)); copied = true }, modifier = Modifier.weight(1f)) {
                        Text(if (copied) "✅ Đã chép" else "📋 Chép yêu cầu")
                    }
                    OutlinedButton(onClick = { openApp() }, modifier = Modifier.weight(1f)) { Text("🌐 Mở $who") }
                }
                if (a.files.isNotEmpty()) {
                    OutlinedButton(onClick = {
                        clip.setText(AnnotatedString(a.prompt)); copied = true
                        val send = (if (a.files.size == 1) Intent(Intent.ACTION_SEND).putExtra(Intent.EXTRA_STREAM, a.files[0])
                        else Intent(Intent.ACTION_SEND_MULTIPLE).putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(a.files)))
                            .setType(a.mime).putExtra(Intent.EXTRA_TEXT, a.prompt).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        val g = Intent(send).setPackage("com.google.android.apps.bard")
                        ctx.startActivity((if (g.resolveActivity(ctx.packageManager) != null) g
                        else Intent.createChooser(send, "Gửi cho Gemini")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (a.mime.startsWith("image")) "📤 Gửi ${a.files.size} ảnh khung hình cho Gemini (kèm yêu cầu)"
                        else "📤 Gửi file âm thanh cho Gemini (kèm yêu cầu)")
                    }
                }
                Hint("Yêu cầu (${a.prompt.length} ký tự): " + a.prompt.take(240).replace("\n", " ") + "...")
                OutlinedTextField(reply, { reply = it }, Modifier.fillMaxWidth().heightIn(min = 120.dp, max = 260.dp),
                    label = { Text("Câu trả lời của $who") })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { clip.getText()?.text?.let { reply = it } }, modifier = Modifier.weight(1f)) {
                        Text("📋 Dán")
                    }
                    Button(onClick = { vm.answerManual(reply) }, enabled = looksLikeAnswer(reply) || reply.contains("|"),
                        modifier = Modifier.weight(1f)) { Text("✅ Dùng") }
                }
                Row {
                    TextButton(onClick = { vm.cancel() }) { Text("Hủy") }
                    Spacer(Modifier.weight(1f))
                    if (a.canApi) TextButton(onClick = { vm.answerManual(RETRY_API) }) { Text("⚡ Thử lại API") }
                }
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
            Choice("Dùng", ai, listOf("manual" to "🖐 Làm tay: chép / dán sang DeepSeek (miễn phí, không lỗi API)",
                "auto" to "⚡ API tự động (lỗi thì tự chuyển sang làm tay)")) { ai = it; vm.prefs.set("ai", it) }
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
        Section("🎙 VoiceStudio trên máy tính (tùy chọn)") {
            Hint("Giọng AI chất lượng cao / giọng nhân bản của bạn từ VoiceStudio (github.com/debpalash/VoiceStudio) chạy " +
                "trên máy tính cùng wifi. Trên máy tính: mở VoiceStudio → bật Network share → nhập địa chỉ IP và mã PIN ở đây. " +
                "Rồi ở mục Giọng đọc chọn nguồn 'VoiceStudio'.")
            var u by remember { mutableStateOf(vm.prefs.str("vs_url")) }
            OutlinedTextField(u, { u = it.trim(); vm.prefs.set("vs_url", u) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Địa chỉ máy tính (vd 192.168.1.10 hoặc 192.168.1.10:3900)") })
            var pin by remember { mutableStateOf(vm.prefs.str("vs_pin")) }
            OutlinedTextField(pin, { pin = it.trim(); vm.prefs.set("vs_pin", pin) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Mã PIN Network share (nếu có)") })
            var key by remember { mutableStateOf(vm.prefs.str("vs_key")) }
            OutlinedTextField(key, { key = it.trim(); vm.prefs.set("vs_key", key) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("API key (nếu máy chủ đặt OMNIVOICE_API_KEY)") }, visualTransformation = PasswordVisualTransformation())
            var model by remember { mutableStateOf(vm.prefs.str("vs_model", "omnivoice")) }
            OutlinedTextField(model, { model = it.trim(); vm.prefs.set("vs_model", model) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Model (mặc định omnivoice)") })
            val scope = rememberCoroutineScope()
            var msg by remember { mutableStateOf("") }
            OutlinedButton(onClick = {
                scope.launch {
                    msg = "Đang kết nối..."
                    msg = try {
                        val vs = VoiceStudio.voices(vm.prefs)
                        "✅ Kết nối được - ${vs.size} giọng: " + vs.take(6).joinToString(", ") { it.second }
                    } catch (e: Exception) {
                        "❌ ${e.message}"
                    }
                }
            }) { Text("🔌 Kiểm tra kết nối") }
            if (msg.isNotEmpty()) Hint(msg)
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
