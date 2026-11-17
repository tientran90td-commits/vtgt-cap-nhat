package com.vtgt.reviewphim

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
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

private val TABS = listOf("film" to ("🎬" to "Phim"), "manga" to ("📚" to "Truyện"), "long" to ("⏱" to "Video dài"),
    "settings" to ("⚙️" to "Cài đặt"))

/** 1 app, 3 chế độ + cài đặt chung, chuyển bằng thanh dưới cùng (có hiệu ứng chuyển cảnh). */
@Composable
fun HomeScreen(film: MainVM, manga: MangaVM, long: LongVM, mode: String, setMode: (String) -> Unit) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("ReviewPhim AI", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("v${BuildConfig.VERSION_NAME}", color = Muted, fontSize = 12.sp)
        }
        UpdateBanner(film)
        Box(Modifier.weight(1f)) {
            AnimatedContent(mode, transitionSpec = {
                val dir = if (TABS.indexOfFirst { it.first == targetState } > TABS.indexOfFirst { it.first == initialState }) 1 else -1
                (fadeIn(tween(260)) + slideInHorizontally(tween(260)) { dir * it / 10 }) togetherWith fadeOut(tween(160))
            }, label = "mode") { m ->
                when (m) {
                    "manga" -> MangaScreen(manga, embedded = true)
                    "long" -> LongScreen(long, embedded = true)
                    "settings" -> SettingsScreen(film)
                    else -> AppScreen(film, embedded = true)
                }
            }
        }
        val busy = mapOf("film" to film.busy, "manga" to manga.busy, "long" to long.busy)
        NavigationBar(tonalElevation = 2.dp) {
            TABS.forEach { (k, v) ->
                NavigationBarItem(selected = mode == k, onClick = { setMode(k) },
                    icon = {
                        BadgedBox(badge = { if (busy[k] == true && mode != k) Badge { Text("…") } }) { Text(v.first, fontSize = 20.sp) }
                    },
                    label = { Text(v.second, fontSize = 12.sp) })
            }
        }
    }
}
