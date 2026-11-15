package com.vtgt.reviewphim

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.LongBuffer
import java.util.zip.ZipFile
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * VieNeu-TTS v3 Nano (Apache-2.0, github.com/pnnbao97/VieNeu-TTS) chạy NGAY TRÊN ĐIỆN THOẠI bằng onnxruntime:
 * giọng Việt AI 24 kHz + nhân bản giọng từ 1 đoạn ghi âm ngắn. Port từ vieneu/v3nano.py (bản ONNX, không torch).
 * Mô hình (~400 MB) tải từ Hugging Face lần đầu; từ điển âm vị sea_g2p.bin tải từ Release của app.
 */
object VieNeu {
    const val SR = 24_000
    private const val HF = "https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Nano/resolve/main/"
    private const val G2P_URL = "https://github.com/tientran90td-commits/vtgt-cap-nhat/releases/download/reviewphim/sea_g2p.bin"
    val GRAPH = listOf("text_encoder.onnx", "duration_predictor.onnx", "vector_estimator.onnx", "codec_decoder.onnx",
        "config.json", "constants.npz")
    val CLONE = listOf("speaker_encoder.onnx", "codec_encoder.onnx", "reference_encoder.onnx")

    /** Thư mục mô hình (test có thể chỉ sang thư mục khác). */
    @Volatile
    var dirOverride: File? = null

