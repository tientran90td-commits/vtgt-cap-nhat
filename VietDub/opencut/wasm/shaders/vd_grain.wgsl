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

fn hash(p: vec2f) -> f32 {
    let q = fract(p * vec2f(123.34, 456.21));
    let r = q + dot(q, q + 45.32);
    return fract(r.x * r.y);
}
// p0 lượng nhiễu, p1 cỡ hạt (px), p2 hạt giống (đổi theo thời gian bằng khung hình chính để hạt chuyển động)
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    let px = floor(input.tex_coord * u.resolution / max(u.scalars.y, 1.0));
    let n = hash(px + vec2f(u.scalars.z * 17.0, u.scalars.z * 31.0)) - 0.5;
    let l = luma(src.rgb);
    let amt = u.scalars.x * (1.0 - abs(l - 0.5));
    return vec4f(clamp(src.rgb + vec3f(n * amt), vec3f(0.0), vec3f(1.0)), src.a);
}
