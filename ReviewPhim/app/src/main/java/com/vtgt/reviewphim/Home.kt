package com.vtgt.reviewphim

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vtgt.reviewphim.longvid.LongScreen
import com.vtgt.reviewphim.longvid.LongVM
import com.vtgt.reviewphim.manga.MangaScreen
import com.vtgt.reviewphim.manga.MangaVM

/** 1 app, 3 chế độ: review / dịch phim · tóm tắt truyện tranh, light novel · video dài tới 10 tiếng. */
@Composable
fun HomeScreen(film: MainVM, manga: MangaVM, long: LongVM, mode: String, setMode: (String) -> Unit) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("ReviewPhim AI", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("v${BuildConfig.VERSION_NAME}", color = Muted, fontSize = 12.sp)
        }
        UpdateBanner(film)
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val busy = mapOf("film" to film.busy, "manga" to manga.busy, "long" to long.busy)
            listOf("film" to "🎬 Phim", "manga" to "📚 Truyện", "long" to "⏱ Video dài").forEach { (k, t) ->
                FilterChip(selected = mode == k, onClick = { setMode(k) },
                    label = { Text(t + if (busy[k] == true && mode != k) " ⏳" else "", fontSize = 13.sp) },
                    modifier = Modifier.weight(1f))
            }
        }
        Box(Modifier.weight(1f)) {
            when (mode) {
                "manga" -> MangaScreen(manga, embedded = true)
                "long" -> LongScreen(long, embedded = true)
                else -> AppScreen(film, embedded = true)
            }
        }
    }
}
