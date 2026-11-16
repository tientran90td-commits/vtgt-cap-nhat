package com.vtgt.reviewphim.longvid

import com.vtgt.reviewphim.CPS
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Một phần của video dài: 1 chương truyện chữ / 1 chương truyện tranh / 1 tập phim.
 * Mỗi phần làm xong riêng (hiểu nội dung -> lời đọc -> video phần) và lưu lại, nên dừng giữa chừng vẫn làm tiếp được.
 */
class Part(
    /** Tên thư mục riêng của phần (không đổi khi xóa / thêm phần khác). */
    val id: String,
    var name: String,
    /** Số đo độ dài nguồn: số ký tự (truyện chữ), số trang (truyện tranh), số giây (phim). */
    var weight: Double,
    /** 0 = mới, 1 = đã có lời đọc / kịch bản, 2 = đã dựng xong video phần. */
    var state: Int = 0,
    var dur: Double = 0.0,
    var error: String = "",
) {
    fun json(): JSONObject = JSONObject().put("id", id).put("name", name).put("weight", weight).put("state", state).put("dur", dur).put("error", error)

    companion object {
        fun of(o: JSONObject) = Part(o.optString("id"), o.optString("name"), o.optDouble("weight", 1.0), o.optInt("state"), o.optDouble("dur"),
            o.optString("error"))
    }
}

/** Dự án video dài, lưu ở thư mục riêng: project.json + parts/NNN/ (nguồn, lời đọc, kịch bản, video phần). */
class Project(val dir: File) {
    var kind = "novel"          // novel | manga | film
    var title = ""
    var mode = "verbatim"       // truyện chữ: verbatim (đọc nguyên văn, dịch nếu cần) | retell (AI kể lại)
    var targetMin = 120         // độ dài mong muốn (kể lại / truyện tranh / phim)
    var cover = ""              // ảnh bìa (truyện chữ)
    val parts = mutableListOf<Part>()
    var memory = ""             // tóm tắt ngắn phần đã làm (để AI nối mạch các phần sau)
    var created = System.currentTimeMillis()

    fun partDir(p: Part) = File(dir, "parts/${p.id}").apply { mkdirs() }

    /** Thêm phần mới (thư mục riêng). */
    fun newPart(name: String, weight: Double): Part {
        var n = parts.size
        while (File(dir, "parts/%05d".format(n)).exists() || parts.any { it.id == "%05d".format(n) }) n++
        return Part("%05d".format(n), name, weight).also { parts += it; partDir(it) }
    }

    fun save() {
        dir.mkdirs()
        val o = JSONObject().put("kind", kind).put("title", title).put("mode", mode).put("targetMin", targetMin)
            .put("cover", cover).put("memory", memory).put("created", created)
            .put("parts", JSONArray().apply { parts.forEach { put(it.json()) } })
        val tmp = File(dir, "project.json.tmp")
        tmp.writeText(o.toString())
        tmp.renameTo(File(dir, "project.json"))   // ghi an toàn: tắt máy giữa chừng không hỏng file
    }

    val doneParts get() = parts.count { it.state >= 2 }
    val totalDur get() = parts.sumOf { it.dur }

    /** Độ dài (giây) dành cho phần [i] khi kể lại / tóm tắt: chia tổng độ dài theo độ dài nguồn của từng phần. */
    fun budget(i: Int): Int {
        val w = parts.sumOf { it.weight }.takeIf { it > 0 } ?: 1.0
        return max(30, (targetMin * 60.0 * parts[i].weight / w).roundToInt())
    }

    /** Ước tính độ dài video (giây). */
    fun estimate(): Double = when {
        kind == "novel" && mode == "verbatim" -> parts.sumOf { it.weight } / CPS
        else -> targetMin * 60.0
    }

    companion object {
        fun load(dir: File): Project? = try {
            val o = JSONObject(File(dir, "project.json").readText())
            Project(dir).apply {
                kind = o.optString("kind", "novel")
                title = o.optString("title")
                mode = o.optString("mode", "verbatim")
                targetMin = o.optInt("targetMin", 120)
                cover = o.optString("cover")
                memory = o.optString("memory")
                created = o.optLong("created", System.currentTimeMillis())
                val a = o.optJSONArray("parts") ?: JSONArray()
                for (i in 0 until a.length()) parts += Part.of(a.getJSONObject(i))
            }
        } catch (e: Exception) {
            null
        }
    }
}

