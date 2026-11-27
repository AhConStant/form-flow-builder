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
import copy
import json
import math
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
C_ACTION_TEXT = "#a8661f"

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
# 同一层三个分支可能同名（都叫「科主任/护士长（护士）审批」），名字键会互相覆盖，
# 所以条件文字再按 (源draw, 目标draw) 存一份，渲染时优先用它。
EDGE_LABEL_D = {}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def strip_no(name):
    """去掉步骤名前的层级序号（1、5.1、5.1.1.1 …）：画布上的 label 就是去序号后的名字。"""
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", str(name or "")).strip()


def wrap(text, max_chars):
    """中文按字数折行：超过一行时均分成若干行，避免出现「8 字 + 1 字」这种孤字。"""
    text = str(text)
    n = len(text)
    if n <= max_chars:
        return [text]
    lines = -(-n // max_chars)          # ceil
    per = -(-n // lines)                # 每行均分
    return [text[i:i + per] for i in range(0, n, per)]


def wrap_judge(text, max_chars=6):
    """判断节点折行：优先在「判断是否」后断开，避免把「办公室」切成「办/公室」。"""
    text = str(text)
    for head in ("判断是否为", "判断是否", "是否"):
        if text.startswith(head) and len(text) > max_chars:
            rest = text[len(head):]
            return [head] + wrap(rest, max_chars)
    return wrap(text, max_chars)


def node_spec(kind, name):
    """kind: start / first / approve / multi / judge / notice / action / end"""
    # 菱形上下收窄，按 6 字折行；其余按 8 字
    lines = wrap_judge(name, 6) if kind == "judge" else wrap(name, 8)
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
    if kind == "action":
        # 执行动作不画节点框：步骤名直接压在连线上（白色描边保证可读）。
        # 节点区域内补一段竖线，否则上下两段边会在文字处留出断口。
        cx = x + w / 2
        cy = y + h / 2
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="3"/>'
                   % (cx, y, cx, y + h, C_ARROW))
        lh = 18
        ty = cy + 4.5 - (len(lines) - 1) * lh / 2
        for i, ln in enumerate(lines):
            out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="13" fill="%s" '
                       'stroke="%s" stroke-width="5" paint-order="stroke" '
                       'text-anchor="middle">%s</text>'
                       % (cx, ty + i * lh, FONT, C_ACTION_TEXT, C_BG, esc(ln)))
        return "\n".join(out)
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

    lh = 17 if kind == "judge" else 20
    fs = 12 if kind == "judge" else 14
    ty = cy + 4 - (len(lines) - 1) * lh / 2
    tx = cx if icon_x is None else icon_x + 20 + (w - 20) // 2
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="%d" fill="%s" '
                   'text-anchor="middle">%s</text>'
                   % (tx, ty + i * lh, FONT, fs, C_TEXT, esc(ln)))
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


def draw_edge(pts, arrow=True):
    """正交折线箭头：pts 是 [(x,y), ...]，最后一点是箭头尖端。

    线段必须画到「箭头底部」（尖端回退 11px），否则两点直边会退化成只有箭头没有线。
    arrow=False：执行动作节点只是线上的文字，不画箭头，避免看起来像终止在那里。
    """
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    if arrow:
        if abs(x2 - x1) < 1:
            base = (x2, y2 - 11)
        else:
            base = (x2 - 11, y2)
        body = list(pts[:-1]) + [base]
    else:
        body = list(pts)
    d = "M%.1f %.1f " % body[0] + " ".join("L%.1f %.1f" % p for p in body[1:])
    out = ['<path d="%s" fill="none" stroke="%s" stroke-width="3" '
           'stroke-linejoin="round"/>' % (d, C_ARROW)]
    if not arrow:
        return "\n".join(out)
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
        n = node_spec(r["kind"], r.get("label") or r["name"])
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


