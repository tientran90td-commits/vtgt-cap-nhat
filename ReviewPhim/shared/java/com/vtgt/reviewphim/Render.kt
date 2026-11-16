package com.vtgt.reviewphim

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.media3.common.Effect
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.effect.BitmapOverlay
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Khung hình thành phẩm. */
enum class Aspect(val label: String) {
    SOURCE("Giữ khung gốc"),
    VERTICAL_FIT("Dọc 9:16 - đủ hình, tiêu đề phía trên"),
    VERTICAL_FILL("Dọc 9:16 - cắt đầy khung"),
}

/**
 * Dựng hình bằng Media3 Transformer (dùng chip mã hóa phần cứng của máy, nhanh):
 * cắt / nối các cảnh, che phụ đề gốc, đổi khung 9:16, chèn phụ đề tiếng Việt + tiêu đề. Không có tiếng
 * (tiếng được trộn riêng bằng ffmpeg rồi ghép vào sau).
 */
class RenderSpec(
    val src: File,
    val info: VInfo,
    /** Các cảnh (giây trong video gốc); null = cả video. */
    val clips: List<Pair<Double, Double>>?,
    val aspect: Aspect,
    /** Chất lượng = số điểm ảnh cạnh ngắn (540 / 720 / 1080). */
    val quality: Int,
    /** Vùng phụ đề gốc cần che (tỉ lệ chiều cao), null = không che. */
    val cover: Pair<Float, Float>?,
    /** Vị trí phụ đề gốc (tỉ lệ chiều cao) - phụ đề Việt đặt đúng chỗ đó để che luôn chữ gốc. */
    val subBand: Pair<Float, Float>,
    /** Phụ đề theo thời gian của video thành phẩm. */
    val cues: List<Cue>,
    val title: String,
    /** Chữ đổi màu theo giọng đọc (karaoke). */
    val karaoke: Boolean = false,
    /** Tiêu đề lớn giữa màn hình 2.6 giây đầu video. */
    val hook: String = "",
)

object Render {
    fun outSize(spec: RenderSpec): Pair<Int, Int> {
        val even = { v: Double -> (v / 2).roundToInt() * 2 }
        return when (spec.aspect) {
            Aspect.SOURCE -> {
                val short = min(spec.info.width, spec.info.height)
                val k = min(1.0, spec.quality.toDouble() / short)
                even(spec.info.width * k) to even(spec.info.height * k)
            }
            else -> spec.quality to even(spec.quality * 16.0 / 9)
        }
    }

    /** Khung video gốc nằm ở đâu trong khung thành phẩm: (trên, cao). */
    private fun videoRect(spec: RenderSpec, w: Int, h: Int): Pair<Float, Float> {
        val sw = spec.info.width.toFloat()
        val sh = spec.info.height.toFloat()
        val scale = when (spec.aspect) {
            Aspect.VERTICAL_FILL -> max(w / sw, h / sh)
            else -> min(w / sw, h / sh)
        }
        val vh = sh * scale
        return (h - vh) / 2 to vh
    }

    suspend fun video(ctx: Context, spec: RenderSpec, out: File, progress: (Float) -> Unit) {
        val (w, h) = outSize(spec)
        val (vTop, vH) = videoRect(spec, w, h)
        val subY = (vTop + vH * (spec.subBand.first + spec.subBand.second) / 2).coerceIn(h * 0.1f, h * 0.92f)
        val titleY = if (spec.aspect == Aspect.VERTICAL_FIT && vTop > h * 0.08f) vTop / 2 else -1f
        val layout = if (spec.aspect == Aspect.VERTICAL_FILL) Presentation.LAYOUT_SCALE_TO_FIT_WITH_CROP
        else Presentation.LAYOUT_SCALE_TO_FIT
        val clips = spec.clips ?: listOf(0.0 to spec.info.duration)
        var offset = 0.0
        val items = clips.mapIndexed { ci, (a, b) ->
            val local = spec.cues.filter { it.end > offset && it.start < offset + (b - a) }
                .map { Cue(it.start - offset, it.end - offset, it.text) }
            val effects = mutableListOf<Effect>()
            spec.cover?.let { effects.add(OverlayEffect(ImmutableList.of<TextureOverlay>(CoverOverlay(spec.info, it)))) }
            effects.add(Presentation.createForWidthAndHeight(w, h, layout))
            val hookHere = if (spec.hook.isNotBlank() && offset < 2.6) spec.hook else ""
            effects.add(OverlayEffect(ImmutableList.of<TextureOverlay>(
                SubtitleOverlay(w, h, local, subY, spec.title, titleY, spec.karaoke, hookHere, 2.6 - offset))))
            val mi = MediaItem.Builder().setUri(android.net.Uri.fromFile(spec.src))
                .setClippingConfiguration(MediaItem.ClippingConfiguration.Builder()
                    .setStartPositionMs((a * 1000).toLong()).setEndPositionMs((b * 1000).toLong()).build())
                .build()
            offset += b - a
            EditedMediaItem.Builder(mi).setRemoveAudio(true).setEffects(Effects(listOf(), effects)).build()
        }
        val comp = Composition.Builder(listOf(EditedMediaItemSequence(items))).build()
        export(ctx, comp, out, progress)
    }

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

