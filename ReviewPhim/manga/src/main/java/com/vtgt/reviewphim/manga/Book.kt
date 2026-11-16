package com.vtgt.reviewphim.manga

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapRegionDecoder
import android.graphics.Color
import android.graphics.Rect
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.provider.DocumentsContract
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.util.zip.ZipFile
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Một trang truyện tranh đã chuẩn hóa (trang dài kiểu webtoon được cắt thành nhiều khúc). */
data class Page(val file: File, val w: Int, val h: Int, val label: String, val strip: Boolean = false)

/** Ảnh minh họa trong light novel, nằm ở vị trí ký tự `pos` của văn bản. */
data class Illus(val pos: Int, val file: File)

/** Truyện đã nhập: truyện tranh (pages) hoặc tiểu thuyết (text + ảnh minh họa). */
data class Book(val kind: String, val title: String, val pages: List<Page> = emptyList(), val text: String = "",
                val illus: List<Illus> = emptyList(), val cover: File? = null) {
    val manga get() = kind == "manga"
    /** Truyện cuộn dọc (manhwa / webtoon): các khúc đã cắt theo khoảng trắng, không tách khung nữa. */
    val webtoon get() = pages.count { it.strip } * 2 > pages.size
}

object Books {
    const val MAX_W = 1080
    private val IMG = Regex("(?i)\\.(jpe?g|png|webp|gif|bmp|avif|heic)$")

    /** So sánh tên file theo số (trang 2 trước trang 10). */
    val natural = Comparator<String> { a, b ->
        val ra = Regex("\\d+|\\D+").findAll(a.lowercase()).map { it.value }.toList()
        val rb = Regex("\\d+|\\D+").findAll(b.lowercase()).map { it.value }.toList()
        for (i in 0 until min(ra.size, rb.size)) {
            val x = ra[i]
            val y = rb[i]
            val c = if (x[0].isDigit() && y[0].isDigit()) {
                val d = x.trimStart('0').length - y.trimStart('0').length
                if (d != 0) d else x.trimStart('0').compareTo(y.trimStart('0'))
            } else x.compareTo(y)
            if (c != 0) return@Comparator c
        }
        ra.size - rb.size
    }

    fun isImage(name: String) = IMG.containsMatchIn(name)

