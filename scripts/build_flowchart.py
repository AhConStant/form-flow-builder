#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表单流程图生成器：把「审批意见栏」变成与平台流程设计器同风格的流程图（SVG / HTML）。

两种数据源：
  1. spec.json        —— 按表单字段顺序推主线：开始 → 申请人 → 每个 approve 字段 → 结束
  2. 流程导出 JSON     —— 读平台的 FlowExportData.FlowStep / FlowStepCon，还原真实流程（用于核对）

用法：
    python build_flowchart.py spec.json --out 流程表单
    python build_flowchart.py spec.json --only 01
    python build_flowchart.py "流程导出_xxx.json" --from-export --out 流程表单

产出：{base}(流程图).svg  +  {base}(流程图).html（内嵌 SVG，便于预览/发人）
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flow_types  # noqa: E402

# ------------------------------ 样式 ------------------------------
CANVAS_W = 640
NODE_W = 176
NODE_H = 54
PILL_H = 58
GAP = 120          # 相邻节点 top 间距
TOP0 = 44          # 第一个节点 top
CX = CANVAS_W // 2

C_BG = "#f7fbfe"
C_GRID = "#e2eef8"
C_GRID5 = "#cfe3f1"
C_FILL = "#eaf1f7"
C_FILL_PILL = "#e9f3f9"
C_STROKE = "#9cbed2"
C_STROKE_PILL = "#7fb7d3"
C_TEXT = "#2e6f8f"
C_ICON = "#5fa8c8"
C_ICON_BG = "#e2f0f8"
C_ARROW = "#5aa9c9"
C_BADGE = "#f2795e"
C_JUDGE_FILL = "#fdf3e3"
C_JUDGE_STROKE = "#e0b071"
C_NOTICE_FILL = "#eef6ee"
C_NOTICE_STROKE = "#8cc08a"

# 各动作类型的配色：(填充, 描边/图标色)
KIND_COLORS = {
    "notice": (C_NOTICE_FILL, C_NOTICE_STROKE),
    "action": ("#fdf1e3", "#d99154"),
    "multi": ("#eef0fb", "#8189c9"),
    "archive": ("#f1f3f5", "#93a1ae"),
    "doc": ("#f5eefb", "#a284c8"),
    "auto": ("#eaf6f6", "#77b5b5"),
}
# 右上角徽标：kind -> (文字, 底色)
BADGES = {"approve": ("审", C_BADGE), "multi": ("多", "#7b86c9"),
          "action": ("执", "#d9822b")}

JUDGE_W, JUDGE_H = 184, 96          # 判断节点（菱形）
NODE_TYPE_KIND = {"nodeStart": "start", "nodeFirst": "first",
                  "nodeApprove": "approve", "nodeJudge": "judge",
                  "nodeNotice": "notice", "nodeAction": "action",
                  "nodeEnd": "end"}

FONT = "'Microsoft YaHei','PingFang SC','Hiragino Sans GB',sans-serif"