    fun dir(ctx: Context): File = (dirOverride ?: File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "vieneu")).apply { mkdirs() }

    fun ready(ctx: Context, clone: Boolean = false): Boolean =
        (GRAPH + (if (clone) CLONE else emptyList())).all { File(dir(ctx), it).length() > 0 } && File(dir(ctx), "sea_g2p.bin").length() > 0

    /** Tải mô hình còn thiếu (bỏ qua file đã có). */
    suspend fun download(ctx: Context, clone: Boolean, log: (String) -> Unit, progress: (Float, String) -> Unit) =
        withContext(Dispatchers.IO) {
            val d = dir(ctx)
            val todo = (GRAPH + (if (clone) CLONE else emptyList())).map { it to HF + it } + listOf("sea_g2p.bin" to G2P_URL)
            val missing = todo.filter { (f, _) -> File(d, f).length() == 0L }
            if (missing.isEmpty()) return@withContext
            log("Tải giọng AI VieNeu về máy (một lần, khoảng ${if (clone) 450 else 340} MB)...")
            for ((k, pair) in missing.withIndex()) {
                val (name, url) = pair
                val out = File(d, name)
                val part = File(d, "$name.part")
                Ai.http.newBuilder().readTimeout(120, java.util.concurrent.TimeUnit.SECONDS)
                    .callTimeout(0, java.util.concurrent.TimeUnit.SECONDS).build()
                    .newCall(Request.Builder().url(url).build()).execute().use { r ->
                        if (!r.isSuccessful) throw IllegalStateException("Tải $name lỗi HTTP ${r.code}")
                        val body = r.body ?: throw IllegalStateException("Tải $name lỗi")
                        val total = body.contentLength()
                        body.byteStream().use { input ->
                            part.outputStream().use { o ->
                                val buf = ByteArray(1 shl 16)
                                var done = 0L
                                var last = 0L
                                while (true) {
                                    currentCoroutineContext().ensureActive()
                                    val n = input.read(buf)
                                    if (n < 0) break
                                    o.write(buf, 0, n)
                                    done += n
                                    if (done - last > (1 shl 20)) {
                                        last = done
                                        val p = if (total > 0) done.toFloat() / total else 0f
                                        progress((k + p) / missing.size, "Tải $name ${done / 1_000_000}/${if (total > 0) total / 1_000_000 else "?"} MB")
                                    }
                                }
                            }
                        }
                    }
                part.renameTo(out)
            }
            log("✅ Đã có giọng AI VieNeu trên máy.")
        }

    // ------------------------------------------------------------------ giọng: có sẵn + nhân bản
    class Voice(val name: String, val spk: FloatArray, val style: FloatArray, val styleRows: Int, val desc: String = "")

    private var presets: Map<String, Voice>? = null

    fun presets(ctx: Context): Map<String, Voice> = presets ?: run {
        val j = JSONObject(ctx.assets.open("voices_v3_nano.json").bufferedReader().use { it.readText() })
        parseVoices(j.getJSONObject("presets")).also { presets = it }
    }

    fun userDir(ctx: Context) = File(ctx.filesDir, "vieneu_voices").apply { mkdirs() }

    fun userVoices(ctx: Context): Map<String, Voice> = userDir(ctx).listFiles { f -> f.name.endsWith(".json") }
        ?.sortedBy { it.lastModified() }?.mapNotNull { f ->
            try {
                parseVoices(JSONObject(f.readText())).values.firstOrNull()
            } catch (e: Exception) {
                null
            }
        }?.associateBy { it.name } ?: emptyMap()

    fun allVoices(ctx: Context): Map<String, Voice> = userVoices(ctx) + presets(ctx)

    fun saveVoice(ctx: Context, v: Voice) {
        val style = JSONArray()
        val cols = v.style.size / v.styleRows
        for (r in 0 until v.styleRows) style.put(JSONArray((0 until cols).map { v.style[r * cols + it].toDouble() }))
        val o = JSONObject().put(v.name, JSONObject().put("description", v.desc)
            .put("speaker_emb", JSONArray(v.spk.map { it.toDouble() })).put("style", style))
        File(userDir(ctx), v.name.replace(Regex("[^\\p{L}\\p{N} _-]"), "_") + ".json").writeText(o.toString())
    }

    fun deleteVoice(ctx: Context, name: String) {
        userDir(ctx).listFiles()?.forEach { f ->
            try {
                if (JSONObject(f.readText()).has(name)) f.delete()
            } catch (e: Exception) {
                // bỏ qua file hỏng
            }
        }
    }

    private fun parseVoices(o: JSONObject): Map<String, Voice> = o.keys().asSequence().associateWith { name ->
        val v = o.getJSONObject(name)
        val spkA = v.getJSONArray("speaker_emb")
        val st = v.getJSONArray("style")
        val rows = st.length()
        val cols = st.getJSONArray(0).length()
        val style = FloatArray(rows * cols)
        for (r in 0 until rows) {
            val row = st.getJSONArray(r)
            for (c in 0 until cols) style[r * cols + c] = row.getDouble(c).toFloat()
        }
        Voice(name, FloatArray(spkA.length()) { spkA.getDouble(it).toFloat() }, style, rows, v.optString("description"))
    }

    // ------------------------------------------------------------------ chia câu (mỗi đoạn <= ~140 ký tự)
    fun chunks(text: String, maxChars: Int = 140): List<Pair<String, Double>> {
        val out = mutableListOf<Pair<String, Double>>()  // (đoạn, nghỉ sau đoạn)
        for (para in text.split(Regex("[\\r\\n]+")).map { it.trim() }.filter { it.isNotEmpty() }) {
            val sents = Regex("[^.!?…]+[.!?…]*").findAll(para).map { it.value.trim() }.filter { it.isNotEmpty() }.toList()
            var cur = ""
            fun flush() {
                if (cur.isNotBlank()) out.add(cur.trim() to if (cur.trimEnd().last() in ".!?…") 0.5 else 0.3)
                cur = ""
            }
            for (s in sents) {
                if (s.length > maxChars) {  // câu quá dài: ngắt ở dấu phẩy rồi ở khoảng trắng
                    flush()
                    for (piece in chunkText(s, maxChars)) out.add(piece to if (piece.trimEnd().last() in ".!?…") 0.5 else 0.3)
                    continue
                }
                if (cur.isNotEmpty() && cur.length + 1 + s.length > maxChars) flush()
                cur = if (cur.isEmpty()) s else "$cur $s"
            }
            flush()
            if (out.isNotEmpty()) out[out.size - 1] = out.last().first to 0.7
        }
        return out
    }

    /** Cắt im lặng ở hai đầu (giữ 40 ms) + fade 15 ms (giống trim_and_fade của VieNeu). */
    fun trimAndFade(w: FloatArray, sr: Int = SR): FloatArray {
        if (w.isEmpty()) return w
        val win = max(1, (0.01 * sr).toInt())
        val nWin = w.size / win
        if (nWin == 0) return w
        val th = 10.0.pow(-45.0 / 20).toFloat()
        var first = -1
        var last = -1
        for (i in 0 until nWin) {
            var s = 0f
            for (j in 0 until win) s += kotlin.math.abs(w[i * win + j])
            if (s / win > th) {
                if (first < 0) first = i
                last = i
            }
        }
        if (first < 0) return FloatArray(0)
        val keep = (0.04 * sr).toInt()
        val a = max(0, first * win - keep)
        val b = min(w.size, (last + 1) * win + keep)
        val out = w.copyOfRange(a, b)
        val n = min((0.015 * sr).toInt(), out.size / 2)
        for (i in 0 until n) {
            val g = (0.5 - 0.5 * cos(PI * i / max(1, n - 1))).toFloat()
            out[i] *= g
            out[out.size - 1 - i] *= g
        }
        return out
    }
}

