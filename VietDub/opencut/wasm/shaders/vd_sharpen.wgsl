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

// p0 độ nét, p1 bán kính (px)
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let t = max(u.scalars.y, 0.5) / u.resolution;
    let src = sample(input.tex_coord);
    let blur = (sample(input.tex_coord + vec2f(t.x, 0.0)) + sample(input.tex_coord - vec2f(t.x, 0.0)) +
                sample(input.tex_coord + vec2f(0.0, t.y)) + sample(input.tex_coord - vec2f(0.0, t.y))) * 0.25;
    let c = src.rgb + (src.rgb - blur.rgb) * u.scalars.x;
    return vec4f(clamp(c, vec3f(0.0), vec3f(1.0)), src.a);
}
