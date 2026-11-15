package com.vtgt.reviewphim

/**
 * sea-g2p (Apache-2.0, github.com/pnnbao97/sea-g2p): chuẩn hóa chữ tiếng Việt (số, ngày, đơn vị...) rồi đổi sang
 * âm vị cho VieNeu-TTS. Thư viện Rust dựng cho Android (native/seag2p-jni), từ điển sea_g2p.bin tải lần đầu.
 */
class SeaG2p(dictPath: String) : AutoCloseable {
    private var handle: Long = nativeOpen(dictPath)

    @Synchronized
    fun phonemize(text: String, puncNorm: Boolean = true): String {
        check(handle != 0L) { "sea-g2p đã đóng" }
        return nativePhonemize(handle, text, puncNorm)
    }

    @Synchronized
    override fun close() {
        if (handle != 0L) nativeClose(handle)
        handle = 0
    }

    companion object {
        init {
            System.loadLibrary("seag2p_jni")
        }

        @JvmStatic private external fun nativeOpen(path: String): Long
        @JvmStatic private external fun nativePhonemize(handle: Long, text: String, puncNorm: Boolean): String
        @JvmStatic private external fun nativeClose(handle: Long)
    }
}