/** Đọc file .npy / .npz của numpy (float32 / float64, little-endian). */
object Npy {
    class Arr(val shape: IntArray, val data: FloatArray)

    fun parse(b: ByteArray): Arr {
        require(b.size > 10 && b[0] == 0x93.toByte()) { "không phải .npy" }
        val major = b[6].toInt()
        val hl = if (major == 1) (b[8].toInt() and 255) or ((b[9].toInt() and 255) shl 8)
        else ByteBuffer.wrap(b, 8, 4).order(ByteOrder.LITTLE_ENDIAN).int
        val start = if (major == 1) 10 else 12
        val header = String(b, start, hl, Charsets.ISO_8859_1)
        val descr = Regex("'descr':\\s*'([^']+)'").find(header)!!.groupValues[1]
        val shape = Regex("'shape':\\s*\\(([^)]*)\\)").find(header)!!.groupValues[1]
            .split(",").map { it.trim() }.filter { it.isNotEmpty() }.map { it.toInt() }.toIntArray()
        val n = shape.fold(1) { a, x -> a * x }
        val bb = ByteBuffer.wrap(b, start + hl, b.size - start - hl).order(ByteOrder.LITTLE_ENDIAN)
        val data = when (descr) {
            "<f4" -> FloatArray(n) { bb.float }
            "<f8" -> FloatArray(n) { bb.double.toFloat() }
            else -> throw IllegalArgumentException("npy kiểu $descr chưa hỗ trợ")
        }
        return Arr(shape, data)
    }

    fun npz(f: File): Map<String, Arr> = ZipFile(f).use { z ->
        z.entries().asSequence().filter { it.name.endsWith(".npy") }
            .associate { e -> e.name.removeSuffix(".npy") to parse(z.getInputStream(e).readBytes()) }
    }
}

/** Kaldi fbank 80 mel (povey, preemph 0.97, bỏ DC, snip_edges) - khớp kaldi-native-fbank (sai lệch ~1e-3). */
object Fbank {
    fun compute(wav: FloatArray, sr: Int = 16000, nMels: Int = 80, meanNorm: Boolean = true): Array<FloatArray> {
        val fl = (sr * 0.025).toInt()
        val fs = (sr * 0.010).toInt()
        require(wav.size >= fl) { "Đoạn ghi âm quá ngắn" }
        val frames = 1 + (wav.size - fl) / fs
        var nfft = 1
        while (nfft < fl) nfft *= 2
        val win = DoubleArray(fl) { (0.5 - 0.5 * cos(2 * PI * it / (fl - 1))).pow(0.85) }
        fun mel(f: Double) = 1127.0 * ln(1 + f / 700.0)
        val lo = mel(20.0)
        val hi = mel(sr / 2.0)
        val d = (hi - lo) / (nMels + 1)
        val half = nfft / 2
        val fm = DoubleArray(half) { mel(it * sr.toDouble() / nfft) }
        val w = Array(nMels) { b ->
            val l = lo + b * d
            val c = l + d
            val r = c + d
            DoubleArray(half) { i ->
                val m = fm[i]
                when {
                    m > l && m <= c -> (m - l) / (c - l)
                    m > c && m < r -> (r - m) / (r - c)
                    else -> 0.0
                }
            }
        }
        val eps = Math.ulp(1.0f).toDouble()
        val re = DoubleArray(nfft)
        val im = DoubleArray(nfft)
        val out = Array(frames) { FloatArray(nMels) }
        for (k in 0 until frames) {
            java.util.Arrays.fill(re, 0.0)
            java.util.Arrays.fill(im, 0.0)
            var mean = 0.0
            for (i in 0 until fl) mean += wav[k * fs + i]
            mean /= fl
            val x = DoubleArray(fl) { wav[k * fs + it] - mean }
            for (i in fl - 1 downTo 1) x[i] -= 0.97 * x[i - 1]
            x[0] -= 0.97 * x[0]
            for (i in 0 until fl) re[i] = x[i] * win[i]
            fft(re, im)
            for (b in 0 until nMels) {
                var e = 0.0
                val wb = w[b]
                for (i in 0 until half) if (wb[i] != 0.0) e += wb[i] * (re[i] * re[i] + im[i] * im[i])
                out[k][b] = ln(max(e, eps)).toFloat()
            }
        }
        if (meanNorm) {
            for (b in 0 until nMels) {
                var m = 0.0
                for (k in 0 until frames) m += out[k][b]
                val mf = (m / frames).toFloat()
                for (k in 0 until frames) out[k][b] -= mf
            }
        }
        return out
    }

