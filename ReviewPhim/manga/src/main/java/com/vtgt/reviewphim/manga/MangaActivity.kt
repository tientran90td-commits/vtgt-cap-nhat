package com.vtgt.reviewphim.manga

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

class MangaActivity : ComponentActivity() {
    private val vm: MangaVM by viewModels()
    private val askNotify = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
        if (savedInstanceState == null) handleShare(intent)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(
                primary = Color(0xFFFF7A59), secondary = Color(0xFFFFD54F),
                background = Color(0xFF14121A), surface = Color(0xFF201C26), surfaceVariant = Color(0xFF2A2533),
            )) {
                MangaScreen(vm)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShare(intent)
    }

    @Suppress("DEPRECATION")
    private fun handleShare(i: Intent?) {
        when (i?.action) {
            Intent.ACTION_SEND_MULTIPLE -> {
                val list: List<Uri> = (if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else i.getParcelableArrayListExtra(Intent.EXTRA_STREAM)) ?: return
                if (list.isNotEmpty()) vm.openImages(list)
            }
            Intent.ACTION_SEND -> {
                val u = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else i.getParcelableExtra(Intent.EXTRA_STREAM)
                if (u != null) {
                    if (i.type?.startsWith("image/") == true) vm.openImages(listOf(u)) else vm.openFile(u)
                    return
                }
                val t = i.getStringExtra(Intent.EXTRA_TEXT) ?: return
                if (t.length > 200) vm.pasteText(t, i.getStringExtra(Intent.EXTRA_SUBJECT) ?: "Truyện")
            }
            Intent.ACTION_VIEW -> i.data?.let { vm.openFile(it) }
        }
    }
}