def free_lane(rows, a_draw, b_draw, sx, tx, ly, limit, minx, miny):
    """折线的横段别压在别的节点上：撞到就往下让到该节点底部，最多让到 limit。

    典型场景：「下一步 → 判断是否包含院领导」从最右列横切回主线时，
    默认高度正好压在中间的「主管院长审批」方框上。
    """
    lo, hi = min(sx, tx), max(sx, tx)
    for _ in range(len(rows)):
        hit = None
        for o in rows:
            if o["draw"] in (a_draw, b_draw):
                continue
            ox, oy = o["x"] - minx, o["y"] - miny
            if ox + o["n"]["w"] < lo or ox > hi:
                continue
            if oy - 8 <= ly <= oy + o["n"]["h"] + 8:
                hit = oy + o["n"]["h"] + 14
                break
        if hit is None:
            break
        ly = hit
    return min(ly, limit)


def find_crossings(rows):
    """折线是否穿过无关节点（只看线段中点是否落在别的节点矩形内）。"""
    hits = []
    by_draw = {r["draw"]: r for r in rows}
    if not rows:
        return hits
    w_cv = (max(r["x"] + r["n"]["w"] for r in rows)
            - min(r["x"] for r in rows)) or 1.0
    for r in rows:
        for t in r.get("to") or []:
            dst = by_draw.get(t)
            if not dst:
                continue
            sx = r["x"] + r["n"]["w"] / 2
            sy = r["y"] + r["n"]["h"]
            tx = dst["x"] + dst["n"]["w"] / 2
            ty = dst["y"]
            span = (dst["y"] - r["y"]) - r["n"]["h"]
            if span > 240 and (abs(sx - tx) < 1 or abs(sx - tx) > w_cv * 0.5):
                # 这类边渲染时走外侧沟槽，不按「直线中点」判断，否则会误报穿框
                continue
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
    """检查排版问题：重叠一律报错；连线穿框只提示。返回问题条数。

    先折叠执行动作再检测——它们不画框，坐标落在连线中段（本就贴着上下游），
    按实框比对会一律误报「重叠」。
    """
    rows, _, _ = fold_action_rows(copy.deepcopy(rows))
    ov = find_overlaps(rows)
    cr = find_crossings(rows)
    if ov:
        for a, b in ov[:6]:
            print("       ! 节点重叠：「%s」与「%s」坐标冲突" % (a, b))
        print("       ! 共 %d 对节点重叠，图不可用；请改 graph 里的 x/y 或改用自动布局" % len(ov))
    for a, b, c in cr[:4]:
        print("       · 连线 %s→%s 穿过「%s」（可通过错开 x/y 或减少跨层连接改善）" % (a, b, c))
    return len(ov) if strict else 0


def cond_labels(graph):
    """judge.conditions/else → {(源名, 目标名): 分支文字}。

    与 build_export 的 StepCondition 同源：一个条件项一条，`value` 给列表就是多条
    （文字用「 / 」连），else 出口写「【取反】…」。
    """
    out = {}
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict) or not (n.get("conditions") or n.get("else")):
            continue
        nm = n.get("name")
        group, total = {}, 0
        for c in n.get("conditions") or []:
            if not isinstance(c, dict):
                continue
            to = c.get("to")
            vals = c.get("value")
            vals = vals if isinstance(vals, list) else [vals]
            lab = c.get("label") or c.get("note") or " / ".join(str(v) for v in vals)
            if to:
                group.setdefault(to, []).append(lab)
                total += len(vals)
        for to, labs in group.items():
            out[(nm, to)] = labs[0] if (total == 1 and len(labs) == 1) else " / ".join(labs)
        alt = flow_types.alt_of(n)
        if alt:
            lab = ""
            if isinstance(n.get("else"), dict):
                lab = n["else"].get("label") or ""
            out[(nm, alt)] = "【取反】%s" % (lab or "其他")
    return out


def _is_action_node(node):
    typ = node.get("type") or flow_types.classify(node["name"])
    return flow_types.meta_of(typ)["kind"] == "action"


