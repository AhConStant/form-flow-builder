# -*- coding: utf-8 -*-
"""
表单流程批量生成器：一份 spec.json -> 每个流程的「移动视图 + Web 视图」（+ 配置清单）

用法:
    python build_forms.py spec.json
    python build_forms.py spec.json --out 流程表单 --only 01,05 --per-row 3
    python build_forms.py spec.json --mobile-only          # 有重复表：先只出移动端
    python build_forms.py spec.json --table-name wx_xxx_Form_0000000200_0001 --web-only
    python build_forms.py spec.json --no-validate

重复表两段式（硬规则）:
    1. spec 里出现 type=table 且未填 tableName 时，只生成移动视图 + 配置清单，
       写出 (待绑定重复表).md，退出码 3，不生成 Web 视图。
    2. 用户给出平台里的重复表名（bindTable）后，用 --table-name 回填，加 --web-only
       再跑一次：**只产出 (Web视图).txt 这一份 sheet**（单独导入同一个表单），
       不重打移动端、不覆盖第一段产物，并自动校验。
    3. spec 里没有 table 字段时，一条命令同时产出移动端与 Web 端。
    4. 单独交付的 (Web视图).txt **不带顶层 events 键**（那是流程导出包内嵌 sheet 的形态），
       生成器写盘时自动去掉；嵌进导出包的那份仍保留。

spec.json 结构见 assets/forms_spec.example.json 与 references/spec-format.md
输出: {output_dir}/{base}(移动视图).txt / (Web视图).txt / (配置清单).md
编码: UTF-8 with BOM，紧凑单行（平台导入硬要求）
"""
import argparse
import copy
import json
import math
import os
import re
import sys
import uuid

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(SKILL_ROOT, "assets")
MOBILE_TPL = os.path.join(TPL_DIR, "mobile_view_template.txt")
WEB_TPL = os.path.join(TPL_DIR, "web_view_template.txt")

# 移动控件白名单（= 模板里出现的 15 类）
MOBILE_TYPES = ["input", "label", "textarea", "radio", "checkbox", "singleCheckbox", "select",
                "datepicker", "inputNum", "inputNumDisplay", "sn", "table", "approve",
                "attachment", "selectDep"]

# 可带计算式 autoCalc 的类型（平台实测只有这 3 类有该属性）
FORMULA_TYPES = {"input", "inputNum", "inputNumDisplay"}

# 公式里 {字段名} 占位符：统一转成平台的 [tableKey\字段名] 写法
REF_RE = re.compile(r"\{([^{}]+)\}")

# 可以作为重复表列的类型（table/approve/attachment 不能做列）
COLUMN_TYPES = ["input", "textarea", "radio", "checkbox", "singleCheckbox", "select",
                "datepicker", "inputNum", "selectDep"]

# 可以放进自定义行（row）的类型：窄控件 + 静态文字
ROW_TYPES = {"input", "inputNum", "inputNumDisplay", "sn", "select", "selectDep", "datepicker",
             "singleCheckbox", "static"}

# 「XX起止时间」→ 主表字段拆成 XX开始时间 + 至 + XX结束时间；重复表列拆成相邻两列
RANGE_RE = re.compile(r"^(?P<pre>.*?)起止(?P<suf>.*)$")

# 字段名 -> 默认值绑定（平台实测：移动用 defVal，Web 用 defaultVal）
TOKEN_MOBILE = {"user": "currentUserName", "dept": "departmentName",
                "date": "currentDateTime", "login": "loginID", "phone": "mobile"}
TOKEN_WEB = {"user": "currentUserName", "dept": "departmentName",
             "date": "currentDate", "login": "loginID", "phone": "mobile"}


def default_token(label):
    """按字段名判断默认值类型：user / dept / date / login / phone / None。"""
    lab = str(label).strip()
    if any(x in lab for x in ("电话", "手机", "联系方式")):
        return "phone"
    if lab in ("姓名", "申请人", "填报人", "拟稿人") or lab.endswith("姓名"):
        return "user"
    if lab in ("工号", "登录账号", "账号"):
        return "login"
    if ("科室" in lab or "部门" in lab or "专科" in lab) and not any(
            x in lab for x in ("负责人", "主任", "意见", "审批", "电话", "联系",
                               "审核", "领导", "批示", "签发", "会签", "核稿",
                               "批准", "确认", "签字")):
        return "dept"
    if any(k in lab for k in ("申请日期", "申请时间", "填报日期", "填发时间", "填报时间")):
        return "date"
    return None

# Web 映射：type -> (buttonType, SheetType)
WEB_BTN = {
    "input": ("input", "input"),
    "inputNum": ("inputnum", "inputNum"),
    "inputNumDisplay": ("inputnumdisplay", "inputNumDisplay"),
    "sn": ("input", "input"),
    "selectDep": ("depselect", "selectDep"),
    "datepicker": ("time", "datepicker"),
    "select": ("select", "select"),
    "textarea": ("textarea", "textarea"),
    "radio": ("radio", "radio"),
    "checkbox": ("checkboxgroup", "checkbox"),
    "singleCheckbox": ("checkbox", "singleCheckbox"),
    "approve": ("approve", "approve"),
    "attachment": ("upload", "attachment"),
}
# 独占整行的宽字段（static/label = 静态文字，仅 Web 承载）
WIDE = {"textarea", "approve", "attachment", "radio", "checkbox", "table", "static", "label"}

S_TITLE, S_LBL1, S_LBLN, S_CTRL1, S_CTRLN = 13, 5, 7, 6, 8
S_TABLE_CELL, S_TABLE_HDR, S_STATIC = 14, 15, 16
# 重复表数据格：平台实测用第 18 个样式（带框 + #f2f2f2 灰底），追加在模板 17 个样式之后
S_TABLE_DATA = 17
DATA_STYLE = {"font": {"size": 12},
              "border": {"bottom": ["thin", "#000"], "right": ["thin", "#000"],
                         "top": ["thin", "#000"], "left": ["thin", "#000"]},
              "bgcolor": "#f2f2f2"}
S_PLAIN = 2   # 无边框样式：Word 正文中的「说明」不在表格框里，Web 端也不加框
FILLER, FILLER_TITLE = {"style": 2}, {"style": 13}

TABLE_META_KEYS = ["tableRange", "bindTable", "showNumber", "isPagination",
                   "pageSize", "addRowOption", "rowLimit", "sortOption"]

EXIT_OK, EXIT_ERROR, EXIT_WAIT_TABLE = 0, 1, 3


def load_tpls():
    m = json.loads(open(MOBILE_TPL, "rb").read().decode("utf-8-sig"))
    w = json.loads(open(WEB_TPL, "rb").read().decode("utf-8-sig"))
    return {e["type"]: e for e in m}, w


