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

// p0 đen trắng, p1 sepia, p2 phai màu, p3 đảo màu, p4 số mức màu (0 = tắt), p5 tách tông xanh-cam
@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let src = sample(input.tex_coord);
    var c = src.rgb;
    let l = luma(c);
    c = mix(c, vec3f(l), clamp(u.scalars.x, 0.0, 1.0));
    let sep = vec3f(dot(c, vec3f(0.393, 0.769, 0.189)), dot(c, vec3f(0.349, 0.686, 0.168)), dot(c, vec3f(0.272, 0.534, 0.131)));
    c = mix(c, sep, clamp(u.scalars.y, 0.0, 1.0));
    let st = clamp(u.extra0.y, 0.0, 1.0);
    let tone = mix(vec3f(0.0, 0.32, 0.38), vec3f(1.0, 0.58, 0.28), smoothstep(0.15, 0.85, l));
    c = mix(c, c * 0.6 + tone * 0.45 * (0.4 + l), st);
    let fade = clamp(u.scalars.z, 0.0, 1.0);
    c = c * (1.0 - fade * 0.25) + vec3f(fade * 0.12);
    c = mix(c, vec3f(l * 0.9 + 0.05), fade * 0.25);
    c = mix(c, vec3f(1.0) - c, clamp(u.scalars.w, 0.0, 1.0));
    let levels = floor(u.extra0.x);
    if (levels >= 2.0) {
        c = floor(c * levels + 0.5) / levels;
    }
    return vec4f(clamp(c, vec3f(0.0), vec3f(1.0)), src.a);
}
