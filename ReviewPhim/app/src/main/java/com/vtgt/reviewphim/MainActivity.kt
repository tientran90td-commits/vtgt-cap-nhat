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
import androidx.compose.ui.graphics.Color

class MainActivity : ComponentActivity() {
    private val vm: MainVM by viewModels()
    private val askNotify = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
        if (savedInstanceState == null) handleShare(intent)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(
                primary = Color(0xFF8B6CFF), secondary = Color(0xFFFFD54F),
                background = Color(0xFF12121A), surface = Color(0xFF1C1C26), surfaceVariant = Color(0xFF262633),
            )) {
                AppScreen(vm)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShare(intent)
    }

    /** Video / link được chia sẻ vào app từ TikTok, YouTube, thư viện ảnh... */
    private fun handleShare(i: Intent?) {
        if (i?.action != Intent.ACTION_SEND) return
        val stream = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else @Suppress("DEPRECATION") i.getParcelableExtra(Intent.EXTRA_STREAM)
        if (stream != null) {
            vm.openVideo(stream)
            return
        }
        i.getStringExtra(Intent.EXTRA_TEXT)?.let { t -> Download.findUrl(t)?.let { vm.download(it) } }
    }
}
