"""Gắn cầu nối VietDub vào OpenCut: thêm hook tự nạp video/thuyết minh/phụ đề khi mở từ VietDub."""
from __future__ import annotations

import shutil
from pathlib import Path


def _sub(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    if old not in s:
        raise SystemExit(f"Không tìm thấy đoạn cần sửa trong {path}: {old[:80]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def apply(web: Path, bridge: Path) -> None:
    src = web / "src"
    (src / "vietdub").mkdir(exist_ok=True)
    shutil.copy2(bridge / "vietdub-bridge.tsx", src / "vietdub" / "bridge.tsx")
    shutil.copy2(bridge / "vietdub-import.ts", src / "vietdub" / "import.ts")
    shutil.copy2(bridge / "vietdub-ai-panel.tsx", src / "vietdub" / "ai-panel.tsx")
    # hiệu ứng mới (shader trong lõi WebAssembly dựng lại - xem wasm/patch_effects.py)
    shutil.copy2(bridge / "vietdub-effects.ts", src / "effects" / "definitions" / "vietdub.ts")
    ed_index = src / "effects" / "definitions" / "index.ts"
    _sub(ed_index, 'import { blurEffectDefinition } from "./blur";',
         'import { blurEffectDefinition } from "./blur";\nimport { VIETDUB_EFFECTS } from "./vietdub";')
    _sub(ed_index, "const defaultEffects = [blurEffectDefinition];",
         "const defaultEffects = [blurEffectDefinition, ...VIETDUB_EFFECTS];")
    # tab "VietDub AI" trong bảng tài nguyên
    store = src / "components" / "editor" / "panels" / "assets" / "assets-panel-store.tsx"
    _sub(store, "\tColorsIcon,\n} from \"@hugeicons/core-free-icons\";",
         "\tColorsIcon,\n\tAiMagicIcon,\n} from \"@hugeicons/core-free-icons\";")
    _sub(store, 'export const TAB_KEYS = [\n\t"media",', 'export const TAB_KEYS = [\n\t"vietdub",\n\t"media",')
    _sub(store, "export const tabs = {\n", 'export const tabs = {\n\tvietdub: {\n\t\ticon: createHugeiconsIcon({ icon: AiMagicIcon }),\n'
         '\t\tlabel: "VietDub AI",\n\t},\n')
    idx = src / "components" / "editor" / "panels" / "assets" / "index.tsx"
    _sub(idx, 'import { EffectsView } from "@/effects/components/assets-view";',
         'import { EffectsView } from "@/effects/components/assets-view";\nimport { VietDubAIView } from "@/vietdub/ai-panel";')
    _sub(idx, "\t\tmedia: <MediaView />,", "\t\tvietdub: <VietDubAIView />,\n\t\tmedia: <MediaView />,")
    ed = src / "app" / "editor" / "[project_id]" / "editor-client.tsx"
    _sub(ed, 'import { usePasteMedia } from "@/media/use-paste-media";',
         'import { usePasteMedia } from "@/media/use-paste-media";\nimport { useVietDubBridge } from "@/vietdub/bridge";')
    _sub(ed, "\tusePasteMedia();\n", "\tusePasteMedia();\n\tuseVietDubBridge();\n")
    # dự án chưa có -> OpenCut tạo dự án mới; giữ ?vietdub=... để cầu nối chạy tiếp
    prov = src / "components" / "providers" / "editor-provider.tsx"
    _sub(prov, "router.replace(`/editor/${newProjectId}`);",
         "router.replace(`/editor/${newProjectId}/${window.location.search}`);")
    _sub(prov, 'name: "Untitled Project",',
         'name: new URLSearchParams(window.location.search).get("name") || "Dự án mới",')
    # bỏ phần cần máy chủ online của OpenCut (gửi góp ý, thư viện âm thanh Freesound) - bản chạy trên máy không có
    hdr = src / "components" / "editor" / "editor-header.tsx"
    _sub(hdr, 'import { FeedbackPopover } from "@/feedback/components/feedback-popover";\n', "")
    _sub(hdr, "\t\t\t\t<FeedbackPopover />\n", "")
    tb = src / "components" / "editor" / "panels" / "assets" / "tabbar.tsx"
    # WebGL: ảnh mẫu hiệu ứng vẽ trên CHUNG canvas với khung xem trước -> vẽ lại khung hình cuối sau khi vẽ ảnh mẫu
    comp = src / "services" / "renderer" / "compositor" / "wasm-compositor.ts"
    _sub(comp, "\trender(frame: FrameDescriptor) {\n\t\trenderFrame(frame);",
         "\tprivate lastFrame: FrameDescriptor | null = null;\n\n"
         "\t/** (VietDub) vẽ lại khung hình cuối (sau khi ảnh mẫu hiệu ứng dùng chung canvas WebGL). */\n"
         "\trepaint() {\n\t\tif (!this.lastFrame) return;\n\t\ttry {\n\t\t\trenderFrame(this.lastFrame);\n"
         "\t\t} catch {\n\t\t\t// khung hình cũ không còn texture -> bỏ qua, lần vẽ sau sẽ đúng\n\t\t}\n\t}\n\n"
         "\trender(frame: FrameDescriptor) {\n\t\tthis.lastFrame = frame;\n\t\trenderFrame(frame);")
    ep = src / "services" / "renderer" / "effect-preview.ts"
    _sub(ep, 'import { gpuRenderer } from "./gpu-renderer";',
         'import { gpuRenderer } from "./gpu-renderer";\nimport { wasmCompositor } from "./compositor/wasm-compositor";\n\n'
         "let repaintQueued = false;\nfunction queuePreviewRepaint() {\n\tif (repaintQueued) return;\n\trepaintQueued = true;\n"
         "\trequestAnimationFrame(() => {\n\t\trepaintQueued = false;\n\t\twasmCompositor.repaint();\n\t});\n}")
    _sub(ep, "\t\t\ttargetCtx.drawImage(result, 0, 0, size, size);\n",
         "\t\t\ttargetCtx.drawImage(result, 0, 0, size, size);\n\t\t\tqueuePreviewRepaint();\n")
    # ẩn tab cần máy chủ online (âm thanh Freesound) và 2 tab "sắp có" (chuyển cảnh, chỉnh màu -> dùng tab Hiệu ứng)
    _sub(tb, "{TAB_KEYS.map((tabKey) => {",
         '{TAB_KEYS.filter((k) => k !== "sounds" && k !== "transitions" && k !== "adjustment").map((tabKey) => {')
