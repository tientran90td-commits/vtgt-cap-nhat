package com.vtgt.reviewphim

import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

/** Một câu lời gốc (và bản dịch tiếng Việt nếu có). Thời gian tính bằng giây. */
data class Line(val start: Double, val end: Double, val text: String, var vi: String = "")

/** Một đoạn lời kể review: cảnh minh họa bắt đầu ở `start` (giây) trong video gốc. */
data class Seg(var start: Double, var text: String, var end: Double = -1.0)

/** Một dòng phụ đề hiện trên video thành phẩm. */
data class Cue(val start: Double, val end: Double, val text: String)

fun fmtTime(s: Double): String {
    val t = max(0, s.toInt())
    return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%02d:%02d".format(t / 60, t % 60)
}

/** Chữ Hán / Nhật / Hàn / Thái còn sót trong câu dịch. */
val FOREIGN = Regex("[\\u3040-\\u30ff\\u3400-\\u9fff\\uac00-\\ud7af\\u0e00-\\u0e7f]")

/** Đọc JSON trong câu trả lời của AI (bỏ ```json, chữ thừa trước/sau, dấu phẩy thừa). */
fun extractJson(text: String): JSONObject {
    val s = text.indexOf('{')
    val e = text.lastIndexOf('}')
    if (s < 0 || e <= s) throw IllegalArgumentException("AI không trả về JSON: " + text.take(200))
    val body = text.substring(s, e + 1)
    return try {
        JSONObject(body)
    } catch (ex: Exception) {
        JSONObject(body.replace(Regex(",\\s*([}\\]])"), "$1"))
    }
}

/** Đọc file phụ đề bất kỳ: .ass / .ssa (anime), .srt, .vtt. */
fun parseSubs(text: String): List<Line> = if (text.contains("[Events]") && text.contains("Dialogue:")) parseAss(text)
else parseSrt(text)

/**
 * Phụ đề .ass (fansub anime): bỏ mã hiệu ứng {\...}, hình vẽ, lời bài hát OP/ED (karaoke), chữ trên biển hiệu,
 * gộp dòng trùng (nhiều lớp hiệu ứng) - chỉ giữ lời thoại cho AI (ý tưởng từ subtitle-translator, MIT).
 */
fun parseAss(text: String): List<Line> {
    var fmt = listOf("Layer", "Start", "End", "Style", "Name", "MarginL", "MarginR", "MarginV", "Effect", "Text")
    val skipStyle = Regex("(?i)\\b(op|ed|opening|ending|song|lyrics?|karaoke|kara|signs?|title|insert|note)\\b|^(op|ed)")
    val out = mutableListOf<Line>()
    fun t(s: String): Double {
        val p = s.trim().split(":")
        return if (p.size == 3) p[0].toDouble() * 3600 + p[1].toDouble() * 60 + p[2].toDouble() else 0.0
    }
    for (raw in text.replace("\r", "").lines()) {
        val ln = raw.trim()
        if (ln.startsWith("Format:", true)) fmt = ln.substringAfter(":").split(",").map { it.trim() }
        if (!ln.startsWith("Dialogue:", true)) continue
        val parts = ln.substringAfter(":").split(",", limit = fmt.size)
        if (parts.size < fmt.size) continue
        val get = { k: String -> parts.getOrNull(fmt.indexOfFirst { it.equals(k, true) })?.trim() ?: "" }
        val body = get("Text")
        val style = get("Style") + " " + get("Name") + " " + get("Effect")
        if (skipStyle.containsMatchIn(style.replace('_', ' ')) || Regex("(?i)\\\\k[fo]?\\d").containsMatchIn(body) ||
            Regex("(?i)\\\\p[1-9]").containsMatchIn(body)) continue
        val clean = body.replace(Regex("\\{[^}]*}"), "").replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
            .replace(Regex("\\s+"), " ").trim()
        if (clean.isEmpty()) continue
        val a = t(get("Start"))
        val b = t(get("End"))
        val prev = out.lastOrNull()
        if (prev != null && prev.text == clean && a - prev.end < 0.5) {
            out[out.size - 1] = prev.copy(end = maxOf(prev.end, b))
            continue
        }
        if (out.any { it.text == clean && kotlin.math.abs(it.start - a) < 0.05 }) continue  // lớp trùng
        out.add(Line(a, b, clean))
    }
    return out.sortedBy { it.start }
}

