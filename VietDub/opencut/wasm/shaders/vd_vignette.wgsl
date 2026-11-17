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

// p0 độ tối (âm = viền sáng), p1 bán kính, p2 độ mềm, p3 độ tròn (0 = theo khung, 1 = tròn)
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    var d = input.tex_coord - vec2f(0.5);
    let aspect = u.resolution.x / max(u.resolution.y, 1.0);
    d.x = mix(d.x, d.x * aspect, clamp(u.scalars.w, 0.0, 1.0));
    let r = length(d) * 1.4142;
    let v = smoothstep(u.scalars.y, u.scalars.y + max(u.scalars.z, 0.01), r);
    var c = src.rgb;
    if (u.scalars.x >= 0.0) {
        c = c * (1.0 - v * u.scalars.x);
    } else {
        c = mix(c, vec3f(1.0), v * -u.scalars.x);
    }
    return vec4f(c, src.a);
}
