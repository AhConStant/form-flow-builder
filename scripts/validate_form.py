# -*- coding: utf-8 -*-
"""
表单 JSON 校验器（移动视图 / Web 视图通用）

用法:
    python validate_form.py <file1.txt> [file2.txt ...]

自动按内容判定视图类型：
  - 顶层是数组  -> 移动视图
  - 顶层是对象  -> Web 视图

校验项见 references/mobile-schema.md 与 references/web-schema.md 的「校验清单」。
退出码 0 = 全部通过，1 = 有错误。
"""
import json
import os
import re
import sys

BOM = b"\xef\xbb\xbf"
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(SKILL_ROOT, "assets")

MOBILE_KEYS = ["children", "class", "icon", "id", "name", "properties", "type"]
# 平台可选键（顶层）：已绑字段的元素带 bindData；平台回写件会多 oldTableKey/oldTableName/isBuildByCode
MOBILE_OPT_KEYS = {"bindData", "oldTableKey", "oldTableName", "isBuildByCode"}
# properties 里按需出现的键（不进模板基准，出现即合法）：计算式 / 条件隐藏 / 流水号
PROP_OPT_KEYS = {"autoCalc", "hideFormula", "snFormula", "snMode", "isBuildByCode"}
TABLE_COL_KEYS = ["id", "name", "properties", "type", "showLabel"]
TABLE_COL_TYPES = ["input", "textarea", "radio", "checkbox", "singleCheckbox", "select",
                   "datepicker", "inputNum", "selectDep"]
PLAIN_STYLE = 2   # 无框样式（Word 正文里的「说明」不加框）

WEB_TOP_KEYS = ["name", "freeze", "styles", "merges", "rows", "cols",
                "autofilter", "approves", "sns", "tables", "dics", "sqlDics", "events"]
WEB_TABLE_KEYS = ["tableRange", "bindTable", "showNumber", "isPagination",
                  "pageSize", "addRowOption", "rowLimit", "sortOption"]
WEB_BTN = {
    "input": ("input", "input"),
    "inputNum": ("inputnum", "inputNum"),
    "inputNumDisplay": ("inputnumdisplay", "inputNumDisplay"),
    "selectDep": ("depselect", "selectDep"),
    "datepicker": ("time", "datepicker"),
    "select": ("select", "select"),
    "textarea": ("textarea", "textarea"),
    "radio": ("radio", "radio"),
    "checkbox": ("checkboxgroup", "checkbox"),
    "singleCheckbox": ("checkbox", "singleCheckbox"),
    "approve": ("approve", "approve"),
    "attachment": ("upload", "attachment"),
    "selectData": ("selectdata", "selectData"),
}
CELL_KEYS = {"style", "merge", "text", "buttonType", "bindData", "placeholder", "chkName",
             "approveName", "options", "required", "localDep", "showSign", "onlyShowSelected",
             "imageScale", "imageOption", "onlySelectData", "SheetType",
             "approveMode", "uploadMode", "dateTimeType", "chkSelectValue", "chkUnSelectValue",
             "bindTable", "bindField", "defaultVal",
             # 数字/金额格：小数位、数字格式（￥/RMB）
             "decimal", "displayFormat", "approveDisplayFormat",
             # Web 单元格上的公式/隐藏（与移动视图同名属性，按用户实测要求下沉到 Web）
             "autoCalc", "hideFormula", "isHidden",
             # 数据选取按钮（801 收文流程导出件）：按钮名 + 选取数据集
             "buttonName", "selDataSet"}

# 平台在新版设计器里会把 inputNumDisplay 的 Web 按钮写成 inputnumdisplay（SheetType 仍是 inputNum）
BT_ALIAS = {"inputNum": {"inputnum", "inputnumdisplay"}}


def load(path):
    raw = open(path, "rb").read()
    errs = []
    if not raw.startswith(BOM):
        errs.append("缺少 UTF-8 BOM 头（平台导入会中文乱码）")
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        return None, errs + ["JSON 解析失败: %s" % e]
    if raw.startswith(BOM):
        body = raw[3:]
    else:
        body = raw
    if b"\n" in body.strip():
        errs.append("提示: 文件含换行，规范要求单行紧凑输出（不阻断）")
    return obj, errs


