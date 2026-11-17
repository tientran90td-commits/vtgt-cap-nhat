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

// p0 cường độ, p1 bán kính (px), p2 ngưỡng sáng
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    var acc = vec3f(0.0);
    var wsum = 0.0;
    let rad = max(u.scalars.y, 1.0);
    for (var ring = 1; ring <= 4; ring = ring + 1) {
        let rr = rad * f32(ring) / 4.0;
        for (var k = 0; k < 12; k = k + 1) {
            let a = f32(k) * 0.5236 + f32(ring) * 0.26;
            let s = sample(input.tex_coord + vec2f(cos(a), sin(a)) * rr / u.resolution).rgb;
            let w = 1.0 / f32(ring);
            acc = acc + max(s - vec3f(u.scalars.z), vec3f(0.0)) * w;
            wsum = wsum + w;
        }
    }
    let glow = acc / max(wsum, 0.001);
    return vec4f(clamp(src.rgb + glow * u.scalars.x * 3.0, vec3f(0.0), vec3f(1.0)), src.a);
}