def resolve_cond_labels(graph, text_map):
    """条件的目标写成执行动作时（图上会折叠成连线文字），换成折叠后的节点名。

    与 build_export 的 redirect 同一个道理：判断 →4.1（动作）→ 4.1.1 审批，
    图上只剩 判断→4.1.1，条件文字必须挂到这条边上。
    """
    nodes = {n["name"]: n for n in graph.get("nodes") or [] if isinstance(n, dict)}
    edges = graph.get("edges") or []

    def follow(nm, seen):
        n = nodes.get(nm)
        if not n or nm in seen or not _is_action_node(n):
            return nm
        for a, b in edges:
            if a == nm and b not in seen:
                return follow(b, seen | {nm})
        return nm

    out = {}
    for (s, d), v in text_map.items():
        out[(s, follow(d, set()))] = v
    return out


def rows_from_graph(graph):
    """spec 的 graph：节点可自带 x/y（手工排版），否则走分层自动布局。"""
    flow_types.expand_conditions(graph)      # judge.conditions/else → 边
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    # label = 图上显示的文字（不含层级序号）；name 仍作唯一键连边
    lab = {n["name"]: (n.get("label") or strip_no(n["name"])) for n in nodes if isinstance(n, dict)}
    manual = nodes and all(isinstance(n, dict) and "x" in n and "y" in n for n in nodes)
    if not manual:
        rows = flow_types.layout_graph(nodes, edges)
        for r in rows:
            r["label"] = lab.get(r["name"], r["name"])
        return rows
    flow_types.assert_unique([n["name"] for n in nodes])
    rows, idx = [], {}
    for i, n in enumerate(nodes):
        key = n.get("type") or flow_types.classify(n["name"])
        if key not in flow_types.TYPE_META:
            key = flow_types.classify(n["name"])
        rows.append({"draw": i + 1, "name": n["name"], "key": key,
                     "label": lab.get(n["name"], n["name"]),
                     "kind": flow_types.meta_of(key)["kind"],
                     "x": float(n["x"]), "y": float(n["y"]), "to": []})
        idx[n["name"]] = rows[-1]
    for a, b in edges:
        if a in idx and b in idx:
            idx[a]["to"].append(idx[b]["draw"])
    return rows


def draw_edge_action_label(x, y, text, canvas_w=None, per=12):
    """长连线上的执行动作文字：与 action 节点同样式（橙色 13px + 白色描边），压在线上。

    canvas_w 给定时把 x 夹在画布内、并把超长文字按 per 字折行，
    否则贴边分支（如「判断人员类别 → 结束」）的文字会被裁掉一半。
    """
    lines = [ln for ln in str(text).split("\n") if ln.strip()]
    if not lines:
        return ""
    if canvas_w:
        lines = [s for ln in lines for s in wrap(ln, per)]
        tw = max(len(s) for s in lines) * 13
        x = max(x, tw / 2.0 + 8)
        x = min(x, canvas_w - tw / 2.0 - 8)
    out, lh = [], 18
    ty = y + 4.5 - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="13" fill="%s" '
                   'stroke="%s" stroke-width="5" paint-order="stroke" '
                   'text-anchor="middle">%s</text>'
                   % (x, ty + i * lh, FONT, C_ACTION_TEXT, C_BG, esc(ln)))
    return "\n".join(out)


