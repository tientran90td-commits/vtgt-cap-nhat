package com.vtgt.reviewphim.manga

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.max
import kotlin.math.min

/** AI chỉ ra nhân vật: tên + trang (1..) + khung (1.., 0 = cả trang). */
data class CastRef(val name: String, val page: Int, val panel: Int)

/**
 * Bảng nhân vật (ảnh mặt + tên) gửi kèm MỌI lần AI đọc tranh để nhận đúng ai là ai, gọi tên thống nhất qua
 * nhiều chương (ý tưởng "trang hồ sơ nhân vật" của manga-reader; code tự viết). AI tự chỉ khung thấy rõ mặt
 * nhân vật mới ("NV | Tên | P12.2"), app cắt khung đó làm ảnh mẫu.
 */
class Roster(private val dir: File) {
    val entries = mutableListOf<Pair<String, File>>()
    var sheet: File? = null
        private set

    init {
        try {
            val a = JSONArray(File(dir, "roster.json").readText())
            for (i in 0 until a.length()) a.getJSONObject(i).let { o ->
                val f = File(dir, o.getString("f"))
                if (f.exists()) entries += o.getString("n") to f
            }
            sheet = File(dir, "bang_nhan_vat.jpg").takeIf { it.exists() && entries.isNotEmpty() }
        } catch (_: Exception) {
        }
    }

    fun names() = entries.map { it.first }

    /** Ảnh gửi kèm (bảng nhân vật đứng đầu). */
    fun files(): List<File> = listOfNotNull(sheet)

    /** Thêm nhân vật mới AI chỉ ra. [pageFile]: trang số (1..) -> file ảnh. Trả về số nhân vật thêm. */
    fun add(refs: List<CastRef>, rtl: Boolean, pageFile: (Int) -> File?): Int {
        var added = 0
        for (r in refs) {
            if (entries.size >= MAX) break
            val key = norm(r.name)
            if (key.isEmpty() || entries.any { norm(it.first) == key }) continue
            val page = pageFile(r.page) ?: continue
            dir.mkdirs()
            val out = File(dir, "nv_${entries.size}.jpg")
            try {
                val crops = if (r.panel > 0) Panels.crops(page, rtl, File(dir, "tmp"), "c") else emptyList()
                val src = crops.getOrNull(r.panel - 1)?.takeIf { crops.size > 1 } ?: page
                val b = BitmapFactory.decodeFile(src.path, BitmapFactory.Options().apply {
                    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeFile(src.path, o)
                    inSampleSize = max(1, Integer.highestOneBit(max(1, max(o.outWidth, o.outHeight) / 600)))
                }) ?: continue
                out.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 88, it) }
                b.recycle()
            } catch (e: Exception) {
                continue
            } finally {
                File(dir, "tmp").deleteRecursively()
            }
            entries += r.name.trim() to out
            added++
        }
        if (added > 0) save()
        return added
    }

    private fun save() {
        dir.mkdirs()
        File(dir, "roster.json").writeText(JSONArray().apply {
            entries.forEach { (n, f) -> put(JSONObject().put("n", n).put("f", f.name)) }
        }.toString())
        sheet = build(entries, File(dir, "bang_nhan_vat.jpg"))
    }

    companion object {
        const val MAX = 10
        private fun norm(s: String) = s.lowercase().replace(Regex("[^\\p{L}\\p{N}]"), "")

        private val ROW = Regex("^[\\s*\\-•>]*NV\\s*[|:]\\s*(.+?)\\s*[|:]\\s*(?:P|Trang|Page)\\s*\\.?\\s*(\\d{1,4})(?:\\s*[.,]\\s*(\\d{1,2}))?",
            RegexOption.IGNORE_CASE)

        /** Đọc các dòng "NV | Tên | P12.2" trong câu trả lời đọc tranh. */
        fun parse(text: String): List<CastRef> = text.lines().mapNotNull { l ->
            ROW.find(l.trim())?.let { m ->
                val name = m.groupValues[1].replace("*", "").trim().trim('"', '\'', '(', ')')
                if (name.length !in 1..40) null else CastRef(name, m.groupValues[2].toInt(), m.groupValues[3].toIntOrNull() ?: 0)
            }
        }

        /** Ghép ảnh mặt + tên thành 1 bảng (4 cột). */
        fun build(entries: List<Pair<String, File>>, out: File): File {
            val cols = min(4, max(1, entries.size))
            val rows = (entries.size + cols - 1) / cols
            val cw = 300
            val img = 300
            val ch = img + 56
            val b = Bitmap.createBitmap(cols * cw, max(1, rows) * ch + 60, Bitmap.Config.ARGB_8888)
            val c = Canvas(b)
            c.drawColor(Color.rgb(24, 24, 30))
            val head = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.rgb(255, 214, 64); textSize = 36f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            }
            c.drawText("BẢNG NHÂN VẬT", 16f, 44f, head)
            val name = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE; textSize = 30f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            }
            for ((k, e) in entries.withIndex()) {
                val x = (k % cols) * cw
                val y = 60 + (k / cols) * ch
                BitmapFactory.decodeFile(e.second.path)?.let { p ->
                    val s = min((img - 12f) / p.width, (img - 12f) / p.height)
                    val w = p.width * s
                    val h = p.height * s
                    c.drawBitmap(p, null, RectF(x + (cw - w) / 2, y + (img - h) / 2, x + (cw + w) / 2, y + (img + h) / 2),
                        Paint(Paint.FILTER_BITMAP_FLAG))
                    p.recycle()
                }
                val lay = StaticLayout.Builder.obtain(e.first, 0, e.first.length, name, cw - 12)
                    .setAlignment(Layout.Alignment.ALIGN_CENTER).setMaxLines(1).build()
                c.save()
                c.translate(x + 6f, y + img + 8f)
                lay.draw(c)
                c.restore()
            }
            out.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 85, it) }
            b.recycle()
            return out
        }
    }
}
