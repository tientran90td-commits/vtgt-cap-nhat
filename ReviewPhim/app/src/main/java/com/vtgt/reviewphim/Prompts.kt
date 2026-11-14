package com.vtgt.reviewphim

/** Yêu cầu gửi AI (dùng chung cho API và dán tay qua DeepSeek web). */
object Prompts {
    val NAME_RULES = """
Quy tắc tên riêng (quan trọng nhất):
- Trước hết tự nhận ra đây là phim / anime / truyện nào (dựa vào TÊN VIDEO, hashtag và lời thoại).
- Anime / truyện Nhật, Hàn, phương Tây được kể lại bằng tiếng Trung (rất hay gặp ở video review Trung Quốc): dùng TÊN GỐC mà fan Việt quen gọi, KHÔNG phiên âm Hán-Việt từ chữ Trung. Ví dụ: 路飞 → Luffy, 鸣人 → Naruto, 佐助 → Sasuke, 炭治郎 → Tanjiro, 五条悟 → Gojo Satoru.
- Phim / truyện gốc Trung Quốc (cổ trang, tiên hiệp, phim Trung): đọc Hán-Việt. Ví dụ: 林动 → Lâm Động, 萧炎 → Tiêu Viêm, 斗气 → đấu khí.
- Tên Hàn / Nhật viết theo cách quen dùng ở Việt Nam (김민준 → Kim Min Jun, 田中 → Tanaka). Tên phương Tây giữ nguyên.
- Thuật ngữ riêng của phim (sức mạnh, chủng tộc, cấp bậc, địa danh) dùng đúng từ fan Việt hay dùng.
""".trim()

    val STYLES = linkedMapOf(
        "hap_dan" to "Kể chuyện cuốn hút, kịch tính như kênh review phim triệu view",
        "hai_huoc" to "Hài hước, dí dỏm, bình luận vui nhưng vẫn kể đủ cốt truyện",
        "nghiem_tuc" to "Nghiêm túc, sâu sắc, phân tích nhân vật và ý nghĩa",
        "co_trang" to "Giọng kể cổ trang, kiếm hiệp, tiên hiệp (ta, ngươi, huynh, đệ...)",
        "nhan_vat" to "Ngôi thứ nhất: nhân vật chính tự kể lại câu chuyện của mình (xưng tôi)",
        "tham_tu" to "Như thám tử phân tích: đặt câu hỏi, gợi bí ẩn, hé lộ manh mối dần dần",
    )

    fun glossary(prefs: Prefs): String {
        val g = prefs.str("glossary").lines().map { it.trim() }.filter { "=" in it }
        return if (g.isEmpty()) "" else "Tên riêng BẮT BUỘC dùng:\n" + g.joinToString("\n")
    }

    /** Viết kịch bản review / tóm tắt từ lời thoại. */
    fun recap(title: String, duration: Double, lines: List<Line>, targetSec: Int, style: String, prefs: Prefs): String {
        val chars = (targetSec * CPS).toInt()
        val n = (targetSec / 11).coerceIn(4, 80)
        return """
Bạn là biên kịch kênh REVIEW PHIM tiếng Việt trên TikTok / YouTube. Dưới đây là lời thoại (có mốc thời gian) của video "$title" dài ${fmtTime(duration)}. Hãy viết kịch bản review / tóm tắt bằng tiếng Việt chuẩn, có dấu đầy đủ.

$NAME_RULES

Yêu cầu kịch bản:
- Văn phong: ${STYLES[style] ?: STYLES.values.first()}. Ngôi thứ ba, câu ngắn, dễ đọc thành tiếng, không ký hiệu lạ, không emoji, không chú thích.
- Đoạn 1 là "hook": 1–2 câu gây tò mò, lấy từ khoảnh khắc kịch tính nhất (cảnh của đoạn này có thể ở giữa / cuối phim).
- Từ đoạn 2 kể theo đúng trình tự thời gian, chia 3 hồi: mở đầu (~25%), diễn biến & xung đột (~50%), cao trào & kết (~25%).
- Tránh cảnh mở đầu / danh đề / credit cuối phim; mỗi đoạn một cảnh khác nhau, không lặp lại.
- Tổng lời kể khoảng $chars ký tự (đọc khoảng ${targetSec / 60} phút ${targetSec % 60} giây), chia thành khoảng $n đoạn, mỗi đoạn 1–3 câu (80–250 ký tự).
- Mỗi đoạn gắn với cảnh minh họa đúng nội dung đó: "start" là số giây trong video (lấy theo mốc thời gian lời thoại). Từ đoạn 2 trở đi "start" tăng dần và rải đều từ đầu tới cuối video.
${glossary(prefs)}

Chỉ trả lời JSON, không giải thích:
{"title": "tiêu đề video review hấp dẫn, tối đa 70 ký tự", "segments": [{"start": 12.5, "text": "lời kể..."}]}

LỜI THOẠI:
${transcriptText(lines)}
""".trim()
    }

