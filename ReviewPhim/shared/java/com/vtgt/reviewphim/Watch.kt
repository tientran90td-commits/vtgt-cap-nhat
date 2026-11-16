package com.vtgt.reviewphim

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.media.MediaMetadataRetriever
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * "AI xem cả phim": chụp khung hình rải suốt video (bỏ khung đen, khung gần giống khung trước), ghép 5x5 khung
 * vào 1 ảnh có ghi mốc thời gian từng ô -> AI nhìn ảnh (Gemini...) mô tả diễn biến hình ảnh theo mốc thời gian.
 * Nhờ vậy cảnh hành động / cảnh không có lời thoại cũng được kể và được chiếu đúng chỗ.
 */
object Watch {
    const val GRID = 5            // 5 x 5 = 25 khung mỗi ảnh ghép
    const val CELL = 256          // cạnh dài của 1 ô (px)
    const val MAX_FRAMES = 750
    const val TAG = "[HÌNH] "     // dòng mô tả hình trong danh sách diễn biến gửi AI viết kịch bản

    data class Sheet(val file: File, val times: List<Double>)

    /** Khoảng cách giữa 2 lần chụp: phim càng dài chụp càng thưa (2-12 giây). */
    fun step(duration: Double): Double = (duration / MAX_FRAMES).coerceIn(2.0, 12.0)

    /** Ước lượng số ảnh ghép (để báo trước số lần làm tay). */
    fun estimateSheets(duration: Double): Int =
        max(1, ceil(min(MAX_FRAMES.toDouble(), duration / step(duration)) * 0.8 / (GRID * GRID)).toInt())

    fun cellSize(w: Int, h: Int): Pair<Int, Int> {
        val a = if (w > 0 && h > 0) w.toDouble() / h else 16.0 / 9
        return if (a >= 1) CELL to max(48, (CELL / a).roundToInt()) else max(48, (CELL * a).roundToInt()) to CELL
    }

