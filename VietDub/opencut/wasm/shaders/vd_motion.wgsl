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

// p0 độ mờ (px), p1 góc (độ), p2 kiểu (0 = theo hướng, 1 = phóng từ tâm), p3 tâm x, p4 tâm y
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    var dir: vec2f;
    if (u.scalars.z > 0.5) {
        dir = (input.tex_coord - vec2f(u.scalars.w, u.extra0.x)) * u.scalars.x / 100.0;
    } else {
        let a = radians(u.scalars.y);
        dir = vec2f(cos(a), sin(a)) * u.scalars.x / u.resolution;
    }
    var acc = vec4f(0.0);
    for (var i = 0; i < 24; i = i + 1) {
        let t = f32(i) / 23.0 - 0.5;
        acc = acc + sample(input.tex_coord + dir * t);
    }
    return acc / 24.0;
}
