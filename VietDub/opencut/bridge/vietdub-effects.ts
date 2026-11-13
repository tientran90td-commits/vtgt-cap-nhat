/**
 * (VietDub) Hiệu ứng thêm cho OpenCut - chạy bằng shader vd-* trong lõi WebAssembly đã dựng lại
 * (xem VietDub/opencut/wasm). Mỗi tham số được đổi thành u_p0..u_p11 cho shader.
 */
import type { EffectDefinition } from "@/effects/types";

type P = Record<string, unknown>;
const num = (p: P, k: string, d = 0): number => {
	const v = p[k];
	const n = typeof v === "number" ? v : Number.parseFloat(String(v));
	return Number.isFinite(n) ? n : d;
};
const bool = (p: P, k: string): number => (p[k] === true || p[k] === "true" ? 1 : 0);

function rgb(value: unknown, fallback: [number, number, number]): [number, number, number] {
	const s = String(value ?? "").trim();
	let m = /^#?([0-9a-f]{6})/i.exec(s);
	if (m) {
		const n = Number.parseInt(m[1], 16);
		return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
	}
	m = /^#?([0-9a-f]{3})$/i.exec(s);
	if (m) {
		const [r, g, b] = m[1].split("").map((c) => Number.parseInt(c + c, 16) / 255);
		return [r, g, b];
	}
	m = /rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/i.exec(s);
	if (m) return [Number(m[1]) / 255, Number(m[2]) / 255, Number(m[3]) / 255];
	return fallback;
}

const n = (key: string, label: string, def: number, min: number, max: number, step = 1) =>
	({ key, label, type: "number" as const, default: def, min, max, step });

// ------------------------------------------------------------------ Chỉnh màu
type Color = { b?: number; c?: number; s?: number; e?: number; t?: number; ti?: number; h?: number; v?: number; hi?: number; sh?: number; g?: number };
const colorUniforms = (x: Color, k = 1) => ({
	u_p0: (x.b ?? 0) * k, u_p1: (x.c ?? 0) * k, u_p2: (x.s ?? 0) * k, u_p3: (x.e ?? 0) * k,
	u_p4: (x.t ?? 0) * k, u_p5: (x.ti ?? 0) * k, u_p6: (x.h ?? 0) * k, u_p7: (x.v ?? 0) * k,
	u_p8: (x.hi ?? 0) * k, u_p9: (x.sh ?? 0) * k, u_p10: 1 + ((x.g ?? 1) - 1) * k,
});

export const colorAdjustEffect: EffectDefinition = {
	type: "vd-color",
	name: "Chỉnh màu",
	keywords: ["màu", "sáng", "tương phản", "bão hòa", "color", "brightness", "contrast", "saturation"],
	params: [
		n("brightness", "Độ sáng", 0, -100, 100), n("contrast", "Tương phản", 0, -100, 100),
		n("saturation", "Bão hòa", 0, -100, 100), n("vibrance", "Sống động", 0, -100, 100),
		n("exposure", "Phơi sáng", 0, -300, 300), n("temperature", "Nhiệt độ màu", 0, -100, 100),
		n("tint", "Sắc xanh - tím", 0, -100, 100), n("hue", "Xoay màu (độ)", 0, -180, 180),
		n("highlights", "Vùng sáng", 0, -100, 100), n("shadows", "Vùng tối", 0, -100, 100),
		n("gamma", "Gamma", 100, 20, 300),
	],
	renderer: {
		passes: [{
			shader: "vd-color",
			uniforms: ({ effectParams: p }) => colorUniforms({
				b: num(p, "brightness") / 200, c: num(p, "contrast") / 100, s: num(p, "saturation") / 100,
				v: num(p, "vibrance") / 100, e: num(p, "exposure") / 100, t: num(p, "temperature") / 100,
				ti: num(p, "tint") / 100, h: num(p, "hue"), hi: num(p, "highlights") / 100,
				sh: num(p, "shadows") / 100, g: num(p, "gamma", 100) / 100,
			}),
		}],
	},
};

