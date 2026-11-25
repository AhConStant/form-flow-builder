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


def fit_con_name(name, limit=50):
    """连线的目标节点名受平台 wmFlowStepCon.NextActualName varchar(50) 限制。

    节点名可以很长（actualName 是 varchar(500)），但连线这一列不能超；
    超长时保留「抄送人（护士长·16人）」这类前缀，把括号里的人名列表去掉。
    """
    if len(name) <= limit:
        return name
    return name.split("：")[0] + "）" if "：" in name else name[:limit]


def build_steps(form, flow_id, step_base, con_base, part_base):
    """按动作类型建节点：默认 开始→申请人→每个 approve→结束；spec 有 flow 就按 flow 走。

    动作类型见 flow_types.TYPE_META：判断=菱形(nodeJudge/6)、通知=nodeNotice/3、审批=nodeApprove/2。
    没实测到 node 编码的类型（存档/生成处理签/空步骤）按规则先落成通知执行，并回一条告警。
    """
    if form.get("graph"):
        g = form["graph"]
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
    by_draw = {r["draw"]: r for r in rows}
    # 连线文字：graph.edgeLabels 的键是「源节点名 → 目标节点名」，值是要显示的字（可能带换行）。
    # 平台把它落在 FlowStepCon 的 note（varchar(200)）与 ConContentDesc（text）上。
    labels = {}
    if form.get("graph"):
        for k, v in (form["graph"].get("edgeLabels") or {}).items():
            if isinstance(k, str) and "→" in k and isinstance(v, str):
                a, b = k.split("→", 1)
                if v.replace("\n", "").strip():
                    labels[(a.strip(), b.strip())] = v.replace("\n", "").strip()
    warns = []
    for r in rows:
        meta = flow_types.meta_of(r["key"])
        if meta["node"] is None:
            warns.append("「%s」是 %s，平台编码未实测，按规则先写成通知执行" % (r["name"], meta["label"]))
        if len(r["name"]) > 50:
            warns.append("「%s」%d 字，连线上的目标节点名会截到 50 字（平台字段上限）"
                         % (r["name"], len(r["name"])))

    steps, cons, parts = [], [], []
    defaults = load_node_defaults()
    for i, r in enumerate(rows):
        meta = flow_types.meta_of(r["key"])
        node = meta["node"] if meta["node"] is not None else flow_types.TYPE_META["notice"]["node"]
        at = (meta["action_type"] if meta["action_type"] is not None
              else flow_types.TYPE_META["notice"]["action_type"])
        draw = r["draw"]
        prev = [p["draw"] for p in rows if draw in (p.get("to") or [])]
        step = copy.deepcopy(defaults["step"])
        icon = {"nodeStart": "green", "nodeEnd": "orange"}.get(node, "purple")
        step.update({
            "FlowID": flow_id, "StepID": step_base + i, "DrawID": draw,
            "stepName": flow_types.label_of_node(node), "actualName": r["name"],
            "node": node, "nodeGroup": node, "ActionTypeID": at,
            "nodeIcon": "%s el-icon-success i ep:success-filled " % icon,
            "nodeStyle": "left:%dpx;top:%dpx;" % (int(r["x"]), int(r["y"])),
            "processTo": ",".join(str(t) for t in r["to"]),
            "processPrev": str(prev[0]) if prev else "",
            # optStep：平台对所有非判断步骤都写 "1"（判断节点为空串）。
            # importantShunt：该步骤「同意执行」的默认目标 = 下一步的绘图号；
            # 多条出线按出线顺序逗号分隔（判断节点就是各分支），没有出线（结束）为空。
            # 这两个键缺了，平台导入后「同意执行」不会默认选中下一步，只会落到「结束」。
            "optStep": "" if node == "nodeJudge" else "1",
            "importantShunt": ",".join(str(t) for t in r["to"]),
            "SortID": 0, "layer": 0, "trendMode": 0, "shuntNext": 0,
        })
        # 注意：importantShunt 不要 pop——平台导出件里每个步骤都有，值见上。
        # 开始/申请人/结束节点也要保留 note（真实导出件里是空串，键不能少）
        steps.append(step)
        part = copy.deepcopy(defaults["part"])
        part.update({"FlowID": flow_id, "StepID": step_base + i,
                     "DrawID": draw, "ID": part_base + i})
        parts.append(part)
        outs = r["to"]
        for t in outs:
            dst = by_draw.get(t)
            if not dst:
                continue
            dmeta = flow_types.meta_of(dst["key"])
            # 判断出线的分支文字：有 edgeLabels 用它（note 限 200 字）；
            # 没有就两支写「是/否」、多支写目标节点名。ConContentDesc 是「 文字 」带前后空格。
            lab = labels.get((r["name"], dst["name"]), "")
            if lab:
                note, desc = lab[:200], " %s " % lab
            elif node == "nodeJudge":
                if len(outs) == 2:
                    first = outs.index(t) == 0
                    note = "是" if first else "否"
                    desc = (" %s " % dst["name"]) if first else (" 【取反】 %s " % dst["name"])
                else:
                    note, desc = dst["name"][:200], " %s " % dst["name"]
            else:
                note, desc = "", ""
            cons.append({
                "FlowID": flow_id, "ConID": con_base + len(cons),
                "DrawID": draw, "NextDrawID": t,
                "tabCode": node, "nextStepName": dmeta["label"],
                "nextActualName": fit_con_name(dst["name"]),
                "ConContent": "", "ConContentDesc": desc, "SortID": 0,
                "comparType": 0, "conValueType": 0, "flowVersion": "1.0",
                "inadvanceSelAllStepMode": 9, "inadvanceSelStepUserMode": 9,
                "isCanDel": True, "isNeedSaveForm": True,
                "MaybeSelUserStepIDs": "", "SQLStatement": "",
                "stepBtnName": "", "stepBtnShowMessage": "",
                # 判断连线 validateType=1（普通 0），否则步骤属性里的分支页签取不到数据
                "note": note, "validateType": 1 if node == "nodeJudge" else 0,
            })
    return steps, cons, parts, rows, warns


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


