@file:OptIn(ExperimentalMaterial3Api::class)

package com.vtgt.reviewphim

import android.content.Intent
import android.net.Uri
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.clickable
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloat
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

/**
 * Một bước bạn làm tay thay cho gọi API: chép yêu cầu -> dán sang AI (DeepSeek / Gemini) -> dán câu trả lời lại.
 * target: "deepseek" | "gemini"; file: file cần gửi kèm (âm thanh cho Gemini nghe).
 */
data class ManualAsk(val step: String, val target: String, val prompt: String, val note: String = "",
                     val files: List<Uri> = emptyList(), val fileName: String = "", val canApi: Boolean = false,
                     val mime: String = "audio/mpeg")

const val RETRY_API = "\u0000api"


val Muted = Color(0xFF9A9AB0)

@Composable
fun Section(title: String, step: Int = 0, done: Boolean = false, content: @Composable () -> Unit) {
    // hiện dần + trượt lên khi mở màn hình (kiểu flutter_animate fadeIn().slideY())
    val shown = remember { androidx.compose.animation.core.MutableTransitionState(false).apply { targetState = true } }
    androidx.compose.animation.AnimatedVisibility(shown,
        enter = androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(380)) +
            androidx.compose.animation.slideInVertically(androidx.compose.animation.core.tween(380)) { it / 6 }) {
        Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(14.dp).animateContentSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (step > 0) {
                        val bg by androidx.compose.animation.animateColorAsState(
                            if (done) Color(0xFF2E7D32) else MaterialTheme.colorScheme.primary, label = "step")
                        Box(Modifier.size(28.dp).background(bg, CircleShape), contentAlignment = Alignment.Center) {
                            Text(if (done) "✓" else "$step", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        }
                        Spacer(Modifier.width(10.dp))
                    }
                    Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
                content()
            }
        }
    }
}

/** Tùy chọn ít dùng: đóng sẵn, bấm để mở / đóng (mở rộng mượt). */
@Composable
fun Advanced(title: String = "⚙ Tùy chọn thêm", content: @Composable () -> Unit) {
    var open by androidx.compose.runtime.saveable.rememberSaveable(title) { mutableStateOf(false) }
    val rot by androidx.compose.animation.core.animateFloatAsState(if (open) 180f else 0f, label = "adv")
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable { open = !open }
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)).padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = MaterialTheme.colorScheme.primary, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f))
            Text("▾", color = MaterialTheme.colorScheme.primary, modifier = Modifier.rotate(rot))
        }
        androidx.compose.animation.AnimatedVisibility(open,
            enter = androidx.compose.animation.expandVertically() + androidx.compose.animation.fadeIn(),
            exit = androidx.compose.animation.shrinkVertically() + androidx.compose.animation.fadeOut()) {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }
        }
    }
}

/**
 * Bảng tiến trình dưới cùng (dùng chung 3 chế độ): thanh tiến độ chạy mượt, trạng thái nhấp nháy khi đang làm,
 * nút chính / Dừng / Làm tay ngay, kết quả trượt vào khi xong, log ẩn sau "Chi tiết".
 */