# 连线文字：(源节点名, 目标节点名) -> 文字（可含换行）。来自 spec 的 graph.edgeLabels
EDGE_LABELS = {}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def wrap(text, max_chars):
    """中文按字数折行：超过一行时均分成若干行，避免出现「8 字 + 1 字」这种孤字。"""
    text = str(text)
    n = len(text)
    if n <= max_chars:
        return [text]
    lines = -(-n // max_chars)          # ceil
    per = -(-n // lines)                # 每行均分
    return [text[i:i + per] for i in range(0, n, per)]


def node_spec(kind, name):
    """kind: start / first / approve / multi / judge / notice / action / end"""
    lines = wrap(name, 8)
    if kind in ("start", "end"):
        h = PILL_H
    elif kind == "judge":
        h = JUDGE_H
    else:
        h = NODE_H if len(lines) == 1 else NODE_H + 22 * (len(lines) - 1)
    w = JUDGE_W if kind == "judge" else NODE_W
    return {"kind": kind, "name": name, "lines": lines, "h": h, "w": w}


def diamond_points(x, y, w, h):
    cx, cy = x + w / 2, y + h / 2
    return [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]


def draw_node(n, x, y):
    """按节点类型画图形；x/y 是左上角。返回 svg 片段。"""
    kind, lines, h, w = n["kind"], n["lines"], n["h"], n["w"]
    out = []
    if kind == "judge":
        pts = " ".join("%.1f,%.1f" % p for p in diamond_points(x, y, w, h))
        out.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.4"/>'
                   % (pts, C_JUDGE_FILL, C_JUDGE_STROKE))
    else:
        pill = kind in ("start", "end")
        rx = h // 2 if pill else 6
        fill, stroke = KIND_COLORS.get(kind, (C_FILL, C_STROKE))
        if pill:
            fill, stroke = C_FILL_PILL, C_STROKE_PILL
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" ry="%d" '
                   'fill="%s" stroke="%s" stroke-width="1.4"/>'
                   % (x, y, w, h, rx, rx, fill, stroke))

    cx, cy = x + w / 2, y + h / 2
    # 左侧图标：判断不画（菱形内空间紧），通知画喇叭，其余画对勾
    if kind == "judge":
        icon_x = None
    elif kind == "notice":
        icon_x = x + 22
        # 朝右的小喇叭：右侧三角形 + 左侧竖条
        out.append('<path d="M%d %.1f L%d %.1f L%d %.1f Z" fill="%s"/>'
                   % (icon_x, cy - 7, icon_x + 13, cy, icon_x, cy + 7, C_NOTICE_STROKE))
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="2"/>'
                   % (icon_x - 1, cy - 7, icon_x - 1, cy + 7, C_NOTICE_STROKE))
    else:
        icon_x = x + 20
        ic = KIND_COLORS.get(kind, (C_FILL, C_ICON))[1]
        out.append('<circle cx="%d" cy="%.1f" r="9" fill="%s" stroke="%s" stroke-width="1.2"/>'
                   % (icon_x, cy, C_ICON_BG, ic))
        out.append('<path d="M%d %.1f l3.2 3.4 l5.4 -6.2" fill="none" stroke="%s" '
                   'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
                   % (icon_x - 5, cy - 1, ic))

    lh = 20
    ty = cy + 5 - (len(lines) - 1) * lh / 2
    tx = cx if icon_x is None else icon_x + 20 + (w - 20) // 2
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="14" fill="%s" '
                   'text-anchor="middle">%s</text>'
                   % (tx, ty + i * lh, FONT, C_TEXT, esc(ln)))
    badge = BADGES.get(kind)
    if badge:
        txt, color = badge
        bx, by = x + w - 2, y - 2
        out.append('<circle cx="%d" cy="%d" r="12" fill="%s"/>' % (bx, by, color))
        out.append('<text x="%d" y="%d" font-family="%s" font-size="12" font-weight="bold" '
                   'fill="#ffffff" text-anchor="middle">%s</text>' % (bx, by + 4, FONT, txt))
    return "\n".join(out)


def draw_arrow(y1, y2, x=CX):
    """竖直箭头（线性布局用）"""
    out = []
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="3"/>'
               % (x, y1, x, y2 - 11, C_ARROW))
    out.append('<path d="M%d %d l-7 -11 l14 0 z" fill="%s"/>' % (x, y2, C_ARROW))
    return "\n".join(out)


