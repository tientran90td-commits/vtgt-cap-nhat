package com.vtgt.reviewphim.manga

import com.vtgt.reviewphim.Ai
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File
import java.net.URI

/**
 * Lấy truyện từ link: trang đọc truyện tranh (ảnh các trang) hoặc trang chương truyện chữ (văn bản),
 * tự đi theo nút "Chương sau". Trang chỉ hiện nội dung bằng JavaScript thì dùng trình duyệt trong app.
 */
object Web {
    const val UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/130.0.0.0 Mobile Safari/537.36"

    data class PageData(val url: String, val title: String, val images: List<String>, val text: String, val next: String?)

    private val IMG_EXT = Regex("(?i)\\.(jpe?g|png|webp|gif|avif)(\\?|#|$)")
    private val JUNK = Regex("(?i)(logo|icon|avatar|banner|sprite|emoji|loading|placeholder|blank\\.|/ads?/|advert|qrcode|facebook|twitter|thumb_|button|badge)")

    fun absolute(base: String, href: String): String? = try {
        val h = href.trim().replace("&amp;", "&")
        when {
            h.isEmpty() || h.startsWith("data:") || h.startsWith("javascript:") || h.startsWith("#") -> null
            h.startsWith("//") -> "https:$h"
            else -> URI(base).resolve(h.replace(" ", "%20")).toString()
        }
    } catch (e: Exception) {
        null
    }

    /** Giải mã trang theo charset trong header / thẻ meta (trang Trung hay dùng GBK). */
    fun decode(bytes: ByteArray, contentType: String?): String {
        val cs = Regex("(?i)charset=[\"']?([\\w-]+)").find(contentType ?: "")?.groupValues?.get(1)
            ?: Regex("(?i)<meta[^>]+charset=[\"']?([\\w-]+)").find(String(bytes, 0, minOf(bytes.size, 4096), Charsets.ISO_8859_1))?.groupValues?.get(1)
        return try {
            String(bytes, charset(cs ?: "UTF-8"))
        } catch (e: Exception) {
            String(bytes, Charsets.UTF_8)
        }
    }

