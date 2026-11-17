package com.vtgt.reviewphim

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.json.JSONObject
import java.io.File

/** Cập nhật app từ GitHub Releases của repo (bản mới do GitHub Actions dựng). */
class Updater(private val ctx: Context) {
    data class Release(val code: Int, val name: String, val url: String, val notes: String)

    suspend fun check(): Release? = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url("https://api.github.com/repos/${BuildConfig.UPDATE_REPO}/releases/tags/${BuildConfig.UPDATE_TAG}")
            .header("Accept", "application/vnd.github+json").build()
        Ai.http.newCall(req).execute().use { r ->
            if (!r.isSuccessful) return@withContext null
            val j = JSONObject(r.body?.string() ?: "{}")
            val body = j.optString("body")
            val code = Regex("versionCode=(\\d+)").find(body)?.groupValues?.get(1)?.toIntOrNull() ?: return@withContext null
            val assets = j.optJSONArray("assets") ?: return@withContext null
            val apk = (0 until assets.length()).map { assets.getJSONObject(it) }
                .firstOrNull { it.optString("name") == BuildConfig.UPDATE_ASSET } ?: return@withContext null
            val notes = body.lines().filter { !it.startsWith("versionCode=") }.joinToString("\n").trim()
            Release(code, j.optString("name"), apk.optString("browser_download_url"), notes)
        }
    }

    fun newer(r: Release?): Boolean = r != null && r.code > BuildConfig.VERSION_CODE

    suspend fun download(r: Release, progress: (Float) -> Unit): File = withContext(Dispatchers.IO) {
        val f = File(ctx.cacheDir, "update.apk")
        Ai.http.newCall(Request.Builder().url(r.url).build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("Tải bản cập nhật lỗi HTTP ${resp.code}")
            val body = resp.body ?: throw IllegalStateException("Tải bản cập nhật lỗi")
            val total = body.contentLength()
            body.byteStream().use { i ->
                f.outputStream().use { o ->
                    val buf = ByteArray(1 shl 16)
                    var done = 0L
                    while (true) {
                        val n = i.read(buf)
                        if (n < 0) break
                        o.write(buf, 0, n)
                        done += n
                        if (total > 0) progress(done.toFloat() / total)
                    }
                }
            }
        }
        f
    }

    /** Mở trình cài đặt của Android (lần đầu Android hỏi cho phép cài từ app này). */
    fun install(f: File) {
        if (!ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
