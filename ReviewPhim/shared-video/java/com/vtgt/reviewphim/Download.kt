package com.vtgt.reviewphim

import android.content.Context
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** Tải video từ link YouTube / TikTok / Douyin / Bilibili... bằng yt-dlp (tự cập nhật mỗi ngày). */
object Download {
    @Volatile
    private var ready = false

    private fun init(ctx: Context) {
        if (ready) return
        YoutubeDL.getInstance().init(ctx.applicationContext)
        Ff.init(ctx)
        ready = true
    }

    fun findUrl(text: String): String? = Regex("https?://[^\\s]+").find(text)?.value?.trimEnd('.', ',', ')', '"')

    suspend fun fetch(ctx: Context, prefs: Prefs, url: String, dir: File, log: (String) -> Unit,
                      progress: (Float) -> Unit): Pair<File, String> = withContext(Dispatchers.IO) {
        init(ctx)
        val day = System.currentTimeMillis() / 86_400_000L
        if (prefs.str("ytdlp_day") != day.toString()) {
            try {
                log("Cập nhật bộ tải video (yt-dlp)...")
                YoutubeDL.getInstance().updateYoutubeDL(ctx.applicationContext, YoutubeDL.UpdateChannel.STABLE)
                prefs.set("ytdlp_day", day.toString())
            } catch (e: Exception) {
                log("Không cập nhật được yt-dlp (${e.message?.take(80)}) - dùng bản đang có.")
            }
        }
        dir.mkdirs()
        val req = YoutubeDLRequest(url)
        req.addOption("--no-playlist")
        req.addOption("-f", "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[ext=mp4]/b")
        req.addOption("--merge-output-format", "mp4")
        req.addOption("-o", File(dir, "%(id)s.%(ext)s").absolutePath)
        req.addOption("--print", "after_move:@@%(title)s|||%(filepath)s")
        req.addOption("--progress")
        req.addOption("--newline")
        val id = "dl_" + System.currentTimeMillis()
        val res = YoutubeDL.getInstance().execute(req, id) { p, _, _ -> if (p >= 0) progress(p / 100f) }
        val line = res.out.lines().lastOrNull { it.startsWith("@@") }
            ?: throw IllegalStateException("Không tải được video:\n" + res.err.takeLast(300))
        val title = line.removePrefix("@@").substringBefore("|||")
        val file = File(line.substringAfter("|||").trim())
        if (!file.exists()) throw IllegalStateException("Tải xong nhưng không thấy file video.")
        file to title
    }
}
