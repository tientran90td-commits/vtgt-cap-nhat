struct VertexOutput {
    @builtin(position) position: vec4f,
    @location(0) tex_coord: vec2f,
}

// (VietDub) tham số chung: p0..p3 = scalars, p4..p7 = extra0, p8..p11 = extra1
struct EffectUniforms {
    resolution: vec2f,
    direction: vec2f,
    scalars: vec4f,
    extra0: vec4f,
    extra1: vec4f,
}

@group(0) @binding(0) var input_texture: texture_2d<f32>;
@group(0) @binding(1) var input_sampler: sampler;
@group(1) @binding(0) var<uniform> u: EffectUniforms;

fn luma(c: vec3f) -> f32 { return dot(c, vec3f(0.2126, 0.7152, 0.0722)); }
fn sample(uv: vec2f) -> vec4f { return textureSampleLevel(input_texture, input_sampler, clamp(uv, vec2f(0.0), vec2f(1.0)), 0.0); }

fn rgb2hsv(c: vec3f) -> vec3f {
    let k = vec4f(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    let p = mix(vec4f(c.bg, k.wz), vec4f(c.gb, k.xy), step(c.b, c.g));
    let q = mix(vec4f(p.xyw, c.r), vec4f(c.r, p.yzx), step(p.x, c.r));
    let d = q.x - min(q.w, q.y);
    let e = 1.0e-10;
    return vec3f(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}
fn hsv2rgb(c: vec3f) -> vec3f {
    let k = vec4f(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    let p = abs(fract(c.xxx + k.xyz) * 6.0 - k.www);
    return c.z * mix(k.xxx, clamp(p - k.xxx, vec3f(0.0), vec3f(1.0)), c.y);
}

// p0 sáng, p1 tương phản, p2 bão hòa, p3 phơi sáng (stop), p4 nhiệt độ màu, p5 sắc xanh-tím,
// p6 xoay màu (độ), p7 sống động, p8 vùng sáng, p9 vùng tối, p10 gamma
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    var c = src.rgb;
    c = c * exp2(u.scalars.w);
    c = c + vec3f(u.scalars.x);
    c = (c - 0.5) * (1.0 + u.scalars.y) + 0.5;
    c = c + vec3f(u.extra0.x * 0.10, u.extra0.y * -0.04 + u.extra0.x * 0.02, -u.extra0.x * 0.10);
    c = c + vec3f(u.extra0.y * 0.05, -u.extra0.y * 0.06, u.extra0.y * 0.05);
    let l = luma(clamp(c, vec3f(0.0), vec3f(1.0)));
    c = c + u.extra1.x * smoothstep(0.5, 1.0, l) * 0.5 + u.extra1.y * (1.0 - smoothstep(0.0, 0.5, l)) * 0.5;
    var g = vec3f(luma(c));
    c = mix(g, c, 1.0 + u.scalars.z);
    let sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    c = mix(vec3f(luma(c)), c, 1.0 + u.extra0.w * (1.0 - clamp(sat, 0.0, 1.0)));
    c = clamp(c, vec3f(0.0), vec3f(1.0));
    if (abs(u.extra0.z) > 0.01) {
        var h = rgb2hsv(c);
        h.x = fract(h.x + u.extra0.z / 360.0);
        c = hsv2rgb(h);
    }
    let gm = max(u.extra1.z, 0.05);
    c = pow(c, vec3f(1.0 / gm));
    return vec4f(clamp(c, vec3f(0.0), vec3f(1.0)), src.a);
}