    fun displayName(ctx: Context, uri: Uri): String {
        try {
            ctx.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0)?.let { return it }
            }
        } catch (_: Exception) {
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "truyen"
    }

    fun titleOf(name: String) = name.substringBeforeLast('.').replace('_', ' ').replace(Regex("\\s+"), " ").trim()

    // ------------------------------------------------------------------ nhập
    /** Nhiều ảnh trang chọn từ thư viện / file. */
    suspend fun fromImages(ctx: Context, uris: List<Uri>, dir: File, layout: String = "auto", progress: (Float) -> Unit): List<Page> {
        val named = uris.map { it to displayName(ctx, it) }.sortedWith { a, b -> natural.compare(a.second, b.second) }
        return pagesFrom(named.size, dir, layout, progress) { i, out ->
            ctx.contentResolver.openInputStream(named[i].first)?.use { s -> out.outputStream().use { s.copyTo(it) } }
            named[i].second
        }
    }

    /** Cả thư mục ảnh (chọn bằng trình chọn thư mục của Android). */
    suspend fun fromTree(ctx: Context, tree: Uri, dir: File, layout: String = "auto", progress: (Float) -> Unit): Pair<String, List<Page>> {
        val r = ctx.contentResolver
        val root = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        val items = mutableListOf<Pair<Uri, String>>()
        r.query(root, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME),
            null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val name = c.getString(1) ?: continue
                if (isImage(name)) items += DocumentsContract.buildDocumentUriUsingTree(tree, c.getString(0)) to name
            }
        }
        if (items.isEmpty()) throw IllegalStateException("Thư mục không có ảnh nào.")
        items.sortWith { a, b -> natural.compare(a.second, b.second) }
        val title = DocumentsContract.getTreeDocumentId(tree).substringAfterLast('/').substringAfterLast(':')
        return titleOf(title) to pagesFrom(items.size, dir, layout, progress) { i, out ->
            r.openInputStream(items[i].first)?.use { s -> out.outputStream().use { s.copyTo(it) } }
            items[i].second
        }
    }

    /** CBZ / ZIP chứa ảnh trang. */
    suspend fun fromZip(zip: File, dir: File, layout: String = "auto", progress: (Float) -> Unit): List<Page> = ZipFile(zip).use { z ->
        val entries = z.entries().toList().filter { !it.isDirectory && isImage(it.name) && !it.name.contains("__MACOSX") }
            .sortedWith { a, b -> natural.compare(a.name, b.name) }
        if (entries.isEmpty()) throw IllegalStateException("File nén không có ảnh nào.")
        pagesFrom(entries.size, dir, layout, progress) { i, out ->
            z.getInputStream(entries[i]).use { s -> out.outputStream().use { s.copyTo(it) } }
            entries[i].name.substringAfterLast('/')
        }
    }

    /** PDF: vẽ từng trang thành ảnh. */
    suspend fun fromPdf(pdf: File, dir: File, progress: (Float) -> Unit): List<Page> = withContext(Dispatchers.IO) {
        dir.mkdirs()
        val out = mutableListOf<Page>()
        PdfRenderer(android.os.ParcelFileDescriptor.open(pdf, android.os.ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
            for (i in 0 until r.pageCount) {
                currentCoroutineContext().ensureActive()
                r.openPage(i).use { p ->
                    val w = MAX_W
                    val h = max(1, (w.toDouble() * p.height / p.width).roundToInt())
                    val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                    b.eraseColor(Color.WHITE)
                    p.render(b, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    out += slice(b, dir, "Trang ${i + 1}", out.size)
                    b.recycle()
                }
                progress((i + 1f) / r.pageCount)
            }
        }
        out
    }

    private suspend fun pagesFrom(n: Int, dir: File, layout: String, progress: (Float) -> Unit,
                                  fetch: (Int, File) -> String): List<Page> = withContext(Dispatchers.IO) {
        dir.mkdirs()
        val tmp = File(dir, "src.tmp")
        val out = mutableListOf<Page>()
        val sizes = mutableListOf<Pair<Int, Int>>()
        for (i in 0 until n) {
            currentCoroutineContext().ensureActive()
            fetch(i, tmp)
            try {
                val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(tmp.path, o)
                out += sliceFile(tmp, dir, "Trang ${i + 1}", out.size)
                sizes += o.outWidth to o.outHeight
            } catch (e: Exception) {
                // ảnh hỏng / không đọc được: bỏ qua trang đó
            }
            progress((i + 1f) / n)
        }
        tmp.delete()
        if (out.isEmpty()) throw IllegalStateException("Không đọc được ảnh trang nào.")
        val webtoon = when (layout) {
            "webtoon" -> true
            "page" -> false
            else -> looksWebtoon(sizes)
        }
        if (webtoon) restitch(out, File(dir, "strip")) else out
    }

    /**
     * Ảnh kiểu webtoon (cuộn dọc): có ảnh rất dài, hoặc mọi ảnh cùng chiều rộng mà tỉ lệ không giống trang sách
     * (trang manga / manhua ~1.3-1.6).
     */
    fun looksWebtoon(sizes: List<Pair<Int, Int>>): Boolean {
        if (sizes.isEmpty()) return false
        if (sizes.any { (w, h) -> h > w * 2.2 }) return true
        if (sizes.size < 3) return false
        val w0 = sizes[0].first
        val sameW = sizes.all { abs(it.first - w0) <= max(2, w0 / 100) }
        val ratios = sizes.map { (w, h) -> h.toDouble() / max(1, w) }.sorted()
        val med = ratios[ratios.size / 2]
        return sameW && (med >= 1.65 || med < 1.0)
    }

    /**
     * Webtoon thường bị cắt thành nhiều ảnh cắt ngang khung tranh: nối các khúc liên tiếp lại rồi cắt lại đúng
     * khoảng trắng giữa các khung (cách SmartStitch / StitchTool làm; code tự viết).
     */
    fun restitch(pages: List<Page>, dir: File): List<Page> {
        dir.mkdirs()
        val w = pages.first().w
        val out = mutableListOf<Page>()
        var carry: Bitmap? = null
        fun emit(b: Bitmap) {
            val f = File(dir, "k%05d.jpg".format(out.size))
            f.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 90, it) }
            out += Page(f, b.width, b.height, "Khúc ${out.size + 1}", strip = true)
        }
        for (p in pages) {
            val src = BitmapFactory.decodeFile(p.file.path) ?: continue
            val b = if (src.width == w) src else Bitmap.createScaledBitmap(src, w, max(1, (src.height.toDouble() * w / src.width).roundToInt()), true)
                .also { src.recycle() }
            val c0 = carry
            val combined = if (c0 == null) b else {
                val m = Bitmap.createBitmap(w, c0.height + b.height, Bitmap.Config.ARGB_8888)
                val cv = android.graphics.Canvas(m)
                cv.drawBitmap(c0, 0f, 0f, null)
                cv.drawBitmap(b, 0f, c0.height.toFloat(), null)
                c0.recycle()
                b.recycle()
                m
            }
            if (combined.height <= w * MAX_RATIO) {
                carry = combined
                continue
            }
            val row = IntArray(w)
            val ys = cuts(w, combined.height) { y -> combined.getPixels(row, 0, w, 0, y, w, 1); rowBlank(row) }
            for ((a, c) in ys.zipWithNext().dropLast(1)) {
                val part = Bitmap.createBitmap(combined, 0, a, w, c - a)
                emit(part)
                part.recycle()
            }
            val last = ys[ys.size - 2]
            carry = Bitmap.createBitmap(combined, 0, last, w, combined.height - last)
            combined.recycle()
        }
        carry?.let { emit(it); it.recycle() }
        pages.forEach { it.file.delete() }
        return out
    }

    // ------------------------------------------------------------------ cắt trang dài (webtoon / manhwa)
    /** Chiều cao tối đa của 1 khúc so với chiều rộng (trang thường ~1.4; webtoon dài được cắt). */
    const val MAX_RATIO = 2.0
    const val TARGET_RATIO = 1.5

    /**
     * Chỗ cắt cho 1 dải cao [h] (tính theo chiều rộng [w]): các mốc y, ưu tiên cắt ở hàng "trống" (khoảng trắng /
     * đen giữa các khung tranh) gần mốc 1.5 lần chiều rộng. [blank] cho biết độ "trống" của từng hàng (nhỏ = trống).
     */
    fun cuts(w: Int, h: Int, blank: (Int) -> Double): List<Int> {
        if (h <= w * MAX_RATIO) return listOf(0, h)
        val out = mutableListOf(0)
        var y = 0
        while (h - y > w * MAX_RATIO) {
            val lo = y + (w * 1.1).toInt()
            val hi = min(h - (w * 0.4).toInt(), y + (w * MAX_RATIO).toInt())
            val want = y + (w * TARGET_RATIO).toInt()
            var best = min(want, hi)
            var bestScore = Double.MAX_VALUE
            var r = lo
            val stepRow = max(1, w / 120)
            while (r <= hi) {
                // trống cả một dải ±12 điểm ảnh (cắt giữa khoảng trắng, không sát mép khung tranh) + gần mốc mong muốn
                val s = maxOf(blank(max(0, r - 12)), blank(r), blank(min(h - 1, r + 12))) + abs(r - want).toDouble() / w * 6.0
                if (s < bestScore) {
                    bestScore = s
                    best = r
                }
                r += stepRow
            }
            out += best
            y = best
        }
        out += h
        return out
    }

    /** Độ "trống" của 1 hàng điểm ảnh: độ lệch độ sáng (hàng trắng / đen đều màu = 0). */
    fun rowBlank(px: IntArray): Double {
        var s = 0.0
        var s2 = 0.0
        for (c in px) {
            val v = ((c shr 16 and 255) + (c shr 8 and 255) + (c and 255)) / 3.0
            s += v
            s2 += v * v
        }
        val m = s / px.size
        return kotlin.math.sqrt(max(0.0, s2 / px.size - m * m))
    }

    private fun slice(b: Bitmap, dir: File, label: String, start: Int): List<Page> {
        val row = IntArray(b.width)
        val ys = cuts(b.width, b.height) { y -> b.getPixels(row, 0, b.width, 0, y, b.width, 1); rowBlank(row) }
        return ys.zipWithNext().mapIndexed { k, (a, c) ->
            val part = Bitmap.createBitmap(b, 0, a, b.width, c - a)
            val f = File(dir, "p%05d.jpg".format(start + k))
            f.outputStream().use { part.compress(Bitmap.CompressFormat.JPEG, 90, it) }
            if (part != b) part.recycle()
            Page(f, b.width, c - a, if (ys.size > 2) "$label.${k + 1}" else label)
        }
    }

    /** Ảnh từ file: thu nhỏ về rộng ≤ 1080, trang dài thì đọc từng vùng (không nạp cả dải dài vào bộ nhớ). */
    fun sliceFile(f: File, dir: File, label: String, start: Int): List<Page> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(f.path, o)
        if (o.outWidth <= 0 || o.outHeight <= 0) throw IllegalArgumentException("ảnh hỏng")
        val sample = max(1, Integer.highestOneBit(max(1, o.outWidth / MAX_W)))
        if (o.outHeight <= o.outWidth * MAX_RATIO || o.outHeight / sample < 4096) {
            val b = BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply { inSampleSize = sample })
                ?: throw IllegalArgumentException("ảnh hỏng")
            val s = scaleTo(b, MAX_W)
            return slice(s, dir, label, start).also { if (s != b) s.recycle(); b.recycle() }
        }
        // dải webtoon rất dài: dò chỗ cắt trên bản thu nhỏ, rồi đọc từng vùng
        val dec = BitmapRegionDecoder.newInstance(f.path) ?: throw IllegalArgumentException("ảnh hỏng")
        try {
            val w = o.outWidth
            val h = o.outHeight
            val k = max(1, Integer.highestOneBit(max(1, w / 120)))  // bản dò ~120px rộng
            val tw = w / k
            val row = IntArray(tw)
            val probes = HashMap<Int, Bitmap>()
            fun band(y: Int): Bitmap {
                val i = y / 2048
                return probes.getOrPut(i) {
                    val y0 = i * 2048
                    dec.decodeRegion(Rect(0, y0, w, min(h, y0 + 2048)), BitmapFactory.Options().apply { inSampleSize = k })
                }
            }
            val ys = cuts(w, h) { y ->
                val b = band(y)
                val yy = ((y % 2048) / k).coerceIn(0, b.height - 1)
                b.getPixels(row, 0, min(tw, b.width), 0, yy, min(tw, b.width), 1)
                rowBlank(row.copyOf(min(tw, b.width)))
            }
            probes.values.forEach { it.recycle() }
            return ys.zipWithNext().mapIndexed { n, (a, c) ->
                val part = dec.decodeRegion(Rect(0, a, w, c), BitmapFactory.Options().apply { inSampleSize = sample })
                val s = scaleTo(part, MAX_W)
                val out = File(dir, "p%05d.jpg".format(start + n))
                out.outputStream().use { s.compress(Bitmap.CompressFormat.JPEG, 90, it) }
                val pg = Page(out, s.width, s.height, "$label.${n + 1}")
                if (s != part) s.recycle()
                part.recycle()
                pg
            }
        } finally {
            dec.recycle()
        }
    }

    private fun scaleTo(b: Bitmap, maxW: Int): Bitmap =
        if (b.width <= maxW) b else Bitmap.createScaledBitmap(b, maxW, max(1, (b.height.toDouble() * maxW / b.width).roundToInt()), true)

    // ------------------------------------------------------------------ light novel
    /** Đọc TXT: UTF-8 / UTF-16 (có BOM) / GB18030 (truyện Trung). */
    fun readText(bytes: ByteArray): String {
        if (bytes.size >= 2 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xFE.toByte()) return String(bytes, Charsets.UTF_16LE).drop(1)
        if (bytes.size >= 2 && bytes[0] == 0xFE.toByte() && bytes[1] == 0xFF.toByte()) return String(bytes, Charsets.UTF_16BE).drop(1)
        val u = String(bytes, Charsets.UTF_8).removePrefix("\uFEFF")
        val bad = u.count { it == '\uFFFD' }
        if (bad == 0 || bad * 1000 < u.length) return u   // UTF-8 chuẩn (cho phép vài byte hỏng trong file dài)
        val gb = String(bytes, charset("GB18030"))
        return if (gb.count { it == '\uFFFD' } < bad) gb else u
    }

    /** Bỏ thẻ HTML, giữ xuống dòng theo đoạn; ảnh -> dấu \u0001đường_dẫn\u0001. */
    fun htmlToText(html: String): String {
        var s = html.replace(Regex("(?is)<(script|style|head)[^>]*>.*?</\\1>"), " ")
        s = s.replace(Regex("(?is)<img[^>]*?\\ssrc\\s*=\\s*[\"']([^\"']+)[\"'][^>]*>"), "\n\u0001$1\u0001\n")
        s = s.replace(Regex("(?is)<image[^>]*?href\\s*=\\s*[\"']([^\"']+)[\"'][^>]*>"), "\n\u0001$1\u0001\n")
        s = s.replace(Regex("(?i)<br\\s*/?>|</(p|div|h[1-6]|li|tr|blockquote)>"), "\n")
        s = s.replace(Regex("(?s)<[^>]+>"), "")
        s = s.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"")
            .replace("&#39;", "'").replace("&apos;", "'").replace("&amp;", "&")
        s = Regex("&#(x?)([0-9a-fA-F]+);").replace(s) {
            val v = it.groupValues[2].toIntOrNull(if (it.groupValues[1].isEmpty()) 10 else 16) ?: 32
            String(Character.toChars(v))
        }
        return s.lines().map { it.replace(Regex("[ \\t\\u3000]+"), " ").trim() }.filter { it.isNotEmpty() }.joinToString("\n")
    }

    /** EPUB: văn bản theo thứ tự chương (spine) + ảnh minh họa đúng vị trí + ảnh bìa. */
    suspend fun fromEpub(epub: File, dir: File, progress: (Float) -> Unit): Book = withContext(Dispatchers.IO) {
        dir.mkdirs()
        ZipFile(epub).use { z ->
            fun read(path: String) = z.getEntry(path)?.let { e -> z.getInputStream(e).use { String(it.readBytes(), Charsets.UTF_8) } }
            val container = read("META-INF/container.xml") ?: throw IllegalStateException("EPUB hỏng (thiếu container.xml).")
            val opfPath = Regex("full-path\\s*=\\s*\"([^\"]+)\"").find(container)?.groupValues?.get(1)
                ?: throw IllegalStateException("EPUB hỏng (không thấy file OPF).")
            val opf = read(opfPath) ?: throw IllegalStateException("EPUB hỏng (thiếu $opfPath).")
            val base = opfPath.substringBeforeLast('/', "")
            fun resolve(from: String, href: String): String {
                val h = java.net.URLDecoder.decode(href.substringBefore('#'), "UTF-8")
                val parts = (if (from.isEmpty()) emptyList() else from.split('/')).toMutableList()
                for (p in h.split('/')) when (p) {
                    ".." -> if (parts.isNotEmpty()) parts.removeAt(parts.size - 1)
                    ".", "" -> {}
                    else -> parts += p
                }
                return parts.joinToString("/")
            }
            val items = HashMap<String, Pair<String, String>>()   // id -> (đường dẫn, loại)
            var coverId = Regex("<meta[^>]*name=\"cover\"[^>]*content=\"([^\"]+)\"").find(opf)?.groupValues?.get(1)
            for (m in Regex("(?s)<item\\s([^>]*)/?>").findAll(opf)) {
                val a = m.groupValues[1]
                val id = Regex("\\bid=\"([^\"]+)\"").find(a)?.groupValues?.get(1) ?: continue
                val href = Regex("\\bhref=\"([^\"]+)\"").find(a)?.groupValues?.get(1) ?: continue
                val type = Regex("media-type=\"([^\"]+)\"").find(a)?.groupValues?.get(1) ?: ""
                items[id] = resolve(base, href) to type
                if ("cover-image" in a) coverId = id
            }
            val spine = Regex("<itemref[^>]*idref=\"([^\"]+)\"").findAll(opf).map { it.groupValues[1] }.toList()
            val title = Regex("(?s)<dc:title[^>]*>(.*?)</dc:title>").find(opf)?.groupValues?.get(1)?.trim() ?: titleOf(epub.name)
            val sb = StringBuilder()
            val illus = mutableListOf<Illus>()
            var nImg = 0
            fun saveImage(path: String): File? {
                val e = z.getEntry(path) ?: return null
                val tmp = File(dir, "img.tmp")
                z.getInputStream(e).use { s -> tmp.outputStream().use { s.copyTo(it) } }
                return try {
                    sliceFile(tmp, dir, "Ảnh ${nImg + 1}", 10000 + nImg * 20).firstOrNull()?.file.also { nImg++ }
                } catch (ex: Exception) {
                    null
                } finally {
                    tmp.delete()
                }
            }
            for ((k, id) in spine.withIndex()) {
                currentCoroutineContext().ensureActive()
                val (path, type) = items[id] ?: continue
                if ("html" !in type && !path.endsWith("html", true) && !path.endsWith("htm", true)) continue
                val html = read(path) ?: continue
                val from = path.substringBeforeLast('/', "")
                for ((n, part) in htmlToText(html).split('\u0001').withIndex()) {
                    if (part.isBlank()) continue
                    if (n % 2 == 1) {  // giữa 2 dấu \u0001 là đường dẫn ảnh
                        if (isImage(part.trim())) saveImage(resolve(from, part.trim()))?.let { illus += Illus(sb.length, it) }
                    } else {
                        sb.append(part.trim()).append("\n\n")
                    }
                }
                progress((k + 1f) / spine.size)
            }
            val cover = coverId?.let { items[it] }?.let { saveImage(it.first) } ?: illus.firstOrNull()?.file
            if (sb.isBlank()) throw IllegalStateException("EPUB không có chữ nào đọc được.")
            Book("novel", title, text = sb.toString().trim(), illus = illus, cover = cover)
        }
    }

    /**
     * Chia văn bản dài thành các phần ~[size] ký tự theo đoạn văn (để AI tóm tắt từng phần).
     * Trả về (vị trí bắt đầu, nội dung).
     */
    fun chunks(text: String, size: Int): List<Pair<Int, String>> {
        val out = mutableListOf<Pair<Int, String>>()
        var start = 0
        while (start < text.length) {
            var end = min(text.length, start + size)
            if (end < text.length) {
                val nl = text.lastIndexOf('\n', end)
                if (nl > start + size / 2) end = nl + 1
                else {
                    val dot = text.lastIndexOfAny(charArrayOf('.', '。', '!', '?', '！', '？'), end)
                    if (dot > start + size / 2) end = dot + 1
                }
            }
            out += start to text.substring(start, end).trim()
            start = end
        }
        return out.filter { it.second.isNotBlank() }
    }
}