    suspend fun get(url: String, referer: String? = null): Pair<ByteArray, String?> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).header("User-Agent", UA)
            .header("Accept-Language", "vi,en;q=0.8,zh;q=0.6,ja;q=0.5,ko;q=0.5")
            .apply { if (referer != null) header("Referer", referer) }
            .apply { runCatching { android.webkit.CookieManager.getInstance()?.getCookie(url) }.getOrNull()?.let { header("Cookie", it) } }
            .build()
        Ai.http.newCall(req).execute().use { r ->
            if (!r.isSuccessful) throw IllegalStateException("Tải $url lỗi HTTP ${r.code}")
            (r.body?.bytes() ?: ByteArray(0)) to r.header("Content-Type")
        }
    }

    /** Ảnh nội dung trong trang theo thứ tự xuất hiện (bỏ logo, icon, quảng cáo). */
    /** Khối quảng cáo: thẻ có id / class là ads, banner, qc, quangcao, sponsor, popup... */
    private val AD_BOX = Regex("(?i)<(div|section|aside|ins|span|p|center|figure|li|ul|a)\\b[^>]*\\b(?:id|class)\\s*=\\s*[\"'][^\"']*" +
        "(?<![a-z0-9])(?:ads?|adv|advert|advertisement|adsbygoogle|banner|sponsor(?:ed)?|qc|quang-?cao|popup|ad-?slot|ad-?box|ad-?container|ad-?wrap)" +
        "(?![a-z0-9])[^\"']*[\"'][^>]*>")
    private val AD_HOST = Regex("(?i)(doubleclick|googlesyndication|googleadservices|adservice|adsystem|adnxs|exoclick|popads|propeller|" +
        "juicyads|adsterra|taboola|outbrain|mgid|criteo|amazon-adsystem|adform|admicro|eclick|/ads?/|/banners?/|/qc/|quangcao)")

    /** Vị trí ngay sau thẻ đóng của khối bắt đầu tại [start] (đếm thẻ lồng cùng tên). */
    fun blockEnd(html: String, start: Int, tag: String): Int {
        val re = Regex("(?i)<$tag\\b|</$tag\\s*>")
        var depth = 0
        for (m in re.findAll(html, start)) {
            if (m.value.startsWith("</")) {
                depth--
                if (depth == 0) return m.range.last + 1
            } else depth++
        }
        return html.indexOf('>', start).let { if (it < 0) html.length else it + 1 }
    }

    /** Tên miền chính ("img.cdn.abc.com" -> "abc.com", "x.abc.com.vn" -> "abc.com.vn"). */
    fun domain(url: String): String {
        val h = (try { URI(url).host ?: "" } catch (e: Exception) { "" }).lowercase().removePrefix("www.")
        val p = h.split('.')
        if (p.size <= 2) return h
        val sld = p[p.size - 2]
        return if (p.last().length == 2 && sld in setOf("com", "net", "org", "gov", "edu", "co", "ac", "info", "biz")) p.takeLast(3).joinToString(".")
        else p.takeLast(2).joinToString(".")
    }

    /** Bỏ khối quảng cáo + ảnh bọc trong link dẫn sang trang khác (kiểu banner quảng cáo). */
    fun stripAds(html: String, base: String): String {
        var s = html
        var from = 0
        var guard = 0
        while (guard++ < 300) {
            val m = AD_BOX.find(s, from) ?: break
            if (Regex("(?i)(no-?ads?|ads?-?free|without-?ads?)").containsMatchIn(m.value)) {  // "không quảng cáo" - giữ
                from = m.range.last + 1
                continue
            }
            s = s.substring(0, m.range.first) + " " + s.substring(blockEnd(s, m.range.first, m.groupValues[1]))
            from = m.range.first
        }
        val home = domain(base)
        s = Regex("(?is)<a\\b[^>]*href\\s*=\\s*[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>").replace(s) { m ->
            if (m.groupValues[2].contains("<img", true) && domain(m.groupValues[1]) != home) " " else m.value
        }
        return s
    }

    /**
     * Ảnh truyện thường cùng 1 máy chủ ảnh: ảnh từ tên miền lạ chỉ có vài cái (quảng cáo) thì bỏ.
     * Giữ tên miền có ≥ 30% số ảnh của tên miền nhiều ảnh nhất.
     */
    fun mainHosts(urls: List<String>): List<String> {
        val ok = urls.filter { !AD_HOST.containsMatchIn(it) }
        if (ok.size < 5) return ok
        val count = ok.groupingBy { domain(it) }.eachCount()
        val top = count.values.max()
        return ok.filter { (count[domain(it)] ?: 0) >= maxOf(2.0, top * 0.3) }
    }

    fun images(html: String, base: String): List<String> {
        val raw = html.replace(Regex("(?is)<(script|style|noscript|header|footer|nav)[^>]*>.*?</\\1>"), " ")
        val clean = stripAds(raw, base)
        // phòng khi khung nội dung bị nhận nhầm là quảng cáo: bỏ lọc khối nếu mất gần hết ảnh
        val n = { x: String -> Regex("(?i)<img\\b").findAll(x).count() }
        val body = if (n(clean) < 3 && n(raw) >= 5) raw else clean
        val out = LinkedHashSet<String>()
        for (m in Regex("(?is)<img\\b([^>]*)>").findAll(body)) {
            val a = m.groupValues[1]
            fun attr(n: String) = Regex("(?i)\\b$n\\s*=\\s*[\"']([^\"']+)[\"']").find(a)?.groupValues?.get(1)
            val srcset = attr("data-srcset") ?: attr("srcset")
            val best = srcset?.split(',')?.map { it.trim().split(Regex("\\s+")) }
                ?.maxByOrNull { it.getOrNull(1)?.filter { c -> c.isDigit() }?.toIntOrNull() ?: 0 }?.firstOrNull()
            val src = listOf("data-src", "data-original", "data-lazy-src", "data-url", "data-echo", "data-cfsrc")
                .firstNotNullOfOrNull { attr(it) } ?: best ?: attr("src") ?: continue
            val u = absolute(base, src) ?: continue
            if (JUNK.containsMatchIn(u) || JUNK.containsMatchIn(attr("class") ?: "") || JUNK.containsMatchIn(attr("alt") ?: "")) continue
            out += u
        }
        if (out.size < 3) {  // trang để danh sách ảnh trong script (JSON): lấy mọi link ảnh
            for (m in Regex("""https?:\\?/\\?/[^"'\s<>]+?\.(?:jpe?g|png|webp)(?:\?[^"'\s<>]*)?""", RegexOption.IGNORE_CASE).findAll(html)) {
                val u = m.value.replace("\\/", "/")
                if (!JUNK.containsMatchIn(u)) out += u
            }
        }
        return mainHosts(out.toList())
    }

    /** Tiêu đề chương: <h1>, không thì <title>. */
    fun title(html: String): String {
        val h1 = Regex("(?is)<h1[^>]*>(.*?)</h1>").find(html)?.groupValues?.get(1)
        val t = h1 ?: Regex("(?is)<title[^>]*>(.*?)</title>").find(html)?.groupValues?.get(1) ?: ""
        return Books.htmlToText(t).replace("\n", " ").trim().take(150)
    }

    /**
     * Văn bản chương truyện: khối có nhiều chữ nhất (khung nội dung chương), bỏ menu / bình luận / quảng cáo.
     * Cách "readability" đơn giản: chấm điểm các khối theo lượng chữ trong <p> / <br>.
     */
    fun text(html: String): String {
        val clean = html.replace(Regex("(?is)<(script|style|noscript|header|footer|nav|aside|form|button|select)[^>]*>.*?</\\1>"), " ")
            .replace(Regex("(?is)<!--.*?-->"), " ")
        // ưu tiên khối có id/class quen thuộc của trang đọc truyện
        val hint = Regex("(?i)<(div|article|section)[^>]*(id|class)\\s*=\\s*[\"'][^\"']*(chapter-c|chapter-content|chapter_content|chr-c|reading-content|entry-content|text-left|novel-content|read-content|content|article|txt|booktxt)[^\"']*[\"'][^>]*>")
        val cands = hint.findAll(clean).map { m ->
            Books.htmlToText(block(clean, m.range.first, m.groupValues[1]).replace(Regex("(?is)<img[^>]*>"), ""))
        }.filter { it.isNotBlank() }.toList()
        // khối bọc ngoài (cả trang) cũng khớp "content": chọn khối TRONG CÙNG còn giữ ≥ 70% lượng chữ nhiều nhất
        val most = cands.maxOfOrNull { it.length } ?: 0
        var best = cands.filter { it.length >= most * 0.7 }.minByOrNull { it.length } ?: ""
        if (best.length < 400) {  // không có khối quen: ghép các đoạn <p>
            val ps = Regex("(?is)<p\\b[^>]*>(.*?)</p>").findAll(clean).map { Books.htmlToText(it.groupValues[1]) }
                .filter { it.length >= 2 }.joinToString("\n")
            if (ps.length > best.length) best = ps
        }
        val junkLine = Regex("(?i)(chương (trước|sau)|next chapter|previous chapter|bình luận|đăng nhập|báo lỗi|tải app|theo dõi|上一章|下一章|目录|加入书签)")
        return best.lines().map { it.trim() }.filter { it.isNotEmpty() && !(it.length < 40 && junkLine.containsMatchIn(it)) }.joinToString("\n")
    }

    /** Nội dung từ thẻ mở tại [start] tới thẻ đóng tương ứng (đếm thẻ lồng nhau cùng tên). */
    fun block(html: String, start: Int, tag: String): String {
        val open = Regex("(?i)<$tag\\b|</$tag\\s*>")
        var depth = 0
        val firstEnd = html.indexOf('>', start)
        if (firstEnd < 0) return ""
        for (m in open.findAll(html, start)) {
            if (m.value.startsWith("</")) {
                depth--
                if (depth == 0) return html.substring(firstEnd + 1, m.range.first)
            } else depth++
        }
        return html.substring(firstEnd + 1)
    }

    /** Link "Chương sau / Next". */
    fun next(html: String, base: String): String? {
        Regex("(?is)<link[^>]+rel=[\"']next[\"'][^>]*href=[\"']([^\"']+)").find(html)?.let { return absolute(base, it.groupValues[1]) }
        val word = Regex("(?i)(chương sau|chương tiếp|chap sau|tiếp theo|next chapter|next chap|next|下一章|下一页|下一話|次の話|다음화|다음)")
        for (m in Regex("(?is)<a\\b([^>]*)>(.*?)</a>").findAll(html)) {
            val attrs = m.groupValues[1]
            val label = Books.htmlToText(m.groupValues[2]) + " " + (Regex("(?i)(title|aria-label|class|id)\\s*=\\s*[\"']([^\"']*)").findAll(attrs).joinToString(" ") { it.groupValues[2] })
            if (!word.containsMatchIn(label) || Regex("(?i)(prev|trước|上一)").containsMatchIn(label)) continue
            val href = Regex("(?i)href\\s*=\\s*[\"']([^\"']+)").find(attrs)?.groupValues?.get(1) ?: continue
            val u = absolute(base, href) ?: continue
            if (u.trimEnd('/') != base.trimEnd('/')) return u
        }
        return null
    }

    fun isImageUrl(u: String) = IMG_EXT.containsMatchIn(u.substringBefore('?') + "?")

    suspend fun page(url: String): PageData {
        val (bytes, type) = get(url)
        val html = decode(bytes, type)
        return PageData(url, title(html), images(html, url), text(html), next(html, url))
    }

    /** Tải ảnh về file (kèm Referer của trang để không bị chặn). */
    suspend fun download(url: String, referer: String?, out: File) {
        val (b, _) = get(url, referer)
        out.writeBytes(b)
    }
}
