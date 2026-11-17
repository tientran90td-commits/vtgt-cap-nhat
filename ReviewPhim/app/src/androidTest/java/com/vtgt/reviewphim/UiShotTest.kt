package com.vtgt.reviewphim

import android.Manifest
import android.content.ContentValues
import android.graphics.Bitmap
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Mở app ở từng chế độ: không lỗi, có nội dung; chụp màn hình (CI lấy về để xem giao diện). */
@RunWith(AndroidJUnit4::class)
class UiShotTest {
    @Test
    fun screens() {
        val ins = InstrumentationRegistry.getInstrumentation()
        val ctx = ins.targetContext
        if (Build.VERSION.SDK_INT >= 33) ins.uiAutomation.grantRuntimePermission(ctx.packageName, Manifest.permission.POST_NOTIFICATIONS)
        val prefs = Prefs(ctx)
        for (m in listOf("film", "manga", "long", "settings")) {
            prefs.set("app_mode", m)
            ActivityScenario.launch(MainActivity::class.java).use {
                Thread.sleep(3000)
                ins.waitForIdleSync()
                val bmp = ins.uiAutomation.takeScreenshot()
                assertTrue("chụp được màn hình $m", bmp != null && bmp.width > 0)
                // màn hình phải có nội dung (nhiều màu khác nhau), không trắng / đen trơn
                val colors = HashSet<Int>()
                for (y in 0 until bmp.height step 37) for (x in 0 until bmp.width step 37) colors += bmp.getPixel(x, y) and 0xF0F0F0
                assertTrue("màn hình $m có nội dung (${colors.size} màu)", colors.size > 8)
                val v = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, "$m.png")
                    put(MediaStore.Downloads.MIME_TYPE, "image/png")
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/ReviewPhim-shots")
                }
                ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v)?.let { u ->
                    ctx.contentResolver.openOutputStream(u)?.use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
                }
            }
        }
        prefs.set("app_mode", "film")
    }
}