    val TRANSLATE_RULES = """
Bạn là biên dịch viên lồng tiếng & phụ đề tiếng Việt chuyên nghiệp. Dịch từng câu sang tiếng Việt chuẩn, tự nhiên, có dấu đầy đủ.
- Dịch ý, giọng điệu và cảm xúc, không dịch word-by-word. Xưng hô hợp quan hệ nhân vật và thể loại phim.
- Mỗi câu phải đọc kịp trong thời gian của nó: không vượt "max chars". Ngắn gọn, bỏ từ thừa.
- Giữ đúng mỗi id một câu tiếng Việt. Không gộp, tách, bỏ hay thêm id.
- Chỉ chữ tiếng Việt: không ghi chú, không phiên âm, không giữ chữ gốc.
- Câu chỉ là tiếng động / nhạc (♪, [cười]) → chuỗi rỗng.
""".trim()

    /** Dịch một phần lời thoại (id bắt đầu từ 1). */
    fun translate(title: String, lines: List<Line>, idx: List<Int>, prefs: Prefs, first: Boolean): String {
        val prev = (maxOf(0, idx.first() - 4) until idx.first()).joinToString("\n") { lines[it].text }
        val body = idx.joinToString("\n") {
            val l = lines[it]
            "${it + 1} | %.1fs | max ${maxChars(lines, it)} chars | ${l.text}".num(l.end - l.start)
        }
        return """
$TRANSLATE_RULES

${if (first) NAME_RULES else "Tiếp tục dịch cùng phim, giữ nguyên tên riêng, thuật ngữ, xưng hô đã dùng.\n\n$NAME_RULES"}
${glossary(prefs)}
TÊN VIDEO: $title
${if (prev.isNotEmpty()) "\nCÂU TRƯỚC ĐÓ (chỉ để hiểu mạch, không dịch):\n$prev\n" else ""}
CÁC CÂU CẦN DỊCH (id | thời lượng | max chars | lời gốc):
$body

Chỉ trả lời JSON, đủ mọi id, không giải thích: {"lines": {"<id>": "<tiếng Việt>"}}
""".trim()
    }

    fun shorten(lines: List<Line>, idx: List<Int>, tighten: Double): String {
        val body = idx.joinToString("\n") {
            "${it + 1} | max ${(maxChars(lines, it) * tighten).toInt()} chars | gốc: ${lines[it].text} | hiện tại: ${lines[it].vi}"
        }
        return """
Rút gọn các câu thuyết minh tiếng Việt sau để đọc kịp thời gian: giữ ý chính, tên riêng và giọng điệu; bỏ từ thừa, dùng từ ngắn hơn. Mỗi câu KHÔNG vượt max chars.
Chỉ trả lời JSON: {"lines": {"<id>": "<câu ngắn hơn>"}}

$body
""".trim()
    }

    /** Đọc câu trả lời dịch: JSON {"lines": {...}} hoặc từng dòng "id | câu". */
    fun parseLines(text: String, idx: Collection<Int>): Map<Int, String> {
        val got = mutableMapOf<Int, String>()
        try {
            val d = extractJson(text)
            val src = d.optJSONObject("lines") ?: d
            for (k in src.keys()) {
                val id = k.trim().toIntOrNull() ?: continue
                val v = src.optString(k, "")
                got[id - 1] = v.trim()
            }
        } catch (e: Exception) {
            Regex("^\\s*(\\d+)\\s*[|.:)\\-]\\s*(.+?)\\s*$", RegexOption.MULTILINE).findAll(text).forEach {
                got[it.groupValues[1].toInt() - 1] = it.groupValues[2].trim().trim('"')
            }
        }
        return got.filter { (i, v) -> i in idx && !FOREIGN.containsMatchIn(v) }
    }

    fun parseRecap(text: String, duration: Double): Pair<String, List<Seg>> {
        val d = extractJson(text)
        val arr = d.optJSONArray("segments") ?: throw IllegalArgumentException("Thiếu danh sách đoạn (segments)")
        val segs = (0 until arr.length()).mapNotNull {
            val o = arr.optJSONObject(it) ?: return@mapNotNull null
            val t = o.optString("text").trim()
            if (t.isEmpty() || FOREIGN.containsMatchIn(t)) return@mapNotNull null
            val lo = duration * 0.02
            val hi = maxOf(lo, duration * 0.95 - 1.0)
            Seg(o.optDouble("start", 0.0).coerceIn(lo, hi), t)
        }
        if (segs.isEmpty()) throw IllegalArgumentException("Kịch bản rỗng")
        // đoạn hook (cảnh cao trào) giữ ở đầu, các đoạn sau theo thời gian
        return d.optString("title", "").trim() to (segs.take(1) + segs.drop(1).sortedBy { it.start })
    }
}
