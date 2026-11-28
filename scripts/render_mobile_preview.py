# -*- coding: utf-8 -*-
"""
移动视图 JSON -> PNG 预览（仅用于目视核对控件清单与顺序，不是平台真实渲染）

用法:
    python render_mobile_preview.py "xxx(移动视图).txt" [输出.png]

与 render_web_preview.py 互补：那个看表格版式，这个看**手机端有哪些控件**——
尤其用来确认「数据选取」有没有生成、按钮名对不对、回填到哪个字段。

依赖: pillow。缺依赖时直接跳过预览，不影响主流程。
"""
import json
import os
import sys

W = 430                 # 手机宽度
PAD = 14
LABEL_W = 96
ROW_GAP = 8
FONT_CANDIDATES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simsun.ttc"]

BG = (255, 255, 255)
LINE = (222, 226, 230)
TXT = (33, 37, 41)
MUTED = (134, 142, 150)
BTN_BG = (255, 244, 229)     # 数据选取按钮：浅橙
BTN_FG = (196, 106, 0)
BOX_BG = (248, 249, 250)


def load_font(size=13, bold=False):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def wrap(draw, text, font, width):
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=font) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur or not lines:
        lines.append(cur)
    return lines


def summary(e):
    """控件右侧的「假控件」里写什么。"""
    t = e["type"]
    pr = e["properties"]
    if t == "selectData":
        dm = ((pr.get("selDataSet") or {}).get("dataMapping") or [{}])[0]
        return pr.get("buttonName") or pr.get("label"), "%s.%s → %s" % (
            (pr.get("selDataSet") or {}).get("dataTable", ""),
            dm.get("DataField", ""), dm.get("MapFieldName") or dm.get("MapField", ""))
    if t == "attachment":
        return "＋ 上传附件", None
    if t == "approve":
        return "（审批意见框）", None
    if t in ("radio", "checkbox", "select"):
        opts = [o.get("label") for o in (pr.get("options") or [])]
        return "  ".join(opts) if opts else "（无选项）", None
    if t == "datepicker":
        return "2026-11-28", None
    if t == "table":
        return "（重复表：%d 列）" % len(e.get("children") or []), None
    if t == "label":
        return "（说明块）", None
    ph = pr.get("placeholder") or ""
    dv = pr.get("defVal") or ""
    return (dv and "默认值：%s" % dv) or ph or "请输入", None


def render(path, out_path):
    from PIL import Image, ImageDraw

    els = json.loads(open(path, "rb").read().decode("utf-8-sig"))
    if isinstance(els, dict):
        els = els.get("elements") or []
    f_lab, f_val, f_small, f_title = load_font(13, True), load_font(13), load_font(11), load_font(16, True)

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    # 先算高度
    rows = []
    for e in els:
        text, hint = summary(e)
        box_w = W - 2 * PAD - LABEL_W - 10
        tl = wrap(probe, text, f_val, box_w - 16)
        hl = wrap(probe, hint, f_small, box_w - 16) if hint else []
        h = max(34, 10 + len(tl) * 18 + (len(hl) * 15 if hl else 0))
        lab = wrap(probe, e["properties"].get("label", ""), f_lab, LABEL_W)
        rows.append((e, lab, tl, hl, max(h, 18 * len(lab) + 6)))

    total = PAD + 30 + sum(r[4] + ROW_GAP for r in rows) + PAD
    img = Image.new("RGB", (W, total), BG)
    d = ImageDraw.Draw(img)
    d.text((PAD, PAD), "移动视图（%d 控件）" % len(els), font=f_title, fill=TXT)
    y = PAD + 30

    for e, lab, tl, hl, h in rows:
        t = e["type"]
        for i, line in enumerate(lab):
            d.text((PAD, y + 6 + i * 18), line, font=f_lab, fill=TXT)
        bx = PAD + LABEL_W + 10
        bw = W - PAD - bx
        if t == "selectData":
            d.rounded_rectangle([bx, y, bx + bw, y + h], 6, fill=BTN_BG, outline=(240, 200, 150))
            d.text((bx + 8, y + 7), tl[0] if tl else "", font=f_val, fill=BTN_FG)
            if hl:
                d.text((bx + 8, y + 7 + 18), hl[0], font=f_small, fill=MUTED)
        elif t == "label":
            d.rectangle([bx, y, bx + bw, y + h], fill=BOX_BG, outline=LINE)
            d.text((bx + 8, y + 7), tl[0] if tl else "", font=f_val, fill=MUTED)
        else:
            d.rounded_rectangle([bx, y, bx + bw, y + h], 4, fill=BOX_BG, outline=LINE)
            for i, line in enumerate(tl):
                d.text((bx + 8, y + 7 + i * 18), line, font=f_val,
                       fill=MUTED if t in ("attachment", "approve", "table") else TXT)
        y += h + ROW_GAP

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    img.save(out_path)
    print("预览 -> %s  (%dx%d, %d 控件)" % (out_path, W, total, len(els)))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = argv[1]
    out = argv[2] if len(argv) > 2 else os.path.splitext(src)[0] + ".png"
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("跳过移动预览：未安装 pillow（pip install pillow）")
        return 0
    render(src, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