/** Đọc file phụ đề .srt / .vtt (vtt có thể thiếu giờ: 00:01.000). */
fun parseSrt(text: String): List<Line> {
    val re = Regex("(?:(\\d+):)?(\\d+):(\\d+)[,.](\\d+)\\s*-->\\s*(?:(\\d+):)?(\\d+):(\\d+)[,.](\\d+)")
    val out = mutableListOf<Line>()
    val rows = text.replace("\r", "").split("\n")
    var i = 0
    while (i < rows.size) {
        val m = re.find(rows[i])
        if (m == null) {
            i++
            continue
        }
        val g = m.groupValues.drop(1).map { it.toDoubleOrNull() ?: 0.0 }
        val a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        val b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        i++
        val sb = StringBuilder()
        while (i < rows.size && rows[i].isNotBlank()) {
            if (re.containsMatchIn(rows[i]) || rows[i].trim().startsWith("```")) break  // AI hay bọc trong ```srt ... ```
            sb.append(' ').append(rows[i].trim())
            i++
        }
        val t = sb.toString().replace(Regex("<[^>]+>|\\{[^}]+}"), "").trim()
        if (t.isNotEmpty()) out.add(Line(a, b, t))
    }
    return out
}

/** Lời thoại AI chép lại: SRT, hoặc từng dòng "[mm:ss] câu" / "mm:ss - câu". `offset`: giây cộng thêm (file chia phần). */
fun parseTimed(text: String, offset: Double = 0.0): List<Line> {
    val srt = parseSrt(text)
    if (srt.isNotEmpty()) return srt.map { Line(it.start + offset, it.end + offset, it.text) }
    val re = Regex("^\\s*\\[?(?:(\\d{1,2}):)?(\\d{1,2}):(\\d{2})(?:[.,](\\d+))?\\]?\\s*[-–:]?\\s*(.+?)\\s*$", RegexOption.MULTILINE)
    val pts = re.findAll(text).map { m ->
        val (h, mi, s, frac, t) = m.destructured
        val sec = (h.toDoubleOrNull() ?: 0.0) * 3600 + mi.toDouble() * 60 + s.toDouble() + ("0.$frac".toDoubleOrNull() ?: 0.0)
        sec to t.trim()
    }.filter { it.second.isNotEmpty() }.toList()
    return pts.mapIndexed { i, (a, t) ->
        val b = pts.getOrNull(i + 1)?.first ?: (a + 3.0)
        Line(a + offset, minOf(b, a + 8.0) + offset, t)
    }
}

fun toSrt(cues: List<Cue>): String {
    fun ts(t: Double): String {
        val ms = (t * 1000).toLong()
        return "%02d:%02d:%02d,%03d".format(ms / 3600000, ms / 60000 % 60, ms / 1000 % 60, ms % 1000)
    }
    return cues.mapIndexed { i, c -> "${i + 1}\n${ts(c.start)} --> ${ts(c.end)}\n${c.text}\n" }.joinToString("\n")
}

/** Chia lời kể dài thành các dòng phụ đề ngắn (ngắt ở dấu câu, rồi ở khoảng trắng). */
fun chunkText(text: String, maxChars: Int): List<String> {
    val parts = text.trim().split(Regex("(?<=[.!?…;:,])\\s+")).map { it.trim() }.filter { it.isNotEmpty() }
    val out = mutableListOf<String>()
    for (p in parts) {
        if (p.length <= maxChars) {
            if (out.isNotEmpty() && out.last().length + 1 + p.length <= maxChars && out.last().length < maxChars / 2) {
                out[out.size - 1] = out.last() + " " + p
            } else {
                out.add(p)
            }
            continue
        }
        var cur = StringBuilder()
        for (w in p.split(Regex("\\s+"))) {
            if (cur.isNotEmpty() && cur.length + 1 + w.length > maxChars) {
                out.add(cur.toString())
                cur = StringBuilder()
            }
            if (cur.isNotEmpty()) cur.append(' ')
            cur.append(w)
        }
        if (cur.isNotEmpty()) out.add(cur.toString())
    }
    return out
}