def draw_edge_label(x, y, text, canvas_w=None, per=12, gap=None):
    """分支条件文字：压在判断出线的竖线中段，底下垫一块画布色小底片。

    gap 给定时按竖向可用空间决定折几行，避免文字长度超过两节点之间的间距、
    糊到目标节点框上（老 spec 的分支名很长的场景）。
    y 是文字块的中心（不是底边）——之前按底边算，文字整体偏上一截，
    横线正好从两行之间穿过，读起来像被划掉。
    """
    lines = [ln for ln in str(text).split("\n") if ln.strip()]
    if not lines:
        return ""
    if gap:
        n_ok = max(1, min(6, int((gap - 6) // 15)))
        # 少折行优先：每行至少 12 字（宽度 132px，仍在节点宽 176 以内），
        # 只有真的放不下才继续收窄——否则「遗失/损坏（请把旧胸牌交还至电脑中心）」
        # 会被折成一列 6 字的小竖条。
        per = max(12, -(-max(len(l) for l in lines) // n_ok))
    if canvas_w:
        lines = [s for ln in lines for s in wrap(ln, per)]
        tw = max(len(s) for s in lines) * 11
        x = max(x, tw / 2.0 + 8)
        x = min(x, canvas_w - tw / 2.0 - 8)
    h = 15
    total = h * len(lines)
    top = y - total / 2.0
    wmax = max(len(s) for s in lines) * 11 + 8
    out = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s" opacity="0.93"/>'
           % (x - wmax / 2.0, top - 2, wmax, total + 4, C_BG)]
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="11" fill="#3d5866" '
                   'stroke="#ffffff" stroke-width="3" paint-order="stroke" '
                   'text-anchor="middle">%s</text>'
                   % (x, top + h * (i + 0.78), FONT, esc(ln)))
    return "\n".join(out)


def fold_action_rows(rows):
    """执行动作在图上不画框、也不参与连线：前驱直接连后继，步骤名只作文字。

    与 build_export.fold_action_nodes 同源——导出的包里这些步骤不存在，
    图上如果还按「src→action→dst」两段画，跨列的 action 文字会脱离连线。
    返回 (去掉 action 的 rows, {draw: node}, {(src, dst): [被折叠的 action draw…]})。
    """
    acts = {r["draw"] for r in rows if r["n"]["kind"] == "action"}
    if not acts:
        return rows, {}, {}
    by = {r["draw"]: r for r in rows}
    texts = {r["draw"]: (r["x"], r["y"], r["n"]) for r in rows if r["draw"] in acts}
    chain = {}
    for r in rows:
        if r["draw"] in acts:
            continue
        new_to = []
        for t in r.get("to") or []:
            cur, seen, path = t, set(), []
            while cur in acts and cur not in seen:
                seen.add(cur)
                path.append(cur)
                nxts = by[cur].get("to") or []
                cur = nxts[0] if nxts else None
                if cur is None:
                    break
            if cur is None:
                continue
            if cur not in new_to:
                new_to.append(cur)
            chain.setdefault((r["draw"], cur), []).extend(path)
        r["to"] = new_to
    return [r for r in rows if r["draw"] not in acts], texts, chain


def dist_to_path(x, y, pts):
    """点到折线的最短距离（判断 action 的原坐标是不是本来就压在线上）。"""
    best = 1e9
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            d = math.hypot(x - x1, y - y1)
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            d = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
        best = min(best, d)
    return best


def path_points(pts):
    """折线上可放文字的位置：各段中点，按段长从长到短。

    文字最终放哪一段由 place_action_texts 统一决定——先按长度优先，
    撞到别的文字就往下一段退，保证「文字永远贴在自己那条线上、且互不重叠」。
    返回 (x, y, ori)：ori="h" 横线段（文字整块抬到线上方，线保持连续），
    ori="v" 竖线段（文字压在线上，靠底片断开竖线）。
    """
    out = []
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        ln = math.hypot(x2 - x1, y2 - y1)
        ori = "h" if abs(x2 - x1) >= abs(y2 - y1) else "v"
        out.append((ln, ((x1 + x2) / 2.0, (y1 + y2) / 2.0, ori)))
    if len(out) > 1:                       # 首尾那一小截是接头，优先级最低
        out[0] = (out[0][0] * 0.35, out[0][1])
        out[-1] = (out[-1][0] * 0.35, out[-1][1])
    out.sort(key=lambda t: -t[0])
    keep = [p for ln, p in out if ln > 12]
    return keep or [(pts[0][0], pts[0][1], "v")]


def _text_y(cy, ori, block_h):
    """横线上的文字抬到线上方；竖线上的文字保持压在线上。"""
    return cy - (block_h / 2.0 + 6) if ori == "h" else cy


def _hit_box(cx, cy, tw, bh, boxes):
    """文字块是否压在某个节点方框上（文字是先画的，会被后画的方框盖掉半截）。"""
    for bx, by, bw, bh_ in boxes:
        if (cx - tw / 2.0 < bx + bw + 4 and cx + tw / 2.0 > bx - 4
                and cy - bh / 2.0 < by + bh_ + 4 and cy + bh / 2.0 > by - 4):
            return True
    return False


def place_action_texts(items, canvas_w, fixed=(), boxes=()):
    """items: [(候选点列表, node_spec)] → [(x, y, node_spec)]，逐个避让。

    距离判断用「横向需错开半宽、纵向需错开一行」，两段文字挨太近就换到下一段；
    boxes 给了就再避一遍方框——压在框上的字会被方框盖掉下半截（用户 2026-11-26 指出
    「医技药人员」糊在「医务科初审」上边框那种）。
    """
    # 手工摆过的先占位（换成同口径的「中心 x, 中心 y, 文字宽」），自动摆的绕着它们走
    placed = [(fx, fy, max(len(l) for l in fan["lines"]) * 13 + 12)
              for fx, fy, fan in fixed]
    out = []
    for cands, an in items:
        tw = max(len(ln) for ln in an["lines"]) * 13 + 12
        bh = max(1, len(an["lines"])) * 18
        best = None
        for cx, cy, ori in cands:
            cx = max(tw / 2.0 + 6, min(cx, canvas_w - tw / 2.0 - 6))
            cy = _text_y(cy, ori, bh)
            # 先原地，再沿线的方向滑开一点（横线上下滑、竖线上下滑），直到不压框、不压字。
            # 顺序固定为「先下后上」：同一条边上有多个执行动作时按链路顺序排，
            # 往下走的那一支才不会出现「流程结束」跑到「存档」上面（用户 2026-11-26 指出）。
            for dy in (0, 24, -24, 44, -44):
                yy = cy + dy
                if (all(abs(cx - px) > (tw + pw) / 2.0 - 8 or abs(yy - py) > 22
                        for px, py, pw in placed)
                        and not _hit_box(cx, yy, tw, bh, boxes)):
                    best = (cx, yy, tw)
                    break
            if best:
                break
        if best is None:
            # 同一条边上有两三个执行动作（如「存档 → 流程结束」）：沿线的方向错开，
            # 文字仍然贴着自己那条线，只是上下分开。
            cx, cy, ori = cands[0]
            cx = max(tw / 2.0 + 6, min(cx, canvas_w - tw / 2.0 - 6))
            cy = _text_y(cy, ori, bh)
            for dy in (28, 54, 80, 108, -28, -54, -80, -108):
                if (all(abs(cx - px) > (tw + pw) / 2.0 - 8 or abs(cy + dy - py) > 22
                        for px, py, pw in placed)
                        and not _hit_box(cx, cy + dy, tw, bh, boxes)):
                    best = (cx, cy + dy, tw)
                    break
            if best is None:
                best = (cx, cy, tw)
        placed.append(best)
        out.append((best[0], best[1], an))
    return out


def corridor_clear(rows, a_draw, b_draw, x, y0, y1, minx, miny):
    """同列直落的竖线是否一路无遮挡（中间没有别的方框）。"""
    for o in rows:
        if o["draw"] in (a_draw, b_draw):
            continue
        ox = o["x"] - minx
        oy = o["y"] - miny
        if ox - 2 <= x <= ox + o["n"]["w"] + 2 and oy < y1 - 2 and oy + o["n"]["h"] > y0 + 2:
            return False
    return True


def draw_action_text(x, y, n):
    """执行动作的文字（橙色 13px + 白描边 + 画布色底片），压在连线上，不画框。

    底片是必须的：文字压在折线上时，横/竖线会从两行字中间穿过去，
    看起来像被划掉（用户 2026-11-26 指出的「不需要主管院长审批」那种）。
    """
    lines = [ln for ln in n["lines"] if ln.strip()]
    if not lines:
        return ""
    cx, cy = x + n["w"] / 2, y + n["h"] / 2
    lh = 18
    ty = cy + 4.5 - (len(lines) - 1) * lh / 2
    wmax = max(len(ln) for ln in lines) * 13 + 10
    block = len(lines) * lh
    out = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s" opacity="0.93"/>'
           % (cx - wmax / 2.0, cy - block / 2.0, wmax, block + 4, C_BG)]
    for i, ln in enumerate(lines):
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="13" fill="%s" '
                   'stroke="%s" stroke-width="5" paint-order="stroke" '
                   'text-anchor="middle">%s</text>'
                   % (cx, ty + i * lh, FONT, C_ACTION_TEXT, C_BG, esc(ln)))
    return "\n".join(out)


def render_canvas(rows):
    """按平台画布坐标渲染，支持分支与汇聚（正交折线）。"""
    if not rows:
        return render_svg([])
    # 执行动作不画框、不参与连线：先折叠掉，再算画布范围——
    # 否则 action 的 x/y（只用来参考、实际文字由折线决定）会把画布撑得很宽。
    rows, action_texts, act_chain = fold_action_rows(rows)
    pad = 62
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
    boxes = [(r["x"] - minx, r["y"] - miny, r["n"]["w"], r["n"]["h"]) for r in rows]
    lab_parts = []          # 连线文字延后到所有线画完再画，底片才能压住线
    act_pending = []        # 执行动作文字：坐标脱离连线的，按折线自动摆
    act_fixed = []          # 执行动作文字：手工摆好、已在连线上的，原样保留
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
            # 判断节点的横向分支从左右顶点出去：否则「是」「否」两条臂都从菱形
            # 底部同一个点起步，读者分不清哪条走了右边；左支还必然横穿菱形下半部。
            # 但目标就在正下方时（中心差 ≤10px）必须走**底顶点直下**，
            # 否则会先向右下再折回来，横段正好从菱形下半部穿过去、分支文字糊在菱形上。
            if r["n"]["kind"] == "judge" and abs(sx - tx) > 1:
                if abs(tx - sx) > 10:
                    sx = (r["x"] - minx) if tx < sx else (r["x"] + r["n"]["w"] - minx)
                    sy = r["y"] + r["n"]["h"] / 2 - miny
            span = (dst["y"] - r["y"]) - r["n"]["h"]
            w_cv = maxx - minx
            mid = w_cv / 2.0
            if ty < sy - 6:
                # 向上回退的边（「转科主任/护士长审批」回原审批、「审批完成」回系统管理员）：
                # 直上或下-横-下都会从节点框中间穿过去，统一走画布左侧沟槽，
                # 再从目标节点左侧水平进入。多条回退边按出线序号错开，避免叠在一起。
                gx = 44 + 16 * i
                ty_mid = dst["y"] + dst["n"]["h"] / 2 - miny
                tx_l = dst["x"] - minx - 4
                pts = [(sx, sy), (sx, sy + 18), (gx, sy + 18),
                       (gx, ty_mid), (tx_l, ty_mid)]
            elif abs(sx - tx) < 1 and (span <= 240 or corridor_clear(
                    rows, r["draw"], dst["draw"], sx, sy, ty, minx, miny)):
                pts = [(sx, sy), (tx, ty)]
            elif span > 240 and (abs(sx - tx) < 1 or abs(sx - tx) > w_cv * 0.5):
                # 真正需要绕行的跨层长边只有两种：
                #   ① 同列直落（如「判断人员类别 → 结束」的异常出口）；
                #   ② 横跨大半幅（如最右一列回到中间主线）。
                # 只跨两三层的普通汇聚（各科审批 → 主管院长）走下面的「下-横-下」折线，
                # 否则每条都要绕到画布最外侧，图会被一堆横线糊住。
                # 左侧沟槽留 44px，给压线的执行动作文字留出排版空间（24 会贴到画布边）。
                gx = (w_cv - 72) if sx > mid else 44
                pts = [(sx, sy), (sx, sy + 20), (gx, sy + 20),
                       (gx, ty - 24), (tx, ty - 24), (tx, ty)]
            else:
                off = 30 + 16 * i
                ly = sy + off
                if ly > ty - 30:                     # 折返太高时改走上方，留出徽标位置
                    ly = max(sy + 12, ty - 30)
                ly = free_lane(rows, r["draw"], dst["draw"],
                               sx, tx, ly, ty - 26, minx, miny)
                pts = [(sx, sy), (sx, ly), (tx, ly), (tx, ty)]
            parts.append(draw_edge(pts, arrow=(dst["n"]["kind"] != "action")))
            lab = (EDGE_LABEL_D.get((r["draw"], dst["draw"]))
                   or EDGE_LABELS.get((r["n"]["name"], dst["n"]["name"])))
            for ad in (act_chain.get((r["draw"], dst["draw"])) or []) if not lab else []:
                ax0, ay0, an = action_texts[ad]
                hx = ax0 + an["w"] / 2.0 - minx
                hy = ay0 + an["h"] / 2.0 - miny
                aw = max(len(l) for l in an["lines"]) * 13 + 12
                ah = max(1, len(an["lines"])) * 18
                # 手工摆过、本来就压在这条线上的：尊重原坐标；
                # 但压在方框上的不算——那种字会被后画的方框盖掉半截，必须重摆。
                if dist_to_path(hx, hy, pts) <= 5 and not _hit_box(hx, hy, aw, ah, boxes):
                    act_fixed.append((hx, hy, an))
                else:
                    act_pending.append((path_points(pts), an))
            if lab:
                if len(pts) == 6:
                    # 走外侧沟槽的跨层长边：文字用执行动作样式压在沟槽竖线中段
                    lab_parts.append(draw_edge_action_label(
                        pts[2][0], (pts[1][1] + pts[3][1]) / 2.0, lab, w_cv))
                elif len(pts) == 5:
                    # 向上回退边（走左侧沟槽）：文字压在沟槽竖线中段，
                    # 多条回退边靠各自 sy 不同自然错开高度。
                    lab_parts.append(draw_edge_action_label(
                        pts[2][0] + 2, (pts[2][1] + pts[3][1]) / 2.0, lab, w_cv))
                elif len(pts) == 4:
                    # 「下-横-下」折线：压横段中点。压在最后那段竖线上会顶到目标框顶
                    # （两节点之间的竖向间隙本来就窄，容不下 3~4 行字）。
                    lx, ly_ = (pts[1][0] + pts[2][0]) / 2.0, pts[1][1]
                    # 横段宽度决定折行；横段为 0（目标就在正下方）时仍按 12 字折，
                    # 否则会被折成一列 6 字的竖条。
                    per = max(12, int(abs(pts[1][0] - pts[2][0]) / 12.5))
                    lab_parts.append(draw_edge_label(lx, ly_, lab, w_cv, per=per))
                else:
                    # 同列直线：压在两个节点之间的中点
                    lab_parts.append(draw_edge_label(
                        tx, (sy + ty) / 2.0, lab, w_cv, gap=max(span, 44)))
    parts.extend(lab_parts)      # 连线文字最后画：底片才能盖住所有经过的线
    for ax, ay, an in act_fixed + place_action_texts(act_pending, w_cv, act_fixed, boxes):
        parts.append(draw_action_text(ax - an["w"] / 2.0, ay - an["h"] / 2.0, an))
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
                        # 画布上的节点名已去掉层级序号（label），这里同时存一份去序号的键，
                        # 否则 edgeLabels 永远匹配不上（标签不会显示）。
                        EDGE_LABELS[(strip_no(sn), strip_no(dn))] = v
                        break
            raw = rows_from_graph(form["graph"])
            # 条件自带的分支文字（低于 edgeLabels 优先级）；目标若是执行动作先穿透到其后继
            EDGE_LABEL_D.clear()
            dmap = {r["name"]: r["draw"] for r in raw}
            for k, v in resolve_cond_labels(form["graph"], cond_labels(form["graph"])).items():
                sd, dd = dmap.get(k[0]), dmap.get(k[1])
                if sd and dd:
                    EDGE_LABEL_D[(sd, dd)] = v
                for sn, dn in ((k[0], k[1]), (strip_no(k[0]), strip_no(k[1]))):
                    EDGE_LABELS.setdefault((sn, dn), v)
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
