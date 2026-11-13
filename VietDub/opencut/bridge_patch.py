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
    _sub(tb, "{TAB_KEYS.map((tabKey) => {", '{TAB_KEYS.filter((k) => k !== "sounds").map((tabKey) => {')
