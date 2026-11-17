package com.vtgt.reviewphim

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import com.vtgt.reviewphim.longvid.LongVM
import com.vtgt.reviewphim.manga.MangaVM

class MainActivity : ComponentActivity() {
    private val film: MainVM by viewModels()
    private val manga: MangaVM by viewModels()
    private val long: LongVM by viewModels()
    private val askNotify = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}
    private var mode by mutableStateOf("film")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        mode = film.prefs.str("app_mode", "film")
        if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
        if (savedInstanceState == null) handleShare(intent)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(
                primary = Color(0xFF8B6CFF), secondary = Color(0xFFFFD54F),
                background = Color(0xFF12121A), surface = Color(0xFF1C1C26), surfaceVariant = Color(0xFF262633),
            )) {
                HomeScreen(film, manga, long, mode) { switchMode(it) }
            }
        }
    }

    private fun switchMode(m: String) {
        mode = m
        film.prefs.set("app_mode", m)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShare(intent)
    }

    /**
     * Chia sẻ vào app: video / link video -> 🎬 Phim; ảnh trang, CBZ / ZIP / PDF / EPUB / TXT, truyện chữ dài -> 📚 Truyện.
     */
    @Suppress("DEPRECATION")
    private fun handleShare(i: Intent?) {
        when (i?.action) {
            Intent.ACTION_SEND_MULTIPLE -> {
                val list: List<Uri> = (if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else i.getParcelableArrayListExtra(Intent.EXTRA_STREAM)) ?: return
                if (list.isEmpty()) return
                switchMode("manga")
                manga.openImages(list)
            }
            Intent.ACTION_SEND -> {
                val u = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else i.getParcelableExtra(Intent.EXTRA_STREAM)
                val type = i.type ?: ""
                if (u != null) {
                    when {
                        type.startsWith("video/") -> { switchMode("film"); film.openVideo(u) }
                        type.startsWith("image/") -> { switchMode("manga"); manga.openImages(listOf(u)) }
                        else -> { switchMode("manga"); manga.openFile(u) }
                    }
                    return
                }
                val t = i.getStringExtra(Intent.EXTRA_TEXT) ?: return
                val url = Download.findUrl(t)
                if (url != null && t.length < 500) {
                    switchMode("film")
                    film.download(url)
                } else if (t.length > 200) {
                    switchMode("manga")
                    manga.pasteText(t, i.getStringExtra(Intent.EXTRA_SUBJECT) ?: "Truyện")
                }
            }
            Intent.ACTION_VIEW -> i.data?.let { d ->
                if (contentResolver.getType(d)?.startsWith("video/") == true) { switchMode("film"); film.openVideo(d) }
                else { switchMode("manga"); manga.openFile(d) }
            }
        }
    }
}
