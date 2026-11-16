package com.vtgt.reviewphim.manga

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.media3.common.Effect
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.MatrixTransformation
import androidx.media3.effect.OverlayEffect
import androidx.media3.effect.Presentation
import androidx.media3.effect.TextureOverlay
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.EditedMediaItemSequence
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.ProgressHolder
import androidx.media3.transformer.Transformer
import com.google.common.collect.ImmutableList
import com.vtgt.reviewphim.Cue
import com.vtgt.reviewphim.SubtitleOverlay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Một cảnh của video: 1 ảnh (đã dựng sẵn khung) chiếu [dur] giây, phụ đề theo thời gian của cả video. */
data class Slide(val image: File, val dur: Double, val scroll: Boolean)

/**
 * Video từ ảnh truyện: trang dài thì cuộn từ trên xuống (kiểu xem webtoon), trang vừa khung thì phóng to chậm;
 * nền mờ của chính trang đó lấp chỗ trống. Phụ đề karaoke + tiêu đề hook như ReviewPhim.
 */
object Slides {
    /** Kích thước khung thành phẩm. */
    fun size(vertical: Boolean, quality: Int): Pair<Int, Int> {
        val long = (quality * 16.0 / 9 / 2).roundToInt() * 2
        return if (vertical) quality to long else long to quality
    }

