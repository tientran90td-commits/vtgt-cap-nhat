package com.vtgt.reviewphim.longvid

import com.vtgt.reviewphim.Prefs
import com.vtgt.reviewphim.Prompts

/** Yêu cầu gửi AI cho video dài (dịch nguyên văn / kể lại từng chương, nối mạch các phần). */
object LongPrompts {
    private fun memory(m: String) =
        if (m.isBlank()) "" else "\nNỘI DUNG NGAY TRƯỚC ĐÓ (chỉ để nối mạch, giữ tên và xưng hô thống nhất, KHÔNG viết lại):\n${m.takeLast(1200)}\n"

    /** Dịch nguyên văn 1 đoạn truyện sang tiếng Việt để đọc thành truyện audio. */
    fun translate(title: String, chapter: String, text: String, prefs: Prefs, prev: String): String = """
Dịch đoạn truyện sau (truyện "$title", $chapter) sang tiếng Việt văn chương tự nhiên, đầy đủ, có dấu, để đọc thành truyện audio.
- Dịch ĐỦ từng câu, không tóm tắt, không bỏ đoạn, không thêm bình luận / chú thích.
- Xưng hô hợp quan hệ nhân vật và thể loại (cổ trang: ta, ngươi, huynh, đệ...). Giữ cách xuống dòng theo đoạn.
- Không để lại chữ nước ngoài.
${Prompts.NAME_RULES}
${Prompts.glossary(prefs)}
${memory(prev)}
Chỉ trả lời bản dịch.

ĐOẠN CẦN DỊCH:
$text
""".trim()

    /** Kể lại 1 chương thành lời kể audio dài khoảng [chars] ký tự. */
    fun retell(title: String, chapter: String, text: String, chars: Int, style: String, prefs: Prefs, prev: String): String = """
Bạn là người kể chuyện của kênh TRUYỆN AUDIO tiếng Việt. Hãy kể lại $chapter của truyện "$title" (văn bản bên dưới) thành lời kể tiếng Việt để đọc thành audio.
- Văn phong: ${Prompts.STYLES[style] ?: Prompts.STYLES.values.first()}. Kể liền mạch, sinh động, có lời thoại quan trọng, đủ tình tiết chính theo đúng trình tự.
- Độ dài khoảng $chars ký tự (không ngắn hơn quá nhiều). Câu dễ đọc thành tiếng, không ký hiệu lạ, không emoji, không tiêu đề, không gạch đầu dòng.
- CHỈ kể những gì có trong văn bản, không bịa thêm. Nối tiếp tự nhiên với nội dung trước đó (không chào lại, không tóm tắt lại phần trước).
${Prompts.NAME_RULES}
${Prompts.glossary(prefs)}
${memory(prev)}
Chỉ trả lời lời kể.

VĂN BẢN CHƯƠNG:
$text
""".trim()

    /** Bỏ phần thừa AI hay thêm (```, "Bản dịch:", dòng ghi chú). */
    fun clean(reply: String): String = reply.trim()
        .removePrefix("```text").removePrefix("```").removeSuffix("```").trim()
        .lines().filterIndexed { i, l -> !(i == 0 && Regex("(?i)^(bản dịch|dưới đây|lời kể|đây là)[^\\n]{0,60}:\\s*$").containsMatchIn(l.trim())) }
        .joinToString("\n").trim()

    /** Bối cảnh các tập / chương trước, đặt trước yêu cầu viết kịch bản (phim, truyện tranh). */
    fun context(prev: String) = if (prev.isBlank()) "" else
        "BỐI CẢNH CÁC PHẦN TRƯỚC (đã kể ở phần trước của video, chỉ để nối mạch, KHÔNG kể lại, không chào lại):\n${prev.takeLast(1200)}\n\n"
}
