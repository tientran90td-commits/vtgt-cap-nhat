package com.vtgt.reviewphim.manga

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import com.vtgt.reviewphim.CPS
import com.vtgt.reviewphim.Line
import com.vtgt.reviewphim.Prefs
import com.vtgt.reviewphim.Prompts
import java.io.File
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Một dòng diễn biến của truyện: trang tranh (manga) hoặc ý chính một phần văn bản (light novel). */
data class Item(val text: String, val page: Int = -1, val pos: Int = 0, val label: String = "")

/** Ảnh ghép tối đa 4 trang (ghi "P12" trên mỗi trang) để AI đọc tranh. */
data class PageSheet(val file: File, val pages: List<Int>)

object Story {
    const val PER_SHEET = 4
    const val CELL_H = 900

    /**
     * Ghép trang thành ảnh để gửi AI nhìn (ít ảnh hơn, đỡ số lần gửi). [panels]: khung tranh của từng trang
     * (tọa độ ảnh gốc) -> vẽ số khung tròn đỏ 1, 2, 3... để AI tả theo từng khung và lời kể chỉ đúng khung.
     */
    fun sheets(pages: List<Page>, dir: File, panels: ((Int) -> List<Box>)? = null): List<PageSheet> {
        dir.mkdirs()
        return pages.indices.chunked(PER_SHEET).mapIndexed { n, idx ->
            val cells = idx.map { i ->
                val ob = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(pages[i].file.path, ob)
                val o = BitmapFactory.Options().apply {
                    inSampleSize = max(1, Integer.highestOneBit(max(1, ob.outHeight / CELL_H)))
                }
                val b = BitmapFactory.decodeFile(pages[i].file.path, o) ?: Bitmap.createBitmap(10, 10, Bitmap.Config.ARGB_8888)
                val w = max(1, (b.width.toDouble() * CELL_H / b.height).roundToInt())
                val cell = Bitmap.createScaledBitmap(b, w, CELL_H, true).also { if (it != b) b.recycle() }
                val boxes = panels?.invoke(i) ?: emptyList()
                if (boxes.size > 1 && ob.outHeight > 0) {
                    val m = if (cell.isMutable) cell else cell.copy(Bitmap.Config.ARGB_8888, true).also { cell.recycle() }
                    val cv = Canvas(m)
                    val k = CELL_H.toFloat() / ob.outHeight
                    val r = 22f
                    val red = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(220, 30, 40) }
                    val white = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                        color = Color.WHITE; textSize = 30f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
                        textAlign = Paint.Align.CENTER
                    }
                    boxes.forEachIndexed { j, bx ->
                        val cx = bx.l * k + r + 6
                        val cy = bx.t * k + r + 6 + if (bx.t * k < 80) 70 else 0   // tránh đè số trang
                        cv.drawCircle(cx, cy, r, red)
                        cv.drawText("${j + 1}", cx, cy + 11f, white)
                    }
                    m
                } else cell
            }
            val gap = 12
            val sheet = Bitmap.createBitmap(cells.sumOf { it.width } + gap * (cells.size - 1), CELL_H, Bitmap.Config.ARGB_8888)
            val c = Canvas(sheet)
            c.drawColor(Color.rgb(30, 30, 30))
            val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.rgb(255, 214, 64); textSize = 54f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            }
            val bg = Paint().apply { color = Color.argb(215, 0, 0, 0) }
            var x = 0
            for ((k, b) in cells.withIndex()) {
                c.drawBitmap(b, null, Rect(x, 0, x + b.width, CELL_H), null)
                val label = "P${idx[k] + 1}"
                val tw = txt.measureText(label)
                c.drawRoundRect(RectF(x + 4f, 4f, x + tw + 24f, 72f), 10f, 10f, bg)
                c.drawText(label, x + 14f, 58f, txt)
                x += b.width + gap
                b.recycle()
            }
            val f = File(dir, "doc_%03d.jpg".format(n + 1))
            f.outputStream().use { sheet.compress(Bitmap.CompressFormat.JPEG, 80, it) }
            sheet.recycle()
            PageSheet(f, idx)
        }
    }

    // ------------------------------------------------------------------ yêu cầu gửi AI
    /** Nhờ AI nhìn các trang truyện tranh và tả diễn biến từng trang. */
    fun readPages(title: String, part: Int, parts: Int, images: Int, first: Int, last: Int, prefs: Prefs,
                  prev: List<String> = emptyList(), numbered: Boolean = false): String = """
Mình gửi kèm $images ảnh, mỗi ảnh ghép tối đa $PER_SHEET trang truyện tranh của "$title"${if (parts > 1) " (phần $part/$parts)" else ""}. Góc trên bên trái mỗi trang có số trang màu vàng (P$first ... P$last). Đọc lần lượt theo số trang.

Hãy ĐỌC KỸ từng trang (tranh + chữ trong khung thoại, truyện Nhật đọc từ phải sang trái) và viết lại diễn biến bằng tiếng Việt:
${if (numbered) "- Các khung tranh trong trang có SỐ TRÒN ĐỎ (1, 2, 3...). Mỗi trang đúng 1 dòng, tả theo từng khung, dạng: P12 | (1) ai làm gì... (2) chuyện gì xảy ra, lời thoại quan trọng dịch sang tiếng Việt trong ngoặc kép... (3) ...\n- Trang không có số khung thì tả cả trang." else "- Mỗi trang đúng 1 dòng, dạng: P12 | ai làm gì, chuyện gì xảy ra, lời thoại quan trọng (dịch sang tiếng Việt, để trong ngoặc kép)."}
- Không bỏ trang nào trong P$first–P$last. Trang chỉ có tranh hành động thì tả hành động (đánh nhau, chiêu thức, rượt đuổi, biểu cảm...). Trang bìa / quảng cáo / lời tác giả ghi "P.. | (bỏ qua)".
- Gọi nhân vật đúng tên trong truyện, thống nhất từ đầu tới cuối; chưa biết tên thì tả ngoại hình.
- Chỉ viết những gì có trên trang, không đoán thêm.
${Prompts.NAME_RULES}
${Prompts.glossary(prefs)}
${memory(prev)}
Chỉ trả lời các dòng "P.. | ...", không giải thích gì thêm.
""".trim()

    /** Mạch truyện của lần trước (để AI nối đúng diễn biến và gọi tên thống nhất giữa các lần gửi). */
    private fun memory(prev: List<String>): String =
        if (prev.isEmpty()) "" else "\nDIỄN BIẾN NGAY TRƯỚC ĐÓ (chỉ để nối mạch và giữ tên nhân vật, KHÔNG viết lại):\n" +
            prev.takeLast(8).joinToString("\n") { "- " + it.take(220) } + "\n"

    private val PAGE_ROW = Regex("^[\\s*\\-•#>]*(?:P|Trang|Page|p)\\s*\\.?\\s*(\\d{1,4})[\\s*]*[|:\\-–.)]+\\s*(.+)$", RegexOption.IGNORE_CASE)

    /** Câu trả lời đọc tranh -> mô tả theo số trang (chỉ nhận trang trong [first, last]). */
    fun parsePages(text: String, first: Int, last: Int): Map<Int, String> {
        val out = LinkedHashMap<Int, String>()
        for (l in text.lines()) {
            val m = PAGE_ROW.find(l.trim()) ?: continue
            val p = m.groupValues[1].toInt()
            val d = m.groupValues[2].replace("**", "").trim()
            if (p !in first..last || d.length < 2) continue
            if (d.lowercase().contains("bỏ qua") && d.length < 20) continue
            out[p] = if (out.containsKey(p)) out[p] + " " + d else d
        }
        return out
    }

    /** Nhờ AI tóm tắt chi tiết 1 phần light novel thành các ý theo thứ tự. */
    fun novelNotes(title: String, part: Int, parts: Int, text: String, prefs: Prefs, prev: List<String> = emptyList()): String = """
Dưới đây là phần $part/$parts của light novel / tiểu thuyết "$title". Hãy tóm tắt CHI TIẾT phần này bằng tiếng Việt thành các ý theo đúng thứ tự diễn biến, để sau đó làm video kể lại truyện.
- Mỗi ý 1 dòng, bắt đầu bằng "- ", 1–2 câu: ai làm gì, ở đâu, vì sao, kết quả; giữ các chi tiết quan trọng, lời thoại then chốt, cảnh hành động, bí mật được hé lộ, cảm xúc nhân vật.
- Khoảng ${(text.length / 900).coerceIn(6, 30)} ý. Chỉ kể những gì có trong đoạn văn, không bịa, không bình luận.
- Tên nhân vật / địa danh / chiêu thức thống nhất, đúng quy tắc tên riêng bên dưới.
${Prompts.NAME_RULES}
${Prompts.glossary(prefs)}
${memory(prev)}
Chỉ trả lời các dòng "- ...", không giải thích.

VĂN BẢN:
$text
""".trim()

    /** Câu trả lời tóm tắt -> các ý (bỏ đầu mục, dòng tiêu đề). */
    fun parseNotes(text: String): List<String> = text.lines().map { it.trim() }
        .filter { Regex("^([-•*+]|\\d{1,3}[.)])\\s+").containsMatchIn(it) }
        .map { it.replace(Regex("^([-•*+]|\\d{1,3}[.)])\\s+"), "").replace("**", "").trim() }
        .filter { it.length >= 8 }

    /** Truyện ngắn: chia thẳng văn bản thành các ý ~[size] ký tự (không cần AI tóm tắt trước). */
    fun rawItems(text: String, size: Int = 600): List<Item> {
        val out = mutableListOf<Item>()
        var pos = 0
        val sb = StringBuilder()
        var at = 0
        for (para in text.split('\n')) {
            if (sb.isEmpty()) at = pos
            if (para.isNotBlank()) sb.append(para.trim()).append(' ')
            pos += para.length + 1
            if (sb.length >= size) {
                out += Item(sb.toString().trim(), pos = at)
                sb.clear()
            }
        }
        if (sb.isNotBlank()) out += Item(sb.toString().trim(), pos = at)
        return out
    }

    /** Viết kịch bản video recap từ diễn biến (đánh số). */
    fun script(title: String, manga: Boolean, items: List<Item>, targetSec: Int, style: String, prefs: Prefs): String {
        val syncRule = if (!manga) "" else "\n- KHỚP TRANH VỚI LỜI: cuối MỖI CÂU trong \"text\" ghi câu đó kể dòng nào: [#12], hoặc đúng khung tranh nếu dòng có số khung (1), (2)...: [#12.2]. Video chiếu đúng tranh đó trong lúc đọc câu đó (ký hiệu này không được đọc lên). Ví dụ: \"Jin-Woo bước vào hầm ngục [#12.1]. Bức tượng khổng lồ bỗng mở mắt [#12.3].\""
        val chars = (targetSec * CPS).toInt()
        val n = (targetSec / 11).coerceIn(4, 90)
        val body = StringBuilder()
        for ((k, it) in items.withIndex()) {
            body.append('#').append(k + 1).append(" [").append(it.label).append("] ").append(it.text.take(700)).append('\n')
        }
        return """
Bạn là biên kịch kênh REVIEW / TÓM TẮT TRUYỆN tiếng Việt trên TikTok / YouTube. Dưới đây là diễn biến của ${if (manga) "truyện tranh" else "light novel / tiểu thuyết"} "$title" (${if (manga) "AI đã đọc từng trang tranh" else "tóm tắt theo thứ tự"}), mỗi dòng đánh số. Hãy viết kịch bản video kể lại truyện bằng tiếng Việt chuẩn, có dấu đầy đủ.

${Prompts.NAME_RULES}

Yêu cầu kịch bản:
- Văn phong: ${Prompts.STYLES[style] ?: Prompts.STYLES.values.first()}. Câu ngắn, dễ đọc thành tiếng, không ký hiệu lạ, không emoji, không chú thích.
- Đoạn 1 là "hook": 1–2 câu gây tò mò lấy từ khoảnh khắc kịch tính nhất.
- Từ đoạn 2 kể theo đúng trình tự, đủ mở đầu – diễn biến & xung đột – cao trào & kết (hoặc cái kết bỏ ngỏ để người xem chờ phần sau). Kể cả cảnh hành động, không chỉ lời thoại.
- Tổng lời kể khoảng $chars ký tự (đọc khoảng ${targetSec / 60} phút ${targetSec % 60} giây), chia khoảng $n đoạn, mỗi đoạn 1–3 câu (80–250 ký tự).
- CHỈ kể những gì có trong diễn biến bên dưới, không bịa thêm tình tiết / kết cục từ hiểu biết bên ngoài.
- Mỗi đoạn ghi rõ nó kể các dòng số mấy: "from" và "to" là số thứ tự dòng (#) bên dưới. Video sẽ chiếu ${if (manga) "đúng các trang tranh" else "ảnh minh họa"} của các dòng đó, nên lời kể phải khớp.$syncRule
- Từ đoạn 2 trở đi "from" tăng dần, không chồng nhau, rải từ đầu tới cuối truyện.
${Prompts.glossary(prefs)}

Chỉ trả lời JSON, không giải thích:
{"title": "tiêu đề video hấp dẫn, tối đa 70 ký tự", "segments": [{"from": 1, "to": 4, "text": "lời kể..."}], "names": {"tên gốc": "tên tiếng Việt đã dùng"}}

DIỄN BIẾN:
$body
""".trim()
    }

    /** Dòng diễn biến dưới dạng "câu thoại" có thời gian giả = số thứ tự (để dùng lại Prompts.parseRecap). */
    fun asLines(items: List<Item>): List<Line> = items.mapIndexed { k, it -> Line(k.toDouble(), k + 1.0, it.text) }

    /**
     * Ảnh minh họa cho đoạn kể [a, b) (chỉ số dòng diễn biến):
     * - manga: các trang của các dòng đó;
     * - light novel: ảnh minh họa nằm trong khoảng văn bản đó, không có thì ảnh gần nhất phía trước, rồi ảnh bìa.
     */
    fun visuals(book: Book, items: List<Item>, a: Int, b: Int): List<File> {
        if (items.isEmpty()) return listOfNotNull(book.cover)
        val lo = a.coerceIn(0, items.size - 1)
        val hi = b.coerceIn(lo + 1, items.size)
        if (book.manga) {
            return (lo until hi).mapNotNull { items[it].page.takeIf { p -> p in book.pages.indices }?.let { p -> book.pages[p].file } }
                .ifEmpty { listOfNotNull(book.pages.getOrNull(items[lo].page)?.file ?: book.pages.firstOrNull()?.file) }
        }
        val p0 = items[lo].pos
        val p1 = items.getOrNull(hi)?.pos ?: Int.MAX_VALUE
        val inside = book.illus.filter { it.pos in p0 until p1 }.map { it.file }
        if (inside.isNotEmpty()) return inside
        val before = book.illus.lastOrNull { it.pos < p0 }?.file
        return listOfNotNull(before ?: book.cover ?: book.illus.firstOrNull()?.file)
    }

    /** Chia [dur] giây cho các ảnh: mỗi ảnh ≥ [minEach] giây, nhiều ảnh quá thì lấy rải đều. */
    fun share(files: List<File>, dur: Double, minEach: Double = 2.2): List<Pair<File, Double>> {
        if (files.isEmpty()) return emptyList()
        val k = max(1, min(files.size, (dur / minEach).toInt()))
        val pick = if (k >= files.size) files else (0 until k).map { files[it * files.size / k] }
        return pick.map { it to dur / pick.size }
    }
}