    /** FFT radix-2 tại chỗ. */
    fun fft(re: DoubleArray, im: DoubleArray) {
        val n = re.size
        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) {
                j = j xor bit
                bit = bit shr 1
            }
            j = j xor bit
            if (i < j) {
                var t = re[i]; re[i] = re[j]; re[j] = t
                t = im[i]; im[i] = im[j]; im[j] = t
            }
        }
        var len = 2
        while (len <= n) {
            val ang = -2 * PI / len
            val wr = cos(ang)
            val wi = kotlin.math.sin(ang)
            var i = 0
            while (i < n) {
                var cr = 1.0
                var ci = 0.0
                for (k in 0 until len / 2) {
                    val ur = re[i + k]
                    val ui = im[i + k]
                    val vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci
                    val vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr
                    re[i + k] = ur + vr
                    im[i + k] = ui + vi
                    re[i + k + len / 2] = ur - vr
                    im[i + k + len / 2] = ui - vi
                    val ncr = cr * wr - ci * wi
                    ci = cr * wi + ci * wr
                    cr = ncr
                }
                i += len
            }
            len = len shl 1
        }
    }
}

/** 4 mô hình ONNX + vòng lấy mẫu flow-matching (CFG) của VieNeu v3 Nano. */
class NanoEngine(dir: File, threads: Int = 0) : AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    private val opts = OrtSession.SessionOptions().apply {
        setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        setIntraOpNumThreads(if (threads > 0) threads else min(4, max(1, Runtime.getRuntime().availableProcessors() / 2)))
        setInterOpNumThreads(1)
    }
    private val dirF = dir
    private val cfg = JSONObject(File(dir, "config.json").readText())
    private val vocab: Map<String, Int> = cfg.getJSONObject("vocab").let { v -> v.keys().asSequence().associateWith { v.getInt(it) } }
    private val emotion: Map<String, String> = cfg.optJSONObject("emotion_tags")?.let { e -> e.keys().asSequence().associateWith { e.getString(it) } } ?: emptyMap()
    private val bos = cfg.getInt("bos_id")
    private val eos = cfg.getInt("eos_id")
    val fps = cfg.optDouble("flow_fps", 24000.0 / 256 / 6)
    private val group = cfg.optInt("group", 6)
    private val refMaxFrames = cfg.optInt("ref_max_frames", 140)
    private val consts = Npy.npz(File(dir, "constants.npz"))
    private val nullSpk = consts.getValue("null_spk")
    private val nullStyle = consts.getValue("null_style")
    private val sText = env.createSession(File(dir, "text_encoder.onnx").path, opts)
    private val sDur = env.createSession(File(dir, "duration_predictor.onnx").path, opts)
    private val sVe = env.createSession(File(dir, "vector_estimator.onnx").path, opts)
    private val sDec = env.createSession(File(dir, "codec_decoder.onnx").path, opts)
    private val nullCtx: OnnxTensor
    private val nullMask: OnnxTensor

    init {
        val ids = longArrayOf(bos.toLong(), eos.toLong())
        nullMask = OnnxTensor.createTensor(env, arrayOf(booleanArrayOf(true, true)))
        nullCtx = run1(sText, mapOf("ids" to longT(ids), "style" to styleT(nullStyle.data, nullStyle.shape.let { it[it.size - 2] })))
    }

    private fun longT(a: LongArray) = OnnxTensor.createTensor(env, LongBuffer.wrap(a), longArrayOf(1, a.size.toLong()))
    private fun floatT(a: FloatArray, vararg shape: Long) = OnnxTensor.createTensor(env, FloatBuffer.wrap(a), shape)
    private fun styleT(a: FloatArray, rows: Int) = floatT(a, 1, rows.toLong(), (a.size / rows).toLong())

    /** Chạy 1 mô hình -> tensor đầu ra đầu tiên (đóng tensor đầu vào tạm, trừ các tensor dùng lại). */
    private fun run1(s: OrtSession, inputs: Map<String, OnnxTensor>, keep: Set<OnnxTensor> = emptySet()): OnnxTensor {
        val r = s.run(inputs)
        val o = r[0] as OnnxTensor
        val copy = OnnxTensor.createTensor(env, FloatBuffer.wrap(floatsOf(o)), o.info.shape)
        r.close()
        inputs.values.filter { it !in keep && it !== nullCtx && it !== nullMask }.forEach { it.close() }
        return copy
    }

    private fun floatsOf(t: OnnxTensor): FloatArray {
        val b = t.floatBuffer
        return FloatArray(b.remaining()).also { b.get(it) }
    }

    fun ids(phones: String): LongArray {
        var s = phones
        for ((tag, ch) in emotion) s = s.replace(tag, ch)
        val out = mutableListOf(bos.toLong())
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            val ch = String(Character.toChars(cp))
            vocab[ch]?.let { out.add(it.toLong()) }  // ký tự ngoài vocab: bỏ qua (như bản Python)
            i += Character.charCount(cp)
        }
        out.add(eos.toLong())
        return out.toLongArray()
    }

    /** log(giây) mà mô hình dự đoán cho câu - để kiểm tra khớp bản Python. */
    fun logSeconds(phones: String, v: VieNeu.Voice): Double {
        val ids = ids(phones)
        val ctx = run1(sText, mapOf("ids" to longT(ids), "style" to styleT(v.style, v.styleRows)))
        val mask = OnnxTensor.createTensor(env, arrayOf(BooleanArray(ids.size) { true }))
        val d = run1(sDur, mapOf("ctx" to ctx, "ctx_mask" to mask, "spk" to floatT(v.spk, 1, v.spk.size.toLong())))
        val r = floatsOf(d)[0].toDouble()
        d.close()
        return r
    }

    /** 1 đoạn âm vị -> sóng âm 24 kHz. steps 16 (chuẩn) / 8 (nhanh); speed > 1 nói nhanh hơn. */
    fun infer(phones: String, v: VieNeu.Voice, steps: Int = 16, cfgScale: Float = 3f, speed: Float = 1f,
              seed: Long = 1234L, cancel: () -> Boolean = { false }): FloatArray {
        val ids = ids(phones)
        val spkData = v.spk
        val ctx = run1(sText, mapOf("ids" to longT(ids), "style" to styleT(v.style, v.styleRows)))
        val mask = OnnxTensor.createTensor(env, arrayOf(BooleanArray(ids.size) { true }))
        val spk = floatT(spkData, 1, spkData.size.toLong())
        val style = styleT(v.style, v.styleRows)
        val nSpk = floatT(nullSpk.data, 1, nullSpk.data.size.toLong())
        val nStyle = styleT(nullStyle.data, nullStyle.shape.let { it[it.size - 2] })
        try {
            val dT = run1(sDur, mapOf("ctx" to ctx, "ctx_mask" to mask, "spk" to spk), keep = setOf(ctx, mask, spk))
            val logS = floatsOf(dT)[0].toDouble()
            dT.close()
            val secs = min(exp(logS) / max(speed.toDouble(), 1e-3), 15.0)
            val frames = max(2, (secs * fps).roundToInt())
            val rnd = java.util.Random(seed)
            val x = FloatArray(144 * frames) { rnd.nextGaussian().toFloat() }
            val n = max(1, steps)
            for (i in 0 until n) {
                if (cancel()) throw kotlinx.coroutines.CancellationException("Đã hủy")
                val t0 = i.toDouble() / n
                val t1 = (i + 1).toDouble() / n
                val keep = setOf(ctx, mask, spk, style, nSpk, nStyle)
                val vC = run1(sVe, mapOf("x" to floatT(x.copyOf(), 1, 144, frames.toLong()), "t" to floatT(floatArrayOf(t0.toFloat()), 1),
                    "ctx" to ctx, "ctx_mask" to mask, "spk" to spk, "style" to style), keep)
                val vc = floatsOf(vC)
                vC.close()
                val vel = if (cfgScale > 0f) {
                    val vU = run1(sVe, mapOf("x" to floatT(x.copyOf(), 1, 144, frames.toLong()), "t" to floatT(floatArrayOf(t0.toFloat()), 1),
                        "ctx" to nullCtx, "ctx_mask" to nullMask, "spk" to nSpk, "style" to nStyle), keep)
                    val vu = floatsOf(vU)
                    vU.close()
                    FloatArray(vc.size) { vu[it] + cfgScale * (vc[it] - vu[it]) }
                } else vc
                val dt = (t1 - t0).toFloat()
                for (k in x.indices) x[k] += dt * vel[k]
            }
            val w = run1(sDec, mapOf("x" to floatT(x, 1, 144, frames.toLong())))
            val wav = floatsOf(w)
            w.close()
            for (k in wav.indices) wav[k] = wav[k].coerceIn(-1f, 1f)
            return VieNeu.trimAndFade(wav)
        } finally {
            listOf(ctx, mask, spk, style, nSpk, nStyle).forEach { runCatching { it.close() } }
        }
    }

    // ------------------------------------------------------------------ nhân bản giọng
    private var sSpkEnc: OrtSession? = null
    private var sCodecEnc: OrtSession? = null
    private var sRef: OrtSession? = null

    /**
     * Đoạn ghi âm (mono, đã đổi sang 16 kHz và 24 kHz) -> giọng mới: x-vector 192 chiều từ fbank Kaldi của cả đoạn
     * (tối đa 30 s) + style token từ 5 giây đầu (codec latent chuẩn hóa, gộp nhóm 6, qua reference encoder).
     */
    fun cloneVoice(name: String, wav16: FloatArray, wav24: FloatArray, desc: String = ""): VieNeu.Voice {
        if (sSpkEnc == null) {
            sSpkEnc = env.createSession(File(dirF, "speaker_encoder.onnx").path, opts)
            sCodecEnc = env.createSession(File(dirF, "codec_encoder.onnx").path, opts)
            sRef = env.createSession(File(dirF, "reference_encoder.onnx").path, opts)
        }
        // x-vector
        val fb = Fbank.compute(wav16.copyOf(min(wav16.size, 16000 * 30)))
        val flat = FloatArray(fb.size * 80).also { a -> fb.forEachIndexed { i, r -> r.copyInto(a, i * 80) } }
        val spkIn = sSpkEnc!!.inputNames.first()
        val sp = run1(sSpkEnc!!, mapOf(spkIn to floatT(flat, 1, fb.size.toLong(), 80)))
        val spk = floatsOf(sp)
        sp.close()
        // style tokens
        val m24 = wav24.copyOf(min(wav24.size, VieNeu.SR * 5))
        val encIn = sCodecEnc!!.inputNames.first()
        val mu = run1(sCodecEnc!!, mapOf(encIn to floatT(m24, 1, 1, m24.size.toLong())))
        val shape = mu.info.shape  // [1, C, T]
        val c = shape[1].toInt()
        val t = shape[2].toInt()
        val z = floatsOf(mu)
        mu.close()
        val mean = consts.getValue("latent_mean").data
        val std = consts.getValue("latent_std").data
        val scale = consts["latent_scale"]?.data?.get(0) ?: cfg.optDouble("latent_scale", 1.0).toFloat()
        for (ci in 0 until c) for (ti in 0 until t) z[ci * t + ti] = (z[ci * t + ti] - mean[ci]) / std[ci] * scale
        // gộp nhóm: [1,C,T] -> [1, C*g, ceil(T/g)]
        val g = group
        val tp = (t + g - 1) / g
        val grouped = FloatArray(c * g * tp)
        for (ci in 0 until c) for (tt in 0 until tp) for (gi in 0 until g) {
            val src = tt * g + gi
            grouped[(ci * g + gi) * tp + tt] = if (src < t) z[ci * t + src] else 0f
        }
        val keepT = min(tp, min((5.0 * fps).toInt(), refMaxFrames))
        val cropped = FloatArray(c * g * keepT)
        for (row in 0 until c * g) System.arraycopy(grouped, row * tp, cropped, row * keepT, keepT)
        val refMask = OnnxTensor.createTensor(env, arrayOf(BooleanArray(keepT) { true }))
        val st = run1(sRef!!, mapOf("ref" to floatT(cropped, 1, (c * g).toLong(), keepT.toLong()), "ref_mask" to refMask))
        val sShape = st.info.shape  // [1, S, C]
        val style = floatsOf(st)
        st.close()
        return VieNeu.Voice(name, spk, style, sShape[1].toInt(), desc)
    }

    override fun close() {
        listOf(sText, sDur, sVe, sDec, sSpkEnc, sCodecEnc, sRef).forEach { runCatching { it?.close() } }
        runCatching { nullCtx.close() }
        runCatching { nullMask.close() }
    }
}