def _keys_order_ok(actual, expected, where):
    errs = []
    if list(actual) != list(expected):
        missing = [k for k in expected if k not in actual]
        extra = [k for k in actual if k not in expected]
        errs.append("%s 键集合/顺序不符: 缺=%s 多=%s" % (where, missing, extra))
    return errs


def _mobile_keys_ok(actual, where):
    """必填键按序出现，可选键（bindData/oldTableKey…）允许穿插在平台规定的位置。"""
    errs = []
    got = [k for k in actual if k in MOBILE_KEYS]
    if got != MOBILE_KEYS:
        errs.append("%s 键集合/顺序不符: 缺=%s 实际=%s"
                    % (where, [k for k in MOBILE_KEYS if k not in actual], got))
    bad = [k for k in actual if k not in MOBILE_KEYS and k not in MOBILE_OPT_KEYS]
    if bad:
        errs.append("%s 出现未登记键: %s" % (where, bad))
    return errs


def _props_ok(pr, tpl_pr, where):
    """属性键：模板基准键一个不能少，可带 PROP_OPT_KEYS；顺序按平台习惯（字母序）。"""
    errs = []
    base = list(tpl_pr)
    missing = [k for k in base if k not in pr]
    if missing:
        errs.append("%s properties 缺基准键: %s" % (where, missing))
    bad = [k for k in pr if k not in base and k not in PROP_OPT_KEYS]
    if bad:
        errs.append("%s properties 出现臆造键: %s" % (where, bad))
    if list(pr) != sorted(pr):
        errs.append("提示: %s properties 未按字母序（平台回写会重排，不阻断）" % where)
    return errs