def field_flags(f):
    """spec 里写了 bind 就以 bind 为准（user/dept/date/login/phone），否则按字段名猜。

    `bind: "none"` = 明确关闭默认值绑定：不写 defVal/defaultVal，也不让
    「默认：申请人部门」覆盖 spec 里的 placeholder（源 Word 灰字提示要原样落位）。
    """
    # 审批/附件/流水号/静态文字/重复表一律不绑默认值：
    # 审批框一旦带 defVal/defaultVal，前端渲染直接打不开（实测 bug）。
    if f.get("type") in ("approve", "attachment", "sn", "static", "label", "table"):
        return dict(token=None, user_default=False,
                    dept_default=False, date_default=False)
    bind = (f.get("bind") or "").strip()
    if bind == "none":
        return dict(token=None, user_default=False,
                    dept_default=False, date_default=False)
    tok = bind if bind in TOKEN_MOBILE else default_token(f["label"])
    return dict(token=tok, user_default=tok == "user",
                dept_default=tok == "dept", date_default=tok == "date")


def put_prop(pr, key, value):
    """按字母序写入一个属性键。

    平台回写时会把 properties 全部重排成字母序，生成时就按字母序放，
    导出/回写两边的键序才一致（校验器也按字母序判定）。
    """
    items = {k: v for k, v in pr.items() if k != key}
    items[key] = value
    pr.clear()
    for k in sorted(items):
        pr[k] = items[k]


def to_formula(expr, prefix=""):
    """把 spec 里的 {字段名} 写法转成平台的公式引用。

    `{天数}`              -> `[tableKey\\天数]`
    `{是否市内(值)}`       -> `[tableKey\\是否市内(值)]`（带 (值) 取选项 value）
    重复表列里 prefix=表名  -> `[tableKey\\表名\\列名]`
    已经是 `[tableKey\\...]` 原文的表达式原样保留（不猜、不改写）。
    """
    text = str(expr or "")
    if "[tableKey" in text:
        return text
    return REF_RE.sub(lambda m: "[tableKey\\%s%s]" % (prefix, m.group(1).strip()), text)


def apply_formula(pr, f, where, prefix=""):
    """把 spec 的 calc / hideWhen 落到 autoCalc / hideFormula 上。

    - `calc`     -> `autoCalc`（仅 input/inputNum/inputNumDisplay，平台实测只这 3 类有）
    - `hideWhen` -> `hideFormula` + 初始 `isHidden=true`（控件先藏起来，条件满足才显示）
    """
    calc = (f.get("calc") or "").strip()
    hide = (f.get("hideWhen") or "").strip()
    if calc:
        if f["type"] not in FORMULA_TYPES:
            raise ValueError("%s「%s」不支持 calc：带计算式的类型只有 %s"
                             % (where, f["label"], "/".join(sorted(FORMULA_TYPES))))
        put_prop(pr, "autoCalc", to_formula(calc, prefix))
    if hide:
        put_prop(pr, "hideFormula", to_formula(hide, prefix))
        pr["isHidden"] = True
        pr["isClearHide"] = False


