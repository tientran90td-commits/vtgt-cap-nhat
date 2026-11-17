"""(VietDub) Thêm hiệu ứng mới vào lõi WebAssembly của OpenCut (rust/crates/effects).

- Chép các shader WGSL vd_*.wgsl vào crates/effects/src/shaders/.
- Đăng ký mỗi shader thành 1 pipeline (cùng cách với gaussian-blur có sẵn).
- Bộ đệm tham số thêm 8 số (extra0, extra1): shader mới nhận u_p0..u_p11; gaussian-blur giữ nguyên.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHADERS = ["vd_color", "vd_tone", "vd_vignette", "vd_sharpen", "vd_pixelate", "vd_chromatic", "vd_grain",
           "vd_glow", "vd_motion", "vd_mirror", "vd_duotone"]


def sub(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    if old not in s:
        raise SystemExit(f"Không tìm thấy đoạn cần sửa trong {path}: {old[:90]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def fix_scene_effect(rust: Path) -> None:
    """Lỗi có sẵn của OpenCut: rename_all của serde không đổi tên trường trong biến thể enum, nên dữ liệu
    {type: "sceneEffect", effectPassGroups} từ TypeScript báo "missing field effect_pass_groups" -> hiệu ứng đặt
    trên rãnh hiệu ứng không bao giờ hiện. Đặt tên trường đúng như TypeScript gửi."""
    f = rust / "crates" / "compositor" / "src" / "frame.rs"
    old = "    SceneEffect {\n        effect_pass_groups: Vec<Vec<EffectPassDescriptor>>,"
    if old in f.read_text(encoding="utf-8"):
        sub(f, old, "    SceneEffect {\n        #[serde(rename = \"effectPassGroups\")]\n"
                    "        effect_pass_groups: Vec<Vec<EffectPassDescriptor>>,")


def fix_webgl_shared_canvas(rust: Path) -> None:
    """Lỗi có sẵn (WebGL): ảnh mẫu hiệu ứng và khung xem trước dùng CHUNG 1 canvas của ngữ cảnh WebGL. Ảnh mẫu đổi
    canvas về 160x160, khung xem trước vẫn nhớ "bề mặt 640x360" nên không cấu hình lại -> chỉ góc trên-trái lọt vào
    (trông như phóng to). Sửa: so với kích thước THẬT của canvas, khác là đặt lại + cấu hình lại bề mặt."""
    comp = rust / "wasm" / "src" / "compositor.rs"
    old = "            if runtime.surface_size != (frame.width, frame.height) {"
    if old in comp.read_text(encoding="utf-8"):
        sub(comp, old, "            if runtime.surface_size != (frame.width, frame.height)\n"
                       "                || runtime.canvas.width() != frame.width\n"
                       "                || runtime.canvas.height() != frame.height\n            {")
    ctx = rust / "crates" / "gpu" / "src" / "context.rs"
    old = "        gl_canvas.set_width(width);\n        gl_canvas.set_height(height);\n"
    if old in ctx.read_text(encoding="utf-8"):
        sub(ctx, old, "        let canvas_changed = gl_canvas.width() != width || gl_canvas.height() != height;\n"
                      "        gl_canvas.set_width(width);\n        gl_canvas.set_height(height);\n")
        sub(ctx, "        if cached_surface.size != (width, height) {\n            self.configure_surface(&cached_surface.surface, width, height)?;",
            "        if canvas_changed || cached_surface.size != (width, height) {\n"
            "            self.configure_surface(&cached_surface.surface, width, height)?;")


def apply(rust: Path) -> None:
    fix_scene_effect(rust)
    fix_webgl_shared_canvas(rust)
    eff = rust / "crates" / "effects" / "src"
    for name in SHADERS:
        shutil.copy2(HERE / "shaders" / f"{name}.wgsl", eff / "shaders" / f"{name}.wgsl")
    p = eff / "pipeline.rs"
    if "VD_SHADERS" in p.read_text(encoding="utf-8"):
        return
    # Lỗi có sẵn (WebGL): lượt vẽ hiệu ứng không đặt khung vẽ -> dùng lại khung của lần vẽ trước (khung xem trước
    # lớn hơn) -> hình hiệu ứng bị phóng to vào 1 góc. Đặt khung vẽ = đúng kích thước texture.
    sub(p, "                render_pass.set_pipeline(pipeline);",
        "                render_pass.set_viewport(0.0, 0.0, width as f32, height as f32, 0.0, 1.0);\n"
        "                render_pass.set_scissor_rect(0, 0, width, height);\n"
        "                render_pass.set_pipeline(pipeline);")
    table = "\n".join(f'    ("{n.replace("_", "-")}", include_str!("shaders/{n}.wgsl")),' for n in SHADERS)
    sub(p, 'const GAUSSIAN_BLUR_SHADER_SOURCE: &str = include_str!("shaders/gaussian_blur.wgsl");',
        'const GAUSSIAN_BLUR_SHADER_SOURCE: &str = include_str!("shaders/gaussian_blur.wgsl");\n\n'
        "/// (VietDub) hiệu ứng thêm: (id shader, mã WGSL). Tham số: u_p0..u_p11.\n"
        f"const VD_SHADERS: &[(&str, &str)] = &[\n{table}\n];\nconst VD_PARAM_COUNT: usize = 12;")
    sub(p, "    direction: [f32; 2],\n    scalars: [f32; 4],\n}",
        "    direction: [f32; 2],\n    scalars: [f32; 4],\n    extra0: [f32; 4],\n    extra1: [f32; 4],\n}")
    sub(p, "        let pipelines =\n            HashMap::from([(GAUSSIAN_BLUR_SHADER_ID.to_string(), gaussian_blur_pipeline)]);",
        '''        let mut pipelines =
            HashMap::from([(GAUSSIAN_BLUR_SHADER_ID.to_string(), gaussian_blur_pipeline)]);
        for (id, source) in VD_SHADERS {
            let module = context
                .device()
                .create_shader_module(wgpu::ShaderModuleDescriptor {
                    label: Some(id),
                    source: wgpu::ShaderSource::Wgsl((*source).into()),
                });
            let pipeline = context
                .device()
                .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                    label: Some(id),
                    layout: Some(&pipeline_layout),
                    vertex: wgpu::VertexState {
                        module: &vertex_shader_module,
                        entry_point: Some("vertex_main"),
                        buffers: &[wgpu::VertexBufferLayout {
                            array_stride: std::mem::size_of::<[f32; 2]>() as u64,
                            step_mode: wgpu::VertexStepMode::Vertex,
                            attributes: &[wgpu::VertexAttribute {
                                format: wgpu::VertexFormat::Float32x2,
                                offset: 0,
                                shader_location: 0,
                            }],
                        }],
                        compilation_options: wgpu::PipelineCompilationOptions::default(),
                    },
                    fragment: Some(wgpu::FragmentState {
                        module: &module,
                        entry_point: Some("fragment_main"),
                        targets: &[Some(wgpu::ColorTargetState {
                            format: context.texture_format(),
                            blend: None,
                            write_mask: wgpu::ColorWrites::ALL,
                        })],
                        compilation_options: wgpu::PipelineCompilationOptions::default(),
                    }),
                    primitive: wgpu::PrimitiveState::default(),
                    depth_stencil: None,
                    multisample: wgpu::MultisampleState::default(),
                    multiview_mask: None,
                    cache: None,
                });
            pipelines.insert((*id).to_string(), pipeline);
        }''')
    sub(p, "    let shader = pass.shader.as_str();\n    let sigma = read_number_uniform(pass, \"u_sigma\")?;",
        "    let shader = pass.shader.as_str();\n    if shader != GAUSSIAN_BLUR_SHADER_ID {\n"
        "        return pack_vd_uniforms(pass, width, height);\n    }\n"
        "    let sigma = read_number_uniform(pass, \"u_sigma\")?;")
    sub(p, "        scalars: [sigma, step, 0.0, 0.0],\n    })\n}",
        '''        scalars: [sigma, step, 0.0, 0.0],
        extra0: [0.0; 4],
        extra1: [0.0; 4],
    })
}

/// (VietDub) hiệu ứng mới: u_p0..u_p11 (thiếu = 0) -> scalars, extra0, extra1.
fn pack_vd_uniforms(
    pass: &EffectPass,
    width: u32,
    height: u32,
) -> Result<EffectUniformBuffer, EffectsError> {
    let mut p = [0.0f32; VD_PARAM_COUNT];
    for (name, value) in &pass.uniforms {
        let index = name
            .strip_prefix("u_p")
            .and_then(|i| i.parse::<usize>().ok())
            .filter(|i| *i < VD_PARAM_COUNT)
            .ok_or_else(|| EffectsError::UnsupportedUniform {
                shader: pass.shader.clone(),
                uniform: name.clone(),
            })?;
        p[index] = match value {
            UniformValue::Number(v) => *v,
            UniformValue::Vector(_) => {
                return Err(EffectsError::InvalidNumberUniform {
                    shader: pass.shader.clone(),
                    uniform: name.clone(),
                });
            }
        };
    }
    Ok(EffectUniformBuffer {
        resolution: [width as f32, height as f32],
        direction: [0.0, 0.0],
        scalars: [p[0], p[1], p[2], p[3]],
        extra0: [p[4], p[5], p[6], p[7]],
        extra1: [p[8], p[9], p[10], p[11]],
    })
}''')


if __name__ == "__main__":
    apply(Path(sys.argv[1]))
    print("đã thêm", len(SHADERS), "hiệu ứng")