object Text {
    /** Dòng tiêu đề chương: "Chương 12", "Chapter 3", "Hồi 5", "第十二章", "Quyển 2 - Chương 1"... */
    val CHAPTER = Regex("^\\s*((quyển|tập|volume|vol\\.?)\\s*[\\divxlc]+\\s*[-–:,.]?\\s*)?" +
        "((chương|chapter|chap|hồi|tiết|phần)\\s*[\\divxlc]+\\b|第\\s*[\\d一二三四五六七八九十百千零〇两]+\\s*[章回节话]).{0,80}$",
        RegexOption.IGNORE_CASE)

    /** Tách văn bản thành các chương theo dòng tiêu đề; không có thì chia đều ~[size] ký tự. */
    fun chapters(text: String, size: Int = 12000): List<Pair<String, String>> {
        val lines = text.lines()
        val heads = lines.indices.filter { i -> lines[i].length <= 100 && CHAPTER.containsMatchIn(lines[i]) }
        val out = mutableListOf<Pair<String, String>>()
        if (heads.size >= 2) {
            val pre = lines.subList(0, heads[0]).joinToString("\n").trim()
            for ((k, h) in heads.withIndex()) {
                val end = heads.getOrNull(k + 1) ?: lines.size
                val body = lines.subList(h + 1, end).joinToString("\n").trim()
                val t = (if (k == 0 && pre.length > 200) pre + "\n\n" else "") + body
                if (t.isNotBlank()) out += lines[h].trim() to t
            }
            return out
        }
        var n = 1
        for ((_, c) in com.vtgt.reviewphim.manga.Books.chunks(text, size)) out += "Phần ${n++}" to c
        return out
    }

    /** Tiếng Việt? (nhiều chữ có dấu tiếng Việt) - truyện tiếng Việt đọc thẳng, truyện nước ngoài phải dịch. */
    fun isVietnamese(text: String): Boolean {
        val s = text.take(6000)
        val letters = s.count { it.isLetter() }
        val cjk = s.count { it in '぀'..'ヿ' || it in '㐀'..'鿿' || it in '가'..'힯' }
        if (cjk > letters / 20) return false
        if (letters < 20) return true
        val vi = s.count { it in "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵĂÂĐÊÔƠƯ" }
        return vi >= letters / 25
    }

    /** Cắt văn bản thành đoạn đọc ≤ [max] ký tự, theo câu (giọng đọc tự nhiên, phụ đề vừa màn hình). */
    fun speakChunks(text: String, max: Int = 220): List<String> {
        val out = mutableListOf<String>()
        for (para in text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }) {
            val sentences = Regex("(?<=[.!?…。！？;；])\\s+|(?<=[.!?…][\"”’»)])\\s+").split(para).filter { it.isNotBlank() }
            val cur = StringBuilder()
            for (s0 in sentences) {
                var s = s0.trim()
                while (s.length > max) {  // câu quá dài: cắt ở dấu phẩy / khoảng trắng
                    val cut = s.lastIndexOfAny(charArrayOf(',', '，', '、', ';', ':'), max).takeIf { it > max / 3 }
                        ?: s.lastIndexOf(' ', max).takeIf { it > max / 3 } ?: max
                    if (cur.isNotEmpty()) { out += cur.toString(); cur.clear() }
                    out += s.substring(0, cut + 1).trim()
                    s = s.substring(cut + 1).trim()
                }
                if (s.isEmpty()) continue
                if (cur.isNotEmpty() && cur.length + 1 + s.length > max) { out += cur.toString(); cur.clear() }
                if (cur.isNotEmpty()) cur.append(' ')
                cur.append(s)
            }
            if (cur.isNotEmpty()) out += cur.toString()
        }
        return out.filter { it.any(Char::isLetterOrDigit) }
    }

    /** "1:02:03" / "02:03" cho mục lục YouTube. */
    fun stamp(sec: Double): String {
        val t = max(0, sec.toInt())
        return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%02d:%02d".format(t / 60, t % 60)
    }

    /** Mục lục chương cho mô tả YouTube (mỗi dòng "00:00 Tên chương"). */
    fun chapterList(parts: List<Part>): String {
        var t = 0.0
        return parts.joinToString("\n") { p -> (stamp(t) + " " + p.name).also { t += p.dur } }
    }
}
