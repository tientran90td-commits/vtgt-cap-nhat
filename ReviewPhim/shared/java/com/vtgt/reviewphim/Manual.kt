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
fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            content()
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

