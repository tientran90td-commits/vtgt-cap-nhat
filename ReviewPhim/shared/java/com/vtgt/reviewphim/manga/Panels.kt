package com.vtgt.reviewphim.manga

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapRegionDecoder
import android.graphics.Rect
import java.io.File
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Khung chữ nhật (tọa độ điểm ảnh, [l, r) x [t, b)). */
data class Box(val l: Int, val t: Int, val r: Int, val b: Int) {
    val w get() = r - l
    val h get() = b - t
    val area get() = w.toLong() * h
}

/**
 * Tách khung tranh trên 1 trang truyện (ý tưởng "đọc từng khung" như Kumiko / manga-reader; code tự viết):
 * cắt XY đệ quy theo các "rãnh" trắng (hoặc đen) giữa các khung - hàng / cột gần như không có nét vẽ.
 * Thứ tự đọc: trên xuống dưới, trong 1 hàng phải sang trái (manga Nhật) hoặc trái sang phải.
 */
object Panels {
    const val SCALE_W = 320

    /**
     * [gray]: độ sáng 0..255 của ảnh thu nhỏ [w] x [h]. Trả về các khung theo thứ tự đọc
     * (1 khung = cả trang khi không tách được).
     */
    fun detect(gray: IntArray, w: Int, h: Int, rtl: Boolean): List<Box> {
        if (w < 8 || h < 8) return listOf(Box(0, 0, w, h))
        // nền: trung bình viền ảnh (trang trắng hoặc trang nền đen)
        var s = 0L
        var n = 0
        for (x in 0 until w) { s += gray[x] + gray[(h - 1) * w + x]; n += 2 }
        for (y in 0 until h) { s += gray[y * w] + gray[y * w + w - 1]; n += 2 }
        val bg = (s / n).toInt()
        val ink = BooleanArray(w * h) { abs(gray[it] - bg) > 48 }
        val out = mutableListOf<Box>()
        split(ink, w, Box(0, 0, w, h), rtl, 0, out)
        val page = w.toLong() * h
        val big = out.filter { it.area >= page * 0.025 && it.w >= w * 0.12 && it.h >= h * 0.06 }
        return if (big.size <= 1) listOf(trim(ink, w, Box(0, 0, w, h)) ?: Box(0, 0, w, h)) else big
    }

    private fun rowInk(ink: BooleanArray, w: Int, b: Box, y: Int): Double {
        var c = 0
        for (x in b.l until b.r) if (ink[y * w + x]) c++
        return c.toDouble() / max(1, b.w)
    }

    private fun colInk(ink: BooleanArray, w: Int, b: Box, x: Int): Double {
        var c = 0
        for (y in b.t until b.b) if (ink[y * w + x]) c++
        return c.toDouble() / max(1, b.h)
    }

    /** Bỏ lề trống quanh khung; null nếu khung trống trơn. */
    private fun trim(ink: BooleanArray, w: Int, b: Box): Box? {
        var t = b.t
        var bt = b.b
        var l = b.l
        var r = b.r
        while (t < bt && rowInk(ink, w, Box(l, t, r, bt), t) < 0.01) t++
        while (bt > t && rowInk(ink, w, Box(l, t, r, bt), bt - 1) < 0.01) bt--
        while (l < r && colInk(ink, w, Box(l, t, r, bt), l) < 0.01) l++
        while (r > l && colInk(ink, w, Box(l, t, r, bt), r - 1) < 0.01) r--
        return if (r - l < 4 || bt - t < 4) null else Box(l, t, r, bt)
    }

    /** Các đoạn liền nhau không phải rãnh (rãnh = ít nét vẽ, đủ rộng). */
    private fun segments(profile: DoubleArray, minGap: Int): List<IntRange> {
        val gut = BooleanArray(profile.size) { profile[it] < 0.012 }
        val out = mutableListOf<IntRange>()
        var i = 0
        while (i < profile.size) {
            while (i < profile.size && gut[i]) i++
            if (i >= profile.size) break
            var j = i
            // kết thúc đoạn khi gặp rãnh đủ rộng
            while (j < profile.size) {
                if (gut[j]) {
                    var k = j
                    while (k < profile.size && gut[k]) k++
                    if (k - j >= minGap || k >= profile.size) break
                    j = k
                } else j++
            }
            out += i until j
            i = j
        }
        return out
    }