    /** Chụp + ghép ảnh, ghi JPEG vào [dir]. */
    suspend fun sheets(src: File, info: VInfo, dir: File, progress: (Float) -> Unit): List<Sheet> = withContext(Dispatchers.Default) {
        dir.mkdirs()
        val (cw, ch) = cellSize(info.width, info.height)
        val st = step(info.duration)
        val mmr = MediaMetadataRetriever()
        mmr.setDataSource(src.absolutePath)
        val out = mutableListOf<Sheet>()
        val cur = mutableListOf<Pair<Double, Bitmap>>()
        fun flush() {
            if (cur.isEmpty()) return
            val f = File(dir, "khung_%03d.jpg".num(out.size + 1))
            compose(cur, cw, ch, f)
            out.add(Sheet(f, cur.map { it.first }))
            cur.forEach { it.second.recycle() }
            cur.clear()
        }
        var prev: IntArray? = null
        var lastKept = -1e9
        var t = min(st / 2, info.duration / 2)
        try {
            while (t < info.duration - 0.3) {
                currentCoroutineContext().ensureActive()
                val fr = mmr.getScaledFrameAtTime((t * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST, cw, ch)
                if (fr != null) {
                    val sig = signature(fr)
                    val keep = sig.average() >= 14 && (prev == null || diff(sig, prev!!) >= 6.0 || t - lastKept >= st * 4)
                    if (keep) {
                        val cell = if (fr.width == cw && fr.height == ch) fr else Bitmap.createScaledBitmap(fr, cw, ch, true).also { fr.recycle() }
                        cur.add(t to cell)
                        prev = sig
                        lastKept = t
                        if (cur.size == GRID * GRID) flush()
                    } else fr.recycle()
                }
                t += st
                progress((t / info.duration).toFloat().coerceAtMost(1f))
            }
            flush()
        } finally {
            cur.forEach { it.second.recycle() }
            mmr.release()
        }
        out
    }

    private fun compose(cells: List<Pair<Double, Bitmap>>, cw: Int, ch: Int, f: File) {
        val rows = (cells.size + GRID - 1) / GRID
        val gap = 4
        val sheet = Bitmap.createBitmap(GRID * cw + (GRID - 1) * gap, rows * ch + (rows - 1) * gap, Bitmap.Config.ARGB_8888)
        val c = Canvas(sheet)
        c.drawColor(Color.rgb(40, 40, 40))
        val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = max(16f, min(cw, ch) * 0.13f)
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val bg = Paint().apply { color = Color.argb(200, 0, 0, 0) }
        for ((k, p) in cells.withIndex()) {
            val x = (k % GRID) * (cw + gap)
            val y = (k / GRID) * (ch + gap)
            c.drawBitmap(p.second, null, Rect(x, y, x + cw, y + ch), null)
            val label = fmtTime(p.first)
            val w = txt.measureText(label)
            c.drawRoundRect(RectF(x + 2f, y + 2f, x + w + 12f, y + txt.textSize + 10f), 6f, 6f, bg)
            c.drawText(label, x + 7f, y + txt.textSize + 4f, txt)
        }
        f.outputStream().use { sheet.compress(Bitmap.CompressFormat.JPEG, 82, it) }
        sheet.recycle()
    }

    /** Dấu vân tay 16x9 độ sáng để bỏ khung gần giống khung trước (cảnh tĩnh). */
    private fun signature(b: Bitmap): IntArray {
        val s = Bitmap.createScaledBitmap(b, 16, 9, true)
        val px = IntArray(16 * 9)
        s.getPixels(px, 0, 16, 0, 0, 16, 9)
        if (s != b) s.recycle()
        return IntArray(px.size) { val c = px[it]; ((c shr 16 and 255) + (c shr 8 and 255) + (c and 255)) / 3 }
    }

    private fun diff(a: IntArray, b: IntArray): Double {
        var s = 0L
        for (i in a.indices) s += abs(a[i] - b[i])
        return s.toDouble() / a.size
    }

    private val T = "(\\d{1,2}:\\d{2}(?::\\d{2})?)"
    private val ROW = Regex("^[\\s*\\-•>#]*\\[?\\s*$T(?:\\s*[-–~>]+\\s*$T)?\\s*]?\\s*[|:\\-–.)]*\\s*(.+)$")

    fun parseClock(s: String): Double {
        val p = s.split(":").map { it.toInt() }
        return if (p.size == 3) p[0] * 3600.0 + p[1] * 60 + p[2] else p[0] * 60.0 + p[1]
    }

    /**
     * Câu trả lời của AI ("mm:ss-mm:ss | mô tả" mỗi dòng) -> các cảnh. Chỉ nhận mốc nằm trong khoảng ảnh đã gửi
     * [lo, hi] (AI bịa mốc ngoài khoảng thì bỏ). Cảnh không ghi mốc kết thúc thì kéo tới cảnh sau (tối đa 20 giây).
     */
    fun parse(text: String, lo: Double, hi: Double, step: Double): List<Line> {
        val rows = text.lines().mapNotNull { ROW.find(it.trim()) }.mapNotNull { m ->
            val a = parseClock(m.groupValues[1])
            val b = m.groupValues[2].takeIf { it.isNotEmpty() }?.let { parseClock(it) }
            val d = m.groupValues[3].replace("*", "").replace(Regex("\\s+"), " ").trim().trim('|', '-', ' ')
            if (d.length < 3 || a < lo - step - 1 || a > hi + step + 1) null else Triple(a, b, d)
        }.sortedBy { it.first }
        return rows.mapIndexed { k, (a, b, d) ->
            val next = rows.getOrNull(k + 1)?.first ?: (hi + step)
            val e = (b?.takeIf { it > a } ?: max(a + step, next)).coerceAtMost(a + 20.0)
            Line(a, max(a + 1.0, e), d)
        }
    }

    /** Lời thoại + mô tả hình, xếp theo thời gian (danh sách diễn biến gửi AI viết kịch bản). */
    fun timeline(lines: List<Line>, scenes: List<Line>): List<Line> =
        if (scenes.isEmpty()) lines else (lines + scenes.map { it.copy(text = TAG + it.text) }).sortedBy { it.start }
}