@Composable
fun ProgressPanel(busy: Boolean, status: String, progress: Float, apiWaiting: Boolean, logs: List<String>, result: Uri?,
                  mainLabel: String, mainEnabled: Boolean, onMain: () -> Unit, onCancel: () -> Unit, onManual: () -> Unit,
                  eta: String = "", stopLabel: String = "⏹ Dừng") {
    val ctx = LocalContext.current
    var showLog by remember { mutableStateOf(false) }
    val p by androidx.compose.animation.core.animateFloatAsState(progress.coerceIn(0f, 1f),
        androidx.compose.animation.core.tween(600), label = "prog")
    val pulse = androidx.compose.animation.core.rememberInfiniteTransition(label = "pulse")
    val glow by pulse.animateFloat(0.45f, 1f, androidx.compose.animation.core.infiniteRepeatable(
        androidx.compose.animation.core.tween(800), androidx.compose.animation.core.RepeatMode.Reverse), label = "glow")
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        tonalElevation = 3.dp) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp).animateContentSize(),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (busy || status.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (busy) Text("●", color = MaterialTheme.colorScheme.primary.copy(alpha = glow), fontSize = 14.sp)
                    if (busy) Spacer(Modifier.width(6.dp))
                    Text(status, fontSize = 13.sp, maxLines = 2, modifier = Modifier.weight(1f))
                    if (busy) Text("${(p * 100).toInt()}%", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary)
                }
                LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)))
                if (eta.isNotBlank()) Hint("⏱ $eta")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.animation.AnimatedVisibility(busy && apiWaiting) {
                    Button(onClick = onManual) { Text("🖐 Làm tay ngay") }
                }
                if (busy) {
                    Button(onClick = onCancel, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)),
                        modifier = Modifier.weight(1f).height(50.dp)) { Text(stopLabel) }
                } else {
                    Button(onClick = onMain, enabled = mainEnabled, shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.weight(1f).height(52.dp)) { Text(mainLabel, fontWeight = FontWeight.Bold) }
                }
                TextButton(onClick = { showLog = !showLog }) { Text(if (showLog) "Ẩn" else "Chi tiết", fontSize = 13.sp) }
            }
            androidx.compose.animation.AnimatedVisibility(result != null && !busy,
                enter = androidx.compose.animation.fadeIn() + androidx.compose.animation.slideInVertically { it / 2 },
                exit = androidx.compose.animation.fadeOut()) {
                val uri = result
                Surface(color = Color(0x332E7D32), shape = RoundedCornerShape(14.dp)) {
                    Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("✅ Video đã lưu", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        OutlinedButton(onClick = {
                            if (uri != null) ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "video/mp4")
                                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        }) { Text("▶ Xem") }
                        OutlinedButton(onClick = {
                            if (uri != null) ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("video/mp4")
                                .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Chia sẻ video"))
                        }) { Text("📤 Chia sẻ") }
                    }
                }
            }
            androidx.compose.animation.AnimatedVisibility(showLog) {
                val st = rememberLazyListState()
                LaunchedEffect(logs.size) { if (logs.isNotEmpty()) st.animateScrollToItem(logs.size - 1) }
                SelectionContainer {
                    LazyColumn(Modifier.fillMaxWidth().heightIn(max = 220.dp), state = st) {
                        itemsIndexed(logs) { _, l -> Text(l, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = Muted) }
                    }
                }
            }
        }
    }
}

@Composable
fun <T> Choice(label: String, value: T, options: List<Pair<T, String>>, onPick: (T) -> Unit) {
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
fun Hint(text: String) = Text(text, color = Muted, fontSize = 12.sp)

@Composable
fun Toggle(text: String, value: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(value, onChange)
        Text(text, fontSize = 14.sp)
    }
}

@Composable
fun ManualDialog(a: ManualAsk, answer: (String?) -> Unit, cancel: () -> Unit) {
    val clip = LocalClipboardManager.current
    val ctx = LocalContext.current
    val gemini = a.target == "gemini"
    val who = if (gemini) "Gemini" else "DeepSeek"
    var reply by remember(a) { mutableStateOf("") }
    var copied by remember(a) { mutableStateOf(false) }
    fun looksLikeAnswer(t: String) = t != a.prompt && (t.contains("{") || t.contains("-->") || Regex("\\d+:\\d{2}").containsMatchIn(t) ||
        Regex("(?m)^\\s*([-•]|P\\d+\\s*\\|)\\s*\\S").containsMatchIn(t))
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
                    "\"${a.fileName}\" trong thư mục Download), dán yêu cầu, gửi.  3. Chép câu trả lời, quay lại đây - app tự dán, bấm Dùng."
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
                    Button(onClick = { answer(reply) }, enabled = looksLikeAnswer(reply) || reply.contains("|"),
                        modifier = Modifier.weight(1f)) { Text("✅ Dùng") }
                }
                Row {
                    TextButton(onClick = { cancel() }) { Text("Hủy") }
                    Spacer(Modifier.weight(1f))
                    if (a.canApi) TextButton(onClick = { answer(RETRY_API) }) { Text("⚡ Thử lại API") }
                }
            }
        }
    }
}

