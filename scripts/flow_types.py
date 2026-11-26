#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流程动作类型：名称 → 类型 → 节点编码 / 画布形状 / 自动布局。

平台的动作列表里「动作名称」是用户随手起的（科室初审意见、稿件发布执行……），
「动作类型」才是语义。实测到的类型（见 references/flow-export.md）：

    审批 / 多选择审批 / 通知执行 / 执行动作 / 条件判断 / 存档 / 生成处理签 / 通知申请人或执行动作

只有 审批(nodeApprove/ActionTypeID=2)、通知执行(nodeNotice/3)、执行动作(nodeAction/4)、
条件判断(nodeJudge/6) 是实测到 node 编码的；其余类型平台编码未知，**按用户规则先落成通知执行**并给出告警。
"""
import math
import re

# key -> 元信息
#   label        中文类型名（与平台动作类型一致）
#   node         FlowStep.node 编码（None = 未实测，回退）
#   action_type  FlowStep.ActionTypeID
#   kind         画布形状：approve/notice/judge/archive/doc/auto/multi
#   verified     是否实测确认过编码
TYPE_META = {
    "start":   {"label": "开始", "node": "nodeStart", "action_type": 0,
                "kind": "start", "verified": True},
    "first":   {"label": "申请人", "node": "nodeFirst", "action_type": 0,
                "kind": "first", "verified": True},
    "end":     {"label": "结束", "node": "nodeEnd", "action_type": 0,
                "kind": "end", "verified": True},
    "approve": {"label": "审批", "node": "nodeApprove", "action_type": 2,
                "kind": "approve", "verified": True},
    "multi":   {"label": "多选择审批", "node": "nodeApprove", "action_type": 2,
                "kind": "multi", "verified": False},
    "notice":  {"label": "通知执行", "node": "nodeNotice", "action_type": 3,
                "kind": "notice", "verified": True},
    "action":  {"label": "执行动作", "node": "nodeAction", "action_type": 4,
                "kind": "action", "verified": True},
    "judge":   {"label": "条件判断", "node": "nodeJudge", "action_type": 6,
                "kind": "judge", "verified": True},
    "archive": {"label": "存档", "node": None, "action_type": None,
                "kind": "archive", "verified": False},
    "doc":     {"label": "生成处理签", "node": None, "action_type": None,
                "kind": "doc", "verified": False},
    "auto":    {"label": "通知申请人或执行动作", "node": None, "action_type": None,
                "kind": "auto", "verified": False},
}

FALLBACK = "notice"          # 判断不出来时按用户要求先当通知执行

# 判定顺序极重要：
#   1) 先判「多选择」再判「审批」，否则「多选择审批」会被判成审批；
#      但用户 2026-11-25 红字确认：多选择审批 → 通知执行（不是审批）。
#   2) 用户红字确认：存档/归档 → 执行动作（不是存档/通知执行）。
_RULES = [
    ("action",  ("通知申请人或执行动作",)),   # 用户 2026-11-25 明确：电脑+绿箭头 → 执行动作；须在 action 组前，否则「执行动作」也会命中所以统一 action
    ("judge",   ("条件判断", "判断", "条件分支", "分支条件", "是否通过", "分流")),
    # 用户 2026-11-26 10:46 纠正：图标「窗口+人+红斜箭头」、步骤名「请选择是否需要…」→ 通知执行，
    # 不是条件判断（判断的图标是「窗口+▼」）。必须排在「会签/审批」前，否则
    # 「请选择是否需要职能科会签」会被 "会签" 误判成审批。
    ("notice",  ("请选择是否需要", "请选择是否", "是否需要")),
    ("notice",  ("多选择", "多选审批", "多人选择")),
    ("action",  ("存档", "归档", "备案存", "入档")),
    ("doc",     ("处理签", "签章", "用印", "盖章", "生成文件")),
    ("auto",    ("空步骤", "自动执行", "系统执行")),
    ("action",  ("执行动作", "抄送", "知会")),
    ("approve", ("审批", "审核", "批准", "核准", "会签", "签发", "批示", "审定", "复核")),
    ("notice",  ("通知", "执行", "发布", "告知", "传达", "推送", "情况", "反馈", "报送", "自动传阅分发")),
]


_SPECIAL = {"开始": "start", "发起": "start", "begin": "start",
            "申请人": "first", "发起人": "first", "填报人": "first",
            "结束": "end", "完成": "end", "end": "end"}


def classify(name):
    """动作名称 → 类型 key；判不出来返回 FALLBACK（通知执行）。"""
    n = str(name or "").strip()
    if not n:
        return FALLBACK
    if n in _SPECIAL:
        return _SPECIAL[n]
    for key, words in _RULES:
        if any(w in n for w in words):
            return key
    # 「…意见」结尾几乎都是审批意见栏
    if n.endswith("意见"):
        return "approve"
    return FALLBACK


def label_of_node(node):
    """node 编码 → 平台里的类型名（stepName 用它，保证与 node 一致）。"""
    for m in TYPE_META.values():
        if m["node"] == node:
            return m["label"]
    return TYPE_META[FALLBACK]["label"]


def meta_of(key):
    return TYPE_META.get(key) or TYPE_META[FALLBACK]


def normalize_items(flow):
    """把 spec 的 flow 列表整理成 [{name, key}]；支持 '类型:名称' 写法。"""
    out = []
    for it in flow or []:
        if isinstance(it, str):
            name, key = it, None
            if ":" in it or "：" in it:
                head, tail = re.split(r"[:：]", it, maxsplit=1)
                if head.strip() in _LABEL2KEY:
                    key, name = _LABEL2KEY[head.strip()], tail.strip()
        else:
            name = it.get("name") or it.get("label") or ""
            key = it.get("type")
            if key in TYPE_META:
                pass
            elif key in _LABEL2KEY:
                key = _LABEL2KEY[key]
            else:
                key = None
        key = key or classify(name)
        out.append({"name": str(name).strip(), "key": key})
    return out


_LABEL2KEY = {m["label"]: k for k, m in TYPE_META.items()}
_LABEL2KEY.update({"判断": "judge", "通知": "notice", "多选": "multi",
                   "开始": "start", "申请人": "first", "结束": "end"})

GAP_Y = 120
BRANCH_GAP = 140
X_MAIN, X_LEFT, X_RIGHT = 460, 261, 660


def layout(items):
    """自动布局：主线竖直，判断节点分出左右两支后再汇聚。

    items: [{name, key}]，判断节点的两个分支 = 紧随其后的两项。
    返回 [{draw, name, kind, x, y, to:[draw...]}]，draw 从 1 开始。
    """
    rows = []
    y = 100
    i = 0
    while i < len(items):
        it = items[i]
        prev = rows[-1] if rows else None
        draw = len(rows) + 1
        rows.append({"draw": draw, "name": it["name"], "key": it["key"],
                     "kind": meta_of(it["key"])["kind"],
                     "x": X_MAIN, "y": y, "to": []})
        me = rows[-1]
        if prev is not None and not prev["to"]:      # 主线串联（先把上一节点指向自己）
            prev["to"] = [draw]

        # 判断节点：紧随其后的两项当左右分支，之后的两支汇聚到再下一个节点
        if it["key"] == "judge" and i + 2 < len(items):
            left_it, right_it = items[i + 1], items[i + 2]
            by = y + BRANCH_GAP
            for x, sub in ((X_LEFT, left_it), (X_RIGHT, right_it)):
                d = len(rows) + 1
                rows.append({"draw": d, "name": sub["name"], "key": sub["key"],
                             "kind": meta_of(sub["key"])["kind"],
                             "x": x, "y": by, "to": []})
                me["to"].append(d)
            i += 3
            if i < len(items):                       # 还有后续节点 → 两支都指向它
                nxt = len(rows) + 1
                rows[-2]["to"] = [nxt]
                rows[-1]["to"] = [nxt]
            y = by + BRANCH_GAP
            continue

        y += GAP_Y
        i += 1
    return rows


def judge_warnings(rows):
    """判断节点分支数异常（1 条或 0 条）时给提示。"""
    out = []
    for r in rows:
        if r.get("kind") == "judge":
            n = len(r.get("to") or [])
            if n < 2:
                out.append("判断节点「%s」只有 %d 条分支（判断应有 2 条以上）" % (r["name"], n))
    return out


def layout_summary(rows):
    cnt = {}
    for r in rows:
        cnt[r["kind"]] = cnt.get(r["kind"], 0) + 1
    order = ("start", "first", "judge", "approve", "multi", "notice", "action",
             "archive", "doc", "auto", "end")
    return "、".join("%s×%d" % (k, cnt[k]) for k in order if k in cnt)


def chain_text(rows):
    """按 draw 顺序给出可读链路（多分支用括号，分支节点只出现一次）。"""
    by = {r["draw"]: r for r in rows}
    parts = []
    for r in rows:
        if len(r["to"]) > 1:
            names = " | ".join(by[t]["name"] for t in r["to"] if t in by)
            parts.append("%s⟶[%s]" % (r["name"], names))
            for t in r["to"]:
                if t in by:
                    by[t]["_skip"] = True
        elif not r.get("_skip"):
            parts.append(r["name"])
    return " → ".join(parts)

def assert_unique(names):
    """节点名重复 → 边按名字连会连错，直接报错。"""
    seen, dup = set(), []
    for n in names:
        if n in seen:
            dup.append(n)
        seen.add(n)
    if dup:
        raise ValueError("流程节点重名：%s（边是按名字连的，请先改名）"
                         % "、".join(sorted(set(dup))))


def layout_graph(nodes, edges, x0=460, gap_y=140, gap_x=200):
    """通用图布局（分层）：支持三路以上分支、嵌套判断、跨层长边。

    nodes: [{name, type, x?, y?}] 或名字列表；edges: [(from, to), ...]
    层级 = 从开始节点起的最长路径；同层按发现顺序左右展开。
    """
    def name_of(v):
        return v if isinstance(v, str) else (v.get("name") or v.get("label"))

    names = [name_of(n) for n in nodes]
    assert_unique(names)
    idx = {n: i for i, n in enumerate(names)}
    succ = {n: [] for n in names}
    for a, b in edges:
        if a in succ and b in idx:
            succ[a].append(b)

    level = {n: 0 for n in names}
    order_seen = {n: i for i, n in enumerate(names)}
    for _ in range(len(names) + 1):
        changed = False
        for a, b in edges:
            if a in level and b in level and level[b] < level[a] + 1:
                level[b] = level[a] + 1
                changed = True
        if not changed:
            break

    layers = {}
    for n in names:
        layers.setdefault(level[n], []).append(n)
    for lv in layers:
        layers[lv].sort(key=lambda n: order_seen[n])

    rows = []
    for lv in sorted(layers):
        group = layers[lv]
        width = len(group)
        for i, n in enumerate(group):
            item = next((x for x in nodes if name_of(x) == n), None)
            key = None
            if isinstance(item, dict):
                key = item.get("type") or item.get("actionType")
            if key not in TYPE_META:
                key = classify(n)
            x = x0 + (i - (width - 1) / 2.0) * gap_x
            rows.append({"draw": len(rows) + 1, "name": n, "key": key,
                         "kind": meta_of(key)["kind"], "x": x, "y": 100 + lv * gap_y,
                         "to": [], "level": lv})
    byname = {r["name"]: r for r in rows}
    for a, b in edges:
        if a in byname and b in byname:
            byname[a]["to"].append(byname[b]["draw"])
    return rows
