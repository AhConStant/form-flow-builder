# -*- coding: utf-8 -*-
"""
Web 视图 JSON -> PNG 预览（仅用于目视核对布局，不是平台真实渲染）

用法:
    python render_web_preview.py "xxx(Web视图).txt" [输出.png]

依赖: pillow（pip install pillow）。缺依赖时直接跳过预览，不影响主流程。
说明: 预览器对所有单元格画边框、按 cols 的 width 排布，并按字符数折行；
      style2 无框效果在这里看不出来 —— 只用来核对「字段名/顺序/合并/控件类型/列宽」，
      不要用预览图反推边框样式。
"""
import json
import os
import re
import sys

DEFAULT_COL_W = 100
DEFAULT_ROW_H = 40
FONT_CANDIDATES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simsun.ttc"]


def load_font(size=12):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def a1(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref.strip())
    if not m:
        raise ValueError("非法单元格引用: %s" % ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)) - 1, col - 1


def render(src, dst=None):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("跳过预览：未安装 pillow（pip install pillow）")
        return None

    obj = json.loads(open(src, "rb").read().decode("utf-8-sig"))
    rows = {k: v for k, v in obj["rows"].items() if k != "len"}
    idx = sorted(int(k) for k in rows)

    ncols = 6
    for r in rows.values():
        for c in (r.get("cells") or {}):
            ncols = max(ncols, int(c) + 1)
    widths = {}
    for k, v in (obj.get("cols") or {}).items():
        if str(k).isdigit() and isinstance(v, dict) and v.get("width"):
            widths[int(k)] = int(v["width"])
    for c in range(ncols):
        widths.setdefault(c, DEFAULT_COL_W)
    xs = [0]
    for c in range(ncols):
        xs.append(xs[-1] + widths[c])

    heights, ypos, y = {}, {}, 0
    for r in idx:
        h = rows[str(r)].get("height") or DEFAULT_ROW_H
        heights[r] = h
        ypos[r] = y
        y += h

    img = Image.new("RGB", (xs[-1] + 1, y + 1), "white")
    d = ImageDraw.Draw(img)
    font = load_font(12)

    merged = {}
    for m in obj.get("merges") or []:
        a, b = m.split(":")
        r1, c1 = a1(a)
        r2, c2 = a1(b)
        merged[(r1, c1)] = (r2, c2)
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if (rr, cc) != (r1, c1):
                    merged[(rr, cc)] = None

    def wrap(text, px):
        max_chars = max(1, int((px - 8) // 12))
        out, line = [], ""
        for ch in str(text):
            if ch == "\n" or len(line) >= max_chars:
                out.append(line)
                line = "" if ch == "\n" else ch
            else:
                line += ch
        if line:
            out.append(line)
        return out

    for r in idx:
        cells = rows[str(r)]["cells"]
        for c in range(ncols):
            if (r, c) in merged and merged[(r, c)] is None:
                continue
            r2, c2 = merged.get((r, c), (r, c))
            x0, y0 = xs[c], ypos[r]
            x1, y1 = xs[c2 + 1], ypos[r2] + heights[r2]
            cell = cells.get(str(c), {})
            d.rectangle([x0, y0, x1, y1], outline="black")
            txt = cell.get("text") or ""
            tag = cell.get("SheetType")
            if tag:
                txt = "[%s] %s" % (tag, txt if txt and txt != "请输入" else "")
            if txt:
                lines = wrap(txt, x1 - x0)
                for i, ln in enumerate(lines[:8]):
                    d.text((x0 + 4, y0 + 3 + i * 14), ln, fill="black", font=font)

    if dst is None:
        dst = os.path.splitext(src)[0] + ".png"
    img.save(dst)
    print("preview ->", dst)
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    render(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