def col_letter(i):
    """0 -> A, 25 -> Z, 26 -> AA"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


RANGE_FIXED = 2          # 开始标签 + 「XX起止日期」标题，结束控件不带标签


def row_field_span(f):
    """字段在自定义行里占几列：标签（可 hideLabel）+ 控件 colspan。"""
    span = int(f.get("colspan", 1))
    if f["type"] == "static":
        return span
    return span + (0 if f.get("hideLabel") else 1)


def range_row_spans(budget):
    """起止一组占 budget 列怎么排（用户标准：不用「至」字）。

        XX开始日期 | 开始控件 | XX起止日期（原字段名，居中标题） | 结束控件（无标签）

    两个日期控件**必须等宽**（宽度不等会让填表人以为两个框填不同粒度）；
    结束控件不显示标签，原字段名放在中间当这一组的标题。列数：
    1 + k + t + k = budget，t = budget - 1 - 2k，取能让 t ∈ {1,2} 的最大 k
    （t=2 时标题更宽，长字段名不折行）。6 列 → 2/1/2、7 → 2/2/2、8 → 3/1/3、9 → 3/2/3。
    """
    k = max(1, (budget - 1) // 2)
    t = budget - 1 - 2 * k
    if t < 1:
        k -= 1
        t = budget - 1 - 2 * k
    return k, max(1, t)


def expand_ranges(form, ncols):
    """时间范围拆成两个日期控件：XX开始日期 + 结束控件，中间用原字段名当标题。

    spec 里写 {"label": "申请担任住院总起止日期", "type": "datepicker"} 即可自动展开；
    也支持显式 {"label": "…", "type": "datepicker", "range": true}。
    Web 版式见 range_row_spans()：**不放「至」，结束控件不带标签**，原字段名（XX起止日期）
    作为这一组的居中标题；两个日期控件等宽。
    """
    if form.get("_ranges_done") or ncols < 6:
        return
    form["_ranges_done"] = True
    fields = form["fields"]
    out, k = [], 0
    for f in fields:
        lab = f.get("label") or ""
        auto = f.get("type") == "datepicker" and "起止" in lab
        m = RANGE_RE.match(lab) if (f.get("range") or auto) else None
        if not m:
            out.append(f)
            continue
        pre, suf = m.group("pre"), m.group("suf")
        # 显式 row：起止和同 row 的其他字段排在同一行（如科室），budget 扣掉它们占的列
        key = f.get("row") or "rng%d" % k
        k += 1
        others = [x for x in fields if x is not f and x.get("row") == key] if f.get("row") else []
        budget = ncols - sum(row_field_span(x) for x in others)
        if budget < RANGE_FIXED + 2:
            raise ValueError("[%s] 起止行「%s」只剩 %d 列（同行的其他字段占了 %d 列，至少需 4 列）"
                             % (form["base"], f["label"], budget, ncols - budget))
        span, title_span = range_row_spans(budget)
        out.append({"label": pre + "开始" + suf, "type": "datepicker",
                    "row": key, "colspan": span})
        out.append({"label": lab, "type": "static", "text": lab,
                    "row": key, "colspan": title_span})
        out.append({"label": pre + "结束" + suf, "type": "datepicker",
                    "row": key, "colspan": span, "hideLabel": True})
    form["fields"] = out


def table_fields(form):
    return [f for f in form["fields"] if f["type"] == "table"]


def expand_range_columns(form):
    """重复表列里的「XX起止时间」自动拆成相邻两列。

    一列只能挂一个控件，所以列里放不下「开始 至 结束」：拆成 XX开始时间 + XX结束时间，
    表宽因此 +1；多张重复表列数不齐时，由 build_web 的加宽规则对齐最宽表。
    spec 里只写一列 {"label": "代住院总排班起止时间", "type": "datepicker"} 即可。
    """
    for f in table_fields(form):
        cols = f.get("columns") or []
        out, splits = [], []
        for c in cols:
            lab = str(c.get("label") or "")
            auto = c.get("type") == "datepicker" and "起止" in lab
            m = RANGE_RE.match(lab) if (c.get("range") or auto) else None
            if not m:
                out.append(c)
                continue
            pre, suf = m.group("pre"), m.group("suf")
            base = {k: v for k, v in c.items() if k not in ("label", "auto", "range")}
            out.append(dict(base, label=pre + "开始" + suf))
            out.append(dict(base, label=pre + "结束" + suf))
            splits.append(pre + "开始" + suf + " / " + pre + "结束" + suf)
        if splits:
            f["columns"] = out
            print("       · 重复表「%s」起止列拆两列：%s（列数 %d → %d）"
                  % (f["label"], "；".join(splits), len(cols), len(out)))


def web_cols(ncols):
    """列宽 + 总列数：与平台导出一致（每列 150，len 固定 26）。"""
    cols = {str(i): {"width": 150} for i in range(ncols)}
    cols["len"] = 26
    return cols


HEIGHT_FACTOR = 1.3   # 平台实际字比估算大，统一按比例抬高
APPROVE_MIN_H = 80    # 审批意见栏默认行高（用户标准：默认 80，标签过长再抬高）
APPROVE_LABEL_W = 150  # A 列宽度，用于估算审批标签折行数


def approve_row_height(label, fs=12):
    """审批意见栏行高：默认 80；标签在 A 列折行后按行数抬高（×1.3 安全系数）。"""
    chars = max(1, (APPROVE_LABEL_W - 12) // fs)
    lines = max(1, -(-len(str(label)) // chars))
    return max(APPROVE_MIN_H, int(round((lines * (fs + 8) + 8) * HEIGHT_FACTOR)))


def auto_row_heights(rows, ncols, fixed=None):
    """按单元格文字和列宽估算行高，避免长标题/长标签被默认行高截断。

    fixed: {行号: 指定高度}，指定行不再自动估算，按给定值落。
    """
    fixed = fixed or {}
    widths = [150] * ncols
    for k, r in rows.items():
        if k == "len" or int(k) in fixed:
            continue
        need = 0
        for c, cell in (r.get("cells") or {}).items():
            text = cell.get("text")
            if not text or "SheetType" in cell:
                continue
            span = (cell.get("merge") or [0, 0])[1] + 1
            c0 = int(c)
            w = sum(widths[c0:c0 + span])
            fs = 24 if cell.get("style") == S_TITLE else 12
            chars_per_line = max(1, int((w - 12) // fs))
            lines = sum(max(1, math.ceil(len(seg) / chars_per_line))
                        for seg in str(text).split("\n"))
            need = max(need, lines * (fs + 8) + 8)
        need = int(round(need * HEIGHT_FACTOR))
        if need > 40 and need > (r.get("height") or 0):
            r["height"] = need
    for r, h in fixed.items():
        rows[str(r)]["height"] = int(h)


def table_ncols(form):
    n = 6
    for f in table_fields(form):
        n = max(n, len(f.get("columns") or []))
    return n


def is_auto_column(c):
    return bool(c.get("auto")) or c.get("label") == "序号"


def table_show_number(f):
    """序号显示：值 = 序号所在列的位置（1 起）；没有序号列返回空串。

    spec 写法：
      - 不写 / true：自动取第一个「序号」列的位置
      - 数字（1 起）：显式指定序号列位置
      - false / 0 / ""：关闭序号显示
    """
    cols = f.get("columns") or []
    v = f.get("showNumber", None)
    if v is False or v == 0 or v == "":
        return ""
    if v is None or v is True:
        for i, c in enumerate(cols, 1):
            if is_auto_column(c):
                return str(i)
        return ""
    s = str(v).strip()
    if not s.isdigit():
        raise ValueError("重复表「%s」showNumber 必须是列位置数字（1 起）或 false/空"
                         % f.get("label", ""))
    n = int(s)
    if not 1 <= n <= len(cols):
        raise ValueError("重复表「%s」showNumber=%d 超出列数 %d"
                         % (f.get("label", ""), n, len(cols)))
    return str(n)


# ----------------------------- 移动视图 -----------------------------
def build_mobile_table(f, mby):
    if not f.get("columns"):
        raise ValueError("[%s] 重复表「%s」缺少 columns（列定义），无法生成移动视图"
                         % (f.get("_base", ""), f["label"]))
    e = copy.deepcopy(mby["table"])
    e["id"] = str(uuid.uuid4())
    pr = e["properties"]
    pr["label"] = f["label"]
    pr["isRequire"] = False          # 重复表整体不设必填，必填落在列上
    pr["isMultiple"] = True
    children = []
    for c in f["columns"]:
        if is_auto_column(c):
            continue  # 序号列移动端不生成，平台自带；Web 端保留列头 + showNumber
        ct = c.get("type", "input")
        if ct not in COLUMN_TYPES:
            raise ValueError("重复表「%s」列「%s」类型不支持: %s（可选: %s）"
                             % (f["label"], c.get("label", "?"), ct, "/".join(COLUMN_TYPES)))
        base = copy.deepcopy(mby[ct])
        child = {
            "id": str(uuid.uuid4()),
            "name": base["name"],
            "properties": base["properties"],
            "type": ct,
            "showLabel": c["label"],
        }
        cp = child["properties"]
        cp["label"] = c["label"]
        cp["isRequire"] = bool(c.get("require", True))
        if ct in ("radio", "checkbox", "select"):
            cp["options"] = [{"label": o, "value": o} for o in (c.get("options") or [])]
        if ct == "selectDep":
            cp["options"] = []
        if ct == "inputNum" and c.get("decimal"):
            cp["decimal"] = c["decimal"]
        apply_formula(cp, {"type": ct, "label": c["label"], "calc": c.get("calc"),
                           "hideWhen": c.get("hideWhen")},
                      "重复表「%s」列" % f["label"], prefix="%s\\" % f["label"])
        if c.get("placeholder"):
            cp["placeholder"] = c["placeholder"]
        if c.get("description"):
            cp["description"] = c["description"]
        children.append(child)
    if not children:
        raise ValueError("重复表「%s」去掉序号列后没有可生成的列" % f["label"])
    e["children"] = children
    return e


def build_mobile_label(f, mby):
    """静态说明块（label 控件）：说明文字逐行写进 description，移动端也能看到说明。"""
    e = copy.deepcopy(mby["label"])
    e["id"] = str(uuid.uuid4())
    pr = e["properties"]
    pr["label"] = f["label"]
    pr["isRequire"] = False
    pr["isHtmlStyle"] = True
    text = str(f.get("text") or f["label"])
    pr["description"] = text if text.endswith("\n") else text + "\n"
    return e


def build_mobile(form, mby, require_all):
    out = []
    for f in form["fields"]:
        t = f["type"]
        if t == "static":
            continue  # 纯 Web 静态说明（分节标题、表内注）移动端省略
        if t not in mby:
            raise ValueError("[%s] 不支持的控件类型: %s（可选: %s）"
                             % (form["base"], t, "/".join(MOBILE_TYPES)))
        if t == "label":
            out.append(build_mobile_label(f, mby))
            continue
        if t == "table":
            f["_base"] = form["base"]
            out.append(build_mobile_table(f, mby))
            continue
        e = copy.deepcopy(mby[t])
        e["id"] = str(uuid.uuid4())
        pr = e["properties"]
        lab = f["label"]
        pr["label"] = lab
        pr["isRequire"] = f.get("require", require_all)
        fl = field_flags(f)
        if t == "approve":
            pr["approveKey"] = lab
            pr["placeholder"] = f.get("placeholder", lab)
        if t == "attachment":
            pr["uploadMode"] = f.get("uploadMode", lab)
        if t in ("radio", "checkbox", "select"):
            pr["options"] = [{"label": o, "value": o} for o in (f.get("options") or [])]
            if f.get("options") is None:
                pr["options"] = []
        if t == "selectDep":
            pr["options"] = []
        if t == "singleCheckbox":
            pr["chkSelectValue"] = "true"
            pr["chkUnSelectValue"] = "false"
        if t == "inputNum" and f.get("decimal"):
            pr["decimal"] = f["decimal"]
        if t == "inputNumDisplay":
            # 数字格式：￥ = 小写金额、RMB = 大写金额，取值靠 autoCalc 的 join()
            pr["displayFormat"] = f.get("format", pr.get("displayFormat", ""))
            pr["isRequire"] = False
            if f.get("decimal"):
                pr["decimal"] = f["decimal"]
        if t == "sn":
            # 流水号：snMode 必须是元素自己的 id，snFormula 决定编号格式
            pr["snMode"] = e["id"]
            pr["snFormula"] = f.get("snFormula") or pr.get("snFormula") or "[Date:YY]-[NO:____]"
            pr["isRequire"] = False
        apply_formula(pr, f, "移动端字段")
        if f.get("placeholder"):
            pr["placeholder"] = f["placeholder"]
        if f.get("description"):
            pr["description"] = f["description"]
        if fl["token"]:
            pr["defVal"] = TOKEN_MOBILE[fl["token"]]
        if fl["date_default"] and not pr.get("description"):
            pr["description"] = "默认当前日期（运行时带入）"
        out.append(e)
    return [platform_keys(e) for e in out]


def platform_keys(e):
    """平台导出的移动元素固定 9 个键：name 之后插 oldTableKey/oldTableName（空串）。"""
    res = {k: e.get(k) for k in ("children", "class", "icon", "id", "name")}
    res["oldTableKey"] = e.get("oldTableKey", "")
    res["oldTableName"] = e.get("oldTableName", "")
    res["properties"] = e["properties"]
    res["type"] = e["type"]
    return res


# ----------------------------- Web 视图 -----------------------------
def build_web_table_cell(c, bind_table, field_no, ncols):
    """一行重复表的数据单元格：带 bindTable，非自动列带 bindField。"""
    t = c.get("type", "input")
    btn, sheet = WEB_BTN[t]
    text = "请输入"
    if t in ("radio",):
        text = "单选框"
    if t in ("checkbox", "singleCheckbox"):
        text = "多选框"
    cell = {"style": S_TABLE_DATA, "bindTable": bind_table, "text": text,
            "buttonType": btn, "placeholder": c.get("placeholder", "请输入"),
            "chkName": c["label"], "approveName": c["label"],
            "options": [{"label": o, "value": o} for o in (c.get("options") or [])]
            if t in ("radio", "checkbox", "select") else [],
            "required": bool(c.get("require", True)),
            "localDep": True, "showSign": False, "onlyShowSelected": False,
            "imageScale": "scale", "imageOption": "upload", "onlySelectData": False,
            "SheetType": sheet}
    if t == "datepicker":
        cell["dateTimeType"] = "date"
    if not is_auto_column(c) and field_no is not None:
        cell["bindField"] = "KC%04d" % field_no
    return cell


def build_web(form, wtpl, per_row):
    ncols = table_ncols(form)
    last = ncols - 1
    rows, merges, approves, tables = {"len": 100}, [], [], []
    fixed_heights = {}
    bind = [0]

    def nb():
        bind[0] += 1
        return "KM%04d" % bind[0]

    def ccell(f, style, merge):
        t = f["type"]
        if t not in WEB_BTN:
            raise ValueError("Web 视图不支持控件类型 %s（该字段请改用 textarea 承载）" % t)
        btn, sheet = WEB_BTN[t]
        lab = f["label"]
        fl = field_flags(f)
        text = "" if t in ("radio", "checkbox", "singleCheckbox", "approve") else "请输入"
        ph = f.get("placeholder") or "请输入"
        if t == "approve":
            ph = f.get("placeholder", lab)
        if fl["user_default"]:
            ph = "默认：申请人"
        if fl["dept_default"]:
            ph = "默认：申请人部门"
        if fl["date_default"]:
            ph = "默认：当前日期"
        c = {"style": style, "merge": merge}
        if t != "attachment":
            c["text"] = text
        c.update({
            "buttonType": btn, "bindData": nb(), "placeholder": ph,
            "chkName": lab, "approveName": lab,
            "options": [{"label": o, "value": o} for o in (f.get("options") or [])]
            if t in ("radio", "checkbox", "select") else [],
            "required": f.get("require", form["require_all"]),
            "localDep": True, "showSign": t == "approve", "onlyShowSelected": False,
            "imageScale": "scale", "imageOption": "upload", "onlySelectData": False,
            "SheetType": sheet,
        })
        if fl["token"]:
            c["defaultVal"] = TOKEN_WEB[fl["token"]]
        if t == "approve":
            c["approveMode"] = lab
            approves.append({"approveName": lab, "approveMode": lab})
        if t == "attachment":
            c["uploadMode"] = f.get("uploadMode", lab)
        if t == "datepicker":
            c["dateTimeType"] = "date"
        if t == "singleCheckbox":
            c["chkSelectValue"] = "true"
            c["chkUnSelectValue"] = "false"
        if t in ("sn", "inputNumDisplay"):
            # 流水号由平台生成、数字格式是计算展示，Web 端都不做必填
            c["required"] = False
        calc = (f.get("calc") or "").strip()
        # 实测：Web 端只有「带计算式的 inputNum」才写 decimal，普通 inputNum 不写
        if calc and t == "inputNum" and f.get("decimal"):
            c["decimal"] = f["decimal"]
        if t == "inputNumDisplay":
            # 平台 Web 端会带 displayFormat + approveDisplayFormat（￥ / RMB）
            fmt = f.get("format", "")
            c["displayFormat"] = fmt
            c["approveDisplayFormat"] = fmt
        if calc:
            c["autoCalc"] = to_formula(calc)          # Web 单元格同样带自动计算
        hide = (f.get("hideWhen") or "").strip()
        if hide:
            c["hideFormula"] = to_formula(hide)       # Web 端只有 hideFormula，没有 isHidden
        return c

    def put(ri, cells):
        row = {"cells": {}}
        for ci, cell in cells.items():
            if cell is not None:
                row["cells"][str(ci)] = cell
        for ci in range(ncols):
            if str(ci) not in row["cells"]:
                row["cells"][str(ci)] = dict(FILLER_TITLE) if ri == 0 else dict(FILLER)
        if ri == 0:
            row["height"] = 100
        rows[str(ri)] = row

    def styles_for(ri):
        return (S_LBL1, S_CTRL1) if ri == 1 else (S_LBLN, S_CTRLN)

    put(0, {0: {"style": S_TITLE, "text": form["title"], "merge": [0, last]}})
    merges.append("A1:%s1" % col_letter(last))

    cur = [1]

    def flush_buf(buf):
        while buf:
            place_short_group(buf[:per_row])
            del buf[:per_row]

    def place_static(f):
        """静态文字：整行 A:最后列 合并。多行说明逐行生成，避免长文本挤在一格被截断。

        `label` 是表单控件（移动端有标签块），虽然 Web 端这一行没有控件格，
        但平台按**表单字段顺序**发 bindData 号，所以它必须占一个号，否则后面
        的审批栏整体前移一位（实测：说明块占 KM0004，科室考核意见应为 KM0005）。
        """
        if f["type"] == "label":
            nb()
        variant = f.get("variant") or "note"
        if variant == "plain":
            st = S_PLAIN          # 无框：与 Word 正文里的「说明」一致（不在表格框内）
        elif variant == "section":
            st = S_LBL1 if cur[0] == 1 else 5
        else:
            st = S_STATIC
        text = f.get("text") or f["label"]
        chars_per_line = max(10, (ncols * 150 - 24) // 12)
        parts = str(text).split("\n")
        line_heights = f.get("lineHeights") or []
        for idx, line in enumerate(parts):
            r = cur[0]
            put(r, {0: {"style": st, "text": line, "merge": [0, last]}})
            merges.append("A%d:%s%d" % (r + 1, col_letter(last), r + 1))
            visual = max(1, -(-len(line) // chars_per_line))
            if len(parts) > 1 or visual > 1:
                rows[str(r)]["height"] = max(40, 8 + 18 * visual)
            if idx < len(line_heights):
                fixed_heights[r] = int(line_heights[idx])
            cur[0] += 1

    def place_wide(f):
        r = cur[0]
        lab_s, ctrl_s = styles_for(r)
        put(r, {0: {"style": lab_s, "text": f["label"]},
                1: ccell(f, ctrl_s, [0, last - 1])})
        merges.append("B%d:%s%d" % (r + 1, col_letter(last), r + 1))
        if f.get("height"):
            fixed_heights[r] = int(f["height"])
        elif f["type"] == "approve":
            fixed_heights[r] = approve_row_height(f["label"])
        cur[0] += 1

    def place_short_group(group):
        """短字段一行。按本行实际字段数分配列宽，末行不满也铺满整行，避免空半行。"""
        r = cur[0]
        lab_s, ctrl_s = styles_for(r)
        n = len(group)
        base, extra = divmod(ncols, n)
        sizes = [base + (1 if i < extra else 0) for i in range(n)]
        cells, mg, pos = {}, [], 0
        for f, size in zip(group, sizes):
            ctrl_span = size - 1
            cells[pos] = {"style": lab_s, "text": f["label"]}
            cells[pos + 1] = ccell(f, ctrl_s, [0, ctrl_span - 1] if ctrl_span > 1 else None)
            if ctrl_span > 1:
                mg.append("%s%d:%s%d" % (col_letter(pos + 1), r + 1,
                                         col_letter(pos + ctrl_span), r + 1))
            pos += size
        put(r, cells)
        merges.extend(mg)
        for f in group:
            if f.get("height"):
                fixed_heights[r] = max(fixed_heights.get(r, 0), int(f["height"]))
        cur[0] += 1

    def place_row_group(group):
        """自定义行：同一 row 的字段/静态文字按顺序铺在一行，格子数与其他行对齐。"""
        r = cur[0]
        lab_s, ctrl_s = styles_for(r)
        cells, ci = {}, 0
        for f in group:
            if f["type"] not in ROW_TYPES:
                raise ValueError("[%s] 字段「%s」类型 %s 不能放进自定义行"
                                 % (form["base"], f["label"], f["type"]))
            span_ = int(f.get("colspan", 1))
            if span_ < 1:
                raise ValueError("[%s] 字段「%s」colspan 非法" % (form["base"], f["label"]))
            if f["type"] == "static":
                cells[ci] = {"style": lab_s, "text": f.get("text") or f["label"]}
                if span_ > 1:  # 静态文字跨列：必须写合并，否则右侧留无边框填充格
                    cells[ci]["merge"] = [0, span_ - 1]
                    merges.append("%s%d:%s%d" % (col_letter(ci), r + 1,
                                                col_letter(ci + span_ - 1), r + 1))
                ci += span_
                continue
            if not f.get("hideLabel"):
                lspan = int(f.get("labelColspan", 1))
                if lspan < 1:
                    raise ValueError("[%s] 字段「%s」labelColspan 非法" % (form["base"], f["label"]))
                cells[ci] = {"style": lab_s, "text": f["label"]}
                if lspan > 1:      # 长标签跨列：与起止行的「开始」标签对齐用
                    cells[ci]["merge"] = [0, lspan - 1]
                    merges.append("%s%d:%s%d" % (col_letter(ci), r + 1,
                                                col_letter(ci + lspan - 1), r + 1))
                ci += lspan
            if f["type"] not in WEB_BTN:
                raise ValueError("[%s] 字段「%s」Web 类型不支持" % (form["base"], f["label"]))
            cells[ci] = ccell(f, ctrl_s, [0, span_ - 1] if span_ > 1 else None)
            if span_ > 1:   # 跨列控件必须登记合并，否则右侧成无边框填充格（空半行）
                merges.append("%s%d:%s%d" % (col_letter(ci), r + 1,
                                            col_letter(ci + span_ - 1), r + 1))
            ci += span_
        if ci > ncols:
            raise ValueError("[%s] 自定义行超出 %d 列（实际 %d 列）"
                             % (form["base"], ncols, ci))
        put(r, cells)
        for f in group:
            if f.get("height"):
                fixed_heights[r] = max(fixed_heights.get(r, 0), int(f["height"]))
        cur[0] += 1

    def place_table(f):
        cols = f["columns"]
        if len(cols) > ncols:
            raise ValueError(
                "[%s] 重复表「%s」有 %d 列，超过本表 %d 列（多张表取最宽者）"
                % (form["base"], f["label"], len(cols), ncols))
        name = f.get("tableName")
        if not name:
            raise ValueError("[%s] 重复表「%s」未绑定表名（tableName）"
                             % (form["base"], f["label"]))
        # 列数少于其它重复表：把右侧若干列各加宽 1 列（span=2）补齐，不删字段
        deficit = ncols - len(cols)
        spans = [1] * len(cols)
        if deficit > 0:
            cand = [i for i in range(len(cols) - 1, -1, -1) if not is_auto_column(cols[i])]
            if len(cand) < deficit:
                raise ValueError(
                    "[%s] 重复表「%s」只有 %d 列、需要补 %d 列，但可加宽的列不足"
                    % (form["base"], f["label"], len(cols), deficit))
            widened = []
            for i in cand[:deficit]:
                spans[i] = 2
                widened.append(cols[i]["label"])
            print("       · 重复表「%s」%d 列 → 对齐 %d 列：加宽 %s"
                  % (f["label"], len(cols), ncols, "、".join(reversed(widened))))
        # 序号显示：showNumber = 序号所在列的位置（1 起）；该列只留 bindTable 样式格
        show_number = table_show_number(f)
        sn_col = int(show_number) - 1 if show_number else -1
        field_no = 0
        hdr_r, data_r = cur[0], cur[0] + 1
        hdr, data = {}, {}
        pos = 0
        for i, c in enumerate(cols):
            span = spans[i]
            hdr[pos] = {"style": S_TABLE_HDR, "text": c["label"]}
            if i == sn_col:
                data[pos] = {"style": S_TABLE_DATA, "bindTable": name}
            elif not is_auto_column(c):
                field_no += 1
                data[pos] = build_web_table_cell(c, name, field_no, ncols)
            else:
                data[pos] = build_web_table_cell(c, name, None, ncols)
            if span > 1:                      # 加宽列：表头与数据格都要登记合并
                hdr[pos]["merge"] = [0, span - 1]
                data[pos]["merge"] = [0, span - 1]
                for k in range(1, span):      # 被覆盖的格子补边框样式，保证封口
                    hdr[pos + k] = {"style": S_TABLE_HDR}
                    data[pos + k] = {"style": S_TABLE_DATA, "bindTable": name}
                merges.append("%s%d:%s%d" % (col_letter(pos), hdr_r + 1,
                                            col_letter(pos + span - 1), hdr_r + 1))
                merges.append("%s%d:%s%d" % (col_letter(pos), data_r + 1,
                                            col_letter(pos + span - 1), data_r + 1))
            pos += span
        put(hdr_r, hdr)
        put(data_r, data)
        rows[str(hdr_r)]["height"] = 60
        tables.append({
            "tableRange": "A%d:%s%d" % (data_r + 1, col_letter(ncols - 1), data_r + 1),
            "bindTable": name,
            "showNumber": show_number,
            "isPagination": False, "pageSize": "",
            "addRowOption": "normal", "rowLimit": "", "sortOption": "normal",
        })
        cur[0] += 2

    buf = []
    fields = form["fields"]
    i = 0
    while i < len(fields):
        f = fields[i]
        if f.get("row"):
            key = f["row"]
            group = []
            while i < len(fields) and fields[i].get("row") == key:
                group.append(fields[i])
                i += 1
            flush_buf(buf)
            place_row_group(group)
            continue
        if f["type"] in ("static", "label"):
            flush_buf(buf)
            place_static(f)
            i += 1
        elif f.get("fullRow") or f["type"] in WIDE:
            flush_buf(buf)
            if f["type"] == "table":
                place_table(f)
            else:
                place_wide(f)
            i += 1
        else:
            buf.append(f)
            i += 1
            if len(buf) == per_row:
                place_short_group(buf)
                buf = []
    flush_buf(buf)
    auto_row_heights(rows, ncols, fixed_heights)

    doc = {
        "name": wtpl["name"], "freeze": wtpl["freeze"],
        # 有重复表时追加数据格样式（模板 17 个样式之后固定是 #f2f2f2 灰底那一个）
        "styles": wtpl["styles"] + ([DATA_STYLE] if tables else []),
        "merges": merges, "rows": rows, "cols": web_cols(ncols), "autofilter": {},
        "approves": approves, "sns": [], "tables": tables, "dics": [], "sqlDics": [],
        # 平台导出件（含流程导出包内嵌的 sheet）末尾带 events；单独导出的 Web 视图没有，两种都认
        "events": "{}",
    }
    return doc


# ----------------------------- 配置清单 -----------------------------
def approval_binding_warning(form):
    """审批栏之前插了移动端可见的说明块 → 平台按顺序配对节点会整体错位。

    平台把「第 N 个审批意见框」自动配到「第 N 个审批节点」，移动视图里在审批栏之前
    每多一个元素，配对就后移一位。`static` 只出 Web、不影响移动端顺序，故不告警。
    """
    if not any(f["type"] == "approve" for f in form["fields"]):
        return None
    blocks = []
    for f in form["fields"]:
        if f["type"] == "approve":
            break
        if f["type"] == "label":
            blocks.append(f["label"])
    if not blocks:
        return None
    return ("移动视图在审批意见栏之前有说明块（%s）：平台按控件顺序自动配对"
            "「第 N 个意见框 ↔ 第 N 个审批节点」，导入后审批框会整体后移一位，"
            "请在表单设计器里把每个意见框重新绑定到对应节点"
            % "、".join("`%s`" % b for b in blocks))


def build_notes(form, require_all):
    from datetime import datetime
    tfs = table_fields(form)
    if tfs and any(not f.get("tableName") for f in tfs):
        delivery = "移动视图（Web 视图待绑定重复表名后再生成）"
    else:
        delivery = "移动视图 / Web 视图各一份"
    lines = ["# %s · %s 配置清单" % (form["base"], form["title"]), "",
             "生成时间：%s；编码：UTF-8 with BOM；交付：%s。"
             % (datetime.now().strftime("%Y-%m-%d %H:%M"), delivery), "",
             "## 字段清单", "",
             "| # | 字段名称 | 控件类型 | 必填 | 默认值/提示 | 选项 |",
             "|---|---|---|---|---|---|"]
    n = 0
    for f in form["fields"]:
        if f["type"] == "static" and f.get("row"):
            continue  # 自定义行里的静态文字是布局分段，不算字段
        n += 1
        i = n
        fl = field_flags(f)
        default = "申请人本人" if fl["user_default"] else \
                  ("申请人部门" if fl["dept_default"] else
                   ("当前日期" if fl["date_default"] else
                    ("登录账号" if fl["token"] == "login" else
                     ("手机号" if fl["token"] == "phone" else "—"))))
        if f["type"] in ("static", "label"):
            req, default = "—（静态文字）", "—"
        elif f["type"] == "table":
            req, default = "—（重复表）", "列见下"
        else:
            req = "是" if f.get("require", require_all) else "否"
        opts = "、".join(f.get("options") or []) or "—"
        lines.append("| %d | %s | %s | %s | %s | %s |"
                     % (i, f["label"], f["type"], req, default, opts))

    if tfs:
        lines += ["", "## 重复表", "",
                  "| 字段 | 列数 | 绑定表名（bindTable） | 序号显示 |", "|---|---|---|---|"]
        for f in tfs:
            sn = table_show_number(f)
            lines.append("| %s | %d | %s | %s |"
                         % (f["label"], len(f.get("columns") or []),
                            f.get("tableName") or "（待绑定）",
                            ("第 %s 列（showNumber）" % sn) if sn else "无序号列"))
        for f in tfs:
            lines.append("")
            lines.append("### %s 列" % f["label"])
            lines.append("")
            lines.append("| # | 列名 | 类型 | 必填 | 自动列（移动端不生成） | 选项 |")
            lines.append("|---|---|---|---|---|---|")
            for i, c in enumerate(f.get("columns") or [], 1):
                lines.append("| %d | %s | %s | %s | %s | %s |"
                             % (i, c["label"], c.get("type", "input"),
                                "是" if c.get("require", True) else "否",
                                "是" if is_auto_column(c) else "否",
                                "、".join(c.get("options") or []) or "—"))

    ap = [f["label"] for f in form["fields"] if f["type"] == "approve"]
    nodes = form.get("nodes")
    flow_view = None
    if form.get("graph") or form.get("flow"):     # 显式流程：按动作类型列节点
        try:
            import flow_types
            if form.get("graph"):
                seq = [{"name": n["name"],
                        "key": n.get("type") or flow_types.classify(n["name"])}
                       for n in (form["graph"].get("nodes") or [])]
            else:
                seq = flow_types.normalize_items(form["flow"])
            flow_view = [(it["name"], flow_types.meta_of(it["key"])["label"]) for it in seq]
        except Exception:
            flow_view = None
    lines += ["", "## 流程节点（须在平台流程设计器中配置，JSON 不承载）", ""]
    if flow_view:
        lines += ["| # | 节点名称 | 动作类型 | 审批人/执行人 | 备注 |",
                  "|---|---|---|---|---|"]
        for i, (nm, tp) in enumerate(flow_view, 1):
            note = "自动生成" if tp in ("开始", "结束") else "（待确认）"
            lines.append("| %d | %s | %s | %s | |" % (i, nm, tp, note))
        if form.get("graph"):
            ec = len(form["graph"].get("edges") or [])
            lines += ["", "> 分支与先后关系见 spec 的 `graph.edges`（%d 条连线），"
                          "流程图与导出 JSON 均由它生成。" % ec]
    elif nodes:
        lines += ["| # | 节点名称 | 审批人/角色 | 进入条件 | 对应意见栏 |",
                  "|---|---|---|---|---|"]
        for i, n in enumerate(nodes, 1):
            lines.append("| %d | %s | %s | %s | %s |" % (
                i, n.get("name", ""), n.get("approver", ""),
                n.get("condition", "无（顺序流转）"), n.get("approveField", "—")))
    elif ap:
        lines += ["> 未提供节点清单，以下按表单审批意见栏倒推，需业务确认审批人与条件分支。", "",
                  "| # | 节点名称 | 审批人/角色 | 进入条件 | 对应意见栏 |",
                  "|---|---|---|---|---|"]
        for i, a in enumerate(ap, 1):
            lines.append("| %d | %s | （待确认） | 无 | %s |" % (i, a, a))
    else:
        lines.append("该表单无审批意见栏，节点需按业务流程另行确认。")
    lines += ["", "## 待确认项", ""]
    pend = []
    for f in form["fields"]:
        if f["type"] in ("radio", "checkbox", "select") and not f.get("options"):
            pend.append("- `%s`：单选/多选/下拉但未给选项，需业务补齐枚举值" % f["label"])
    for f in tfs:
        if not f.get("tableName"):
            pend.append("- `%s`：重复表已出移动端，**待提供平台重复表名（bindTable）**，"
                        "回填后再生成 Web 视图" % f["label"])
        for c in f.get("columns") or []:
            if c.get("type") in ("radio", "checkbox", "select") and not c.get("options"):
                pend.append("- `%s` 列 `%s`：未给选项枚举" % (f["label"], c["label"]))
    warn = approval_binding_warning(form)
    if warn:
        pend.insert(0, "- **审批栏顺序提醒**：" + warn)
    lines += pend or ["- 无硬性缺口（枚举值、重复表名均已就位）；审批人/条件分支按上表在流程设计器确认。"]
    if len(lines) and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def pending_note(form):
    """生成 (待绑定重复表).md：把要问用户的信息一次列清。"""
    lines = ["# %s · %s：重复表待绑定" % (form["base"], form["title"]), "",
             "移动视图已生成；**Web 视图暂不生成**，因为重复表还没有绑定平台表名。", "",
             "> 表名是每张表单、每一次生成都要重新索取的：不要复用上一张表单或上一次的表名。",
             "> 形如 `wx_XXXXXXXX_Form_0000000123_0001`，从平台表单设计器的重复表属性里抄全名。", "",
             "请提供下表中每个重复表在平台里的表名：", ""]
    lines += ["| 重复表字段 | 列数 | 序号列 | 列名 | 平台表名 |", "|---|---|---|---|---|"]
    for f in table_fields(form):
        sn = table_show_number(f)
        lines.append("| %s | %d | %s | %s | （待填） |"
                     % (f["label"], len(f.get("columns") or []),
                        ("第 %s 列" % sn) if sn else "无",
                        "、".join(c["label"] for c in f.get("columns") or [])))
    lines += ["", "拿到表名后执行（即使 spec 里写过 tableName，也以命令行这次传入的为准）：", "",
              "```bash",
              'python scripts/build_forms.py spec.json --table-name "wx_..._0001"',
              "```", "",
              '多个重复表时写成 `--table-name "字段名=wx_..._0001"` 并分别重复。', "",
              "脚本会重新生成移动视图、Web 视图（`tables[].tableRange` 指向数据行，"
              "列单元格写 `bindTable` + `bindField`；序号列写 `showNumber=列位置`），"
              "并自动跑校验。", ""]
    return "\n".join(lines)


def wbom(path, obj):
    with open(path, "wb") as fp:
        fp.write(b"\xef\xbb\xbf")
        fp.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="只生成指定流程，前缀匹配，逗号分隔，如 01,05")
    ap.add_argument("--per-row", type=int, default=None, choices=[2, 3])
    ap.add_argument("--table-name", action="append", default=None,
                    help="重复表名（bindTable），每次生成都要重新传入；单表直接给，"
                         "多表用 字段名=表名，可重复")
    ap.add_argument("--mobile-only", action="store_true", help="只生成移动视图，不生成 Web 视图")
    ap.add_argument("--web-only", action="store_true",
                    help="只生成 Web 视图（重复表第二段用）：不重建/不覆盖移动视图 txt，"
                         "只写 (Web视图).txt 这一份 sheet")
    ap.add_argument("--notes", action="store_true",
                    help="额外产出 (配置清单).md / (待绑定重复表).md（默认只出两个视图 txt）")
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()

    spec = json.loads(open(a.spec, "rb").read().decode("utf-8-sig"))
    out_dir = a.out or spec.get("output_dir") or os.path.join(os.getcwd(), "流程表单")
    per_row = a.per_row or spec.get("fields_per_row", 2)
    require_all = spec.get("require_all", True)
    os.makedirs(out_dir, exist_ok=True)

    mby, wtpl = load_tpls()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import validate_form
    forms = spec["forms"]
    if a.only:
        keys = [k.strip() for k in a.only.split(",")]
        forms = [f for f in forms if any(str(f["base"]).startswith(k) for k in keys)]

    for form in forms:
        form.setdefault("require_all", require_all)
        expand_range_columns(form)                # 重复表列里的起止先拆两列（会改变列数）
        expand_ranges(form, table_ncols(form))    # 再按最终列数拆主表的时间范围
        for f in form["fields"]:
            if f["type"] not in MOBILE_TYPES and f["type"] != "static":
                raise ValueError("[%s] 字段「%s」类型非法: %s" % (form["base"], f["label"], f["type"]))
            if f["type"] == "table" and not f.get("columns"):
                raise ValueError("[%s] 重复表「%s」缺少 columns（列定义）"
                                 % (form["base"], f["label"]))

    all_tables = [f for form in forms for f in table_fields(form)]
    labels = [f["label"] for f in all_tables]
    if len(labels) != len(set(labels)) and len(labels) > 1:
        raise ValueError("本次有多个重复表且字段名重复，无法按字段名给表名；请分批生成")

    # 表名每次生成都重新索取：spec 里遗留的 tableName 一律忽略
    provided = {}
    if a.table_name:
        simple = [v for v in a.table_name if "=" not in v]
        for v in a.table_name:
            if "=" in v:
                k, name = v.split("=", 1)
                provided[k.strip()] = name.strip()
        if simple:
            if len(all_tables) != 1:
                raise ValueError("本次有 %d 个重复表，--table-name 请写成 字段名=表名 并分别给出"
                                 % len(all_tables))
            provided[all_tables[0]["label"]] = simple[0].strip()
        missing = [f["label"] for f in all_tables if not provided.get(f["label"])]
        if missing:
            raise ValueError("以下重复表还没给表名: %s" % "、".join(missing))
    elif any(f.get("tableName") for f in all_tables):
        print("  ! 检测到 spec 里写了 tableName，已忽略：有重复表时每次都要重新索取表名")

    for f in all_tables:
        f["tableName"] = provided.get(f["label"])

    pending = [f for f in all_tables if not f.get("tableName")]

    produced = []
    for form in forms:
        form_pending = [f for f in table_fields(form) if not f.get("tableName")]
        mp = os.path.join(out_dir, form["base"] + "(移动视图).txt")
        wp = os.path.join(out_dir, form["base"] + "(Web视图).txt")
        # 两段式第二段：拿到表名只补 Web，移动视图第一段已生成，不再重复产出
        skip_mobile = bool(a.web_only
                           or (not a.mobile_only and not form_pending and os.path.exists(mp)))
        m = None if skip_mobile else build_mobile(form, mby, form["require_all"])
        w = None
        if not a.mobile_only and not form_pending:
            w = build_web(form, wtpl, per_row)
        if w is not None:
            errs = validate_form.check_web(w, wtpl)
            hard = [e for e in errs if not e.startswith("提示:")]
            if hard:
                print("FAIL  %s Web 视图校验未通过，未写入文件：" % form["base"])
                for e in errs:
                    print("      - %s" % e)
                return 1
        if m is not None:
            wbom(mp, m)
            produced.append(mp)
        if form_pending and os.path.exists(wp):
            os.remove(wp)          # 表名没确认就不留上次的 Web，避免误当本次产物
        if w is not None:
            # 单独交付的 Web 视图不带 events（那是流程导出包内嵌 sheet 的形态），
            # 校验用带 events 的对象，写盘去掉即可
            wbom(wp, {k: v for k, v in w.items() if k != "events"})
            produced.append(wp)
            stale = os.path.join(out_dir, form["base"] + "(待绑定重复表).md")
            if os.path.exists(stale):
                os.remove(stale)   # 已绑定，删掉过期的待绑定说明
        if a.notes:
            np_ = os.path.join(out_dir, form["base"] + "(配置清单).md")
            with open(np_, "w", encoding="utf-8", newline="\n") as fp:
                fp.write(build_notes(form, form["require_all"]))
        print("%-24s 移动=%-10s Web=%2d 行/%2d 合并/%2d 审批"
              % (form["base"], ("沿用第一段" if skip_mobile else "%d 控件" % len(m)),
                 (len(w["rows"]) - 1) if w else 0,
                 len(w["merges"]) if w else 0,
                 len(w["approves"]) if w else 0))
        warn = approval_binding_warning(form)
        if warn:
            print("  ! " + warn)

    if pending:
        for form in forms:
            if not [f for f in table_fields(form) if not f.get("tableName")]:
                continue
            if a.notes:
                pp = os.path.join(out_dir, form["base"] + "(待绑定重复表).md")
                with open(pp, "w", encoding="utf-8", newline="\n") as fp:
                    fp.write(pending_note(form))
        print("\n" + "=" * 60)
        print("有 %d 个重复表待绑定，%s：" % (len(pending),
              "Web 视图无法生成（--web-only 仍需先给表名）" if a.web_only
              else "本次只生成移动视图"))
        for f in pending:
            print("  - %s：%s（%d 列）" % (f.get("_base", ""), f["label"],
                                          len(f.get("columns") or [])))
        print('给出平台表名后重跑：python scripts/build_forms.py spec.json --table-name "<表名>"')
        print("DONE -> %s  (%d 个文件，Web 视图待生成)" % (out_dir, len(produced)))
        if not a.no_validate:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import validate_form
            print("\n=== 校验（仅已生成的视图）===")
            return validate_form.main(produced) or EXIT_WAIT_TABLE
        return EXIT_WAIT_TABLE

    if a.mobile_only:
        print("\n仅生成移动视图（--mobile-only），未生成 Web 视图。")
        print("DONE -> %s  (%d 个文件)" % (out_dir, len(produced)))
        if not a.no_validate:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import validate_form
            print("\n=== 校验 ===")
            return validate_form.main(produced)
        return EXIT_OK

    if a.web_only:
        print("\n仅生成 Web 视图（--web-only）：移动视图沿用第一段产物，不重建、不覆盖。")

    print("\nDONE -> %s  (%d 个文件)" % (out_dir, len(produced)))

    if not a.no_validate:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import validate_form
        print("\n=== 校验 ===")
        return validate_form.main(produced)
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as e:          # spec/布局类问题：给一行结论，不抛栈
        print("FAIL %s" % e)
        sys.exit(1)
    except FileNotFoundError as e:
        print("FAIL 找不到文件: %s" % e)
        sys.exit(1)