    /**
     * Dựng sẵn khung cho 1 ảnh: rộng = khung video; ảnh cao hơn khung (sau khi vừa chiều rộng) thì giữ cả chiều cao
     * để cuộn, không thì đặt giữa trên nền mờ. Trả về (file, có cuộn không).
     */
    fun frame(src: File, w: Int, h: Int, out: File): Pair<File, Boolean> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(src.path, o)
        val sw = max(1, o.outWidth)
        val sh = max(1, o.outHeight)
        val img = BitmapFactory.decodeFile(src.path, BitmapFactory.Options().apply {
            inSampleSize = max(1, Integer.highestOneBit(max(1, sw / w)))
        }) ?: Bitmap.createBitmap(16, 16, Bitmap.Config.ARGB_8888)
        val fitW = h.toDouble() * sw / sh   // rộng khi vừa chiều cao
        val tallH = (w.toDouble() * sh / sw).roundToInt()
        val scroll = tallH > h * 1.18 && tallH <= h * 4   // dài vừa phải: cuộn; quá dài (hiếm) thì thu cả trang vào khung
        val ch = if (scroll) tallH else h
        val c = Bitmap.createBitmap(w, ch, Bitmap.Config.ARGB_8888)
        val cv = Canvas(c)
        // nền: chính ảnh đó phóng to, làm mờ (thu nhỏ rồi phóng lại) và tối đi
        val small = Bitmap.createScaledBitmap(img, 24, max(1, (24.0 * sh / sw).roundToInt()), true)
        val sc = max(w.toFloat() / small.width, ch.toFloat() / small.height)
        val bw = small.width * sc
        val bh = small.height * sc
        cv.drawBitmap(small, null, RectF((w - bw) / 2, (ch - bh) / 2, (w + bw) / 2, (ch + bh) / 2),
            Paint(Paint.FILTER_BITMAP_FLAG))
        cv.drawColor(Color.argb(120, 0, 0, 0))
        small.recycle()
        val p = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
        if (scroll) {
            cv.drawBitmap(img, null, Rect(0, 0, w, ch), p)
        } else {
            val k = min(w.toDouble() / sw, h.toDouble() / sh)
            val dw = sw * k
            val dh = sh * k
            cv.drawBitmap(img, null, RectF(((w - dw) / 2).toFloat(), ((h - dh) / 2).toFloat(),
                ((w + dw) / 2).toFloat(), ((h + dh) / 2).toFloat()), p)
        }
        img.recycle()
        out.outputStream().use { c.compress(Bitmap.CompressFormat.JPEG, 92, it) }
        c.recycle()
        return out to scroll
    }

    /** Khung chữ khi light novel không có ảnh minh họa: tên truyện trên nền chuyển màu. */
    fun titleCard(title: String, sub: String, w: Int, h: Int, out: File): File {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(b)
        val bg = Paint().apply {
            shader = LinearGradient(0f, 0f, w.toFloat(), h.toFloat(), Color.rgb(40, 24, 90), Color.rgb(12, 12, 26), Shader.TileMode.CLAMP)
        }
        c.drawRect(0f, 0f, w.toFloat(), h.toFloat(), bg)
        val base = min(w, h).toFloat()
        fun text(t: String, size: Float, color: Int, y: Float) {
            val tp = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                textSize = size; this.color = color; typeface = Typeface.create(Typeface.SERIF, Typeface.BOLD)
            }
            val lay = StaticLayout.Builder.obtain(t, 0, t.length, tp, (w * 0.84f).toInt())
                .setAlignment(Layout.Alignment.ALIGN_CENTER).setMaxLines(5).build()
            c.save()
            c.translate(w * 0.08f, y - lay.height / 2f)
            lay.draw(c)
            c.restore()
        }
        text(title, base * 0.085f, Color.rgb(255, 214, 64), h * 0.40f)
        if (sub.isNotBlank()) text(sub, base * 0.05f, Color.WHITE, h * 0.58f)
        out.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 92, it) }
        b.recycle()
        return out
    }

    /**
     * Chuyển động của 1 ảnh: cuộn từ đầu tới cuối trang (ảnh cao hơn khung), hoặc phóng to 1.0 -> 1.07.
     * Thời gian tính từ khung đầu tiên của cảnh.
     */
    @UnstableApi
    class Motion(private val dur: Double, private val visible: Float, private val scroll: Boolean) : MatrixTransformation {
        private var firstUs = -1L
        override fun getMatrix(presentationTimeUs: Long): Matrix {
            if (firstUs < 0) firstUs = presentationTimeUs
            val p = ((presentationTimeUs - firstUs) / 1e6 / max(0.1, dur)).toFloat().coerceIn(0f, 1f)
            val e = p * p * (3 - 2 * p)   // nhanh dần rồi chậm dần
            val m = Matrix()
            if (scroll) {
                // khung hình chỉ thấy phần giữa (tỉ lệ visible); dời ảnh để thấy từ mép trên xuống mép dưới
                val room = 1f - visible
                m.setTranslate(0f, -room + 2f * room * e)
            } else {
                val s = 1f + 0.07f * e
                m.setScale(s, s)
            }
            return m
        }
    }

    @androidx.annotation.OptIn(UnstableApi::class)
    suspend fun render(ctx: Context, slides: List<Slide>, w: Int, h: Int, cues: List<Cue>, karaoke: Boolean, hook: String,
                       out: File, progress: (Float) -> Unit) {
        var offset = 0.0
        val items = slides.map { s ->
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(s.image.path, o)
            val visible = if (s.scroll && o.outHeight > 0) min(1f, h.toFloat() / o.outHeight) else 1f
            val local = cues.filter { it.end > offset && it.start < offset + s.dur }.map { Cue(it.start - offset, it.end - offset, it.text) }
            val hookHere = if (hook.isNotBlank() && offset < 2.6) hook else ""
            val effects = mutableListOf<Effect>(
                Motion(s.dur, visible, s.scroll),
                Presentation.createForWidthAndHeight(w, h, Presentation.LAYOUT_SCALE_TO_FIT_WITH_CROP),
                OverlayEffect(ImmutableList.of<TextureOverlay>(SubtitleOverlay(w, h, local, h * 0.80f, "", -1f, karaoke,
                    hookHere, 2.6 - offset))),
            )
            val mi = MediaItem.Builder().setUri(android.net.Uri.fromFile(s.image)).setMimeType(MimeTypes.IMAGE_JPEG)
                .setImageDurationMs((s.dur * 1000).toLong()).build()
            offset += s.dur
            EditedMediaItem.Builder(mi).setFrameRate(30).setEffects(Effects(listOf(), effects)).build()
        }
        val comp = Composition.Builder(listOf(EditedMediaItemSequence(items))).build()
        export(ctx, comp, out, progress)
    }

    @androidx.annotation.OptIn(UnstableApi::class)
    private suspend fun export(ctx: Context, comp: Composition, out: File, progress: (Float) -> Unit) =
        withContext(Dispatchers.Main) {
            suspendCancellableCoroutine<Unit> { cont ->
                val handler = Handler(Looper.getMainLooper())
                val tr = Transformer.Builder(ctx)
                    .setVideoMimeType(MimeTypes.VIDEO_H264)
                    .addListener(object : Transformer.Listener {
                        override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                            if (cont.isActive) cont.resume(Unit)
                        }

                        override fun onError(composition: Composition, exportResult: ExportResult, exportException: ExportException) {
                            if (cont.isActive) cont.resumeWithException(
                                RuntimeException("Dựng video lỗi: ${exportException.errorCodeName} ${exportException.message}", exportException))
                        }
                    })
                    .build()
                out.delete()
                tr.start(comp, out.absolutePath)
                val holder = ProgressHolder()
                val tick = object : Runnable {
                    override fun run() {
                        if (!cont.isActive) return
                        if (tr.getProgress(holder) == Transformer.PROGRESS_STATE_AVAILABLE) progress(holder.progress / 100f)
                        handler.postDelayed(this, 500)
                    }
                }
                handler.post(tick)
                cont.invokeOnCancellation { handler.post { tr.cancel() } }
            }
        }
}