def check_mobile(obj, tpl):
    errs = []
    if not isinstance(obj, list):
        return ["移动视图顶层必须是控件数组"]
    by_type = {e["type"]: e for e in tpl}
    seen = set()
    for i, e in enumerate(obj):
        where = "控件#%d(%s)" % (i, e.get("properties", {}).get("label", "?"))
        errs += _mobile_keys_ok(e, where)
        t = e.get("type")
        if t not in by_type:
            errs.append("%s 控件类型不在白名单: %s" % (where, t))
            continue
        errs += _props_ok(e["properties"], by_type[t]["properties"], where)
        cid = e.get("id", "")
        if not cid or cid in seen:
            errs.append("%s id 为空或重复: %s" % (where, cid))
        seen.add(cid)
        if not e["properties"].get("label"):
            errs.append("%s label 为空" % where)
        if not isinstance(e["properties"].get("isRequire"), bool):
            errs.append("%s isRequire 不是布尔值" % where)
        # 硬规则：审批/附件不带默认值（带 defVal 的审批框前端直接打不开）
        if t in ("approve", "attachment"):
            dv = e["properties"].get("defVal")
            if dv not in (None, ""):
                errs.append("%s %s 不允许带 defVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, t, dv))
        if t == "table":
            cols = e.get("children") or []
            if not cols:
                errs.append("%s 重复表没有列（children 为空）" % where)
            for j, c in enumerate(cols):
                errs += _keys_order_ok(c, TABLE_COL_KEYS, "%s 列#%d" % (where, j))
                if "class" in c or "icon" in c:
                    errs.append("%s 列#%d 不应含 class/icon" % (where, j))
                if not c.get("properties", {}).get("label"):
                    errs.append("%s 列#%d label 为空" % (where, j))
                ct = c.get("type")
                if ct not in TABLE_COL_TYPES:
                    errs.append("%s 列#%d 类型非法: %s" % (where, j, ct))
                elif ct in by_type:
                    errs += _props_ok(c["properties"], by_type[ct]["properties"],
                                      "%s 列#%d" % (where, j))
        # 流水号：snMode 必须等于元素自身 id（平台实测，写错会导致编号不生效）
        if t == "sn":
            pr = e["properties"]
            if pr.get("snMode") != cid:
                errs.append("%s 流水号 snMode 应等于自身 id（%s），实际 %r"
                            % (where, cid, pr.get("snMode")))
            if not pr.get("snFormula"):
                errs.append("%s 流水号缺少 snFormula（编号格式）" % where)
        # 数字格式：displayFormat 只有 ￥（小写金额）/ RMB（大写金额）/ 空 三种实测取值
        if t == "inputNumDisplay":
            fmt = e["properties"].get("displayFormat", "")
            if fmt not in ("", "￥", "RMB"):
                errs.append("%s 数字格式 displayFormat 取值可疑: %r（实测 ￥ / RMB / 空）"
                            % (where, fmt))
        # 数据选取（移动端）：label 必须与 buttonName 同名，且 MapField 指回 KM 号
        if t == "selectData":
            pr = e["properties"]
            if pr.get("label") != pr.get("buttonName"):
                errs.append("%s 数据选取 label 应与 buttonName 一致（%r ≠ %r）"
                            % (where, pr.get("label"), pr.get("buttonName")))
            if pr.get("onlySelectData") is not True:
                errs.append("%s 数据选取 onlySelectData 应为 true" % where)
            dm = ((pr.get("selDataSet") or {}).get("dataMapping") or [])
            if not dm:
                errs.append("%s 数据选取缺少 selDataSet.dataMapping（选了值回填不到字段）" % where)
            else:
                mf = dm[0].get("MapField") or ""
                if not re.fullmatch(r"KM\d{4}", str(mf)):
                    errs.append("%s 数据选取 MapField 应为目标字段的 KM00xx，实际 %r" % (where, mf))
        # 条件隐藏：hideFormula 有值时初始态应为 isHidden=true
        if e["properties"].get("hideFormula") and not e["properties"].get("isHidden"):
            errs.append("提示: %s 有 hideFormula 但 isHidden=false（平台实测隐藏字段初始 isHidden=true）"
                        % where)
    if not obj:
        errs.append("控件数组为空")
    return errs


def _has_border(tpl, style, side):
    try:
        st = tpl["styles"][int(style)]
    except Exception:
        return False
    return side in (st.get("border") or {})


def check_layout(body, ncols, tpl, rects):
    """表格封口 + 空半行检查：内容没铺满整行、右/左边框缺失都算问题。"""
    errs = []
    cover = {}
    anchor_end = {}
    for m, r1, c1, r2, c2 in rects:
        anchor_end[(r1, c1)] = (r2, c2)
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if (rr, cc) != (r1, c1):
                    cover[(rr, cc)] = (r1, c1)

    def cell_at(r, c):
        return (body.get(str(r)) or {}).get("cells", {}).get(str(c))

    def anchor_at(r, c):
        return cover.get((r, c), (r, c))

    plain_rows = []
    for r in sorted(int(k) for k in body):
        if r == 0:
            continue
        cells = (body.get(str(r)) or {}).get("cells") or {}
        eff = []
        for c in range(ncols):
            if (r, c) in cover:
                continue
            cell = cells.get(str(c))
            if cell is None:
                continue
            end = anchor_end.get((r, c), (r, c))[1]
            eff.append((c, end, cell))
        content = [x for x in eff if x[2].get("text") or "SheetType" in x[2] or "bindTable" in x[2]]
        if not content:
            continue
        # 说明行（与 Word 正文一致）：整行一个无框格、跨满全部列，不参与封口/空半行判定。
        # 若只跨了部分列，仍会落到下面的空半行/封口检查里报错。
        if (len(eff) == 1 and eff[0][0] == 0 and eff[0][1] == ncols - 1
                and eff[0][2].get("style") == PLAIN_STYLE and eff[0][2].get("text")):
            plain_rows.append(r + 1)
            continue
        last_end = max(x[1] for x in content)
        if last_end < ncols - 1:
            rest = [x for x in eff if x[0] > last_end]
            if rest and all(not _has_border(tpl, x[2].get("style"), "left")
                            and not _has_border(tpl, x[2].get("style"), "right")
                            for x in rest):
                errs.append("行%d 空半行：内容只到 %s 列，右侧 %d 列为无边框填充"
                            % (r + 1, col_letter(last_end), ncols - 1 - last_end))

        ar, ac = anchor_at(r, ncols - 1)
        edge = cell_at(ar, ac)
        if edge is not None and not _has_border(tpl, edge.get("style"), "right"):
            errs.append("行%d 最后一列右边框缺失（表格未封口）" % (r + 1))

        ar, ac = anchor_at(r, 0)
        left = cell_at(ar, ac)
        if left is not None and not _has_border(tpl, left.get("style"), "left"):
            errs.append("行%d 第一列左边框缺失（表格未封口）" % (r + 1))

    if plain_rows:
        shown = ("行%d" % plain_rows[0] if len(plain_rows) == 1
                 else "行%d–%d" % (plain_rows[0], plain_rows[-1]))
        errs.append("提示: %s 为无框说明行（style %d），按 Word 正文样式跳过封口/空半行校验"
                    % (shown, PLAIN_STYLE))
    return errs


def a1(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref.strip())
    if not m:
        raise ValueError("非法单元格引用: %s" % ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)) - 1, col - 1


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _row_cells(body, r):
    return (body.get(str(r)) or {}).get("cells") or {}