    private fun split(ink: BooleanArray, w: Int, box: Box, rtl: Boolean, depth: Int, out: MutableList<Box>) {
        val b = trim(ink, w, box) ?: return
        if (depth > 6) { out += b; return }
        val gap = max(2, (min(b.w, b.h) * 0.012).roundToInt())
        // ưu tiên tách hàng (rãnh ngang), không được thì tách cột
        val rows = segments(DoubleArray(b.h) { rowInk(ink, w, b, b.t + it) }, gap)
        if (rows.size >= 2) {
            for (r in rows) split(ink, w, Box(b.l, b.t + r.first, b.r, b.t + r.last + 1), rtl, depth + 1, out)
            return
        }
        val cols = segments(DoubleArray(b.w) { colInk(ink, w, b, b.l + it) }, gap)
        if (cols.size >= 2) {
            val ordered = if (rtl) cols.reversed() else cols
            for (c in ordered) split(ink, w, Box(b.l + c.first, b.t, b.l + c.last + 1, b.b), rtl, depth + 1, out)
            return
        }
        out += b
    }

    /** Ảnh trang -> các file khung tranh (cắt từ ảnh gốc, có lề nhỏ). Trang 1 khung thì trả về chính trang đó. */
    /**
     * Các khung tranh của trang theo thứ tự đọc, tọa độ ảnh gốc (khung 1 = số 1 khi đánh số cho AI đọc).
     * Rỗng nếu cả trang chỉ là 1 khung.
     */
    fun boxes(page: File, rtl: Boolean): List<Box> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(page.path, o)
        val pw = o.outWidth
        if (pw <= 0 || o.outHeight <= 0) return emptyList()
        val small = BitmapFactory.decodeFile(page.path, BitmapFactory.Options().apply {
            inSampleSize = max(1, Integer.highestOneBit(max(1, pw / SCALE_W)))
        }) ?: return emptyList()
        val sw = small.width
        val sh = small.height
        val px = IntArray(sw * sh)
        small.getPixels(px, 0, sw, 0, 0, sw, sh)
        small.recycle()
        val gray = IntArray(px.size) { val c = px[it]; ((c shr 16 and 255) * 3 + (c shr 8 and 255) * 6 + (c and 255)) / 10 }
        val found = detect(gray, sw, sh, rtl)
        if (found.size <= 1) return emptyList()
        val k = pw.toDouble() / sw
        return found.map { Box((it.l * k).roundToInt(), (it.t * k).roundToInt(), (it.r * k).roundToInt(), (it.b * k).roundToInt()) }
    }

    fun crops(page: File, rtl: Boolean, dir: File, tag: String): List<File> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(page.path, o)
        val pw = o.outWidth
        val ph = o.outHeight
        if (pw <= 0 || ph <= 0) return listOf(page)
        val boxes = boxes(page, rtl)
        if (boxes.size <= 1) return listOf(page)
        val k = 1.0
        val dec = BitmapRegionDecoder.newInstance(page.path) ?: return listOf(page)
        dir.mkdirs()
        return try {
            boxes.mapIndexed { i, bx ->
                val pad = max(4, pw / 150)
                val r = Rect(max(0, (bx.l * k).roundToInt() - pad), max(0, (bx.t * k).roundToInt() - pad),
                    min(pw, (bx.r * k).roundToInt() + pad), min(ph, (bx.b * k).roundToInt() + pad))
                val bmp = dec.decodeRegion(r, null)
                val f = File(dir, "${tag}_k$i.jpg")
                f.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 92, it) }
                bmp.recycle()
                f
            }
        } finally {
            dec.recycle()
        }
    }
}
