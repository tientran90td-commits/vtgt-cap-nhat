package com.vtgt.reviewphim

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Request
import org.json.JSONObject

/**
 * Danh sách nhân vật chính thức từ MyAnimeList qua Jikan (API công khai, miễn phí, không cần key) - ý tưởng từ
 * Aniflow (MIT). Đưa vào yêu cầu cho AI để tên nhân vật đúng ngay từ đầu (Ichigo, Yhwach...) thay vì phiên âm sai.
 */
object Cast {
    data class Found(val title: String, val names: List<String>)

    /** "Kurosaki, Ichigo" -> "Kurosaki Ichigo" (thứ tự họ - tên fan Việt hay dùng cho anime). */
    fun malName(n: String): String = n.split(",").map { it.trim() }.filter { it.isNotEmpty() }.joinToString(" ")

    suspend fun lookup(query: String): Found? = withContext(Dispatchers.IO) {
        val q = query.trim()
        if (q.isEmpty()) return@withContext null
        for (kind in listOf("anime", "manga")) {
            val search = "https://api.jikan.moe/v4/$kind".toHttpUrl().newBuilder()
                .addQueryParameter("q", q).addQueryParameter("limit", "1").build()
            val first = get(search.toString())?.optJSONArray("data")?.optJSONObject(0) ?: continue
            val id = first.optInt("mal_id")
            val title = first.optString("title_english").ifBlank { first.optString("title") }
            val chars = get("https://api.jikan.moe/v4/$kind/$id/characters")?.optJSONArray("data") ?: continue
            val all = (0 until chars.length()).mapNotNull { chars.optJSONObject(it) }
            val main = all.filter { it.optString("role") == "Main" }
            val rest = all.filter { it.optString("role") != "Main" }
            val names = (main + rest).mapNotNull { it.optJSONObject("character")?.optString("name") }
                .map(::malName).filter { it.isNotBlank() }.distinct().take(60)
            if (names.isNotEmpty()) return@withContext Found(title, names)
        }
        null
    }

    private fun get(url: String): JSONObject? {
        val req = Request.Builder().url(url).header("Accept", "application/json").build()
        Ai.http.newCall(req).execute().use { r -> return if (r.isSuccessful) JSONObject(r.body?.string() ?: "{}") else null }
    }
}
