"""Việt hóa giao diện OpenCut: tìm chữ hiển thị (chữ trong thẻ JSX, thuộc tính hiển thị, thông báo...) trong mã
nguồn và thay bằng bản dịch trong vi.json. Chỉ thay ở đúng ngữ cảnh hiển thị - không đụng tới tên biến, khóa, so sánh.

    python translate_vi.py extract <thư mục src> <file json>   # liệt kê chữ cần dịch
    python translate_vi.py check <thư mục src> vi.json         # chữ nào còn thiếu bản dịch
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ATTRS = ("placeholder", "title", "aria-label", "alt", "label", "description", "tooltip", "heading", "subtitle",
         "emptyMessage", "emptyText", "confirmText", "cancelText", "confirmLabel", "cancelLabel", "buttonText",
         "helperText", "hint", "message", "text", "content", "caption", "actionLabel", "submitLabel")
KEYS = ("label", "title", "description", "placeholder", "tooltip", "heading", "message", "subtitle", "hint",
        "emptyText", "emptyMessage", "confirmText", "cancelText", "confirmLabel", "buttonText", "helperText",
        "actionLabel", "submitLabel", "caption", "displayName")
SKIP_DIRS = ("__tests__", "/app/api", "/app/blog", "/db/", "/auth/", "/env/", "/scripts/")

# chữ trong thẻ JSX: >Chữ hiển thị<   (không chứa ký tự code)
JSX_TEXT = re.compile(r">(\s*)([A-Za-z][^<>{}=;`]*?[A-Za-z0-9.!?)…:'\"%])(\s*)<", re.S)
ATTR = re.compile(r"\b(" + "|".join(re.escape(a) for a in ATTRS) + r")=(\{?)\"([^\"\n]*[A-Za-z][^\"\n]*)\"(\}?)")
KEY = re.compile(r"\b(" + "|".join(KEYS) + r"):\s*\"([^\"\n]*[A-Za-z][^\"\n]*)\"")
TOAST = re.compile(r"\btoast(?:\.(?:success|error|info|warning|message|loading))?\(\s*\"([^\"\n]*[A-Za-z][^\"\n]*)\"")
DESC = re.compile(r"\bdescription:\s*\"([^\"\n]*[A-Za-z][^\"\n]*)\"")
TERNARY = re.compile(r"\?\s*\"([A-Z][^\"\n]*[a-z][^\"\n]*)\"\s*:\s*\"([A-Z][^\"\n]*[a-z][^\"\n]*)\"")


def looks_text(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 300:
        return False
    if re.search(r"[(){}\[\];=&|]|=>|\bconst\b|\breturn\b|\.\w+\(", s):
        return False
    if re.fullmatch(r"[a-z0-9_\-./:#]+", s):  # id, đường dẫn, class css
        return False
    if re.fullmatch(r"[a-z]+(-[a-z0-9]+)+", s) or s.startswith(("http", "/", "#", "bg-", "text-")):
        return False
    return bool(re.search(r"[A-Za-z]{2,}", s))


def files(src: Path):
    for f in sorted(src.rglob("*")):
        if f.suffix in (".tsx", ".ts") and not any(d in f.as_posix() for d in SKIP_DIRS) and not f.name.endswith(".d.ts"):
            yield f


def extract(src: Path) -> dict[str, list[str]]:
    found: dict[str, set] = {}

    def add(t, f):
        t = " ".join(t.split())
        if looks_text(t):
            found.setdefault(t, set()).add(f.relative_to(src).as_posix())
    for f in files(src):
        s = f.read_text(encoding="utf-8")
        if f.suffix == ".tsx":
            for m in JSX_TEXT.finditer(s):
                add(m.group(2), f)
        for m in ATTR.finditer(s):
            add(m.group(3), f)
        for m in KEY.finditer(s):
            add(m.group(2), f)
        for m in TOAST.finditer(s):
            add(m.group(1), f)
        for m in TERNARY.finditer(s):
            add(m.group(1), f)
            add(m.group(2), f)
    return {k: sorted(v) for k, v in sorted(found.items())}


def apply(src: Path, vi: dict[str, str]) -> int:
    """Thay chữ theo từ điển; trả về số chỗ đã thay."""
    vi = {k: v for k, v in vi.items() if v and v != k}
    n = 0

    def tr(t):
        return vi.get(" ".join(t.split()))

    for f in files(src):
        s = f.read_text(encoding="utf-8")
        orig = s

        def jsx(m):
            v = tr(m.group(2))
            return f">{m.group(1)}{v}{m.group(3)}<" if v else m.group(0)

        def attr(m):
            v = tr(m.group(3))
            return f'{m.group(1)}={m.group(2)}"{json.dumps(v, ensure_ascii=False)[1:-1]}"{m.group(4)}' if v \
                else m.group(0)

        def key(m):
            v = tr(m.group(2))
            return f"{m.group(1)}: {json.dumps(v, ensure_ascii=False)}" if v else m.group(0)

        def toast(m):
            v = tr(m.group(1))
            return m.group(0).replace(f'"{m.group(1)}"', json.dumps(v, ensure_ascii=False)) if v else m.group(0)

        def tern(m):
            a, b = tr(m.group(1)), tr(m.group(2))
            if not (a or b):
                return m.group(0)
            return (f'? {json.dumps(a or m.group(1), ensure_ascii=False)} : '
                    f'{json.dumps(b or m.group(2), ensure_ascii=False)}')
        if f.suffix == ".tsx":
            s = JSX_TEXT.sub(jsx, s)
        s = ATTR.sub(attr, s)
        s = KEY.sub(key, s)
        s = TOAST.sub(toast, s)
        s = TERNARY.sub(tern, s)
        if s != orig:
            n += 1
            f.write_text(s, encoding="utf-8")
    return n


if __name__ == "__main__":
    cmd, src = sys.argv[1], Path(sys.argv[2])
    if cmd == "extract":
        data = extract(src)
        Path(sys.argv[3]).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(len(data), "chuỗi")
    elif cmd == "check":
        vi = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        miss = [k for k in extract(src) if k not in vi]
        print(len(miss), "chuỗi chưa dịch")
        for k in miss:
            print(" ", k)