/**
 * Máy chủ AI riêng: LiteLLM (tự thử lại, xoay nhiều key, chuyển AI dự phòng khi quá tải), hoặc AI chạy trên máy tính
 * nhà (Ollama / LM Studio). Có địa chỉ thì app dùng trước các AI khác.
 */
@Composable
fun CustomAiSection(prefs: Prefs) {
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(prefs.str("custom_url")) }
    var key by remember { mutableStateOf(prefs.str("key_custom")) }
    var model by remember { mutableStateOf(prefs.str("custom_model")) }
    var vmodel by remember { mutableStateOf(prefs.str("custom_vmodel")) }
    var msg by remember { mutableStateOf("") }
    var found by remember { mutableStateOf<List<String>>(emptyList()) }
    Text("🖥 Máy chủ AI riêng (LiteLLM / Ollama / LM Studio)", fontWeight = FontWeight.SemiBold)
    Hint("LiteLLM chạy trên máy tính / máy chủ: tự thử lại khi quá tải, xoay vòng nhiều key, tự chuyển AI dự phòng " +
        "(Gemini → DeepSeek → Groq...). Hoặc AI miễn phí chạy trên máy tính nhà (Ollama, LM Studio). Có địa chỉ thì app dùng trước tiên. " +
        "Hướng dẫn: thư mục ReviewPhim/litellm trên GitHub.")
    OutlinedTextField(url, { url = it.trim(); prefs.set("custom_url", url) }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text("Địa chỉ (vd 192.168.1.10:4000 - để trống = không dùng)") })
    OutlinedTextField(key, { key = it.trim(); prefs.set("key_custom", key) }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text("Key (master key LiteLLM; Ollama / LM Studio để trống)") }, visualTransformation = PasswordVisualTransformation())
    OutlinedTextField(model, { model = it.trim(); prefs.set("custom_model", model) }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text("Model viết / dịch (vd chinh, qwen2.5:14b)") })
    OutlinedTextField(vmodel, { vmodel = it.trim(); prefs.set("custom_vmodel", vmodel) }, Modifier.fillMaxWidth(), singleLine = true,
        label = { Text("Model nhìn ảnh (vd nhin-anh, gemma3:12b; \"-\" = máy chủ không nhìn được ảnh)") })
    OutlinedButton(onClick = {
        scope.launch {
            msg = "Đang kết nối..."
            msg = try {
                found = Ai.testCustom(prefs)
                "✅ Kết nối được - ${found.size} model: " + found.take(8).joinToString(", ")
            } catch (e: Exception) {
                found = emptyList()
                "❌ ${e.message ?: e.javaClass.simpleName}"
            }
        }
    }, enabled = url.isNotBlank()) { Text("🔌 Kiểm tra kết nối") }
    if (msg.isNotEmpty()) Hint(msg)
    if (found.isNotEmpty() && model.isBlank()) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        found.take(3).forEach { m -> TextButton(onClick = { model = m; prefs.set("custom_model", m) }) { Text(m.take(24)) } }
    }
}

/** Ô chọn nhanh: biểu tượng to + chữ ngắn (gọn trên màn hình nhỏ), nhấn có hiệu ứng thu nhỏ. */
@Composable
fun Tile(icon: String, label: String, enabled: Boolean, modifier: Modifier = Modifier, primary: Boolean = false, onClick: () -> Unit) {
    val src = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val sc by androidx.compose.animation.core.animateFloatAsState(if (pressed) 0.94f else 1f, label = "tile")
    val bg = if (primary) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant
    val fg = if (primary) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface
    Surface(modifier.height(76.dp).graphicsLayer { scaleX = sc; scaleY = sc; alpha = if (enabled) 1f else 0.45f },
        shape = RoundedCornerShape(16.dp), color = bg) {
        Column(Modifier.fillMaxSize().clickable(src, androidx.compose.material3.ripple(), enabled = enabled, onClick = onClick)
            .padding(4.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Text(icon, fontSize = 22.sp)
            Text(label, fontSize = 12.sp, color = fg, maxLines = 1, fontWeight = FontWeight.Medium)
        }
    }
}