def draw_edge(pts):
    """正交折线箭头：pts 是 [(x,y), ...]，最后一点是箭头尖端。

    线段必须画到「箭头底部」（尖端回退 11px），否则两点直边会退化成只有箭头没有线。
    """
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    if abs(x2 - x1) < 1:
        base = (x2, y2 - 11)
    else:
        base = (x2 - 11, y2)
    body = list(pts[:-1]) + [base]
    d = "M%.1f %.1f " % body[0] + " ".join("L%.1f %.1f" % p for p in body[1:])
    out = ['<path d="%s" fill="none" stroke="%s" stroke-width="3" '
           'stroke-linejoin="round"/>' % (d, C_ARROW)]
    if abs(x2 - x1) < 1:
        out.append('<path d="M%.1f %.1f l-7 -11 l14 0 z" fill="%s"/>' % (x2, y2, C_ARROW))
    else:
        out.append('<path d="M%.1f %.1f l-11 -7 l0 14 z" fill="%s"/>' % (x2, y2, C_ARROW))
    return "\n".join(out)


def grid_defs(height):
    return ('<defs>'
            '<pattern id="g10" width="10" height="10" patternUnits="userSpaceOnUse">'
            '<path d="M10 0 L0 0 0 10" fill="none" stroke="%s" stroke-width="0.6"/></pattern>'
            '<pattern id="g50" width="50" height="50" patternUnits="userSpaceOnUse">'
            '<path d="M50 0 L0 0 0 50" fill="none" stroke="%s" stroke-width="0.8"/></pattern>'
            '</defs>' % (C_GRID, C_GRID5))


def render_svg(nodes, title=""):
    """线性布局：竖直串联（spec 按 approve 推导时用）。"""
    total = TOP0 + len(nodes) * GAP + 40
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (CANVAS_W, total, CANVAS_W, total),
             grid_defs(total),
             '<rect width="100%%" height="100%%" fill="%s"/>' % C_BG,
             '<rect width="100%" height="100%" fill="url(#g50)"/>',
             '<rect width="100%" height="100%" fill="url(#g10)"/>']
    y = TOP0
    prev_bottom = None
    for n in nodes:
        x = CX - n["w"] // 2
        if prev_bottom is not None:
            parts.append(draw_arrow(prev_bottom, y))
        parts.append(draw_node(n, x, y))
        prev_bottom = y + n["h"]
        y += GAP
    parts.append("</svg>")
    return "\n".join(parts)


def layout_from_steps(steps):
    """把 FlowStep 的 nodeStyle 坐标变成画布行。"""
    out = []
    for st in steps:
        kind = NODE_TYPE_KIND.get(st.get("node"), "approve")
        name = st.get("actualName") or st.get("stepName") or "节点"
        n = node_spec(kind, name)
        m = re.search(r"left:\s*(-?[\d.]+)px;\s*top:\s*(-?[\d.]+)px",
                      st.get("nodeStyle") or "")
        x = float(m.group(1)) if m else 0.0
        y = float(m.group(2)) if m else 0.0
        if kind == "judge":
            x += (NODE_W - JUDGE_W) / 2
        out.append({"draw": int(st["DrawID"]), "x": x, "y": y, "n": n,
                    "to": [int(t) for t in str(st.get("processTo") or "")
                           .replace(" ", "").split(",") if t]})
    out.sort(key=lambda r: (r["y"], r["x"]))
    return out


def canvas_rows(rows):
    """flow_types.layout() 的行 → 画布行（补 node_spec；菱形左缘补差保持居中）。"""
    out = []
    for r in rows:
        n = node_spec(r["kind"], r["name"])
        x = r["x"] + ((NODE_W - JUDGE_W) / 2 if r["kind"] == "judge" else 0)
        out.append({"draw": r["draw"], "x": x, "y": r["y"], "n": n,
                    "to": r.get("to") or []})
    return out


def find_overlaps(rows):
    """节点矩形两两求交：返回 [(nameA, nameB)]。坐标写重了会在这里被抓到。"""
    bad = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            aw, ah = a["n"]["w"], a["n"]["h"]
            bw, bh = b["n"]["w"], b["n"]["h"]
            if a["x"] < b["x"] + bw and b["x"] < a["x"] + aw \
                    and a["y"] < b["y"] + bh and b["y"] < a["y"] + ah:
                bad.append((a["n"]["name"], b["n"]["name"]))
    return bad


