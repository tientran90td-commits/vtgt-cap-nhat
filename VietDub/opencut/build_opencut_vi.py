"""Dựng OpenCut (bản classic, giấy phép MIT - https://github.com/opencut-app/opencut-classic) thành web tĩnh
tiếng Việt để chạy kèm VietDub (không cần Node.js, không cần máy chủ, không cần đăng nhập).

Cách dùng (cần Bun hoặc Node 20+):
    python build_opencut_vi.py <thư mục mã nguồn opencut-classic> <file zip đầu ra>

Script sửa bản sao mã nguồn:
- Xuất web tĩnh (next export), bỏ các trang web giới thiệu, blog, API, đăng nhập, thống kê truy cập.
- Trang dựng /editor/<id> chạy được với mọi id (VietDub phục vụ chung 1 trang).
- Dịch giao diện sang tiếng Việt theo từ điển vi.json.
- Thêm cầu nối VietDub: mở dự án là tự nạp video + phụ đề Việt + thuyết minh vào timeline.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMIT = "cf5e79e919144200294fb9fed22a222592a0aeea"

NEXT_CONFIG = '''import type { NextConfig } from "next";
import { withContentCollections } from "@content-collections/next";

const nextConfig: NextConfig = {
	compiler: { removeConsole: process.env.NODE_ENV === "production" },
	reactStrictMode: true,
	output: "export",
	trailingSlash: true,
	images: { unoptimized: true },
};

export default withContentCollections(nextConfig);
'''

HOME_PAGE = '''"use client";
import { useEffect } from "react";

export default function Home() {
	useEffect(() => {
		window.location.replace("/projects/" + window.location.search);
	}, []);
	return null;
}
'''

EDITOR_PAGE = '''import EditorClient from "./editor-client";

export function generateStaticParams() {
	return [{ project_id: "_" }];
}

export default function Page() {
	return <EditorClient />;
}
'''

REMOVE = ["app/api", "app/blog", "app/rss.xml", "app/sitemap.ts", "app/robots.ts", "app/sponsors",
          "app/contributors", "app/roadmap", "app/privacy", "app/terms", "app/brand", "app/changelog"]


def sub(path: Path, old: str, new: str, count: int = 1, regex: bool = False) -> None:
    s = path.read_text(encoding="utf-8")
    if regex:
        s2, n = re.subn(old, new, s, count=count, flags=re.S)
    else:
        n = s.count(old)
        s2 = s.replace(old, new, count if count else -1)
    if not n:
        raise SystemExit(f"Không tìm thấy đoạn cần sửa trong {path}: {old[:80]!r}")
    path.write_text(s2, encoding="utf-8")


def patch_static(web: Path) -> None:
    src = web / "src"
    (web / "next.config.ts").write_text(NEXT_CONFIG, encoding="utf-8")
    env = (web / ".env.example").read_text(encoding="utf-8").replace("NODE_ENV=development", "NODE_ENV=production")
    (web / ".env.local").write_text(env, encoding="utf-8")
    for rel in REMOVE:
        p = src / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    (src / "app" / "page.tsx").write_text(HOME_PAGE, encoding="utf-8")
    lay = src / "app" / "layout.tsx"
    sub(lay, 'import { BotIdClient } from "botid/client";\n', "")
    sub(lay, r"const protectedRoutes = \[.*?\];\n", "", regex=True)
    sub(lay, r"<BotIdClient[^>]*/>\s*", "", regex=True)
    sub(lay, r'<Script\s+src="https://cdn\.databuddy\.cc/databuddy\.js".*?/>\s*', "", regex=True)
    sub(lay, '<html lang="en"', '<html lang="vi"')
    ed = src / "app" / "editor" / "[project_id]"
    page = ed / "page.tsx"
    client = ed / "editor-client.tsx"
    page.rename(client)
    sub(client, 'import { useParams } from "next/navigation";', 'import { usePathname } from "next/navigation";')
    sub(client, "export default function Editor() {\n\tconst params = useParams();\n\tconst projectId = params.project_id as string;",
        "export default function Editor() {\n\tconst pathname = usePathname();\n"
        "\tconst projectId = decodeURIComponent((pathname || \"\").split(\"/\").filter(Boolean)[1] || \"\");")
    page.write_text(EDITOR_PAGE, encoding="utf-8")


IS_SHORTCUT_KEY = """

const MODIFIERS: ReadonlySet<string> = new Set([
	"ctrl", "alt", "shift", "ctrl+shift", "alt+shift", "ctrl+alt", "ctrl+alt+shift",
]);

