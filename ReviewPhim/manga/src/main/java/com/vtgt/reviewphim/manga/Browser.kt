@file:OptIn(ExperimentalMaterial3Api::class)

package com.vtgt.reviewphim.manga

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.vtgt.reviewphim.Choice
import com.vtgt.reviewphim.Hint
import org.json.JSONArray

/** Ô dán link: tự lấy ảnh truyện tranh / chữ truyện, hoặc mở trình duyệt trong app. */
@Composable
fun LinkDialog(vm: MangaVM, close: () -> Unit, openBrowser: (String) -> Unit) {
    var link by remember { mutableStateOf("") }
    var want by remember { mutableStateOf("auto") }
    var chapters by remember { mutableStateOf(vm.prefs.str("m_chapters", "1").toInt()) }
    AlertDialog(onDismissRequest = close, title = { Text("🔗 Lấy truyện từ link") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(link, { link = it }, Modifier.fillMaxWidth().heightIn(min = 90.dp),
                label = { Text("Link chương đầu (hoặc nhiều link chương / link ảnh, mỗi dòng 1 link)") })
            Choice("Loại truyện", want, listOf("auto" to "Tự nhận", "manga" to "Truyện tranh (lấy ảnh)", "novel" to "Truyện chữ (lấy văn bản)")) { want = it }
            Choice("Số chương lấy liên tiếp (đi theo nút Chương sau)", chapters,
                listOf(1, 2, 3, 5, 10, 20, 30, 50).map { it to "$it chương" }) { chapters = it; vm.save("m_chapters", "$it") }
            Hint("Trang hiện truyện bằng JavaScript / cần đăng nhập thì dùng 🌐 trình duyệt trong app: mở chương, cuộn hết, bấm Lấy ảnh / Lấy chữ, " +
                "sang chương sau rồi lấy tiếp. Chỉ dùng truyện bạn được phép sử dụng.")
        }
    }, confirmButton = {
        Button(onClick = { vm.openLink(link, chapters, want); close() }, enabled = link.contains("http")) { Text("📥 Tự lấy") }
    }, dismissButton = {
        Row {
            TextButton(onClick = { openBrowser(link.lines().firstOrNull { it.trim().startsWith("http") }?.trim() ?: ""); close() }) {
                Text("🌐 Trình duyệt")
            }
            TextButton(onClick = close) { Text("Hủy") }
        }
    })
}

// JS chạy trong trang: danh sách ảnh nội dung (đã tải, đủ lớn) theo thứ tự; chữ của khối nhiều chữ nhất
private const val JS_IMAGES = """(function(){var out=[];var seen={};
document.querySelectorAll('img').forEach(function(i){
 var s=i.currentSrc||i.src||'';var d=i.getAttribute('data-src')||i.getAttribute('data-original')||i.getAttribute('data-lazy-src')||'';
 if((!s||s.indexOf('data:')===0)&&d)s=d;
 if(!s||s.indexOf('data:')===0||seen[s])return;
 var w=i.naturalWidth||i.width,h=i.naturalHeight||i.height;
 if((w>=300&&h>=200)||(d&&w===0)){seen[s]=1;out.push(new URL(s,location.href).href);}
});return JSON.stringify({url:location.href,title:document.title,images:out});})()"""

private const val JS_TEXT = """(function(){function own(e){var s=0;for(var k=0;k<e.childNodes.length;k++){var n=e.childNodes[k];
 if(n.nodeType===3)s+=n.textContent.trim().length;else if(n.tagName==='P'||n.tagName==='SPAN'||n.tagName==='FONT')s+=(n.innerText||'').length;}return s;}
var best=null,bs=0;document.querySelectorAll('div,article,section,main,td').forEach(function(e){var v=own(e);if(v>bs){bs=v;best=e;}});
var h=document.querySelector('h1');
return JSON.stringify({url:location.href,title:(h&&h.innerText)||document.title,text:best?best.innerText:document.body.innerText});})()"""