def find_crossings(rows):
    """折线是否穿过无关节点（只看线段中点是否落在别的节点矩形内）。"""
    hits = []
    by_draw = {r["draw"]: r for r in rows}
    for r in rows:
        for t in r.get("to") or []:
            dst = by_draw.get(t)
            if not dst:
                continue
            sx = r["x"] + r["n"]["w"] / 2
            sy = r["y"] + r["n"]["h"]
            tx = dst["x"] + dst["n"]["w"] / 2
            ty = dst["y"]
            mids = [((sx + sx) / 2, (sy + ty) / 2)] if abs(sx - tx) < 2 else \
                   [(sx, (sy + ty) / 2), (tx, (sy + ty) / 2)]
            for (mx, my) in mids:
                for o in rows:
                    if o["draw"] in (r["draw"], dst["draw"]):
                        continue
                    if o["x"] < mx < o["x"] + o["n"]["w"] and o["y"] < my < o["y"] + o["n"]["h"]:
                        hits.append((r["n"]["name"], dst["n"]["name"], o["n"]["name"]))
                        break
    return hits


def report_layout(rows, strict=True):
    """检查排版问题：重叠一律报错；连线穿框只提示。返回问题条数。"""
    ov = find_overlaps(rows)
    cr = find_crossings(rows)
    if ov:
        for a, b in ov[:6]:
            print("       ! 节点重叠：「%s」与「%s」坐标冲突" % (a, b))
        print("       ! 共 %d 对节点重叠，图不可用；请改 graph 里的 x/y 或改用自动布局" % len(ov))
    for a, b, c in cr[:4]:
        print("       · 连线 %s→%s 穿过「%s」（可通过错开 x/y 或减少跨层连接改善）" % (a, b, c))
    return len(ov) if strict else 0


def rows_from_graph(graph):
    """spec 的 graph：节点可自带 x/y（手工排版），否则走分层自动布局。"""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    manual = nodes and all(isinstance(n, dict) and "x" in n and "y" in n for n in nodes)
    if not manual:
        return flow_types.layout_graph(nodes, edges)
    flow_types.assert_unique([n["name"] for n in nodes])
    rows, idx = [], {}
    for i, n in enumerate(nodes):
        key = n.get("type") or flow_types.classify(n["name"])
        if key not in flow_types.TYPE_META:
            key = flow_types.classify(n["name"])
        rows.append({"draw": i + 1, "name": n["name"], "key": key,
                     "kind": flow_types.meta_of(key)["kind"],
                     "x": float(n["x"]), "y": float(n["y"]), "to": []})
        idx[n["name"]] = rows[-1]
    for a, b in edges:
        if a in idx and b in idx:
            idx[a]["to"].append(idx[b]["draw"])
    return rows


def draw_edge_label(x, y, text):
    """分支条件文字：贴在判断节点正下方的竖线右侧，逐行往下排。

    白色描边（paint-order=stroke）保证压到连线也读得清。
    """
    lines = [ln for ln in str(text).split("\n") if ln.strip()]
    if not lines:
        return ""
    out, h = [], 15
    top = y - h * len(lines)          # y = 文字底边（目标节点上沿再上移 6px）
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="11" fill="#3d5866" '
                   'stroke="#ffffff" stroke-width="3.5" paint-order="stroke" '
                   'text-anchor="middle">%s</text>'
                   % (x, top + h * (i + 1), FONT, esc(ln)))
    return "\n".join(out)


