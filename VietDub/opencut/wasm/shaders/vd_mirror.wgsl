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

// p0 kiểu: 0 lật ngang, 1 lật dọc, 2 gương trái->phải, 3 gương trên->dưới, 4 gương 4 phía
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    var uv = input.tex_coord;
    let m = u32(u.scalars.x + 0.5);
    if (m == 0u) { uv.x = 1.0 - uv.x; }
    else if (m == 1u) { uv.y = 1.0 - uv.y; }
    else if (m == 2u) { uv.x = 0.5 - abs(uv.x - 0.5); }
    else if (m == 3u) { uv.y = 0.5 - abs(uv.y - 0.5); }
    else { uv = vec2f(0.5) - abs(uv - vec2f(0.5)); }
    return sample(uv);
}