// ------------------------------------------------------------------ Bộ lọc màu có sẵn
type Tone = { gray?: number; sepia?: number; fade?: number; split?: number };
const PRESETS: Record<string, { label: string; color: Color; tone: Tone }> = {
	warm: { label: "Ấm áp", color: { t: 0.45, s: 0.12, b: 0.02 }, tone: {} },
	cool: { label: "Lạnh", color: { t: -0.45, ti: -0.1, s: -0.05 }, tone: {} },
	cinema: { label: "Điện ảnh (xanh - cam)", color: { c: 0.18, s: -0.08, sh: -0.1 }, tone: { split: 0.55 } },
	vintage: { label: "Hoài cổ", color: { c: -0.1, t: 0.25, s: -0.25 }, tone: { fade: 0.6, sepia: 0.2 } },
	bw: { label: "Đen trắng", color: { c: 0.15 }, tone: { gray: 1 } },
	noir: { label: "Đen trắng gắt", color: { c: 0.45, b: -0.04 }, tone: { gray: 1 } },
	sepia: { label: "Nâu cổ điển (sepia)", color: { c: 0.05 }, tone: { sepia: 0.85 } },
	vivid: { label: "Rực rỡ", color: { s: 0.45, v: 0.3, c: 0.12 }, tone: {} },
	fade: { label: "Phai màu", color: { c: -0.2, s: -0.3 }, tone: { fade: 0.8 } },
	night: { label: "Đêm", color: { b: -0.06, t: -0.55, s: -0.25, c: 0.1 }, tone: {} },
	candy: { label: "Kẹo ngọt", color: { s: 0.25, ti: 0.3, b: 0.04, hi: 0.15 }, tone: { fade: 0.2 } },
	autumn: { label: "Mùa thu", color: { t: 0.5, h: -8, s: 0.15, c: 0.08 }, tone: { split: 0.2 } },
	matte: { label: "Mờ lì", color: { c: -0.25, sh: 0.25 }, tone: { fade: 0.5 } },
};

export const filterPresetEffect: EffectDefinition = {
	type: "vd-filter",
	name: "Bộ lọc màu",
	keywords: ["bộ lọc", "filter", "lut", "preset", "điện ảnh", "hoài cổ", "đen trắng"],
	params: [
		{
			key: "preset", label: "Bộ lọc", type: "select", default: "cinema",
			options: Object.entries(PRESETS).map(([value, x]) => ({ value, label: x.label })),
		},
		n("intensity", "Độ mạnh", 100, 0, 100),
	],
	renderer: {
		passes: [
			{
				shader: "vd-color",
				uniforms: ({ effectParams: p }) =>
					colorUniforms((PRESETS[String(p.preset)] ?? PRESETS.cinema).color, num(p, "intensity", 100) / 100),
			},
			{
				shader: "vd-tone",
				uniforms: ({ effectParams: p }) => {
					const t = (PRESETS[String(p.preset)] ?? PRESETS.cinema).tone;
					const k = num(p, "intensity", 100) / 100;
					return { u_p0: (t.gray ?? 0) * k, u_p1: (t.sepia ?? 0) * k, u_p2: (t.fade ?? 0) * k,
						u_p3: 0, u_p4: 0, u_p5: (t.split ?? 0) * k };
				},
			},
		],
	},
};

export const toneEffect: EffectDefinition = {
	type: "vd-tone",
	name: "Đen trắng & tông màu",
	keywords: ["đen trắng", "sepia", "phai", "đảo màu", "posterize", "grayscale", "invert"],
	params: [
		n("gray", "Đen trắng", 100, 0, 100), n("sepia", "Nâu cổ điển", 0, 0, 100), n("fade", "Phai màu", 0, 0, 100),
		n("invert", "Đảo màu", 0, 0, 100), n("levels", "Số mức màu (0 = tắt)", 0, 0, 16),
		n("split", "Tách tông xanh - cam", 0, 0, 100),
	],
	renderer: {
		passes: [{
			shader: "vd-tone",
			uniforms: ({ effectParams: p }) => ({
				u_p0: num(p, "gray", 100) / 100, u_p1: num(p, "sepia") / 100, u_p2: num(p, "fade") / 100,
				u_p3: num(p, "invert") / 100, u_p4: num(p, "levels"), u_p5: num(p, "split") / 100,
			}),
		}],
	},
};

