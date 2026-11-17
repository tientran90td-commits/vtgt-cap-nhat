package com.vtgt.reviewphim.manga

import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.Seg
import com.vtgt.reviewphim.Wav
import com.vtgt.reviewphim.splitCues
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.max
import kotlin.math.min

/**
 * Khớp giọng đọc với tranh: lời kể có ghi chú cuối câu [#12] (dòng diễn biến 12) hoặc [#12.3] (khung 3 của trang đó).
 * Mỗi câu đọc riêng, biết đúng thời lượng -> chiếu đúng trang / khung tranh trong lúc đọc câu đó.
 */
object Sync {
    /** 1 câu kể + tranh của nó: [item] chỉ số dòng diễn biến (0..), [panel] chỉ số khung (0..), -1 = chưa chỉ định. */
    data class Beat(val text: String, val item: Int, val panel: Int)

    private val REF = Regex("\\[\\s*#?\\s*(\\d{1,4})(?:\\s*[.,:\\-]\\s*(\\d{1,2}))?\\s*]")

    /** Bỏ ghi chú [#12.3] khỏi lời đọc / phụ đề. */
    fun clean(text: String): String = REF.replace(text, "")
        .replace(Regex("\\s+([,.!?…;:])"), "$1").replace(Regex("\\s{2,}"), " ").trim()

    /**
     * Tách đoạn kể thành câu, mỗi câu gắn với dòng diễn biến / khung tranh nó nói tới.
     * Câu không ghi chú: theo câu trước (cùng trang, khung tiếp theo); câu đầu không ghi thì lấy dòng [a].
     * Ghi chú ngoài khoảng [a, b) của đoạn vẫn nhận nếu là dòng có thật (< [total]).
     */
    fun beats(text: String, a: Int, b: Int, total: Int): List<Beat> {
        // tách câu; ghi chú đứng ngay sau dấu câu thuộc về câu trước ("... mắt. [#5]")
        val parts = Regex("(?<=[.!?…])(?:\\s*\\[[^\\]]*])*\\s+").let { re ->
            val out = mutableListOf<String>()
            var last = 0
            for (m in re.findAll(text)) {
                val end = m.range.last + 1
                out += text.substring(last, end).trim()
                last = end
            }
            out += text.substring(last).trim()
            out.filter { it.isNotBlank() }
        }
        val res = mutableListOf<Beat>()
        var item = a.coerceIn(0, max(0, total - 1))
        for (p in parts) {
            val refs = REF.findAll(p).toList()
            val spoken = clean(p)
            if (spoken.none { it.isLetterOrDigit() }) {
                // chỉ có ghi chú (đứng sau dấu câu cuối đoạn): thuộc về câu trước
                val m = refs.lastOrNull()
                val n = m?.groupValues?.get(1)?.toInt()?.minus(1)
                if (m != null && n != null && n in 0 until total && res.isNotEmpty()) {
                    item = n
                    res[res.size - 1] = res.last().copy(item = n, panel = m.groupValues[2].toIntOrNull()?.minus(1) ?: -1)
                }
                continue
            }
            var panel = -1
            refs.lastOrNull()?.let { m ->
                val n = m.groupValues[1].toInt() - 1
                if (n in 0 until total) {
                    item = n
                    panel = m.groupValues[2].toIntOrNull()?.minus(1) ?: -1
                }
            }
            res += Beat(spoken, item, panel)
        }
        if (res.isEmpty() && text.isNotBlank()) res += Beat(clean(text), a.coerceIn(0, max(0, total - 1)), -1)
        return res
    }

    /**
     * Đọc giọng từng câu + dựng danh sách cảnh khớp tranh. [shots]: các ảnh của 1 trang (khung tranh theo thứ tự,
     * hoặc cả trang). Trả về (cảnh, phụ đề, tổng giây); tiếng ghi vào [narr].
     */
    suspend fun build(
        segs: List<Seg>, items: List<Item>, narr: File, maxChars: Int,
        shots: suspend (pageIndex: Int) -> List<File>,
        card: suspend () -> File,
        frame: suspend (File) -> Pair<File, Boolean>,
        speak: suspend (text: String, key: String) -> File,
        progress: (Int, Int) -> Unit,
    ): Triple<List<Slide>, List<Cue>, Double> {
        val slides = mutableListOf<Slide>()
        val cues = mutableListOf<Cue>()
        val cursor = HashMap<Int, Int>()      // trang -> khung tiếp theo sẽ chiếu
        var t = 0.0
        Wav.Writer(narr).use { wr ->
            for ((k, s) in segs.withIndex()) {
                progress(k, segs.size)
                val a = s.start.toInt()
                val b = if (s.end > s.start) s.end.toInt() else a + 1
                val beats = beats(s.text, a, b, items.size)
                for ((j, bt) in beats.withIndex()) {
                    val pcm = Wav.read(speak(bt.text, "s${k}_$j"))
                    val dur = pcm.seconds + if (j == beats.lastIndex) 0.35 else 0.12
                    val page = items.getOrNull(bt.item)?.page ?: -1
                    val all = if (page >= 0) shots(page) else emptyList()
                    val pick: List<File> = when {
                        all.isEmpty() -> listOf(card())
                        bt.panel in all.indices -> {   // AI chỉ đúng khung
                            cursor[page] = bt.panel + 1
                            listOf(all[bt.panel])
                        }
                        else -> {                       // chiếu tiếp các khung chưa chiếu của trang, đủ cho câu này
                            val from = cursor[page] ?: 0
                            val n = max(1, min(all.size, (dur / 1.6).toInt()))
                            val start = if (from >= all.size) 0 else from
                            val take = all.drop(start).take(n).ifEmpty { listOf(all.first()) }
                            cursor[page] = start + take.size
                            take
                        }
                    }
                    for (f in pick) {
                        val (img, scroll) = frame(f)
                        val d = dur / pick.size
                        // cùng ảnh liền nhau (câu sau nói tiếp khung đó): kéo dài cảnh trước, không cắt
                        val prev = slides.lastOrNull()
                        if (prev != null && prev.image == img) slides[slides.size - 1] = prev.copy(dur = prev.dur + d)
                        else slides += Slide(img, d, scroll)
                    }
                    wr.silenceTo(t + 0.05)
                    wr.write(pcm)
                    cues += splitCues(bt.text, t + 0.05, pcm.seconds, maxChars)
                    t += dur
                    wr.silenceTo(t)
                }
            }
        }
        return Triple(slides, cues, t)
    }

    /** Khung tranh của 1 trang (tách khung khi bật, trang cuộn dọc thì cả khúc). */
    suspend fun shotsOf(book: Book, page: Int, zoom: Boolean, rtl: Boolean, dir: File, cache: HashMap<Int, List<File>>): List<File> =
        cache.getOrPut(page) {
            val f = book.pages.getOrNull(page)?.file ?: return@getOrPut emptyList()
            if (!zoom || book.webtoon) listOf(f) else withContext(Dispatchers.Default) {
                try {
                    Panels.crops(f, rtl, dir, "p$page")
                } catch (e: Exception) {
                    listOf(f)
                }
            }
        }
}
