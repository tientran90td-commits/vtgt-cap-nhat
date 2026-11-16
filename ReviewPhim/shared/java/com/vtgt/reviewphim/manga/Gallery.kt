package com.vtgt.reviewphim.manga

import android.graphics.BitmapFactory
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.max

/** Ảnh thu nhỏ đọc nền (không chặn giao diện). */
@Composable
private fun thumb(f: File, maxSide: Int): ImageBitmap? = produceState<ImageBitmap?>(null, f.path, maxSide) {
    value = withContext(Dispatchers.IO) {
        try {
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(f.path, o)
            val s = max(1, Integer.highestOneBit(max(1, max(o.outWidth, o.outHeight) / maxSide)))
            BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply { inSampleSize = s })?.asImageBitmap()
        } catch (e: Exception) {
            null
        }
    }
}.value

/**
 * Xem trước các trang đã tải: lưới ảnh nhỏ, chạm để xem to, giữ lâu (hoặc bật "Chọn") để chọn nhiều trang rồi xóa
 * (ảnh quảng cáo lọt lưới, trang bìa, lời tác giả...). [onDelete] nhận chỉ số các trang bị xóa.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PageGallery(title: String, pages: List<Page>, busy: Boolean, onDelete: (Set<Int>) -> Unit, close: () -> Unit) {
    var selecting by remember { mutableStateOf(false) }
    var picked by remember { mutableStateOf(setOf<Int>()) }
    var view by remember { mutableStateOf<Int?>(null) }
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
            Column {
                Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(title, fontWeight = FontWeight.Bold, maxLines = 1)
                        Text(if (selecting) "Đã chọn ${picked.size} trang - chạm để chọn / bỏ chọn" else
                            "${pages.size} trang · chạm xem to · giữ lâu để chọn và xóa", fontSize = 12.sp, color = Color(0xFF9A9AB0))
                    }
                    if (selecting) {
                        Button(onClick = { onDelete(picked); picked = emptySet(); selecting = false }, enabled = picked.isNotEmpty() && !busy,
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E))) { Text("🗑 Xóa ${picked.size}") }
                        TextButton(onClick = { selecting = false; picked = emptySet() }) { Text("Hủy") }
                    } else {
                        OutlinedButton(onClick = { selecting = true }, enabled = !busy) { Text("Chọn") }
                        TextButton(onClick = close) { Text("Đóng") }
                    }
                }
                LazyVerticalGrid(GridCells.Adaptive(104.dp), Modifier.fillMaxSize().padding(4.dp)) {
                    itemsIndexed(pages, key = { _, p -> p.file.path }) { i, p ->
                        val on = i in picked
                        Box(Modifier.padding(3.dp).aspectRatio(0.7f)
                            .border(if (on) 3.dp else 1.dp, if (on) Color(0xFFFF5252) else Color(0x33FFFFFF))
                            .background(Color(0xFF15151C))
                            .combinedClickable(
                                onClick = {
                                    if (!selecting) view = i
                                    else picked = if (on) picked - i else picked + i
                                },
                                onLongClick = { if (!busy) { selecting = true; picked = picked + i } })) {
                            thumb(p.file, 360)?.let { Image(it, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
                            Text(p.label.ifBlank { "${i + 1}" }, fontSize = 11.sp, color = Color.White,
                                modifier = Modifier.align(Alignment.BottomStart).background(Color(0xAA000000)).padding(horizontal = 4.dp))
                            if (on) Text("✓", color = Color.White, fontWeight = FontWeight.Bold,
                                modifier = Modifier.align(Alignment.TopEnd).background(Color(0xFFFF5252)).padding(horizontal = 6.dp))
                        }
                    }
                }
            }
        }
    }
    view?.let { i ->
        PageViewer(pages, i, busy, onDelete = { onDelete(setOf(it)); view = null }, move = { view = it }, close = { view = null })
    }
}

/** Xem to 1 trang (cuộn dọc cho trang dài), ◀ ▶ chuyển trang, xóa trang. */
@Composable
private fun PageViewer(pages: List<Page>, i: Int, busy: Boolean, onDelete: (Int) -> Unit, move: (Int) -> Unit, close: () -> Unit) {
    val p = pages.getOrNull(i) ?: return
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = Color.Black) {
            Column {
                Row(Modifier.fillMaxWidth().padding(6.dp), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    TextButton(onClick = { move(i - 1) }, enabled = i > 0) { Text("◀") }
                    Text("${p.label.ifBlank { "Trang ${i + 1}" }} · ${i + 1}/${pages.size} · ${p.w}x${p.h}",
                        Modifier.weight(1f), color = Color.White, fontSize = 13.sp)
                    TextButton(onClick = { move(i + 1) }, enabled = i < pages.size - 1) { Text("▶") }
                }
                Box(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
                    thumb(p.file, 1600)?.let { Image(it, null, Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth) }
                }
                Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onDelete(i) }, enabled = !busy, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFB3261E)),
                        modifier = Modifier.weight(1f)) { Text("🗑 Xóa trang này") }
                    OutlinedButton(onClick = close, modifier = Modifier.weight(1f)) { Text("Đóng") }
                }
            }
        }
    }
}
