package com.vtgt.reviewphim

import android.content.Context
import kotlin.math.max
import kotlin.math.min

/**
 * Khớp lời kể với điểm CẮT CẢNH (học cơ chế từ movie-narrator / MovieShort-AI, code tự viết):
 * mỗi đoạn lời kể ghép vài cảnh ngắn bắt đầu đúng chỗ đổi cảnh, bỏ cảnh đen / quá ngắn, hình đổi liên tục
 * như kênh review thay vì 1 cảnh dài đứng yên.
 */
object Shots {
    const val CUT_SCORE = 12.0
    const val DARK_Y = 22.0
    const val MAX_SHOT = 3.6
    const val MIN_SHOT = 0.8

    data class Frame(val t: Double, val score: Double, val y: Double)
    data class Shot(val a: Double, val b: Double, val y: Double)

    /** Khung (thời điểm, điểm đổi cảnh, độ sáng) trong [a, a+len] - 6 khung/giây, ảnh nhỏ nên nhanh. */
    suspend fun analyze(ctx: Context, src: java.io.File, a: Double, len: Double): List<Frame> {
        val lines = mutableListOf<String>()
        try {
            Ff.run(ctx, listOf("-ss", "%.3f".num(max(0.0, a)), "-t", "%.3f".num(len), "-i", src.absolutePath, "-an", "-sn",
                "-vf", "fps=6,scale=96:-2,signalstats,scdet=threshold=0,metadata=mode=print", "-f", "null", "-")) {
                if ("pts_time:" in it || "YAVG=" in it || "scd.score=" in it) lines.add(it)
            }
        } catch (e: RuntimeException) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            return emptyList()  // máy nào lỗi bước này: dùng 1 cảnh liền như cũ
        }
        return parse(lines, max(0.0, a))
    }

    fun parse(lines: List<String>, offset: Double): List<Frame> {
        val out = mutableListOf<Frame>()
        var t: Double? = null
        var y = 128.0
        var sc = 0.0
        for (ln in lines) {
            when {
                "pts_time:" in ln -> {
                    t?.let { out.add(Frame(it, sc, y)) }
                    t = offset + (ln.substringAfterLast("pts_time:").trim().split(" ")[0].toDoubleOrNull() ?: 0.0)
                    y = 128.0
                    sc = 0.0
                }
                "lavfi.signalstats.YAVG=" in ln -> y = ln.substringAfterLast("=").trim().toDoubleOrNull() ?: y
                "lavfi.scd.score=" in ln -> sc = ln.substringAfterLast("=").trim().toDoubleOrNull() ?: sc
            }
        }
        t?.let { out.add(Frame(it, sc, y)) }
        return out
    }

    fun shots(frames: List<Frame>, end: Double): List<Shot> {
        val out = mutableListOf<Shot>()
        var cur: Double? = null
        val ys = mutableListOf<Double>()
        for (f in frames) {
            if (cur == null) {
                cur = f.t; ys.clear(); ys.add(f.y)
            } else if (f.score >= CUT_SCORE) {
                out.add(Shot(cur, f.t, ys.average()))
                cur = f.t; ys.clear(); ys.add(f.y)
            } else ys.add(f.y)
        }
        if (cur != null && end > cur) out.add(Shot(cur, end, ys.average()))
        return out
    }

    /** Các mẩu cảnh (bắt đầu, độ dài) từ `start`, đủ `need` giây. */
    fun plan(sh: List<Shot>, start: Double, need: Double, limit: Double): List<Pair<Double, Double>> {
        val pieces = mutableListOf<Pair<Double, Double>>()
        var got = 0.0
        for (s in sh) {
            if (got >= need - 0.05) break
            if (s.b <= start || s.y < DARK_Y || s.b - s.a < MIN_SHOT) continue
            val a2 = max(s.a, start)
            val take = minOf(s.b - a2, MAX_SHOT, need - got)
            if (take < MIN_SHOT && need - got > MIN_SHOT) continue
            pieces.add(a2 to take)
            got += take
        }
        if (got < need - 0.05) {
            var a = pieces.lastOrNull()?.let { it.first + it.second } ?: start
            a = min(a, max(0.0, limit - (need - got)))
            pieces.add(a to need - got)
        }
        val merged = mutableListOf<Pair<Double, Double>>()
        for ((a, d) in pieces) {
            val last = merged.lastOrNull()
            if (last != null && kotlin.math.abs(last.first + last.second - a) < 0.02) merged[merged.size - 1] = last.first to last.second + d
            else merged.add(a to d)
        }
        return merged
    }

    /**
     * Cảnh cho 1 đoạn kể neo theo câu thoại [a, b]: chọn vài cảnh rải đều trong khoảng đó (không trôi sang nội dung
     * khác). Khoảng ngắn hơn lời kể thì nới dần ra hai bên nhưng không quá [lo, hi] (khoảng của đoạn trước / sau).
     */
    fun planIn(sh: List<Shot>, a: Double, b: Double, need: Double, lo: Double, hi: Double,
               extra: List<Shot> = emptyList()): List<Pair<Double, Double>> {
        var s = a
        var e = b
        var k = 0
        while (e - s < need && k < 2 && (s > lo + 0.01 || e < hi - 0.01)) {  // nới tối đa 2 giây mỗi bên
            s = max(lo, s - 1.0)
            e = min(hi, e + 1.0)
            k++
        }
        fun good(list: List<Shot>, s0: Double, e0: Double) = list.filter { it.b > s0 && it.a < e0 && it.y >= DARK_Y }
            .map { max(it.a, s0) to min(it.b, e0) }.filter { it.second - it.first >= MIN_SHOT }
        val pool = good(sh, s, e).toMutableList()
        if (pool.sumOf { it.second - it.first } < need) {  // thêm cảnh AI gợi ý dùng lại (nhắc lại nhân vật / sự việc)
            for (x in good(extra, -1e9, 1e9)) if (x !in pool) pool.add(x)
        }
        if (pool.isEmpty()) {  // không dò được cảnh: lấy liền mạch quanh khoảng câu thoại
            val st = max(lo, min((s + e - need) / 2, hi - need)).coerceAtLeast(0.0)
            return listOf(st to need)
        }
        val out = mutableListOf<Pair<Double, Double>>()
        if (pool.sumOf { it.second - it.first } >= need) {  // đủ hình: rải đều
            val n = max(1, kotlin.math.ceil(need / MAX_SHOT).toInt())
            val pick = if (pool.size <= n) pool else (0 until n).map { pool[(it * pool.size) / n] }
            val each = need / pick.size
            var debt = 0.0
            for ((x, y) in pick) {
                val want = each + debt
                val take = min(y - x, want)
                out.add(x to take)
                debt = want - take
            }
            var i = 0
            while (debt > 0.05 && i < pool.size * 3) {  // cảnh chọn quá ngắn: bù bằng cảnh khác trong khoảng
                val (x, y) = pool[i % pool.size]
                val take = minOf(y - x, debt, MAX_SHOT)
                out.add(x to take)
                debt -= take
                i++
            }
            return out
        }
        // không đủ hình mới: DÙNG LẠI các cảnh hợp nội dung (lượt sau lấy phần khác của cảnh)
        var got = 0.0
        var rnd = 0
        while (got < need - 0.05 && rnd < 20) {
            for ((x, y) in pool) {
                if (got >= need - 0.05) break
                val len = y - x
                val off = if (rnd % 2 == 1 && len - min(len / 2, 1.0) >= MIN_SHOT) min(len / 2, 1.0) else 0.0
                val take = minOf(len - off, MAX_SHOT, need - got)
                if (take < 0.3) continue
                out.add(x + off to take)
                got += take
            }
            rnd++
        }
        return out
    }

    /** Karaoke: số ký tự đã "đọc tới" ở tỉ lệ thời gian p (0..1) của dòng phụ đề - chữ đổi màu theo giọng đọc. */
    fun karaokeChars(text: String, p: Double): Int {
        if (p <= 0) return 0
        if (p >= 1) return text.length
        val words = Regex("\\S+\\s*").findAll(text).map { it.value }.toList()
        val total = words.sumOf { it.trim().length + 1 }.toDouble()
        var acc = 0.0
        var chars = 0
        for (w in words) {
            acc += (w.trim().length + 1) / total
            chars += w.length
            if (acc >= p) return chars
        }
        return text.length
    }
}