def form_set_ok(steps, web):
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
    # 同一个意见框可以被多个节点复用（院长书记审批在源流程里出现 18 次），
    # 所以按「去重后的名字集合」比，而不是按节点个数比
    names = uniq(_strip_people(s.get("actualName"))
                 for s in steps if s.get("node") in ("nodeApprove", "nodeNotice"))
    missing = [n for n in names if n not in boxes]
    extra = [b for b in boxes if b not in names]
    return (not missing and not extra), missing, extra


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

    for s in steps:                        # 审批节点绑定自己的意见框（按标题识别）
        if s.get("node") not in ("nodeApprove", "nodeNotice"):
            continue
        title = match_opinion(s["actualName"], boxes)
        if not title:
            if s.get("node") == "nodeApprove":
                print("  ! 审批节点「%s」找不到对应意见框，未生成表单设置（审批走平台处理签）"
                      % s["actualName"])
            continue
        if s.get("node") == "nodeNotice" and _opinion_core(title) != _opinion_core(s["actualName"]):
            # 抄送节点只在核心词能对上时才绑（避免把审批意见框误绑到抄送人身上）
            print("  ! 抄送节点「%s」与意见框「%s」只是宽松匹配，已跳过" % (s["actualName"], title))
            continue
        add(s["DrawID"], s["StepID"], code_of[title], title, comment=True)
    return out


def patch_skeleton(base, form, steps, cons, parts, ids):
    """在导出骨架上替换流程节点，并把各处 ID 改成新号段。"""
    d = copy.deepcopy(base)
    fe = d["FlowExportData"]
    flow_id, tpl_id = ids["flow_id"], ids["template_id"]

    fe["FlowID"] = flow_id
    fe["FlowStep"] = steps
    fe["FlowStepCon"] = cons
    fe["FlowStepPart"] = parts
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
    web = ext_web if ext_web is not None else (
        None if pending else build_forms.build_web(copy.deepcopy(form), wtpl, per_row))

    ids = {
        "flow_id": a.flow_id, "template_id": a.template_id,
        "version_id": a.template_id + 2914,
        "part_user": 74990, "extra_op": 7010,
        "main_view_id": a.template_id + 702,     # 「主视图」的 ViewID（视图绑定的默认目标）
    }
    steps, cons, parts, rows, warns = build_steps(
        form, ids["flow_id"], 64560, 85630, 64300)
    d = patch_skeleton(base, form, steps, cons, parts, ids)
    ok, missing, extra = form_set_ok(steps, web)
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

    warns.extend(flow_types.judge_warnings(rows))
    seen_xy = {}
    for r in rows:
        key = (round(r["x"]), round(r["y"]))
        seen_xy.setdefault(key, []).append(r["name"])
    for (x, y), names in seen_xy.items():
        if len(names) > 1:
            warns.append("节点坐标重复 (%d,%d)：%s —— 导入后画布上会叠在一起" % (x, y, "、".join(names)))
    chain = flow_types.chain_text(rows)
    print("%-24s 节点=%d  %s" % (form["base"], len(rows), chain))
    for w in warns:
        print("       ! %s" % w)
    print("     FlowID=%d TemplateID=%d 主表=%s"
          % (ids["flow_id"], ids["template_id"], T["mainTableName"]))
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
        if pending:
            print("     自检：移动 %d 控件 / 流程图 %d 节点（Web 待补）  %s"
                  % (len(els), nsteps, "OK" if not hard else "FAIL"))
        else:
            sheet = json.loads(back["TemplateData"]["mainView"]["sheet"])
            hard += [x for x in validate_form.check_web(sheet, wtpl) if not x.startswith("提示:")]
            print("     自检：Web %d 行 / 移动 %d 控件 / 流程图 %d 节点  %s"
                  % (len([k for k in sheet["rows"] if k != "len"]), len(els), nsteps,
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
