package com.vtgt.reviewphim

import android.content.Context

/** Cài đặt lưu trên máy (key AI chỉ nằm trong máy này). */
class Prefs(ctx: Context) {
    private val p = ctx.getSharedPreferences("settings", Context.MODE_PRIVATE)

    fun str(k: String, d: String = ""): String = p.getString(k, d) ?: d
    fun set(k: String, v: String) = p.edit().putString(k, v).apply()
    fun num(k: String, d: Float): Float = p.getFloat(k, d)
    fun setNum(k: String, v: Float) = p.edit().putFloat(k, v).apply()
    fun bool(k: String, d: Boolean): Boolean = p.getBoolean(k, d)
    fun setBool(k: String, v: Boolean) = p.edit().putBoolean(k, v).apply()
    /** Key đầu tiên của 1 AI (ô key có thể chứa nhiều key, cách nhau dấu phẩy / xuống dòng). */
    fun key(id: String): String = keys(id).firstOrNull() ?: ""

    /** Mọi key của 1 AI: key này quá tải / hết lượt thì app tự đổi sang key kế. */
    fun keys(id: String): List<String> = str("key_$id").split(',', ';', '\n', ' ', '\t').map { it.trim() }.filter { it.length >= 8 }
}