/** (VietDub) hàm này bị thiếu ở bản classic cuối cùng: kiểm tra chuỗi phím tắt hợp lệ. */
export function isShortcutKey(value: string): value is ShortcutKey {
	if (isKey(value)) return true;
	const i = value.lastIndexOf("+");
	if (i <= 0) return false;
	return MODIFIERS.has(value.slice(0, i)) && isKey(value.slice(i + 1));
}
"""


IS_ACTION = """

/** (VietDub) hàm này bị thiếu ở bản classic cuối cùng: tên hành động có trong danh sách không. */
export function isActionWithOptionalArgs(value: string): value is TActionWithOptionalArgs {
	return Object.prototype.hasOwnProperty.call(ACTIONS, value);
}
"""


def patch_fixes(web: Path) -> None:
    """Sửa lỗi có sẵn trong mã nguồn classic (kho đã đóng giữa lúc đang sửa dở, không còn ai sửa).
    Không sửa thì: lưu phím tắt lỗi, chuyển đổi dự án cũ mở sai cơ sở dữ liệu, kho sticker không nạp."""
    src = web / "src"
    kb = src / "actions" / "keybinding.ts"
    if "export function isShortcutKey" not in kb.read_text(encoding="utf-8"):
        sub(kb, "export type ShortcutKey = ModifierBasedShortcutKey | SingleCharacterShortcutKey;\n",
            "export type ShortcutKey = ModifierBasedShortcutKey | SingleCharacterShortcutKey;\n" + IS_SHORTCUT_KEY)
    df = src / "actions" / "definitions.ts"
    if "export function isActionWithOptionalArgs" not in df.read_text(encoding="utf-8"):
        df.write_text(df.read_text(encoding="utf-8") + IS_ACTION, encoding="utf-8")
    # new IndexedDBAdapter<T>(a, b, 1)  ->  new IndexedDBAdapter<T>({ dbName: a, storeName: b, version: 1 })
    pat = re.compile(r"new IndexedDBAdapter<([^>]+)>\(\s*([^,()]+?),\s*([^,()]+?),\s*(\d+),?\s*\)")
    for f in (src / "services" / "storage" / "migrations").glob("*.ts"):
        t = f.read_text(encoding="utf-8")
        t2 = pat.sub(lambda m: f"new IndexedDBAdapter<{m.group(1)}>({{ dbName: {m.group(2)}, storeName: "
                               f"{m.group(3)}, version: {m.group(4)} }})", t)
        t2 = re.sub(r"projectsAdapter\.set\(\s*projectId,\s*result\.project\s*\)",
                    "projectsAdapter.set({ key: projectId, value: result.project })", t2)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    sub(src / "stickers" / "providers" / "index.ts", "stickersRegistry.register(provider.id, provider);",
        "stickersRegistry.register({ key: provider.id, definition: provider });")


def patch_after_translate(web: Path) -> None:
    """Chỗ chữ tiếng Anh được dùng làm kiểu dữ liệu (TypeScript) -> nới thành string sau khi dịch."""
    sub(web / "src" / "timeline" / "audio-separation" / "index.ts", '}): "Extract audio" | "Recover audio" {',
        "}): string {")
    manual = HERE / "vi_manual.json"
    if manual.exists():  # các chỗ chữ nằm trong code (return "...", điều kiện, bảng tra) - sửa đúng từng chỗ
        for item in json.loads(manual.read_text(encoding="utf-8")):
            rel, old, new = item[:3]
            sub(web / "src" / rel, old, new, count=item[3] if len(item) > 3 else 1)


def build(root: Path, out_zip: Path) -> None:
    web = root / "apps" / "web"
    bun = shutil.which("bun") or str(Path.home() / ".bun" / "bin" / "bun")
    subprocess.run([bun, "install"], cwd=root, check=True)
    subprocess.run([bun, "run", "build"], cwd=web, check=True)
    out = web / "out"
    if not (out / "projects" / "index.html").exists():
        raise SystemExit("Dựng xong nhưng thiếu trang projects.")
    shutil.copy2(root / "LICENSE", out / "LICENSE-OpenCut.txt")  # giấy phép MIT của OpenCut đi kèm bản dựng
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file() and not f.name.endswith(".map"):
                z.write(f, f.relative_to(out).as_posix())
    print(f"Xong: {out_zip} ({out_zip.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    root, out_zip = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    web = root / "apps" / "web"
    patch_static(web)
    patch_fixes(web)
    if (HERE / "translate_vi.py").exists():
        sys.path.insert(0, str(HERE))
        import translate_vi

        translate_vi.apply(web / "src", json.loads((HERE / "vi.json").read_text(encoding="utf-8")))
        patch_after_translate(web)
    if (HERE / "bridge").exists():  # cầu nối VietDub
        sys.path.insert(0, str(HERE))
        import bridge_patch

        bridge_patch.apply(web, HERE / "bridge")
    build(root, out_zip)


if __name__ == "__main__":
    main()
