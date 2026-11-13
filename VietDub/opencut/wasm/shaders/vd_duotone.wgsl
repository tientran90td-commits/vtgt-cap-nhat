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

// p0..p2 màu vùng tối (rgb), p4..p6 màu vùng sáng (rgb), p8 độ mạnh
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    let l = luma(src.rgb);
    let c = mix(u.scalars.xyz, u.extra0.xyz, l);
    return vec4f(mix(src.rgb, c, clamp(u.extra1.x, 0.0, 1.0)), src.a);
}