def render_canvas(rows):
    """按平台画布坐标渲染，支持分支与汇聚（正交折线）。"""
    if not rows:
        return render_svg([])
    pad = 46
    minx = min(r["x"] for r in rows) - pad
    maxx = max(r["x"] + r["n"]["w"] for r in rows) + pad
    miny = min(r["y"] for r in rows) - pad
    maxy = max(r["y"] + r["n"]["h"] for r in rows) + pad
    w, h = int(maxx - minx), int(maxy - miny)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (w, h, w, h),
             grid_defs(h),
             '<rect width="100%%" height="100%%" fill="%s"/>' % C_BG,
             '<rect width="100%" height="100%" fill="url(#g50)"/>',
             '<rect width="100%" height="100%" fill="url(#g10)"/>']
    by_draw = {r["draw"]: r for r in rows}
    # 先画线，后画节点，避免线压住图形
    lane = {}
    for r in rows:
        for i, t in enumerate(r["to"]):
            dst = by_draw.get(t)
            if not dst:
                continue
            sx = r["x"] + r["n"]["w"] / 2 - minx
            sy = r["y"] + r["n"]["h"] - miny
            tx = dst["x"] + dst["n"]["w"] / 2 - minx
            ty = dst["y"] - miny
            span = (dst["y"] - r["y"]) - r["n"]["h"]
            if abs(sx - tx) < 1 and span <= 240:
                pts = [(sx, sy), (tx, ty)]
            elif span > 240 and abs(sx - tx) > 1:
                # 跨层长边（跳过中间层）：绕外侧沟槽走，避免穿过中间节点
                gx = (minx - minx + 24) if tx < sx else (maxx - minx - 24)
                pts = [(sx, sy), (sx, sy + 20), (gx, sy + 20),
                       (gx, ty - 24), (tx, ty - 24), (tx, ty)]
            else:
                off = 30 + 16 * i
                ly = sy + off
                if ly > ty - 30:                     # 折返太高时改走上方，留出徽标位置
                    ly = max(sy + 12, ty - 30)
                pts = [(sx, sy), (sx, ly), (tx, ly), (tx, ty)]
            parts.append(draw_edge(pts))
            lab = EDGE_LABELS.get((r["n"]["name"], dst["n"]["name"]))
            if lab and r["n"]["kind"] == "judge" and (dst["y"] - r["y"]) <= 240:
                # 只标「判断 → 本分支第一个节点」的短边；空分支直连汇合点的长边不标，
                # 否则文字会压在沿途节点上（空分支含义见交付说明）
                parts.append(draw_edge_label(tx, ty - 6, lab))
    for r in rows:
        parts.append(draw_node(r["n"], int(r["x"] - minx), int(r["y"] - miny)))
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(svg, title):
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>%s</title><style>body{margin:0;background:#eef4f8;display:flex;"
            "justify-content:center;padding:24px}svg{box-shadow:0 2px 10px rgba(0,0,0,.08);"
            "border-radius:6px}</style></head><body>%s</body></html>"
            % (esc(title), svg))


# ------------------------------ 数据源 ------------------------------
def from_spec(form):
    """按字段顺序推主线：开始 → 申请人 → approve... → 结束"""
    nodes = [node_spec("start", "开始"), node_spec("first", "申请人")]
    for f in form["fields"]:
        if f["type"] == "approve":
            nodes.append(node_spec("approve", f["label"]))
    nodes.append(node_spec("end", "结束"))
    return nodes


