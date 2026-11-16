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
        val cast = prefs.str("cast")
        val sb = StringBuilder()
        if (cast.isNotBlank()) sb.append("Nhân vật chính thức của \"${prefs.str("cast_title")}\" (MyAnimeList, tên Latin - phim Trung " +
            "thì đổi sang Hán-Việt): $cast\n")
        if (g.isNotEmpty()) sb.append("Tên riêng BẮT BUỘC dùng:\n" + g.joinToString("\n"))
        return sb.toString().trim()
    }

    /** Tên riêng AI trả về ({"names": {"gốc": "Việt"}}) -> nhớ vào bảng tên cho các tập sau (bộ nhớ truyện). */
    fun parseNames(text: String): Map<String, String> = try {
        val o = extractJson(text).optJSONObject("names")
        if (o == null) emptyMap() else o.keys().asSequence().associateWith { o.optString(it).trim() }
            .filter { (k, v) -> k.isNotBlank() && v.isNotBlank() && k != v && !FOREIGN.containsMatchIn(v) && k.length <= 40 }
    } catch (e: Exception) {
        emptyMap()
    }

    /** Ghép tên mới vào bảng tên (không ghi đè tên bạn đã sửa). Trả về số tên mới. */
    fun learnNames(prefs: Prefs, names: Map<String, String>): Int {
        val cur = prefs.str("glossary").lines().map { it.trim() }.filter { it.isNotEmpty() }.toMutableList()
        val have = cur.mapNotNull { it.split("=").firstOrNull()?.trim() }.toSet()
        val add = names.filterKeys { it !in have }.map { (k, v) -> "$k = $v" }
        if (add.isEmpty()) return 0
        prefs.set("glossary", (cur + add).takeLast(300).joinToString("\n"))
        return add.size
    }

    /** Nhờ AI xem các ảnh ghép khung hình (mỗi ô ghi mốc thời gian) và tả diễn biến hình ảnh. */
    fun watch(title: String, part: Int, parts: Int, lo: Double, hi: Double, images: Int, dialogue: List<Line>, prefs: Prefs): String {
        val talk = dialogue.joinToString("\n") { "[${fmtTime(it.start)}] ${it.text.trim()}" }.take(2500)
        return """
Mình gửi kèm $images ảnh ghép khung hình của video "$title"${if (parts > 1) " (phần $part/$parts)" else ""}, từ ${fmtTime(lo)} đến ${fmtTime(hi)}. Mỗi ảnh có nhiều ô, mỗi ô là 1 khung hình, góc trên bên trái ô ghi mốc thời gian của khung đó. Đọc các ô từ trái sang phải, từ trên xuống dưới, các ảnh theo thứ tự.

Hãy XEM KỸ từng ô và tả lại DIỄN BIẾN HÌNH ẢNH bằng tiếng Việt như người đang xem phim: ai đang làm gì, đánh nhau / rượt đuổi / chiêu thức / cháy nổ, ai thắng ai thua, biểu cảm, sự kiện quan trọng, bối cảnh đổi sang đâu, chữ quan trọng trên màn hình. KHÔNG bỏ sót cảnh hành động không có lời thoại.
- Mỗi dòng 1 sự việc, đúng dạng: mm:ss-mm:ss | mô tả ngắn (tối đa 25 từ). Mốc lấy đúng số ghi trên ô. Gộp các ô liên tiếp cùng một sự việc thành 1 dòng.
- Gọi nhân vật bằng tên nếu biết (từ tên phim / lời thoại bên dưới), không thì tả ngoại hình (cô gái tóc đỏ, gã mặc giáp đen...) và gọi thống nhất.
- Chỉ tả những gì thấy trong ảnh, không đoán thêm. Bỏ qua ô đen, logo, danh đề, credit.
Chỉ trả lời các dòng mô tả, không giải thích gì thêm.
${glossary(prefs)}
${if (talk.isNotBlank()) "\nLỜI THOẠI TRONG KHOẢNG NÀY (chỉ để biết tên nhân vật, tham khảo):\n$talk" else ""}
""".trim()
    }

    /** Viết kịch bản review / tóm tắt từ lời thoại (+ mô tả hình ảnh "[HÌNH]" nếu AI đã xem cả video). */
    fun recap(title: String, duration: Double, lines: List<Line>, targetSec: Int, style: String, prefs: Prefs): String {
        val chars = (targetSec * CPS).toInt()
        val n = (targetSec / 11).coerceIn(4, 80)
        val seen = lines.any { it.text.startsWith(Watch.TAG) }
        val src = if (seen) "diễn biến (lời thoại + mô tả hình ảnh)" else "lời thoại"
        val actionRule = if (!seen) "" else "\n- KHÔNG bỏ qua các cảnh hành động / cảnh hay không có thoại (dòng [HÌNH]): kể lại sinh động, " +
            "đó thường là cao trào và hợp làm hook. Kết hợp hình và lời thoại để hiểu đúng ai làm gì."
        return """
Bạn là biên kịch kênh REVIEW PHIM tiếng Việt trên TikTok / YouTube. Dưới đây là ${if (seen) "DIỄN BIẾN gồm lời thoại và mô tả hình ảnh (dòng bắt đầu bằng [HÌNH] là AI đã xem từng cảnh và tả lại)" else "lời thoại"} (đánh số, có mốc thời gian) của video "$title" dài ${fmtTime(duration)}. Hãy viết kịch bản review / tóm tắt bằng tiếng Việt chuẩn, có dấu đầy đủ.

$NAME_RULES

Yêu cầu kịch bản:
- Văn phong: ${STYLES[style] ?: STYLES.values.first()}. Ngôi thứ ba, câu ngắn, dễ đọc thành tiếng, không ký hiệu lạ, không emoji, không chú thích.
- Đoạn 1 là "hook": 1–2 câu gây tò mò, lấy từ khoảnh khắc kịch tính nhất (cảnh của đoạn này có thể ở giữa / cuối phim).
- Từ đoạn 2 kể theo đúng trình tự thời gian, chia 3 hồi: mở đầu (~25%), diễn biến & xung đột (~50%), cao trào & kết (~25%).
- Tránh cảnh mở đầu / danh đề / credit cuối phim. Được DÙNG LẠI cảnh khi hợp nội dung: đoạn kể nhắc lại nhân vật / sự việc / trận đấu ở chỗ khác thì thêm "reuse": [số câu có cảnh đó] để chiếu lại cảnh ấy.
- Tổng lời kể khoảng $chars ký tự (đọc khoảng ${targetSec / 60} phút ${targetSec % 60} giây), chia thành khoảng $n đoạn, mỗi đoạn 1–3 câu (80–250 ký tự).
- CHỈ kể những gì có trong $src bên dưới. KHÔNG bịa thêm tình tiết, nhân vật, kết cục lấy từ hiểu biết bên ngoài; chỗ nào không rõ thì kể chung chung, không đoán.$actionRule
- Mỗi đoạn ghi rõ nó kể lại các dòng số mấy: "from" và "to" là số thứ tự dòng (#) ở danh sách bên dưới, đúng chỗ sự việc đó xảy ra (thường 3–15 dòng). Video sẽ chiếu đúng cảnh của các dòng đó, nên đoạn kể phải khớp nội dung các dòng này.
- Từ đoạn 2 trở đi "from" tăng dần, các đoạn không chồng lên nhau, rải từ đầu tới cuối lời thoại.
${glossary(prefs)}

Chỉ trả lời JSON, không giải thích:
{"title": "tiêu đề video review hấp dẫn, tối đa 70 ký tự", "segments": [{"from": 12, "to": 18, "text": "lời kể...", "reuse": [3]}], "names": {"tên gốc trong lời thoại": "tên tiếng Việt đã dùng"}}

${if (seen) "DIỄN BIẾN (số dòng, mốc thời gian, lời thoại gốc hoặc [HÌNH] mô tả cảnh):" else "LỜI THOẠI (số câu, mốc thời gian, lời gốc):"}
${transcriptIds(lines, if (seen) 80000 else 60000)}
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

Chỉ trả lời JSON, đủ mọi id, không giải thích: {"lines": {"<id>": "<tiếng Việt>"}, "names": {"<tên gốc>": "<tên tiếng Việt đã dùng>"}}
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

    /** Nhờ Gemini (web / app) nghe file âm thanh và chép lời thoại - không cần API key. */
    fun transcribe(title: String, part: Int, parts: Int, minutes: Int): String = """
Mình gửi kèm file âm thanh lời thoại của video "$title"${if (parts > 1) " (phần $part/$parts)" else ""}, dài khoảng $minutes phút.
Hãy nghe và chép lại TOÀN BỘ lời nói, đúng ngôn ngữ gốc (KHÔNG dịch, không tóm tắt, không bỏ câu).
Trả lời CHỈ bằng phụ đề định dạng SRT chuẩn, mốc thời gian chính xác theo file (HH:MM:SS,mmm --> HH:MM:SS,mmm), mỗi câu 1 mục ngắn, không giải thích gì thêm.
""".trim()

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

    fun parseRecap(text: String, duration: Double, lines: List<Line> = emptyList()): Pair<String, List<Seg>> {
        val d = extractJson(text)
        val arr = d.optJSONArray("segments") ?: throw IllegalArgumentException("Thiếu danh sách đoạn (segments)")
        val segs = (0 until arr.length()).mapNotNull {
            val o = arr.optJSONObject(it) ?: return@mapNotNull null
            val t = o.optString("text").trim()
            if (t.isEmpty() || FOREIGN.containsMatchIn(t)) return@mapNotNull null
            val from = o.optInt("from", 0)
            if (from >= 1 && lines.isNotEmpty()) {  // neo theo số câu thoại: lấy đúng thời gian của các câu đó
                val a = (from - 1).coerceIn(0, lines.size - 1)
                val b = (o.optInt("to", from) - 1).coerceIn(a, lines.size - 1)
                val ra = o.optJSONArray("reuse")
                val reuse = (0 until (ra?.length() ?: 0)).mapNotNull { k ->
                    lines.getOrNull(ra!!.optInt(k, 0) - 1)?.let { l -> maxOf(0.0, l.start - 0.5) to l.end + 0.5 }
                }.take(4)
                return@mapNotNull Seg(lines[a].start, t, lines[b].end, reuse)
            }
            val lo = duration * 0.02
            val hi = maxOf(lo, duration * 0.95 - 1.0)
            Seg(o.optDouble("start", 0.0).coerceIn(lo, hi), t)
        }
        if (segs.isEmpty()) throw IllegalArgumentException("Kịch bản rỗng")
        // đoạn hook (cảnh cao trào) giữ ở đầu, các đoạn sau theo thời gian
        return d.optString("title", "").trim() to (segs.take(1) + segs.drop(1).sortedBy { it.start })
    }
}