/** Giọng VieNeu dùng trong app: tải mô hình, đọc câu thành WAV, nhân bản giọng từ file ghi âm. */
class VieNeuTts(private val ctx: Context) {
    private var engine: NanoEngine? = null
    private var g2p: SeaG2p? = null

    @Synchronized
    private fun eng(): NanoEngine = engine ?: NanoEngine(VieNeu.dir(ctx)).also { engine = it }

    @Synchronized
    private fun g2p(): SeaG2p = g2p ?: SeaG2p(File(VieNeu.dir(ctx), "sea_g2p.bin").path).also { g2p = it }

    fun phonemize(text: String): String = g2p().phonemize(text, true)

    suspend fun ensure(clone: Boolean, log: (String) -> Unit, progress: (Float, String) -> Unit) {
        if (!VieNeu.ready(ctx, clone)) VieNeu.download(ctx, clone, log, progress)
    }

    /** Đọc 1 câu -> WAV 24 kHz 16-bit (các đoạn nối với khoảng nghỉ như VieNeu). */
    suspend fun synth(text: String, voice: String, out: File, speed: Float, steps: Int = 16): File = withContext(Dispatchers.Default) {
        val v = VieNeu.allVoices(ctx)[voice] ?: VieNeu.presets(ctx).values.first()
        val e = eng()
        val job = currentCoroutineContext()
        val parts = VieNeu.chunks(text)
        Wav.Writer(out, VieNeu.SR).use { w ->
            for ((k, p) in parts.withIndex()) {
                job.ensureActive()
                val ph = phonemize(p.first)
                val wav = e.infer(ph, v, steps = steps, speed = speed, seed = 1234L + k, cancel = { !job.isActive })
                w.write(Pcm(VieNeu.SR, ShortArray(wav.size) { (wav[it] * 32767f).toInt().toShort() }))
                if (k < parts.size - 1) w.silenceTo(w.seconds + p.second * 0.6)
            }
        }
        out
    }