def main(argv):
    ap = argparse.ArgumentParser(description="表单流程图生成（SVG + HTML）")
    ap.add_argument("src", help="spec.json 或 流程导出 JSON")
    ap.add_argument("--from-export", action="store_true", help="按平台流程导出 JSON 还原流程图")
    ap.add_argument("--out", help="输出目录（默认与 spec 的 output_dir 一致）")
    ap.add_argument("--only", help="只处理指定流程（base 前缀，逗号分隔）")
    a = ap.parse_args(argv)

    if a.from_export:
        d = json.load(open(a.src, encoding="utf-8-sig"))
        fe = d.get("FlowExportData") or d
        steps = fe.get("FlowStep") or []
        if not steps:
            raise ValueError("流程导出文件里没有 FlowStep：%s" % a.src)
        rows = layout_from_steps(steps)
        if report_layout(rows):
            return 1
        svg = render_canvas(rows)
        base = os.path.splitext(os.path.basename(a.src))[0]
        base = re.sub(r"^流程导出_", "", base)
        base = re.sub(r"_v[\d.]+$", "", base)
        out_dir = a.out or os.path.dirname(os.path.abspath(a.src))
        os.makedirs(out_dir, exist_ok=True)
        sp = os.path.join(out_dir, base + "(流程图).svg")
        hp = os.path.join(out_dir, base + "(流程图).html")
        open(sp, "w", encoding="utf-8", newline="\n").write(svg)
        open(hp, "w", encoding="utf-8", newline="\n").write(render_html(svg, base + " 流程图"))
        summary = flow_types.layout_summary([{"kind": r["n"]["kind"]} for r in rows])
        print("%-24s 节点=%d  %s" % (base, len(rows), summary))
        print("       -> %s" % sp)
        no_cond = all(not (c.get("ConContent") or "") for c in (fe.get("FlowStepCon") or []))
        branches = [r for r in rows if len(r["to"]) > 1]
        if branches:
            print("       ! 含 %d 个分支节点%s" % (
                len(branches), "（分支条件为空，图中不标注条件）" if no_cond else ""))
        return 0

    spec = json.load(open(a.src, encoding="utf-8-sig"))
    forms = spec["forms"]
    if a.only:
        keys = [k.strip() for k in a.only.split(",")]
        forms = [f for f in forms if any(f["base"].startswith(k) for k in keys)]
        if not forms:
            raise ValueError("--only 没匹配到任何流程")
    outs = []
    for form in forms:
        if form.get("graph"):                    # 显式图：支持三路分支、嵌套判断
            EDGE_LABELS.clear()
            for k, v in (form["graph"].get("edgeLabels") or {}).items():
                for sep in ("→", "->"):
                    if sep in k:
                        sn, dn = k.split(sep, 1)
                        EDGE_LABELS[(sn.strip(), dn.strip())] = v
                        break
            raw = rows_from_graph(form["graph"])
            rows = canvas_rows(raw)
            if report_layout(rows):
                return 1
            for w in flow_types.judge_warnings(raw):
                print("       ! %s" % w)
            outs.append((form["base"], render_canvas(rows),
                         "%d 节点  %s" % (len(rows), flow_types.layout_summary(raw))))
            continue
        if form.get("flow"):                     # 显式流程：支持判断/通知/存档等动作类型
            items = flow_types.normalize_items(form["flow"])
            if not any(it["key"] in ("approve", "multi") for it in items):
                print("  ! %s 没有审批类动作，跳过流程图" % form["base"])
                continue
            raw = flow_types.layout(items)
            rows = canvas_rows(raw)
            if report_layout(rows):
                return 1
            for w in flow_types.judge_warnings(raw):
                print("       ! %s" % w)
            outs.append((form["base"], render_canvas(rows),
                         "%d 节点  %s" % (len(rows), flow_types.layout_summary(raw))))
            continue
        ns = from_spec(form)
        if not any(n["kind"] == "approve" for n in ns):
            print("  ! %s 没有审批意见栏，跳过流程图" % form["base"])
            continue
        outs.append((form["base"], render_svg(ns),
                     "%d 节点  %s" % (len(ns), " → ".join(n["name"] for n in ns))))
    out_dir = a.out or spec.get("output_dir") or "流程表单"

    if not outs:
        print("没有可生成的流程图")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    for base, svg, desc in outs:
        sp = os.path.join(out_dir, base + "(流程图).svg")
        hp = os.path.join(out_dir, base + "(流程图).html")
        open(sp, "w", encoding="utf-8", newline="\n").write(svg)
        open(hp, "w", encoding="utf-8", newline="\n").write(render_html(svg, base + " 流程图"))
        print("%-24s %s" % (base, desc))
        print("       -> %s" % sp)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, FileNotFoundError) as e:
        print("FAIL %s" % e)
        sys.exit(1)