export const vignetteEffect: EffectDefinition = {
	type: "vd-vignette",
	name: "Viền tối",
	keywords: ["vignette", "viền", "tối góc"],
	params: [n("amount", "Độ tối (âm = viền sáng)", 60, -100, 100), n("size", "Kích thước", 55, 0, 100),
		n("softness", "Độ mềm", 45, 1, 100), n("round", "Tròn đều", 0, 0, 100)],
	renderer: {
		passes: [{
			shader: "vd-vignette",
			uniforms: ({ effectParams: p }) => ({
				u_p0: num(p, "amount", 60) / 100, u_p1: num(p, "size", 55) / 100,
				u_p2: num(p, "softness", 45) / 100, u_p3: num(p, "round") / 100,
			}),
		}],
	},
};

export const sharpenEffect: EffectDefinition = {
	type: "vd-sharpen",
	name: "Làm nét",
	keywords: ["sharpen", "nét", "rõ"],
	params: [n("amount", "Độ nét", 80, 0, 300), n("radius", "Bán kính (px)", 1, 0.5, 5, 0.1)],
	renderer: {
		passes: [{
			shader: "vd-sharpen",
			uniforms: ({ effectParams: p, width }) => ({
				u_p0: num(p, "amount", 80) / 100, u_p1: num(p, "radius", 1) * Math.max(1, width / 1920),
			}),
		}],
	},
};

export const pixelateEffect: EffectDefinition = {
	type: "vd-pixelate",
	name: "Khảm điểm ảnh",
	keywords: ["pixel", "khảm", "che", "mosaic", "censor"],
	params: [n("size", "Cỡ ô (px)", 20, 1, 150)],
	renderer: {
		passes: [{
			shader: "vd-pixelate",
			uniforms: ({ effectParams: p, width }) => ({ u_p0: num(p, "size", 20) * (width / 1920) }),
		}],
	},
};

export const chromaticEffect: EffectDefinition = {
	type: "vd-chromatic",
	name: "Lệch màu RGB",
	keywords: ["rgb", "chromatic", "glitch", "lệch màu"],
	params: [n("amount", "Độ lệch (px)", 6, 0, 60), n("angle", "Góc", 0, -180, 180),
		{ key: "radial", label: "Tỏa từ tâm", type: "boolean", default: false }],
	renderer: {
		passes: [{
			shader: "vd-chromatic",
			uniforms: ({ effectParams: p, width }) => ({
				u_p0: num(p, "amount", 6) * (width / 1920), u_p1: num(p, "angle"), u_p2: bool(p, "radial"),
			}),
		}],
	},
};

export const grainEffect: EffectDefinition = {
	type: "vd-grain",
	name: "Nhiễu hạt phim",
	keywords: ["grain", "nhiễu", "hạt", "film"],
	params: [n("amount", "Lượng nhiễu", 25, 0, 100), n("size", "Cỡ hạt (px)", 1.5, 1, 8, 0.5),
		n("seed", "Hạt giống (đặt khung hình chính để hạt chuyển động)", 0, 0, 1000)],
	renderer: {
		passes: [{
			shader: "vd-grain",
			uniforms: ({ effectParams: p, width }) => ({
				u_p0: num(p, "amount", 25) / 100, u_p1: num(p, "size", 1.5) * Math.max(1, width / 1920), u_p2: num(p, "seed"),
			}),
		}],
	},
};