/** Rải các dòng phụ đề của một đoạn lời kể theo độ dài chữ trong khoảng [start, start + dur]. */
fun splitCues(text: String, start: Double, dur: Double, maxChars: Int): List<Cue> {
    val chunks = chunkText(text, maxChars)
    if (chunks.isEmpty()) return emptyList()
    val total = chunks.sumOf { it.length }.toDouble()
    var t = start
    return chunks.map { c ->
        val d = dur * c.length / total
        val cue = Cue(t, t + d, c)
        t += d
        cue
    }
}

/** Tỉ lệ giống nhau của 2 chuỗi (0..1), dùng để gộp các khung hình OCR cùng một câu phụ đề. */
fun similarity(a: String, b: String): Double {
    if (a == b) return 1.0
    if (a.isEmpty() || b.isEmpty()) return 0.0
    val x = a.take(80)
    val y = b.take(80)
    var prev = IntArray(y.length + 1) { it }
    for (i in 1..x.length) {
        val cur = IntArray(y.length + 1)
        cur[0] = i
        for (j in 1..y.length) {
            cur[j] = min(min(cur[j - 1] + 1, prev[j] + 1), prev[j - 1] + if (x[i - 1] == y[j - 1]) 0 else 1)
        }
        prev = cur
    }
    return 1.0 - prev[y.length].toDouble() / max(x.length, y.length)
}

/** Số ký tự tiếng Việt đọc được mỗi giây ở tốc độ bình thường. */
const val CPS = 14.5

/** Số ký tự tối đa để đọc kịp câu thứ i (tới đầu câu sau, tối đa thêm 1.5 giây). */
fun maxChars(lines: List<Line>, i: Int): Int {
    val ln = lines[i]
    val nxt = lines.getOrNull(i + 1)
    val own = ln.end - ln.start
    val slot = max(own, min((nxt?.start ?: (ln.end + 1.0)) - ln.start, own + 1.5))
    return max(8, (slot * CPS).toInt())
}

/** Lời thoại ĐÁNH SỐ để AI chỉ rõ đoạn kể nằm ở câu nào (#from - #to) -> app lấy đúng hình của các câu đó. */
fun transcriptIds(lines: List<Line>, limit: Int = 60000): String {
    if (lines.isEmpty()) return ""
    var group = 1
    while (true) {
        val blocks = lines.indices.chunked(group)
        val cap = max(40, limit / blocks.size - 24)
        val sb = StringBuilder()
        for (b in blocks) {
            val id = if (b.size == 1) "#${b[0] + 1}" else "#${b.first() + 1}-${b.last() + 1}"
            val txt = b.joinToString(" ") { lines[it].text.trim() }.take(cap)
            sb.append(id).append(" [").append(fmtTime(lines[b.first()].start)).append("] ").append(txt).append('\n')
        }
        if (sb.length <= limit || group >= 64) return sb.toString().take(limit)
        group *= 2
    }
}

/** Lời thoại có mốc thời gian để gửi AI. Phim dài: gộp theo khoảng thời gian và cắt bớt chữ mỗi khoảng cho vừa giới hạn. */
fun transcriptText(lines: List<Line>, limit: Int = 60000): String {
    if (lines.isEmpty()) return ""
    var window = 0.0
    while (true) {
        val buckets = mutableListOf<Pair<Double, StringBuilder>>()
        for (ln in lines) {
            if (buckets.isEmpty() || ln.start - buckets.last().first >= window) buckets.add(ln.start to StringBuilder())
            buckets.last().second.append(ln.text.trim()).append(' ')
        }
        val cap = max(40, limit / buckets.size - 10)
        val sb = StringBuilder()
        for ((t, text) in buckets) {
            sb.append('[').append(fmtTime(t)).append("] ").append(text.toString().trim().take(cap)).append('\n')
        }
        if (sb.length <= limit || window >= 640) return sb.toString().take(limit)
        window = if (window == 0.0) 10.0 else window * 2
    }
}