/** Trình duyệt trong app: bạn tự mở chương truyện, app lấy ảnh / chữ đang hiện trên trang (gom nhiều chương). */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun BrowserDialog(vm: MangaVM, start: String, close: () -> Unit) {
    var url by remember { mutableStateOf(start.ifBlank { "https://www.google.com" }) }
    var web by remember { mutableStateOf<WebView?>(null) }
    var loading by remember { mutableFloatStateOf(0f) }
    val images = remember { mutableListOf<Pair<String, String?>>() }
    val text = remember { StringBuilder() }
    var title by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf("Mở chương truyện, cuộn hết để ảnh tải xong, rồi bấm Lấy ảnh / Lấy chữ. Sang chương sau và lấy tiếp.") }
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
            Column {
                Row(Modifier.fillMaxWidth().padding(6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedTextField(url, { url = it }, Modifier.weight(1f), singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
                        keyboardActions = KeyboardActions(onGo = { web?.loadUrl(fix(url)) }))
                    OutlinedButton(onClick = { web?.loadUrl(fix(url)) }) { Text("Đi") }
                }
                if (loading in 0.01f..0.99f) LinearProgressIndicator(progress = { loading }, modifier = Modifier.fillMaxWidth())
                AndroidView(factory = { c ->
                    WebView(c).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.loadsImagesAutomatically = true
                        settings.userAgentString = Web.UA
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView?, u: String?) {
                                if (u != null) url = u
                            }
                        }
                        webChromeClient = object : WebChromeClient() {
                            override fun onProgressChanged(view: WebView?, p: Int) {
                                loading = p / 100f
                            }
                        }
                        loadUrl(fix(url))
                        web = this
                    }
                }, modifier = Modifier.weight(1f).fillMaxWidth())
                Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(msg, fontSize = 12.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { web?.goBack() }) { Text("◀") }
                        Button(onClick = {
                            web?.evaluateJavascript(JS_IMAGES) { r ->
                                try {
                                    val o = org.json.JSONObject(JSONArray("[$r]").getString(0))
                                    val arr = o.getJSONArray("images")
                                    val page = o.optString("url")
                                    var add = 0
                                    for (i in 0 until arr.length()) {
                                        val s = arr.getString(i)
                                        if (images.none { it.first == s }) { images += s to page; add++ }
                                    }
                                    if (title.isBlank()) title = o.optString("title")
                                    msg = "🖼 +$add ảnh (tổng ${images.size}). Sang chương sau rồi bấm Lấy ảnh tiếp, hoặc bấm ✅ Dùng."
                                } catch (e: Exception) {
                                    msg = "Không lấy được ảnh: ${e.message}"
                                }
                            }
                        }, modifier = Modifier.weight(1f)) { Text("🖼 Lấy ảnh") }
                        Button(onClick = {
                            web?.evaluateJavascript(JS_TEXT) { r ->
                                try {
                                    val o = org.json.JSONObject(JSONArray("[$r]").getString(0))
                                    val t = o.optString("text").trim()
                                    val h = o.optString("title").trim()
                                    if (title.isBlank()) title = h
                                    text.append(h).append("\n\n").append(t).append("\n\n")
                                    msg = "📝 +${t.length} ký tự (tổng ${text.length}). Sang chương sau rồi bấm Lấy chữ tiếp, hoặc bấm ✅ Dùng."
                                } catch (e: Exception) {
                                    msg = "Không lấy được chữ: ${e.message}"
                                }
                            }
                        }, modifier = Modifier.weight(1f)) { Text("📝 Lấy chữ") }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TextButton(onClick = close) { Text("Đóng") }
                        Button(onClick = {
                            vm.fromBrowser(images.toList(), text.toString(), title)
                            close()
                        }, enabled = true, modifier = Modifier.weight(1f)) { Text("✅ Dùng (${images.size} ảnh · ${text.length} ký tự)") }
                    }
                }
            }
        }
    }
}

private fun fix(u: String): String {
    val t = u.trim()
    return when {
        t.startsWith("http://") || t.startsWith("https://") -> t
        t.contains('.') && !t.contains(' ') -> "https://$t"
        else -> "https://www.google.com/search?q=" + java.net.URLEncoder.encode(t, "UTF-8")
    }
}