    /** Nhân bản giọng từ file âm thanh bất kỳ (ghi âm, mp3, video...). */
    suspend fun clone(name: String, src: File, log: (String) -> Unit): VieNeu.Voice = withContext(Dispatchers.Default) {
        val w16 = File(ctx.cacheDir, "clone16.wav")
        val w24 = File(ctx.cacheDir, "clone24.wav")
        // mono + cắt im lặng hai đầu + chuẩn hóa âm lượng, tối đa 30 giây
        val af = "silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=1:stop_threshold=-45dB:stop_duration=0.3," +
            "dynaudnorm=f=150:g=15"
        Ff.run(ctx, listOf("-i", src.path, "-t", "30", "-vn", "-ac", "1", "-af", af, "-ar", "16000", "-c:a", "pcm_s16le", w16.path))
        Ff.run(ctx, listOf("-i", src.path, "-t", "30", "-vn", "-ac", "1", "-af", af, "-ar", "24000", "-c:a", "pcm_s16le", w24.path))
        val a = Wav.read(w16)
        val b = Wav.read(w24)
        if (a.seconds < 3.0) throw IllegalStateException("Đoạn giọng mẫu quá ngắn (${"%.1f".num(a.seconds)} s) - cần 5-15 giây nói rõ.")
        log("Nhân bản giọng từ ${"%.1f".num(a.seconds)} giây ghi âm...")
        val v = eng().cloneVoice(name, FloatArray(a.data.size) { a.data[it] / 32768f }, FloatArray(b.data.size) { b.data[it] / 32768f })
        VieNeu.saveVoice(ctx, v)
        w16.delete()
        w24.delete()
        v
    }

    fun close() {
        engine?.close()
        g2p?.close()
        engine = null
        g2p = null
    }
}
