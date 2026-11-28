#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按平台「流程导出」格式打包表单：一个 JSON 同时装下 Web 视图、移动视图、流程图。

导出件结构（实测）：
    {
      "FlowExportData": { FlowStep / FlowStepCon / FlowStepPart / FlowSet / FlowSetVersion ... },
      "TemplateData": {
         "mainTableName": "wx_XXXXXXXX_Form_0000000123",
         "mainView": { "sheet": "<Web 视图 JSON 字符串>",
                       "template": "{\"elements\":[...],\"script\":\"\"}" , ... },
         "templateData": { "name": ..., "TemplateID": ... },
         "templateViewList": [...]
      }
    }

要点（实测差异，别踩）：
- `sheet` 与 `template` 都是 **JSON 字符串**，不是对象。
- Web 视图回写后与我们产物**完全一致**，不需要加工。
- 移动视图回写后每元素多 `oldTableKey`/`oldTableName` 两个键（顺序：name 之后、properties 之前），
  每个 properties 多一个 `isBuildByCode`（按字母序插入），且 properties 键**按字母排序**。

用法：
    python build_export.py spec.json --base-export "流程导出_模板.json" --out 导出
    python build_export.py spec.json --base-export ... --flow-id 625 --template-id 563
"""
import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_forms  # noqa: E402
import flow_types    # noqa: E402

NEW_KEYS_PROPS = "isBuildByCode"
NODE_DEFAULTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "flow_node_defaults.json")


def load_node_defaults():
    """平台流程节点的完整默认键（FlowStep 200 / FlowStepPart 96），缺文件就退回精简版。"""
    try:
        return json.loads(open(NODE_DEFAULTS, encoding="utf-8").read())
    except Exception:
        return {"step": {}, "part": {}}


def normalize_element(el):
    """把我们的元素整理成平台回写后的形状（9 个顶层键 + properties 补 isBuildByCode）。"""
    out = {}
    for k in ("children", "class", "icon", "id", "name"):
        out[k] = el.get(k)
    out["oldTableKey"] = ""
    out["oldTableName"] = ""
    pr = dict(el["properties"])
    # 平台导出件里没有 isBuildByCode（回写会丢掉），这里不再补
    out["properties"] = {k: pr[k] for k in sorted(pr)}
    out["type"] = el["type"]
    return out


def strip_element(el):
    """反向：去掉平台专属键，还原成能过我们校验器的形状（用于自检）。"""
    out = {}
    for k in ("children", "class", "icon", "id", "name", "properties", "type"):
        out[k] = el.get(k)
    pr = {k: v for k, v in el["properties"].items() if k != NEW_KEYS_PROPS}
    out["properties"] = pr
    return out


def declared_form_fields(form):
    """spec 节点上的 `formField` → {节点 actualName: 意见框名}。

    平台允许「节点名 ≠ 意见框名」直接绑定（801 收文流程 2026-11-28 实测：
    `各院领导阅知、责任科室阅办` 绑的是 `传阅意见`，且表单里没有这个控件）。
    节点上写 `formField` 就按它绑；不写仍按步骤名全等/宽松匹配（R23）。
    """
    out = {}
    for n in (form.get("graph") or {}).get("nodes") or []:
        if isinstance(n, dict) and n.get("formField"):
            nm = (n.get("label") or strip_no(n.get("name") or "")).strip()
            if nm:
                out[nm] = str(n["formField"]).strip()
    return out


def strip_no(name):
    """去掉步骤名前的层级序号（1、5.1、5.1.1.1 …）。

    平台导入后会自己按结构编号，步骤名里再带一遍序号就重复了；
    老 spec 的 nodes 只有 name（带序号）、没有 label，这里做兜底。
    """
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", str(name or "")).strip()


# ---------------------------------------------------------------- 判断条件
# 平台把判断规则存成 FlowStepCondition（一行 = 判断节点的一个条件项），
# 与连线的 ConContent `[n]` 对应。写法见 references/flow-export.md。
COND_OPS = {"=": "eq", "==": "eq", "eq": "eq", "!=": "ne", "<>": "ne", "ne": "ne",
            ">": "gt", "gt": "gt", "<": "lt", "lt": "lt",
            ">=": "ge", "ge": "ge", "<=": "le", "le": "le"}
LIST_TYPES = ("radio", "checkbox", "select", "selectDep", "multiSelect")


def cond_blank():
    """一条空的 StepCondition（35 键，键序与平台导出件一致）。"""
    return {
        "DrawID": 0, "FlowID": 0, "ID": 0, "SortID": 0,
        "SourceDrawID": 0, "SourceStepID": 0, "StepID": 0,
        "TargetDrawID": 0, "TargetStepID": 0,
        "compareType": "eq", "flowVersion": "1.0",
        "isCanDel": True, "isComputed": False, "isUse": True,
        "jIdentity": "[1]",
        "leftCollDealType": "1,2,3", "leftDescription": "", "leftDetailsType": "Str",
        "leftHandle": "", "leftHandleDescription": "", "leftHandleHidden": "",
        "leftProbableType": "Str", "leftVarCode": "", "leftVarName": "",
        "leftVarType": "FormVariable", "note": "",
        "rightCollDealType": "1,2,3", "rightDescription": "", "rightDetailsType": "Str",
        "rightProbableType": "Str", "rightVarCode": "", "rightVarName": "",
        "rightVarType": "ListVariable", "tabCode": "BaseJudge", "variFilterType": "Default",
    }


def field_code_map(web):
    """Web 视图里 chkName → (字段码, 控件类型)：判断条件的左值靠它定位字段。

    单选/多选/下拉在平台里存 `<码>_Value`，条件里也要写这个后缀。
    """
    out = {}
    for r in ((web or {}).get("rows") or {}).values():
        if not isinstance(r, dict):
            continue
        for cell in (r.get("cells") or {}).values():
            if not isinstance(cell, dict):
                continue
            code, st = cell.get("bindData"), cell.get("SheetType") or ""
            name = (cell.get("chkName") or "").strip()
            if code and st != "approve" and name and name not in out:
                out[name] = (code, st)
    return out


def _cond_values(val):
    """一个条件项的值 → 多个值（列表写法拆成多条条件）。"""
    if isinstance(val, (list, tuple)):
        return [v for v in val]
    return [val]


def _left_of(field, code_map, where):
    """左值：表单变量。返回 (left_dict, 控件类型) 或 (None, None)。"""
    info = code_map.get(field)
    if not info:
        print("  ! 判断「%s」的条件字段「%s」在表单里找不到，跳过这条条件" % (where, field))
        return None, None
    code, st = info
    is_list = st in LIST_TYPES
    name = field + ("(值)" if is_list else "")
    dtype = ("ListCustom" if is_list else
             "Int" if st in ("inputNum", "inputNumDisplay", "number", "amount") else
             "Date" if st in ("date", "datepicker", "dateRange") else "Str")
    return ({
        "type": "FormVariable",
        "code": code + ("_Value" if is_list else ""),
        "name": "<%#myField\\" + name + "%>",
        "desc": "表单变量：" + name,
        "details": dtype,
    }, st)


def _right_of(value, field, left):
    """右值：选项字段用集合变量，数字用常量，其余按字符串常量。"""
    if left["details"] == "ListCustom":
        return {"type": "ListVariable", "code": str(value), "name": str(value),
                "desc": "集合变量：【%s】%s" % (field, value), "details": "ListCustom"}
    if left["details"] == "Int":
        return {"type": "ConstantVariable", "code": str(value),
                "name": "<@%Int://%s@>" % value,
                "desc": "常量变量：%s" % value, "details": "Int"}
    return {"type": "ConstantVariable", "code": str(value), "name": str(value),
            "desc": "常量变量：%s" % value, "details": "Str"}


def _cond_label(value, given=""):
    """条件项的显示文字：显式 note 优先，列表值用「 / 」连。"""
    if given:
        return str(given)
    return " / ".join(str(v) for v in _cond_values(value))


def build_conditions(form, steps, code_map, flow_id, start_id, redirect=None, rows=None):
    """judge.conditions → StepCondition 列表 + 每条出线的文字/ConContent。

    平台规则（实测 422 / 403 导出件）：
    - 出线的 `ConContent` 写「条件因子」的编号：一条边挂一个条件写 `[3]`，
      挂多个就按 ` Or ` 串起来（`[1] Or [2]`）；不成立的那支写 `![n]`（取反）。
      **不能留空**——留空时平台只把 Desc 当显示文字，条件步骤是空的，分支不会走。
    - `ConContentDesc` 是显示文字（带前后空格）：多个条件用「 【或者】 」连，
      单条件直接是条件名；取反支是「 【取反】 是 」。
    - 条件的目标写成执行动作（图上折叠掉的那种）也能穿透到它的后继节点。
    出线一律按**绘图号**配对（actualName 允许重名，如三条分支都叫「科主任审批」）。
    返回 (条件列表, {(判断绘图号, 目标绘图号): (note, desc, ConContent)}, 告警)。
    """
    redirect = redirect or {}
    conds_out, edge_text, warns = [], {}, []
    node_of = {}
    for n in (form.get("graph") or {}).get("nodes") or []:
        if isinstance(n, dict) and (n.get("conditions") or n.get("else")):
            node_of[n["name"]] = n
    if not node_of:
        return conds_out, edge_text, warns
    by_draw = {s["DrawID"]: s for s in steps}
    draw_of = {r["name"]: r["draw"] for r in (rows or [])}
    short_of, dup_short = {}, set()
    for r in rows or []:
        k = strip_no(r["name"])
        if k in short_of:
            dup_short.add(k)
        else:
            short_of[k] = r["draw"]

    def resolve(to, where):
        """条件的目标名 → 折叠后的绘图号（执行动作一路穿到底）。"""
        if not to:
            return None
        if to in draw_of:
            return draw_of[to]
        k = strip_no(to)
        ends = [d for d in (redirect.get(k) or []) if d in by_draw]
        if ends:
            if len(ends) > 1:
                warns.append("判断「%s」的目标「%s」经执行动作分成 %d 条线，条件只取第一条"
                             % (where, to, len(ends)))
            return ends[0]
        if k in short_of and k not in dup_short:
            return short_of[k]
        warns.append("判断「%s」的分支目标「%s」不是流程节点，条件与分支文字未生成"
                     % (where, to))
        return None

    for s in steps:
        if s.get("node") != "nodeJudge":
            continue
        node = None
        for nm, nd in node_of.items():
            if nm == s["actualName"] or strip_no(nm) == s["actualName"]:
                node = nd
                break
        if not node:
            continue
        items = []                       # 一个值一项：{v, dst, lab, op, left, field, sql}
        for c in node.get("conditions") or []:
            if not isinstance(c, dict):
                continue
            field = c.get("field") or c.get("left")
            to = c.get("to")
            sql = c.get("sql")           # 表单字段表达不了的判断：左常量 vs 右 SQL 计数
            if not to or (not field and not sql):
                warns.append("判断「%s」有条件缺 field/to，已跳过" % s["actualName"])
                continue
            if sql:
                const = c.get("const", 0)
                left = {"type": "ConstantVariable", "code": str(const),
                        "name": "<@%%Int://%s@>" % const, "desc": "常量变量：%s" % const,
                        "details": "Int"}
            else:
                left, _st = _left_of(field, code_map, s["actualName"])
                if not left:
                    continue
            dst = resolve(to, s["actualName"])
            if dst is None:
                continue
            op = c.get("op") or c.get("compareType")
            vals = _cond_values(c.get("value")) or (
                [c.get("label") or c.get("note") or "SQL条件"] if sql else [])
            for v in vals:
                items.append({"v": v, "dst": dst,
                              "lab": _cond_label(v, c.get("label") or c.get("note")),
                              "op": op, "left": left, "field": field, "sql": sql})
        if not items:
            continue
        # 写条件行：一个值 = 一条 jIdentity
        for i, it in enumerate(items, 1):
            rec = cond_blank()
            if it.get("sql"):
                right = {"type": "SQLVariable", "code": it["sql"], "name": "",
                         "desc": "SQL变量：【%s】" % it["sql"], "details": "Str"}
            else:
                right = _right_of(it["v"], it["field"], it["left"])
            rec.update({
                "DrawID": s["DrawID"], "FlowID": flow_id,
                "ID": start_id + len(conds_out), "StepID": s["StepID"],
                "compareType": COND_OPS.get(str(it["op"] or "eq"), "eq"),
                "jIdentity": "[%d]" % i, "note": it["lab"],
                "leftVarType": it["left"]["type"], "leftVarCode": it["left"]["code"],
                "leftVarName": it["left"]["name"], "leftDescription": it["left"]["desc"],
                "leftDetailsType": it["left"]["details"],
                "leftProbableType": it["left"]["details"],
                "rightVarType": right["type"], "rightVarCode": right["code"],
                "rightVarName": right["name"], "rightDescription": right["desc"],
                "rightDetailsType": right["details"], "rightProbableType": right["details"],
            })
            conds_out.append(rec)
        # else 出口
        alt = flow_types.alt_of(node)
        alt_dst = resolve(alt, s["actualName"]) if alt else None
        alt_label = ""
        if isinstance(node.get("else"), dict):
            alt_label = node["else"].get("label") or ""
        # 按实际出线顺序归组（steps.processTo 就是 importantShunt 的顺序）
        groups = {}
        for it in items:
            groups.setdefault(it["dst"], []).append(it["lab"])
        if alt_dst is not None:
            groups.setdefault(alt_dst, [])
        order = []
        for did in str(s.get("processTo") or "").split(","):
            did = did.strip()
            if did.isdigit() and int(did) in groups and int(did) not in order:
                order.append(int(did))
        for did in groups:
            if did not in order:
                order.append(did)
        # 单条件 + 两支、又没写 else：另一支就是取反，也要进 order 才能写 `![1]`
        outs = [int(x) for x in str(s.get("processTo") or "").split(",") if x.strip().isdigit()]
        if len(items) == 1 and alt_dst is None and len(outs) == 2:
            for d in outs:
                if d not in order:
                    order.append(d)
        # 每条出线上的条件序号 = jIdentity 里的编号（一个值一项，按条件书写顺序）
        idx_by_dst = {}
        for i, it in enumerate(items, 1):
            idx_by_dst.setdefault(it["dst"], []).append(i)
        all_idx = list(range(1, len(items) + 1))
        item_labs = [it["lab"] for it in items]
        for i, did in enumerate(order):
            labs = groups.get(did) or []
            idxs = idx_by_dst.get(did) or []
            if did == alt_dst and not labs:
                lab = alt_label or "其他"
                note = "【取反】 %s" % lab
                # else 兜底若写的是字段枚举里的一个具体取值，应改成显式条件（09 规则 R25）：
                # 用兜底表达会显示成「【取反】 财务科」，运行时容易误读成排除财务科。
                if alt_label and not any(w in alt_label for w in
                                         ("其他", "其它", "错误", "否", "不", "无", "未", "空", "异常")):
                    warns.append("判断「%s」的 else 出口写作「%s」，像是字段的一个具体取值；"
                                 "若它确实在枚举内，应写成显式条件而不是兜底（09 规则 R25）"
                                 % (s["actualName"], alt_label))
                # 「其他情况」= 所有条件都不成立。多条条件时平台实测写法是
                # `!([1] or [2] or …)`（小写 or、整体加括号，707 导出件 2026-11-28），
                # 不是 `![1] And ![2]`；说明文字同步写成「 【取反】（ A 【或者】 B ）」。
                if len(all_idx) > 1:
                    con = "!(%s)" % " or ".join("[%d]" % k for k in all_idx)
                    desc = " 【取反】（ %s ）" % " 【或者】 ".join(item_labs)
                else:
                    con, desc = "![%d]" % all_idx[0], " 【取反】 %s " % lab
            elif idxs:
                # 一条边挂多个条件时，ConContent 用 `[1] Or [2]` 串（平台实测写法），
                # 光留空只写 Desc 的话导入后「条件步骤」是空的、分支不会自动走。
                note = labs[0] if len(labs) == 1 else " / ".join(labs)
                desc = " %s " % " 【或者】 ".join(labs)
                con = " Or ".join("[%d]" % k for k in idxs)
            else:
                note, desc, con = "", "", ""
            # 单条件 + 两支、又没写 else：第二支就是取反（沿用平台 `![1]` 写法）
            if len(items) == 1 and alt_dst is None and len(order) == 2 and i == 1:
                con = "![%d]" % (idxs[0] if idxs else all_idx[0])
                note, desc = "【取反】是", " 【取反】 是 "
            edge_text[(s["DrawID"], did)] = (note, desc, con)
        # 自检：有条件的判断，每条出线都该绑上条件；漏一条平台里就要人工选分支
        outs = [int(x) for x in str(s.get("processTo") or "").split(",") if x.strip().isdigit()]
        missing = [d for d in outs
                   if not (edge_text.get((s["DrawID"], d)) or ("", "", ""))[2]]
        if missing:
            warns.append("判断「%s」有 %d 条出线没绑条件（Draw %s），平台里要人工选分支"
                         % (s["actualName"], len(missing),
                            "、".join(str(d) for d in missing)))
    return conds_out, edge_text, warns


def fit_con_name(name, limit=50):
    """连线的目标节点名受平台 wmFlowStepCon.NextActualName varchar(50) 限制。

    节点名可以很长（actualName 是 varchar(500)），但连线这一列不能超；
    超长时保留「抄送人（护士长·16人）」这类前缀，把括号里的人名列表去掉。
    """
    if len(name) <= limit:
        return name
    return name.split("：")[0] + "）" if "：" in name else name[:limit]


def fold_action_nodes(rows):
    """把「执行动作」节点折叠成连线文字（用户 2026-11-26 明确要求）。

    执行动作在流程图上只是压在连线上的文字、不是步骤：导出包里必须**删掉这些节点**，
    让前驱直接连到后继，原步骤名成为这条连线上的文字（FlowStepCon.note / ConContentDesc）。
    返回 (折叠后的 rows, {(源名, 目标名): 连线文字}, {action 名: [折叠后的终点绘图号]})；
    draw 重新按顺序编号。第三个表给判断条件用——条件的 to 写在 action 上时要能穿过它。
    """
    acts = {r["draw"]: r for r in rows if r.get("kind") == "action"}
    if not acts:
        return rows, {}, {}
    succ = {r["draw"]: list(r.get("to") or []) for r in rows}

    def walk(d, seen):
        """沿 action 链一路向前，返回 [(终点 draw, [途经的执行动作文字…])]。"""
        if d not in acts:
            return [(d, [])]
        if d in seen:                      # 防环
            return []
        lab = acts[d].get("label") or strip_no(acts[d]["name"])
        out = []
        for nxt in succ.get(d, []):
            for end, labs in walk(nxt, seen | {d}):
                out.append((end, [lab] + labs))
        return out

    keep = [r for r in rows if r["draw"] not in acts]
    old2new = {r["draw"]: i + 1 for i, r in enumerate(keep)}
    by_old = {r["draw"]: r for r in keep}
    labels, redirect = {}, {}
    for r in keep:
        new_to = []
        for t in r.get("to") or []:
            if t in acts:
                for end, labs in walk(t, set()):
                    if end not in old2new:
                        continue
                    nd = old2new[end]
                    if nd not in new_to:
                        new_to.append(nd)
                    if labs:
                        # 相邻同名的执行动作只留一个（源表常见「同名连续两步」），
                        # 否则连线文字会出现「不同意，退回申请 → 不同意，退回申请」。
                        ded = []
                        for s in labs:
                            if not ded or ded[-1] != s:
                                ded.append(s)
                        labels[(r["name"], by_old[end]["name"])] = " → ".join(ded)
            elif t in old2new and old2new[t] not in new_to:
                new_to.append(old2new[t])
        r["to"] = new_to
    for a in acts.values():
        ends = []
        for end, _ in walk(a["draw"], set()):
            if end in old2new and old2new[end] not in ends:
                ends.append(old2new[end])          # 折叠后的绘图号（名字可能重名，号唯一）
        redirect[strip_no(a["name"])] = ends
    for r in keep:
        r["draw"] = old2new[r["draw"]]
    return keep, labels, redirect


# 分流/合流节点的键值与普通节点不同（2026-11-27 平台实测样本）：
# 它们是「无人员、无表单」的结构节点，平台给的是另一套默认值。
# 普通节点是 singleApprove=10 / agreePercent=100.0 / selUserRange=1 / unFinishedActive=0 …
SHUNT_CONVERG_OVERRIDES = {
    "singleApprove": 0,
    "agreePercent": 0.0,
    "negativePercent": 0.0,
    "selUserRange": 2,
    "signUpRange": 2,
    "signUpInfluenceTrend": 2,
    "signUpApproveUidMode": 0,
    "unFinishedActive": 1,
    "unFinishedNotify": 9,
    "agentOneFinishedNotify": 9,
    "agentOriginFinishedNotify": 9,
    "agentUnFinishedNotify": 9,
    "flowTriggerSetMode": 0,
    "flowToNoticeMode": 1,
    "flowToNoticeAttMode": 1,
    "flowToNoticeFormMode": 1,
    "flowToCirMode": 1,
    "flowToCirAttMode": 1,
    "isCanAssist": False,
    "isCanDirectDelivery": True,
    "isCanEntrust": False,
    "isCanSignUp": False,
}

# 「例外出口」的名字特征：退回修改 / 终止 / 流程结束 —— 这些不是并行分支。
_EXIT_WORDS = ("返回", "退回", "终止", "结束", "不同意", "作废", "撤销", "错误")


def _is_exit_branch(name, label=""):
    """退回 / 终止类的出线：不是并行分支，插了分流平台会当成两条并行线。"""
    text = "%s %s" % (name or "", label or "")
    return any(w in text for w in _EXIT_WORDS)


def business_next(draws, by_draw):
    """业务上的「下一步」：跳过 分流/合流 这两个结构节点。

    平台导出件里 importantShunt（「同意执行」的默认目标）不写结构节点：
    保卫科负责人审批 → 分流 → 两个分支，写的是 "6,7"；人事科会签 → 合流 → 分管院领导，写的是 "8"。
    """
    out = []
    for t in draws or []:
        r = by_draw.get(t)
        if r is not None and r.get("key") in ("shunt", "converg"):
            for x in business_next(r.get("to") or [], by_draw):
                if x not in out:
                    out.append(x)
        elif t not in out:
            out.append(t)
    return out


def insert_shunt_converg(rows, labels=None, only=None):
    """并行分支落成「分流(nodeIsShunt/14) + 合流(nodeToConverg/15)」两个结构节点。

    2026-11-27 平台实测（停车优惠申请表，人事科会签 ∥ 财务科会签）：
    只把两条出线挂在同一个节点上，平台不认并行——导入后流程图缺结构、
    节点属性里也没有 Shunt* 一组键。

    **只给显式声明的分叉节点插**（`graph.nodes[].parallel: true`）：
    09 流程里审批节点的两条出线绝大多数是「同意 / 返回修改」或「有协同科室 / 无协同科室」
    这类二选一，靠拓扑分不出来（707 实测：自动插会把二选一误判成并行，
    34 节点被撑到 38，还多出两个重合的合流）。所以默认关闭，标记了才插。

    标记后仍只把同时满足下面三条的分支算并行：

      1. 目标在当前节点**下方**（y 更大）——往回走的是退回边；
      2. 目标名/连线文字不含 返回/退回/终止/结束… 这类例外出口词；
      3. 至少两条这样的分支。

    其余出线（退回、终止）保持原样直连，不塞进分流。

    返回 (rows, [(分流row, 合流row或None, [分支draw…])], {(源名, 原目标名): 新目标名})；
    第三个表给连线文字用——分支改接到合流后，原来压在边上的执行动作文字要跟着搬。
    """
    labels = labels if labels is not None else {}
    only = set(only or ())
    if not rows or not only:
        return rows, [], {}
    by_draw = {r["draw"]: r for r in rows}

    def indeg(d):
        return sum(1 for r in rows if d in (r.get("to") or []))

    def reach(d):
        seen, stack = set(), list(by_draw[d].get("to") or [])
        while stack:
            x = stack.pop()
            if x in seen or x not in by_draw:
                continue
            seen.add(x)
            stack.extend(by_draw[x].get("to") or [])
        return seen

    nxt = max([r["draw"] for r in rows] or [0]) + 1
    made, moved = [], {}
    for f in [r for r in rows
              if len(r.get("to") or []) > 1 and r.get("key") != "judge"]:
        if f["name"] not in only and strip_no(f["name"]) not in only:
            continue
        par = []
        for t in f["to"]:
            d = by_draw.get(t)
            if not d:
                continue
            if d["y"] <= f["y"] + 1:                    # 同层或往上：退回 / 例外出口
                continue
            if _is_exit_branch(d["name"], labels.get((f["name"], d["name"]), "")):
                continue
            par.append(t)
        if len(par) < 2:
            continue

        s = {"draw": nxt, "name": "分流", "label": "分流", "key": "shunt",
             "kind": "shunt", "x": f["x"], "y": f["y"] + 60, "to": list(par)}
        nxt += 1
        # 原出线里非并行的（退回/终止）继续直连，分流只接管并行那几条
        rest = [t for t in f["to"] if t not in par]
        f["to"] = ([s["draw"]] if not rest else
                   [s["draw"]] + rest)   # 分流在前，「同意」默认走并行段
        rows.append(s)
        by_draw[s["draw"]] = s

        # 汇聚点 = 各并行分支共同可达、入线 >1、且在分流下方的第一个非判断节点
        common = None
        for b in par:
            rb = reach(b)
            common = rb if common is None else (common & rb)
        target = None
        for d in sorted(common or []):
            if (indeg(d) > 1 and by_draw[d].get("key") != "judge"
                    and by_draw[d]["y"] > s["y"]):
                target = by_draw[d]
                break

        m = None
        if target:
            m = {"draw": nxt, "name": "合流", "label": "合流", "key": "converg",
                 "kind": "converg", "x": target["x"], "y": target["y"] - 60,
                 "to": [target["draw"]], "_shunt_parent": s["draw"],
                 "_shunt_children": True, "_shunt_layer": 1}
            nxt += 1
            rows.append(m)
            by_draw[m["draw"]] = m
            for b in par:
                bd = by_draw[b]
                if target["draw"] in (bd.get("to") or []):
                    bd["to"] = [x for x in bd["to"] if x != target["draw"]] + [m["draw"]]
                    old = (bd["name"], target["name"])
                    if old in labels:            # 边上的执行动作文字跟着搬到合流
                        moved[old] = m["name"]
                bd["_shunt_first"] = bd["draw"]
                bd["_shunt_parent"] = s["draw"]
                bd["_shunt_children"] = True
                bd["_shunt_layer"] = 1
        made.append((s, m, par))
    return rows, made, moved


def _chain_rows(rows):
    """打印用的业务链路：把分流/合流折回普通连线，终端摘要里不出现结构节点。"""
    tmp = [dict(r) for r in rows]
    by = {r["draw"]: r for r in tmp}
    struct = {d for d, r in by.items() if r.get("key") in ("shunt", "converg")}
    for r in tmp:
        if r["draw"] in struct:
            continue
        new_to = []
        for t in r.get("to") or []:
            if t in struct:
                for x in by[t].get("to") or []:
                    if x not in new_to:
                        new_to.append(x)
            elif t not in new_to:
                new_to.append(t)
        r["to"] = new_to
    return [r for r in tmp if r["draw"] not in struct]


def build_steps(form, flow_id, step_base, con_base, part_base, web=None):
    """按动作类型建节点：默认 开始→申请人→每个 approve→结束；spec 有 flow 就按 flow 走。

    动作类型见 flow_types.TYPE_META：判断=菱形(nodeJudge/6)、通知=nodeNotice/3、审批=nodeApprove/2。
    没实测到 node 编码的类型（存档/生成处理签/空步骤）按规则先落成通知执行，并回一条告警。
    web 只用于取字段码（判断条件的左值），没有 Web 视图时判断条件会跳过并告警。
    """
    if form.get("graph"):
        g = form["graph"]
        flow_types.expand_conditions(g)      # judge.conditions/else → 边（写没写 edges 都能跑）
        nodes, edges = g.get("nodes") or [], g.get("edges") or []
        manual = nodes and all(isinstance(n, dict) and "x" in n and "y" in n for n in nodes)
        rows = (flow_types.layout_graph(nodes, edges) if not manual else _rows_manual(nodes, edges))
    elif form.get("flow"):
        items = flow_types.normalize_items(form["flow"])
        rows = flow_types.layout(items)
    else:
        names = (["开始", "申请人"]
                 + [f["label"] for f in form["fields"] if f["type"] == "approve"]
                 + ["结束"])
        rows = flow_types.layout(flow_types.normalize_items(names))
    # 显示名：graph.nodes 里的 label（不含层级序号）；name 仍作内部唯一键/连线用
    if form.get("graph"):
        _lab = {n["name"]: (n.get("label") or strip_no(n["name"]))
                for n in (form["graph"].get("nodes") or []) if isinstance(n, dict)}
        for r in rows:
            r["label"] = _lab.get(r["name"], r["name"])
    # 执行动作不生成步骤：折叠成连线文字（用户 2026-11-26 明确要求）
    rows, _fold_labels, _redirect = fold_action_nodes(rows)
    # 连线文字先备好：并行分支判定要用它识别「返回修改」这类例外出口
    labels, user_lab = {}, set()
    if form.get("graph"):
        for k, v in (form["graph"].get("edgeLabels") or {}).items():
            if isinstance(k, str) and "→" in k and isinstance(v, str):
                a, b = k.split("→", 1)
                if v.replace("\n", "").strip():
                    # 换行是给人看的排版，平台 note 里压成空格，不能直接删——删了会粘成一坨
                    labels[(a.strip(), b.strip())] = re.sub(r"\s*\n\s*", " ", v).strip()
                    user_lab.add((a.strip(), b.strip()))
    labels.update(_fold_labels)   # 执行动作折叠出来的连线文字
    # 并行分支：折叠完动作再插，避免折叠改变拓扑后对不上（2026-11-27 平台实测）。
    # 只认 spec 里显式标了 parallel 的分叉节点——二选一出口和并行长一个样，不能靠拓扑猜。
    _only = {n["name"] for n in ((form.get("graph") or {}).get("nodes") or [])
             if isinstance(n, dict) and n.get("parallel")}
    rows, _parallel, _moved = insert_shunt_converg(rows, labels, only=_only)
    for (a, old), new in _moved.items():
        lab = labels.pop((a, old), None)
        if lab and (a, new) not in labels:
            labels[(a, new)] = lab
    by_draw = {r["draw"]: r for r in rows}
    warns = []
    for _s, _m, _brs in _parallel:
        warns.append("并行分支「%s」已插分流(14)%s合流(15)"
                     % ("、".join(by_draw[b]["name"] for b in _brs if b in by_draw),
                        " + " if _m else "（未找到汇聚点，缺）"))
    for r in rows:
        meta = flow_types.meta_of(r["key"])
        if meta["node"] is None:
            warns.append("「%s」是 %s，平台编码未实测，按规则先写成通知执行" % (r["name"], meta["label"]))
        if len(r["name"]) > 50:
            warns.append("「%s」%d 字，连线上的目标节点名会截到 50 字（平台字段上限）"
                         % (r["name"], len(r["name"])))

    steps, cons, parts = [], [], []
    explicit = set()                 # 用户用 edgeLabels 显式写了文字的连线（条件不覆盖它）
    defaults = load_node_defaults()
    for i, r in enumerate(rows):
        meta = flow_types.meta_of(r["key"])
        node = meta["node"] if meta["node"] is not None else flow_types.TYPE_META["notice"]["node"]
        at = (meta["action_type"] if meta["action_type"] is not None
              else flow_types.TYPE_META["notice"]["action_type"])
        draw = r["draw"]
        prev = sorted({p["draw"] for p in rows if draw in (p.get("to") or [])})
        step = copy.deepcopy(defaults["step"])
        icon = {"nodeStart": "green", "nodeEnd": "orange",
                "nodeIsShunt": "green", "nodeToConverg": "green"}.get(node, "purple")
        step.update({
            "FlowID": flow_id, "StepID": step_base + i, "DrawID": draw,
            "stepName": flow_types.label_of_node(node), "actualName": r.get("label") or r["name"],
            "node": node, "nodeGroup": node, "ActionTypeID": at,
            "nodeIcon": "%s el-icon-success i ep:success-filled " % icon,
            "nodeStyle": "left:%dpx;top:%dpx;" % (int(r["x"]), int(r["y"])),
            "processTo": ",".join(str(t) for t in r["to"]),
            # processPrev 是「所有前驱」的绘图号，逗号分隔（平台导出件里汇聚点就是 3,5,6），
            # 只写第一条会让平台认为其它来线没接上。
            "processPrev": ",".join(str(p) for p in prev),
            # optStep：平台对所有非判断步骤都写 "1"（判断节点为空串）。
            # importantShunt：该步骤「同意执行」的默认目标 = 下一步的绘图号；
            # 多条出线按出线顺序逗号分隔（判断节点就是各分支），没有出线（结束）为空。
            # 这两个键缺了，平台导入后「同意执行」不会默认选中下一步，只会落到「结束」。
            "optStep": "" if node in ("nodeJudge", "nodeIsShunt", "nodeToConverg") else "1",
            # importantShunt 跳过分流/合流，写业务上的真正下一步（见 business_next）
            "importantShunt": ",".join(str(t) for t in business_next(r["to"], by_draw)),
            # 分流/合流与并行分支节点的 Shunt* 一组键（2026-11-27 平台实测样本）：
            #   分流   "" / shuntChildren=false / shuntLayer=0
            #   分支   ShuntFirstID=自身 / ShuntParentID=分流 / true / 1
            #   合流   ShuntParentID=分流 / true / 1
            "ShuntFirstID": str(r.get("_shunt_first") or ""),
            "ShuntParentID": str(r.get("_shunt_parent") or ""),
            "shuntChildren": bool(r.get("_shunt_children")),
            "shuntLayer": int(r.get("_shunt_layer") or 0),
            # 退回设置：除开始/申请人/结束/判断外，节点默认「允许退回」
            # （平台「退回设置」页的开关 = isCanReturn；退回类型=退回申请人、具体步骤=无限制，全按默认）
            "isCanReturn": node not in ("nodeStart", "nodeFirst", "nodeEnd", "nodeJudge"),
            "SortID": 0, "layer": 0, "trendMode": 0, "shuntNext": 0,
        })
        if node in ("nodeIsShunt", "nodeToConverg"):
            # 结构节点没有人员、没有表单：平台导出件里是另一套默认键，
            # 且没有 note、nodeIcon 不带普通节点那个尾随空格（逐键比对样本得出）
            step.update(SHUNT_CONVERG_OVERRIDES)
            step["nodeIcon"] = "%s el-icon-success i ep:success-filled" % icon
            step.pop("note", None)
        # 注意：importantShunt 不要 pop——平台导出件里每个步骤都有，值见上。
        # 开始/申请人/结束节点也要保留 note（真实导出件里是空串，键不能少）
        steps.append(step)
        part = copy.deepcopy(defaults["part"])
        part.update({"FlowID": flow_id, "StepID": step_base + i,
                     "DrawID": draw, "ID": part_base + i})
        parts.append(part)
        outs = r["to"]
        # 该判断是否已有分支带语义名（例如折叠成连线文字的执行动作步骤名）。
        # 只要有一条分支写的是「包含/不包含…」这类说明，其余分支就不能再写「是/否」，
        # 否则同一个判断上一支写全句、下一支写「是」，看起来自相矛盾（用户 2026-11-26 指出）。
        named_branch = any(labels.get((r["name"], by_draw[t]["name"]))
                           for t in outs if t in by_draw)
        for t in outs:
            dst = by_draw.get(t)
            if not dst:
                continue
            dmeta = flow_types.meta_of(dst["key"])
            # 判断出线的分支文字：有 edgeLabels 用它（note 限 200 字）；
            # 简单是非判断（两支且无任何语义分支名）写「是/否」，否则写目标分支名。
            # ConContentDesc 是「 文字 」带前后空格。
            lab = labels.get((r["name"], dst["name"]), "")
            dst_show = dst.get("label") or strip_no(dst["name"])
            if lab:
                note, desc = lab[:200], " %s " % lab
                if (r["name"], dst["name"]) in user_lab:   # 只有 edgeLabels 算「用户显式」
                    explicit.add((draw, t))
            elif node == "nodeJudge":
                if len(outs) == 2 and not named_branch:
                    first = outs.index(t) == 0
                    note = "是" if first else "否"
                    desc = (" %s " % dst_show) if first else (" 【取反】 %s " % dst_show)
                else:
                    branch = dst_show
                    note, desc = branch[:200], " %s " % branch
            else:
                note, desc = "", ""
            cons.append({
                "FlowID": flow_id, "ConID": con_base + len(cons),
                "DrawID": draw, "NextDrawID": t,
                "tabCode": node, "nextStepName": dmeta["label"],
                "nextActualName": fit_con_name(dst_show),
                "ConContent": "", "ConContentDesc": desc, "SortID": 0,
                "comparType": 0, "conValueType": 0, "flowVersion": "1.0",
                "inadvanceSelAllStepMode": 9, "inadvanceSelStepUserMode": 9,
                "isCanDel": True, "isNeedSaveForm": True,
                "MaybeSelUserStepIDs": "", "SQLStatement": "",
                "stepBtnName": "", "stepBtnShowMessage": "",
                # 判断连线 validateType=1（普通 0），否则步骤属性里的分支页签取不到数据
                "note": note, "validateType": 1 if node == "nodeJudge" else 0,
            })
    # 判断条件（StepCondition）：节点建好后回填连线文字与 ConContent。
    # 用户的 edgeLabels 优先，条件只补没写文字的那些出线。
    conditions = []
    if steps:
        code_map = field_code_map(web)
        if not code_map:
            has_cond = any(isinstance(n, dict) and (n.get("conditions") or n.get("else"))
                           for n in ((form.get("graph") or {}).get("nodes") or []))
            if has_cond:
                warns.append("没有 Web 视图（重复表缺表名？），判断条件的字段码取不到，"
                             "StepCondition 未生成")
        conditions, cond_text, cwarn = build_conditions(
            form, steps, code_map, flow_id, 50000, redirect=_redirect, rows=rows)
        warns.extend(cwarn)
        for c in cons:
            key = (c["DrawID"], c["NextDrawID"])
            hit = cond_text.get(key)
            if not hit:
                continue
            note, desc, con = hit
            if key in explicit:      # 用户 edgeLabels 的文字优先，但条件绑定必须补上
                if con:
                    c["ConContent"] = con
                continue
            c["note"], c["ConContentDesc"], c["ConContent"] = note[:200], desc, con
    return steps, cons, parts, rows, warns, conditions


def apply_table_names(forms, values, allow_missing=False):
    """重复表必须先有平台表名，否则 Web 视图里的 bindTable 是空的。

    allow_missing=True 时：没给表名不算错，返回 True（= 本次只出移动视图 + 流程图）。
    """
    tables = [f for form in forms for f in form["fields"] if f.get("type") == "table"]
    if not tables:
        return False
    if not values:
        if allow_missing:
            return True
        raise ValueError("表单含 %d 张重复表，需要 --table-name 给表名（多表写成 字段名=表名）"
                         % len(tables))
    provided = {}
    for v in values:
        if "=" in v:
            k, name = v.split("=", 1)
            provided[k.strip()] = name.strip()
        elif len(tables) == 1:
            provided[tables[0]["label"]] = v.strip()
        else:
            raise ValueError("有 %d 张重复表，--table-name 请写成 字段名=表名" % len(tables))
    missing = [t["label"] for t in tables if not provided.get(t["label"])]
    if missing:
        if allow_missing:
            return True
        raise ValueError("以下重复表还没给表名：%s" % "、".join(missing))
    for t in tables:
        t["tableName"] = provided[t["label"]]
    return False


def _rows_manual(nodes, edges):
    """graph 里每个节点都给了 x/y：直接按坐标建行。"""
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


def opinion_boxes(web):
    """意见框清单 [(标题, 意见编码)]。

    权威来源是视图顶层 `approves` 数组：`approveName` 是标题，`approveMode` 是意见编码；
    数组缺项时退回 approve 单元格的 `approveMode`/`approveName`。
    **意见编码是中文（默认等于标题），不是 `bindData` 的 KM00xx** —— 后者只是控件
    「绑定数据库字段」，表单设置里显示的是意见编码。
    """
    out, seen = [], set()
    for a in (web or {}).get("approves") or []:
        title = (a.get("approveName") or "").strip()
        code = (a.get("approveMode") or "").strip() or title
        if title and (title, code) not in seen:
            seen.add((title, code))
            out.append((title, code))
    for r in ((web or {}).get("rows") or {}).values():
        if not isinstance(r, dict):
            continue
        for cell in (r.get("cells") or {}).values():
            if (cell.get("SheetType") or "") != "approve":
                continue
            title = (cell.get("approveName") or cell.get("chkName") or "").strip()
            code = (cell.get("approveMode") or "").strip() or title
            if title and (title, code) not in seen:
                seen.add((title, code))
                out.append((title, code))
    return out


def _opinion_core(s):
    """去掉括号里的人名/说明，再去掉审批类后缀，用于宽松比对。"""
    s = re.sub(r"[（(【\[].*?[)）】\]]", "", s or "")
    s = re.sub(r"(审批|审核|意见|会签|备案|确认)$", "", s.strip())
    return s.strip()


def match_opinion(node_name, boxes):
    """节点名 ↔ 意见框标题：同名优先，再去括号/去后缀比核心词，最后做包含匹配。

    包含匹配要求短名至少占长名的 60%，否则「党委书记」会把「党委书记、院长」这种节点吃掉。
    """
    name = (node_name or "").strip()
    for title, _ in boxes:
        if title == name:
            return title
    core = _opinion_core(name)
    if not core:
        return None
    for title, _ in boxes:
        if _opinion_core(title) == core:
            return title
    hits = []
    for title, _ in boxes:
        tc = _opinion_core(title)
        if not tc:
            continue
        if core in tc or tc in core:
            short = min(len(core), len(tc))
            if short >= 0.6 * max(len(core), len(tc)):
                hits.append(title)
    return max(hits, key=len) if hits else None


def _strip_people(name):
    """去掉重名序号和人名括号：「院长书记审批（林兴栋、陈冠林）·2」→「院长书记审批」。"""
    n = re.sub(r"·\d+\s*$", "", (name or "").strip())
    return re.sub(r"[（(][^（()）]*[)）]\s*$", "", n).strip()


def form_set_ok(steps, web, form=None):
    """表单设置只在「意见框标题 == 流程步骤名称」时才生成。

    用户口径：标题描述与步骤名不一样时**不做表单设置**（绑也是绑错的，
    导入后还得逐个人工改），留给平台里手工配。
    返回 (是否一致, 缺的意见框, 多出来的意见框)。
    """
    def uniq(seq):
        out = []
        for x in seq:
            if x and x not in out:
                out.append(x)
        return out

    boxes = uniq(_strip_people(t) for t, _ in opinion_boxes(web))
    declared = declared_form_fields(form or {})
    # 同一个意见框可以被多个节点复用（院长书记审批在源流程里出现 18 次），
    # 所以按「去重后的名字集合」比，而不是按节点个数比
    names = uniq(_strip_people(s.get("actualName"))
                 for s in steps if s.get("node") in ("nodeApprove", "nodeNotice"))
    # 节点上显式写了 formField 的，不再要求表单里有同名意见框（可以是流程意见字段）
    missing = [n for n in names if n not in boxes and n not in declared]
    # 有显式声明时，「表单里多出来的意见框」不算冲突——可能就是这个声明在用它
    extra = [] if declared else [b for b in boxes if b not in names]
    return (not missing and not extra), missing, extra


def build_bookmarks(form, bind_of, flow_id):
    """公文业务模块的「表单字段 → 公文属性」映射（docUsedBookmarkList）。

    平台导出件（801 收文流程）里这张表把表单字段绑到公文模块的标准字段：
    `Title`(公文标题) / `DocType`(公文种类) / `Urgent`(紧急程度) / `Secret`(密级) /
    `AttNum`(附件份数) / `CcGov`(抄送机关) / `Keyword`(主题词) / `Adjunct`(附件说明) /
    `UserName`(经办人) / `CDate`(起草日期)。
    select 类字段平台还会再落一条 `_Value`（`UrgentID` / `SecretID`）存选项值。

    spec 写法：
        "bookmarks": [{"label": "公文标题", "formField": "Title"},
                      {"label": "紧急程度", "formField": "Urgent", "value": true}]
    """
    out = []
    for i, b in enumerate(form.get("bookmarks") or [], 1):
        lab = (b.get("label") or "").strip()
        field = (b.get("formField") or "").strip()
        bd = bind_of.get(lab)
        if not lab or not field or not bd:
            if lab and not bd:
                print("  ! 书签「%s」在表单里找不到同名字段，已跳过" % lab)
            continue
        out.append({
            "BookMark": lab, "DataMapField": bd, "DataMapOption": lab,
            "FlowID": flow_id, "FormField": field,
            "FormOption": b.get("formOption") or lab, "ID": len(out) + 1,
            "IsApprove": False, "IsMain": True, "IsMonitor": False,
            "ModeRelationID": 0,
        })
        if b.get("value"):      # 选项字段的「值」bookmark（平台照 KM00xx_Value 存选项 ID）
            out.append({
                "ApproveForName": "", "ApproveModCode": "",
                "BookMark": "%s(值)" % lab, "DataMapField": "%s_Value" % bd,
                "DataMapOption": "%s(值)" % lab, "Descript": "",
                "FlowID": flow_id, "FormField": "%sID" % field,
                "FormOption": "%s(值)" % lab, "ID": len(out) + 1,
                "IsApprove": False, "IsMain": True, "IsMonitor": False,
                "ModeCode": "", "ModeRelationID": 0, "ParentUID": "",
            })
    return out


def build_form_set(web, steps, flow_id, form=None, start_id=36000):
    """按 Web 视图生成「表单设置」（FlowFormSet）：每个节点的字段权限清单。

    平台实测规则：
    - **申请人节点**拿到全部「非审批」字段（含重复表列，`parentCode` = 该表 bindTable），
      单选/多选/下拉多一条 `_Value`，数字格式控件多一条 `_Label`；说明块（label 占号无单元格）也有一条；
    - **审批节点**拿到自己那个意见框：`fieldCode` 写**意见编码**（`approveMode`，中文，通常等于标题）、
      `fieldName` 写意见框标题、`isComment: true`。写 KM 编码会被当普通字段，
      表单设置里就显示成数据库字段名了（用户截图实测）。
    - 节点名带人名时按标题宽松匹配（`match_opinion`）；抄送节点与意见框同名时也绑上。
    """
    if not web:
        return []
    rows = web.get("rows") or {}
    fields, tcols, all_codes = [], [], []
    boxes = opinion_boxes(web)
    code_of = {title: code for title, code in boxes}
    for rk, r in rows.items():
        if rk == "len":
            continue
        for cell in (r.get("cells") or {}).values():
            bd, st = cell.get("bindData"), (cell.get("SheetType") or "")
            if bd:
                if bd[2:].isdigit():
                    all_codes.append(int(bd[2:]))
                if st != "approve":
                    fields.append((bd, cell.get("chkName") or "", st))
            if cell.get("bindTable") and cell.get("bindField"):
                tcols.append((cell["bindTable"], cell["bindField"], cell.get("chkName") or "", st))

    def variant(st):
        if st in ("radio", "checkbox", "select", "selectDep"):
            return ("_Value", "(值)")
        if st == "inputNumDisplay":
            return ("_Label", "(文本)")
        return None

    out, nid = [], [start_id]

    def add(draw, step_id, code, name, parent="", comment=False):
        out.append({
            "DrawID": draw, "FlowID": flow_id, "ID": nid[0], "RoleID": 0, "SortID": 1,
            "StepID": step_id, "fieldCode": code, "fieldName": name, "flowVersion": "1.0",
            "isBatchEdit": False, "isCanDel": True, "isComment": comment, "isEdit": True,
            "isEmptyFillBack": True, "isHidden": False, "isOpinionRequired": True,
            "isOpinionSummarized": True, "isReadonly": False, "isUse": True,
            "opinionSource": 0, "parentCode": parent, "roleCode": "", "roleName": "",
            "tabCode": "FixedFormSet",
        })
        nid[0] += 1

    applicant = next((s for s in steps if s.get("node") == "nodeFirst"), None)
    if applicant:
        dr, sid = applicant["DrawID"], applicant["StepID"]
        for code, name, st in fields:
            add(dr, sid, code, name)
            v = variant(st)
            if v:
                add(dr, sid, code + v[0], name + v[1])
        if all_codes:                      # 说明块：占号但 Web 上没有单元格
            labels = [f for f in (form or {}).get("fields", []) if f.get("type") == "label"]
            nxt = max(all_codes) + 1
            for i, lf in enumerate(labels):
                add(dr, sid, "KM%04d" % (nxt + i), lf.get("label") or "说明")
        for parent, code, name, st in tcols:
            add(dr, sid, code, name, parent)
            v = variant(st)
            if v:
                add(dr, sid, code + v[0], name + v[1], parent)

    declared = declared_form_fields(form or {})
    for s in steps:                        # 审批节点绑定自己的意见框（按标题识别）
        if s.get("node") not in ("nodeApprove", "nodeNotice"):
            continue
        fix = declared.get(s["actualName"])   # spec 显式指定优先（允许与步骤名不同）
        title = fix or match_opinion(s["actualName"], boxes)
        if not title:
            if s.get("node") == "nodeApprove":
                print("  ! 审批节点「%s」找不到对应意见框，未生成表单设置（审批走平台处理签）"
                      % s["actualName"])
            continue
        if (not fix and s.get("node") == "nodeNotice"
                and _opinion_core(title) != _opinion_core(s["actualName"])):
            # 抄送节点只在核心词能对上时才绑（避免把审批意见框误绑到抄送人身上）
            print("  ! 抄送节点「%s」与意见框「%s」只是宽松匹配，已跳过" % (s["actualName"], title))
            continue
        add(s["DrawID"], s["StepID"], code_of.get(title, title), title, comment=True)
    return out


def patch_skeleton(base, form, steps, cons, parts, ids, conditions=None):
    """在导出骨架上替换流程节点，并把各处 ID 改成新号段。"""
    d = copy.deepcopy(base)
    fe = d["FlowExportData"]
    flow_id, tpl_id = ids["flow_id"], ids["template_id"]

    fe["FlowID"] = flow_id
    fe["FlowStep"] = steps
    fe["FlowStepCon"] = cons
    fe["FlowStepPart"] = parts
    fe["StepCondition"] = conditions or []
    # 平台导出件里流程是「已验证」状态（isValidate=true），导入后不会拦着点「发布」；
    # 骨架默认 false，两处一起改。
    fe["FlowSet"]["isValidate"] = True
    fe["FlowSetVersion"]["isValidate"] = True
    fe["FlowSet"]["FlowID"] = flow_id
    fe["FlowSet"]["TemplateID"] = tpl_id
    # 平台导入弹窗里的「流程名称」读的是 FlowSet.name（不是 FlowSetVersion.name），两处都要改
    fe["FlowSet"]["name"] = form["base"]
    # 平台导出件在 FlowSet / FlowSetVersion 上都有一个 note 键
    fe["FlowSet"].setdefault("note", "")
    fe["FlowSetVersion"].setdefault("note", "")
    fe["FlowSetVersion"]["FlowID"] = str(flow_id)
    fe["FlowSetVersion"]["TemplateID"] = str(tpl_id)
    fe["FlowSetVersion"]["ID"] = str(ids["version_id"])
    fe["FlowSetVersion"]["name"] = form["base"]
    # 视图绑定：默认视图 / 通知/待办/其他 都指到「主视图」（平台导出件即如此）
    for k in ("DefaultFormViewID", "NotifyAuthFormViewID",
              "NotifyUserFormViewID", "OtherUserFormViewID"):
        if k in fe["FlowSetVersion"]:
            fe["FlowSetVersion"][k] = ids["main_view_id"]
    fe["FlowSetVersionPart"]["FlowID"] = flow_id
    fe["FlowSetVersionPart"]["ID"] = ids["version_id"]

    # 业务模块：平台导出件里是 modCode/modeCode（收文=docRec / 17、党组发文=doc / 24），
    # 不写就落到通用 'wm'，公文属性（文号/密级/主题词）在列表里都不显示
    mc = (form.get("modCode") or "").strip()
    if mc:
        md = (form.get("modeDes") or "wm").strip()
        for blk in (fe["FlowSet"], fe["FlowSetVersion"]):
            blk["modCode"] = mc
            blk["modeCode"] = mc
            blk["modeDes"] = md
    # 流程分类：平台导出件里表单流程=9、公文流程=17（801 收文实测），公文类要跟着换
    fk = form.get("flowKindID")
    if fk:
        fe["FlowSet"]["FlowKindID"] = fk
        fe["FlowSetVersion"]["FlowKindID"] = fk

    for i, p in enumerate(fe.get("FlowParticipant") or []):
        p["ID"] = ids["part_user"] + i
        p["FlowID"] = flow_id
    for i, op in enumerate(fe.get("FlowExtraOperation") or []):
        op["ID"] = ids["extra_op"] + i
        op["FlowID"] = flow_id
        op["userRange"] = ids["part_user"] + (0 if i == 0 else 1)
    return d


def main(argv):
    ap = argparse.ArgumentParser(description="按流程导出格式打包（Web+移动+流程图）")
    ap.add_argument("spec")
    ap.add_argument("--base-export", default=None,
                    help="结构骨架；不传则用内置 assets/flow_export_skeleton.json，"
                         "无需用户再上传平台导出件")
    ap.add_argument("--out", help="输出目录（默认 spec 的 output_dir）")
    ap.add_argument("--flow-id", type=int, default=625)
    ap.add_argument("--template-id", type=int, default=563)
    ap.add_argument("--table", help="主表名 mainTableName（默认沿用骨架并改尾号）")
    ap.add_argument("--table-name", action="append", default=None,
                    help="重复表名，可重复；单表直接给，多表写成 字段名=表名")
    ap.add_argument("--mobile-view", help="现成「(移动视图).txt」：原样嵌进包里，不重新生成表单")
    ap.add_argument("--web-view", help="现成「(Web视图).txt」：原样嵌进包里，不重新生成表单")
    ap.add_argument("--check", action="store_true", default=True, help="生成后自检（默认开）")
    a = ap.parse_args(argv)

    spec = json.loads(open(a.spec, "rb").read().decode("utf-8-sig"))
    form = spec["forms"][0]
    form.setdefault("require_all", spec.get("require_all", True))
    per_row = spec.get("fields_per_row", 2)
    out_dir = a.out or spec.get("output_dir") or os.getcwd()

    base_path = a.base_export or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "assets", "flow_export_skeleton.json")
    if not os.path.exists(base_path):
        raise FileNotFoundError("骨架文件不存在：%s" % base_path)
    pending = apply_table_names([form], a.table_name, allow_missing=True)
    build_forms.expand_range_columns(form)
    build_forms.expand_ranges(form, build_forms.table_ncols(form))
    base = json.loads(open(base_path, encoding="utf-8-sig").read())
    mby, wtpl = build_forms.load_tpls()
    # 两段式第二段：拿到表名只补 Web，移动视图沿用第一段已生成的（不重复 build）
    first_path = os.path.join(out_dir, "流程导出_%s_v1.0_移动视图.json" % form["base"])
    reused_tpl = None
    if not pending and os.path.exists(first_path):
        prev = json.loads(open(first_path, encoding="utf-8").read())
        reused_tpl = prev["TemplateData"]["mainView"]["template"]
        print("       · 复用第一段移动视图：%s" % os.path.basename(first_path))
    # 现成双视图：用户给了「(移动视图).txt + (Web视图).txt」就原样嵌入，一个控件都不重建
    ext_mobile = ext_web = None
    if a.mobile_view and a.web_view:
        mv_raw = json.loads(open(a.mobile_view, "rb").read().decode("utf-8-sig"))
        els = mv_raw["elements"] if isinstance(mv_raw, dict) else mv_raw
        script = mv_raw.get("script", "") if isinstance(mv_raw, dict) else ""
        ext_mobile = {"elements": els, "script": script}
        ext_web = json.loads(open(a.web_view, "rb").read().decode("utf-8-sig"))
        if pending:
            raise ValueError("给了现成视图就不要再用 --table-name（表单已经定稿，重复表名在视图里）")
        print("       · 嵌入现成视图：移动 %d 控件 / Web %d 行（原样，不重建）"
              % (len(els), len([k for k in ext_web.get("rows", {}) if k != "len"])))

    mobile = (None if (reused_tpl is not None or ext_mobile is not None)
              else build_forms.build_mobile(copy.deepcopy(form), mby, form["require_all"]))
    web_meta = {}
    web = ext_web if ext_web is not None else (
        None if pending else build_forms.build_web(copy.deepcopy(form), wtpl, per_row,
                                                   meta=web_meta))

    ids = {
        "flow_id": a.flow_id, "template_id": a.template_id,
        "version_id": a.template_id + 2914,
        "part_user": 74990, "extra_op": 7010,
        "main_view_id": a.template_id + 702,     # 「主视图」的 ViewID（视图绑定的默认目标）
    }
    steps, cons, parts, rows, warns, conditions = build_steps(
        form, ids["flow_id"], 64560, 85630, 64300, web=web)
    d = patch_skeleton(base, form, steps, cons, parts, ids, conditions)
    ok, missing, extra = form_set_ok(steps, web, form)
    if ok:
        d["FlowExportData"]["FlowFormSet"] = build_form_set(
            web, steps, ids["flow_id"], form, 36000)   # 表单设置：节点 × 字段权限
    else:
        d["FlowExportData"]["FlowFormSet"] = []
        print("       · 意见框标题与步骤名不一致 → 不生成表单设置（留空）")
        if missing:
            print("         缺意见框的步骤 %d 个：%s" % (len(missing), "、".join(missing[:5])))
        if extra:
            print("         多出的意见框 %d 个：%s" % (len(extra), "、".join(extra[:5])))

    # TemplateData：装 Web（sheet）+ 移动（template）
    T = d["TemplateData"]
    old_main = T.get("mainTableName") or ""
    if a.table:
        T["mainTableName"] = a.table
    else:
        # 主表名按尾部号段 +1 推一个新号（如 ..._0000000564 → ..._0000000565）
        m = re.search(r"(\d+)$", old_main or "")
        if m:
            g = m.group(1)
            T["mainTableName"] = old_main[:m.start()] + str(int(g) + 1).zfill(len(g))
        else:
            T["mainTableName"] = old_main
    T["templateData"]["name"] = form["base"]
    T["templateData"]["TemplateID"] = a.template_id
    T["templateData"]["CDate"] = 1795332994980
    # 公文表单（配了 modCode）才是「流程生成的公文模板」；普通表单平台导出件里是 false
    T["templateData"]["isFromFlow"] = bool((form.get("modCode") or "").strip())
    # 公文业务模块的书签映射：表单字段 -> 公文属性（Title/DocType/Urgent…）
    T["docUsedBookmarkList"] = build_bookmarks(
        form, web_meta.get("bind") or {}, ids["flow_id"])
    if T["docUsedBookmarkList"]:
        print("       · 书签映射 %d 条（公文业务模块）" % len(T["docUsedBookmarkList"]))
    # 视图清单里每个视图都各自存了一份 sheet/template，必须一起替换，
    # 否则会把骨架表单（旧流程）的字段和重复表名带进新包。
    if ext_web is not None:
        sheet_str = json.dumps(ext_web, ensure_ascii=False, separators=(",", ":"))
    else:
        sheet_str = "" if pending else json.dumps(web, ensure_ascii=False, separators=(",", ":"))
    if ext_mobile is not None:                 # 原样，不做 normalize_element
        tpl_str = json.dumps(ext_mobile, ensure_ascii=False, separators=(",", ":"))
    elif reused_tpl is not None:
        tpl_str = reused_tpl
    else:
        tpl_str = json.dumps({"elements": [normalize_element(e) for e in mobile], "script": ""},
                             ensure_ascii=False, separators=(",", ":"))
    for v in T["templateViewList"]:
        v["TemplateID"] = str(a.template_id)
        is_main = str(v.get("isMain")).lower() == "true"   # 骨架里是布尔，不是字符串
        v["ViewID"] = str(a.template_id + 700 + (1 if is_main else 2))
        v["sheet"] = sheet_str
        v["template"] = tpl_str
        if is_main:
            v["viewName"] = "数据定义"
    mv = T["mainView"]
    mv["TemplateID"] = a.template_id
    mv["ViewID"] = a.template_id + 701
    mv["template"] = tpl_str
    mv["sheet"] = sheet_str

    os.makedirs(out_dir, exist_ok=True)
    suffix = "_移动视图" if pending else ""
    path = os.path.join(out_dir, "流程导出_%s_v1.0%s.json" % (form["base"], suffix))
    # 与平台导出件一致：紧凑单行、不转义中文
    open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")))

    biz_rows = _chain_rows(rows)          # 打印链路：不出现分流/合流
    warns.extend(flow_types.judge_warnings(biz_rows))
    seen_xy = {}
    for r in rows:
        key = (round(r["x"]), round(r["y"]))
        seen_xy.setdefault(key, []).append(r["name"])
    for (x, y), names in seen_xy.items():
        if len(names) > 1:
            warns.append("节点坐标重复 (%d,%d)：%s —— 导入后画布上会叠在一起" % (x, y, "、".join(names)))
    chain = flow_types.chain_text(biz_rows)
    print("%-24s 节点=%d  %s" % (form["base"], len(rows), chain))
    for w in warns:
        print("       ! %s" % w)
    print("     FlowID=%d TemplateID=%d 主表=%s"
          % (ids["flow_id"], ids["template_id"], T["mainTableName"]))
    if conditions:
        print("     判断条件 %d 条（StepCondition）：%s"
              % (len(conditions), "、".join(
                  "Draw%s[j%s]%s" % (c["DrawID"], c["jIdentity"].strip("[]"), c["note"])
                  for c in conditions)))
    covered = {c["DrawID"] for c in conditions}
    uncovered = [s["actualName"] for s in steps
                 if s.get("node") == "nodeJudge" and s["DrawID"] not in covered]
    if uncovered:
        print("     ! 这些判断没有条件规则（导入后要在平台手工配）：%s"
              % "、".join(uncovered))
    print("     -> %s" % path)

    if pending:
        print("     ! 重复表未绑定：本次 JSON 只含【移动视图 + 流程图】，Web 视图留空")
        for t in [f for f in form["fields"] if f.get("type") == "table"]:
            print("       - %s（%d 列）" % (t["label"], len(t.get("columns") or [])))
        print('     拿到表名后重跑：--table-name "字段名=wx_..._0001"')

    if a.check and ext_web is not None:
        # 现成视图模式：不按本技能的键名规范挑刺（平台版本不同，键本来就不一样），
        # 只校验「嵌进去的和给的一模一样」——一个控件都不许被改写。
        back = json.load(open(path, encoding="utf-8"))
        T2 = back["TemplateData"]
        sheet_back = json.loads(T2["mainView"]["sheet"])
        tpl_back = json.loads(T2["mainView"]["template"])
        same_web = sheet_back == ext_web
        same_mob = tpl_back.get("elements") == ext_mobile["elements"]
        per_view = all(
            json.loads(v["sheet"]) == ext_web
            and json.loads(v["template"]).get("elements") == ext_mobile["elements"]
            for v in T2["templateViewList"])
        nsteps = len(back["FlowExportData"]["FlowStep"])
        nfs = len(back["FlowExportData"].get("FlowFormSet") or [])
        print("     自检：Web %d 行 / 移动 %d 控件 / 流程图 %d 节点 / 表单设置 %s"
              % (len([k for k in sheet_back["rows"] if k != "len"]),
                 len(tpl_back.get("elements") or []), nsteps,
                 ("%d 条" % nfs) if nfs else "未生成"))
        print("     视图原样嵌入：Web %s / 移动 %s / 各 viewList 一致 %s"
              % ("一致" if same_web else "不一致", "一致" if same_mob else "不一致",
                 "是" if per_view else "否"))
        if not (same_web and same_mob and per_view):
            return 1
        return 3 if pending else 0

    if a.check:
        import validate_form
        back = json.load(open(path, encoding="utf-8"))
        els = json.loads(back["TemplateData"]["mainView"]["template"])["elements"]
        mtpl = json.loads(open(build_forms.MOBILE_TPL, "rb").read().decode("utf-8-sig"))
        hard = [x for x in validate_form.check_mobile(
            [strip_element(e) for e in els], mtpl) if not x.startswith("提示:")]
        nsteps = len(back["FlowExportData"]["FlowStep"])
        ncond = len(back["FlowExportData"].get("StepCondition") or [])

        # 硬规则（用户 2026-11-27 二次纠正）：09 截图生成的流程一律以「开始 → 申请人」开头，
        # 但「申请人」是补出来的独立节点（nodeFirst），截图第 2 行（如「2 申请人声明」）原样保留，
        # 不得把它改名成「申请人」、也不得吞掉。这里只校验开始节点的唯一后继是这个补出来的申请人。
        st_by_id = {s["DrawID"]: s for s in back["FlowExportData"]["FlowStep"]}
        starts = [s for s in st_by_id.values() if s.get("node") == "nodeStart"]
        if starts:
            nxt = (starts[0].get("processTo") or "").split(",")[0].strip()
            nx = st_by_id.get(int(nxt)) if nxt.isdigit() else None
            if not nx or nx.get("node") != "nodeFirst" or nx.get("actualName") != "申请人":
                hard.append("流程开头必须是「开始 → 申请人」（当前「开始 → %s」）"
                            % (nx.get("actualName") if nx else "空"))

        if pending:
            print("     自检：移动 %d 控件 / 流程图 %d 节点 / 判断条件 %d 条  %s"
                  % (len(els), nsteps, ncond, "OK" if not hard else "FAIL"))
        else:
            sheet = json.loads(back["TemplateData"]["mainView"]["sheet"])
            hard += [x for x in validate_form.check_web(sheet, wtpl) if not x.startswith("提示:")]
            print("     自检：Web %d 行 / 移动 %d 控件 / 流程图 %d 节点 / 判断条件 %d 条  %s"
                  % (len([k for k in sheet["rows"] if k != "len"]), len(els), nsteps, ncond,
                     "OK" if not hard else "FAIL"))
        for x in hard:
            print("       - %s" % x)
        if hard:
            return 1
        return 3 if pending else 0
    return 3 if pending else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, FileNotFoundError, KeyError) as e:
        print("FAIL %s" % e)
        sys.exit(1)
