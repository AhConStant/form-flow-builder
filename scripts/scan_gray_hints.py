#!/usr/bin/env python3
"""扫描 .docx 里的灰色字体提示，输出可直接写进 spec.placeholder 的文字。

用法：
    python scripts/scan_gray_hints.py "输入.docx"            # 人读
    python scripts/scan_gray_hints.py "输入.docx" --json     # 机器读

识别范围：
  - 显式浅灰 RGB（R=G=B，0x70~0xD9，如 BFBFBF / A6A6A6 / 999999）
  - Word 主题灰（themeColor=background1/2 或 text1/2，且带 themeShade/themeTint，
    如 background1 + shade BF）
不识别强调主题色和彩色文字，避免把正文误判成提示。
"""

import argparse
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": W[1:-1]}


def _is_gray_rpr(rpr):
    if rpr is None:
        return False
    color = rpr.find(W + "color")
    if color is None:
        return False
    val = (color.get(W + "val") or "").lower()
    if re.fullmatch(r"[0-9a-f]{6}", val):
        r, g, b = int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16)
        return r == g == b and 0x70 <= r <= 0xD9
    theme = color.get(W + "themeColor") or ""
    shade = color.get(W + "themeShade") or ""
    tint = color.get(W + "themeTint") or ""
    return theme in ("background1", "background2", "text1", "text2") and bool(shade or tint)


def _cell_hints(tc):
    """同一段落内连续的灰色 run 合成一条提示；跨段落不合并。"""
    for p in tc.iter(W + "p"):
        parts, cur = [], []
        for run in p.findall(W + "r"):
            text = "".join(t.text or "" for t in run.findall(W + "t"))
            if not text:
                continue
            if _is_gray_rpr(run.find(W + "rPr")):
                cur.append(text)
            elif cur:
                parts.append("".join(cur))
                cur = []
        if cur:
            parts.append("".join(cur))
        for part in parts:
            part = re.sub(r"\s+", " ", part).strip()
            if part:
                yield part


def scan(path):
    xml = zipfile.ZipFile(path).read("word/document.xml")
    root = ET.fromstring(xml)
    out = []
    for ti, tbl in enumerate(root.iter(W + "tbl")):
        for ri, tr in enumerate(tbl.findall(W + "tr")):
            cells = tr.findall(W + "tc")
            texts = ["".join(t.text or "" for t in tc.iter(W + "t")).strip() for tc in cells]
            for ci, tc in enumerate(cells):
                for hint in _cell_hints(tc):
                    label = next((texts[j] for j in range(ci - 1, -1, -1) if texts[j]), "")
                    out.append({"table": ti, "row": ri + 1, "col": ci + 1,
                                "label": label, "hint": hint})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docx", help="要扫描的 .docx 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON 数组")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    hints = scan(args.docx)
    if args.json:
        print(json.dumps(hints, ensure_ascii=False, indent=2))
    else:
        for h in hints:
            print("表%d R%dC%d [%s] -> %s" % (h["table"] + 1, h["row"], h["col"],
                                               h["label"], h["hint"]))
        print("共 %d 条灰色提示" % len(hints))


if __name__ == "__main__":
    main()