def check_web(obj, tpl):
    errs = []
    if not isinstance(obj, dict):
        return ["Web 视图顶层必须是对象"]
    # events 是可选键（流程导出包里内嵌的 sheet 带、单独导出的 Web 视图不带）
    top = {k: v for k, v in obj.items() if k != "events"}
    errs += _keys_order_ok(top, [k for k in WEB_TOP_KEYS if k != "events"], "顶层")
    if "events" in obj and list(obj)[-1] != "events":
        errs.append("events 若存在必须放在顶层最后")
    sty = obj.get("styles") or []
    # 模板样式必须原样保留；允许在后面追加新样式（如平台新版给重复表数据格的灰底样式 17）
    if sty[:len(tpl["styles"])] != tpl["styles"]:
        errs.append("styles 与模板不一致（模板样式必须原样复用，新增样式只能追加在后面）")
    if len(sty) > len(tpl["styles"]):
        tpl = dict(tpl, styles=sty)      # 封口判定用实际样式表
    if obj.get("freeze") != tpl["freeze"]:
        errs.append("freeze 与模板不一致")
    if "events" in obj and obj.get("events") != "{}":
        errs.append('events 若存在必须是字符串 "{}"')

    rows = obj.get("rows") or {}
    body = {k: v for k, v in rows.items() if k != "len"}
    if rows.get("len") != 100:
        errs.append('rows["len"] 应为 100')
    idx = sorted(int(k) for k in body)
    if idx != list(range(len(idx))):
        errs.append("行号不连续: %s" % idx)

    # 列数由实际单元格推断（6 列标准；含 >6 列重复表时自动变宽）
    ncols = 6
    for r in body.values():
        for c in (r.get("cells") or {}):
            if str(c).isdigit():
                ncols = max(ncols, int(c) + 1)
    if ncols < 6:
        errs.append("列数少于 6（实际 %d）" % ncols)

    cols = obj.get("cols") or {}
    if cols.get("len") != 26:
        errs.append('cols["len"] 应为 26')
    want_cols = [str(i) for i in range(ncols)]
    got_cols = sorted((k for k in cols if k != "len"), key=int)
    if got_cols != want_cols:
        errs.append("cols 列宽键应为 0..%d，实际 %s" % (ncols - 1, got_cols))
    for k in got_cols:
        if not isinstance(cols[k], dict) or "width" not in cols[k]:
            errs.append("cols[%s] 缺少 width" % k)

    for k, r in body.items():
        cells = r.get("cells") or {}
        for c in range(ncols):
            if str(c) not in cells:
                errs.append("行%s 缺第 %d 列单元格（会被导入当作空列）" % (k, c))
        if k == "0" and int(r.get("height") or 0) < 100:
            errs.append("标题行 height 应 ≥ 100")

    # 合并区
    rects = []
    for m in obj.get("merges") or []:
        try:
            a, b = m.split(":")
            r1, c1 = a1(a)
            r2, c2 = a1(b)
        except Exception as e:
            errs.append("merge 非法 %s (%s)" % (m, e))
            continue
        if c2 >= ncols:
            errs.append("merge %s 超出实际列数 %d" % (m, ncols))
        rects.append((m, r1, c1, r2, c2))
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            m1, r1, c1, r2, c2 = rects[i]
            n1, s1, d1, s2, d2 = rects[j]
            if not (r2 < s1 or s2 < r1 or c2 < d1 or d2 < c1):
                errs.append("合并区重叠: %s 与 %s" % (m1, n1))

    for m, r1, c1, r2, c2 in rects:
        anchor = _row_cells(body, r1).get(str(c1))
        if anchor is None:
            errs.append("合并区 %s 的锚点缺失" % m)
            continue
        want = [r2 - r1, c2 - c1]
        if anchor.get("merge") != want:
            errs.append("合并区 %s 锚点 merge 应为 %s，实际 %s" % (m, want, anchor.get("merge")))
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                if (rr, cc) == (r1, c1):
                    continue
                cell = _row_cells(body, rr).get(str(cc))
                if cell is None:
                    errs.append("合并区 %s 覆盖格 %s%d 不存在（必须留填充格）" % (m, chr(65 + cc), rr + 1))
                elif "bindData" in cell or "SheetType" in cell:
                    errs.append("合并区 %s 覆盖格 %s%d 不应有控件" % (m, chr(65 + cc), rr + 1))
                elif "bindTable" in cell and set(cell) - {"style", "bindTable"}:
                    # 重复表跨列时平台会在覆盖格上也写 bindTable（只允许 style + bindTable）
                    errs.append("合并区 %s 覆盖格 %s%d 只能有 style/bindTable，实际 %s"
                                % (m, chr(65 + cc), rr + 1, sorted(cell)))

    errs += check_layout(body, ncols, tpl, rects)

    # 行高自动适配文字行数：任意行可写 height，但必须是正整数
    for k, r in body.items():
        if "height" in r:
            h = r["height"]
            if not isinstance(h, int) or h <= 0:
                errs.append("行%s height 必须是正整数" % k)

    # 控件单元格
    binds, approves_seen = [], set()
    table_cells = {}
    for k, r in body.items():
        for c, cell in (r.get("cells") or {}).items():
            if "SheetType" not in cell:
                extra = set(cell) - CELL_KEYS
                if extra & {"required", "bindData", "bindTable"}:
                    errs.append("行%s列%s 控件键不完整" % (k, c))
                if "bindTable" in cell:
                    # showNumber=1 的序号列：只剩 style + bindTable，由平台自动编号
                    if set(cell) - {"style", "bindTable"}:
                        errs.append("行%s列%s 自动编号格只能有 style/bindTable，实际 %s"
                                    % (k, c, sorted(cell)))
                    table_cells[(int(k), int(c))] = cell["bindTable"]
                continue
            where = "行%s列%s(%s)" % (k, c, cell.get("chkName", "?"))
            extra = set(cell) - CELL_KEYS
            if extra:
                errs.append("%s 出现臆造键: %s" % (where, sorted(extra)))
            st = cell.get("SheetType")
            cand = [v for v in WEB_BTN.values() if v[1] == st]
            if not cand:
                errs.append("%s SheetType 不在映射表: %s" % (where, st))
            elif cell.get("buttonType") != cand[0][0] and \
                    cell.get("buttonType") not in BT_ALIAS.get(st, ()):
                errs.append("%s buttonType 应为 %s（SheetType=%s）" % (where, cand[0][0], st))
            if not isinstance(cell.get("required"), bool):
                errs.append("%s required 不是布尔值" % where)
            if st == "attachment" and "text" in cell:
                errs.append("%s attachment 单元格不应含 text 键" % where)
            if st == "approve":
                if cell.get("showSign") is not True:
                    errs.append("%s approve 应 showSign=true" % where)
                approves_seen.add(cell.get("approveName"))
            else:
                if cell.get("showSign") is not False:
                    errs.append("%s 非 approve 应 showSign=false" % where)
            # 硬规则：审批/附件不带默认值（带 defaultVal 的审批框前端直接打不开）
            if st in ("approve", "attachment") and cell.get("defaultVal") not in (None, ""):
                errs.append("%s %s 不允许带 defaultVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, st, cell.get("defaultVal")))

            if "bindTable" in cell:
                # 重复表数据格：不写 bindData，按 bindTable + bindField 绑定
                if "bindData" in cell:
                    errs.append("%s 重复表单元格不应有 bindData" % where)
                bt = cell.get("bindTable")
                if not bt:
                    errs.append("%s bindTable 为空" % where)
                table_cells[(int(k), int(c))] = bt
                bf = cell.get("bindField")
                if bf is not None and not re.fullmatch(r"KC\d{4}", str(bf)) \
                        and not re.search(r"[\u4e00-\u9fa5]", str(bf)):
                    errs.append("%s bindField 命名不规范: %s（应为 KC0001 起，或移动视图重复表列标题）"
                                % (where, bf))
            else:
                if not cell.get("bindData"):
                    errs.append("%s bindData 为空" % where)
                else:
                    binds.append(cell["bindData"])

    if len(binds) != len(set(binds)):
        dup = sorted({b for b in binds if binds.count(b) > 1})
        errs.append("bindData 重复: %s" % dup)
    for b in binds:
        if not re.fullmatch(r"KM\d{4}", str(b)):
            errs.append("bindData 命名不规范: %s（应为 KM0001 起）" % b)

    # tables 数组
    tables = obj.get("tables") or []
    if not isinstance(tables, list):
        errs.append("tables 必须是数组")
        tables = []
    covered = set()
    for t in tables:
        errs += _keys_order_ok(t, WEB_TABLE_KEYS, "tables[]")
        rng = t.get("tableRange", "")
        try:
            a, b = rng.split(":")
            r1, c1 = a1(a)
            r2, c2 = a1(b)
        except Exception as e:
            errs.append("tables[].tableRange 非法 %s (%s)" % (rng, e))
            continue
        if r1 != r2:
            errs.append("tables[].tableRange 必须是单行（数据行）: %s" % rng)
        if c2 >= ncols:
            errs.append("tables[].tableRange 超出实际列数: %s" % rng)
        bt = t.get("bindTable")
        if not bt:
            errs.append("tables[].bindTable 为空")
        show_number = t.get("showNumber")
        if not (show_number == "" or (isinstance(show_number, str) and show_number.isdigit())):
            errs.append('tables[].showNumber 必须是序号列位置（"1" 起）或 ""，实际 %r'
                        % show_number)
        if isinstance(show_number, str) and show_number.isdigit():
            idx = c1 + int(show_number) - 1
            if idx > c2:
                errs.append("tables[].showNumber=%s 超出 tableRange 列范围" % show_number)
            else:
                first = _row_cells(body, r1).get(str(idx)) or {}
                if "SheetType" in first or "bindField" in first or "text" in first:
                    errs.append("showNumber=%s 时 %s%d 应为自动编号样式格（只含 style/bindTable）"
                                % (show_number, col_letter(idx), r1 + 1))
        def _covered(r, c):
            """被合并区覆盖（非左上锚点）的格子不承载 bindTable。"""
            for _m, mr1, mc1, mr2, mc2 in rects:
                if mr1 <= r <= mr2 and mc1 <= c <= mc2 and not (r == mr1 and c == mc1):
                    return True
            return False

        fields = set()
        for cc in range(c1, c2 + 1):
            cell = _row_cells(body, r1).get(str(cc))
            if cell is None:
                errs.append("tables[] 范围 %s 的 %s%d 单元格不存在" % (rng, col_letter(cc), r1 + 1))
                continue
            if _covered(r1, cc):
                covered.add((r1, cc))
                continue
            if cell.get("bindTable") != bt:
                errs.append("tables[] 范围 %s 的 %s%d bindTable 应为 %s"
                            % (rng, col_letter(cc), r1 + 1, bt))
            covered.add((r1, cc))
            bf = cell.get("bindField")
            if bf:
                if bf in fields:
                    errs.append("tables[] 范围 %s 内 bindField 重复: %s" % (rng, bf))
                fields.add(bf)
    for (r, c), bt in table_cells.items():
        if (r, c) not in covered:
            errs.append("行%s列%s 的重复表单元格未被任何 tables[] 的 tableRange 覆盖"
                        % (r, c))

    ap = {x.get("approveName") for x in (obj.get("approves") or [])}
    if ap != approves_seen:
        errs.append("approves 数组与 approve 单元格不匹配: 数组=%s 单元格=%s"
                    % (sorted(ap), sorted(approves_seen)))
    return errs


def main(paths):
    mtpl = json.loads(open(os.path.join(TPL_DIR, "mobile_view_template.txt"), "rb")
                      .read().decode("utf-8-sig"))
    wtpl = json.loads(open(os.path.join(TPL_DIR, "web_view_template.txt"), "rb")
                      .read().decode("utf-8-sig"))
    bad = 0
    for p in paths:
        obj, errs = load(p)
        if obj is not None:
            if isinstance(obj, list):
                errs += check_mobile(obj, mtpl)
                kind = "移动视图"
            else:
                errs += check_web(obj, wtpl)
                kind = "Web视图"
        else:
            kind = "?"
        hard = [e for e in errs if not e.startswith("提示:")]
        if hard:
            bad += 1
            print("FAIL  %s  [%s]" % (os.path.basename(p), kind))
            for e in errs:
                print("      - %s" % e)
        else:
            note = "".join("\n      - " + e for e in errs)
            print("OK    %s  [%s]%s" % (os.path.basename(p), kind, note))
    print("\n%d/%d 通过" % (len(paths) - bad, len(paths)))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