                        override fun onError(composition: Composition, exportResult: ExportResult,
                                             exportException: ExportException) {
                            if (cont.isActive) cont.resumeWithException(
                                RuntimeException("Dựng video lỗi: ${exportException.errorCodeName} ${exportException.message}",
                                    exportException))
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

/** Dải che phụ đề gốc (theo kích thước video gốc). */
private class CoverOverlay(info: VInfo, band: Pair<Float, Float>) : BitmapOverlay() {
    private val bmp: Bitmap = Bitmap.createBitmap(info.width, info.height, Bitmap.Config.ARGB_8888).also {
        val c = Canvas(it)
        val p = Paint().apply { color = Color.argb(235, 12, 12, 16) }
        val pad = info.height * 0.01f
        c.drawRect(RectF(0f, band.first * info.height - pad, info.width.toFloat(), band.second * info.height + pad), p)
    }

    override fun getBitmap(presentationTimeUs: Long): Bitmap = bmp
}

/**
 * Phụ đề + tiêu đề vẽ trên một ảnh trong suốt đúng cỡ khung thành phẩm. Thời gian tính từ khung hình đầu tiên
 * của cảnh (không phụ thuộc cách Media3 đánh số thời gian khi nối nhiều cảnh).
 */
class SubtitleOverlay(
    private val w: Int, private val h: Int, private val cues: List<Cue>, private val subY: Float,
    private val title: String, private val titleY: Float,
    private val karaoke: Boolean = false, private val hook: String = "", private val hookUntil: Double = 0.0,
) : BitmapOverlay() {
    private var firstUs = -1L
    private var lastKey = Int.MIN_VALUE
    private var bmp: Bitmap? = null

    override fun getBitmap(presentationTimeUs: Long): Bitmap {
        if (firstUs < 0) firstUs = presentationTimeUs
        val t = (presentationTimeUs - firstUs) / 1e6
        val idx = cues.indexOfFirst { t >= it.start && t < it.end }
        val lit = if (karaoke && idx >= 0) Shots.karaokeChars(cues[idx].text,
            (t - cues[idx].start) / (cues[idx].end - cues[idx].start)) else 0
        val showHook = hook.isNotBlank() && t < hookUntil
        val key = idx * 10000 + lit * 2 + if (showHook) 1 else 0
        val cur = bmp
        if (cur != null && key == lastKey) return cur
        lastKey = key
        // ảnh MỚI mỗi lần đổi chữ: Media3 chỉ tải lại ảnh khi đối tượng Bitmap khác
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(b)
        val base = min(w, h).toFloat()
        if (titleY > 0 && title.isNotBlank()) {
            drawText(c, title, base * 0.068f, Color.rgb(255, 214, 64), titleY, w * 0.9f, bold = true, maxLines = 3)
        }
        if (idx >= 0) drawText(c, cues[idx].text, base * 0.052f, Color.WHITE, subY, w * 0.9f, bold = true, maxLines = 3,
            lit = if (karaoke) lit else -1)
        if (showHook) drawText(c, hook, base * 0.085f, Color.rgb(255, 214, 64), h * 0.42f, w * 0.88f, bold = true, maxLines = 4)
        bmp = b
        return b
    }

    private fun drawText(c: Canvas, text: String, size: Float, color: Int, centerY: Float, maxW: Float, bold: Boolean,
                         maxLines: Int, lit: Int = -1) {
        val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = size
            typeface = Typeface.create(Typeface.SANS_SERIF, if (bold) Typeface.BOLD else Typeface.NORMAL)
        }
        val layout = StaticLayout.Builder.obtain(text, 0, text.length, paint, maxW.toInt())
            .setAlignment(Layout.Alignment.ALIGN_CENTER).setMaxLines(maxLines).build()
        c.save()
        c.translate((c.width - maxW) / 2, centerY - layout.height / 2f)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = size * 0.16f
        paint.strokeJoin = Paint.Join.ROUND
        paint.color = Color.BLACK
        layout.draw(c)
        paint.style = Paint.Style.FILL
        paint.color = color
        if (lit >= 0) {  // karaoke: phần đã đọc màu vàng, phần chưa đọc màu trắng (viền vẫn đen)
            val sp = android.text.SpannableString(text)
            if (lit > 0) sp.setSpan(android.text.style.ForegroundColorSpan(Color.rgb(255, 214, 64)), 0,
                minOf(lit, text.length), android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            StaticLayout.Builder.obtain(sp, 0, sp.length, paint, maxW.toInt())
                .setAlignment(Layout.Alignment.ALIGN_CENTER).setMaxLines(maxLines).build().draw(c)
        } else {
            layout.draw(c)
        }
        c.restore()
    }
}