export const glowEffect: EffectDefinition = {
	type: "vd-glow",
	name: "Phát sáng",
	keywords: ["glow", "bloom", "sáng", "lung linh"],
	params: [n("intensity", "Cường độ", 50, 0, 100), n("radius", "Bán kính (px)", 20, 1, 80), n("threshold", "Ngưỡng sáng", 60, 0, 100)],
	renderer: {
		passes: [{
			shader: "vd-glow",
			uniforms: ({ effectParams: p, width }) => ({
				u_p0: num(p, "intensity", 50) / 100, u_p1: num(p, "radius", 20) * (width / 1920), u_p2: num(p, "threshold", 60) / 100,
			}),
		}],
	},
};

export const motionBlurEffect: EffectDefinition = {
	type: "vd-motion",
	name: "Mờ chuyển động",
	keywords: ["motion blur", "mờ", "tốc độ", "chuyển động"],
	params: [n("amount", "Độ mờ (px)", 30, 0, 200), n("angle", "Hướng (độ)", 0, -180, 180)],
	renderer: {
		passes: [{
			shader: "vd-motion",
			uniforms: ({ effectParams: p, width }) => ({ u_p0: num(p, "amount", 30) * (width / 1920), u_p1: num(p, "angle"), u_p2: 0 }),
		}],
	},
};

export const zoomBlurEffect: EffectDefinition = {
	type: "vd-zoom-blur",
	name: "Mờ phóng to",
	keywords: ["zoom blur", "mờ phóng", "tâm"],
	params: [n("amount", "Độ mờ", 20, 0, 100), n("cx", "Tâm ngang (%)", 50, 0, 100), n("cy", "Tâm dọc (%)", 50, 0, 100)],
	renderer: {
		passes: [{
			shader: "vd-motion",
			uniforms: ({ effectParams: p }) => ({
				u_p0: num(p, "amount", 20) / 2, u_p1: 0, u_p2: 1, u_p3: num(p, "cx", 50) / 100, u_p4: num(p, "cy", 50) / 100,
			}),
		}],
	},
};

const MIRROR = ["flip-h", "flip-v", "mirror-lr", "mirror-tb", "mirror-4"];
export const mirrorEffect: EffectDefinition = {
	type: "vd-mirror",
	name: "Lật / gương",
	keywords: ["lật", "gương", "mirror", "flip"],
	params: [{
		key: "mode", label: "Kiểu", type: "select", default: "flip-h",
		options: [
			{ value: "flip-h", label: "Lật ngang" }, { value: "flip-v", label: "Lật dọc" },
			{ value: "mirror-lr", label: "Gương trái sang phải" }, { value: "mirror-tb", label: "Gương trên xuống dưới" },
			{ value: "mirror-4", label: "Gương 4 phía" },
		],
	}],
	renderer: {
		passes: [{
			shader: "vd-mirror",
			uniforms: ({ effectParams: p }) => ({ u_p0: Math.max(0, MIRROR.indexOf(String(p.mode))) }),
		}],
	},
};

export const duotoneEffect: EffectDefinition = {
	type: "vd-duotone",
	name: "Hai tông màu",
	keywords: ["duotone", "hai màu", "tông"],
	params: [
		{ key: "dark", label: "Màu vùng tối", type: "color", default: "#1b1464" },
		{ key: "light", label: "Màu vùng sáng", type: "color", default: "#ffb86c" },
		n("strength", "Độ mạnh", 100, 0, 100),
	],
	renderer: {
		passes: [{
			shader: "vd-duotone",
			uniforms: ({ effectParams: p }) => {
				const [r0, g0, b0] = rgb(p.dark, [0.1, 0.08, 0.4]);
				const [r1, g1, b1] = rgb(p.light, [1, 0.72, 0.42]);
				return { u_p0: r0, u_p1: g0, u_p2: b0, u_p4: r1, u_p5: g1, u_p6: b1, u_p8: num(p, "strength", 100) / 100 };
			},
		}],
	},
};

export const VIETDUB_EFFECTS: EffectDefinition[] = [
	filterPresetEffect, colorAdjustEffect, toneEffect, vignetteEffect, sharpenEffect, glowEffect, grainEffect,
	chromaticEffect, motionBlurEffect, zoomBlurEffect, pixelateEffect, mirrorEffect, duotoneEffect,
];
