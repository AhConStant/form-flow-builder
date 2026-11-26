# 本地补丁清单（升级技能后必须复查）

> 本文件记录**官方包里没有、本地加上去**的修改。每次用新版 zip 覆盖 `C:\Users\54232\.workbuddy\skills\form-flow-builder` 之后，逐条确认还在；不在就按下面重新打。

## P1 · 审批框 / 附件永不带默认值（2026-11-24）

**问题**：`approve` 带 `defVal`/`defaultVal` → 平台前端打不开。`部门领导审核` 里的“部门”命中 dept 规则被绑成 `departmentName`。

**补丁位置**

1. `scripts/build_forms.py` → `field_flags()` 开头：
```python
    if f.get("type") in ("approve", "attachment", "sn", "static", "label", "table"):
        return dict(token=None, user_default=False,
                    dept_default=False, date_default=False)
```
2. `scripts/build_forms.py` → `default_token()` 的 dept 排除词补：
```python
("负责人", "主任", "意见", "审批", "电话", "联系",
 "审核", "领导", "批示", "签发", "会签", "核稿",
 "批准", "确认", "签字")
```
3. `scripts/validate_form.py` → 移动端 `check_mobile()` 内、`isRequire` 校验之后：
```python
        if t in ("approve", "attachment"):
            dv = e["properties"].get("defVal")
            if dv not in (None, ""):
                errs.append("%s %s 不允许带 defVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, t, dv))
```
4. `scripts/validate_form.py` → Web 端控件校验里、`showSign` 分支之后：
```python
            if st in ("approve", "attachment") and cell.get("defaultVal") not in (None, ""):
                errs.append("%s %s 不允许带 defaultVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, st, cell.get("defaultVal")))
```
5. 文档：`SKILL.md` 默认值那条加半句；`references/field-rules.md` 加「硬规则：审批框/附件永不绑默认值」小节。

## P2 · 「同意执行」默认下一步（2026-11-25）

**问题**：平台里审批节点的「同意执行」默认落到「结束」，必须手选下一步。

**根因**：官方生成器把 `optStep` 写成空、还把 `importantShunt` 整个 pop 掉。平台真实导出件里是：
- `optStep` = `"1"`（判断节点为空串）
- `importantShunt` = 该步骤出线目标的 **DrawID**，多条按顺序逗号分隔（判断节点就是各分支），结束节点为空串

**补丁位置**：`scripts/build_export.py` 的 `build_steps()`，`step.update({...})` 里把

```python
            "optStep": "," * (len(r["to"]) - 1) if node == "nodeJudge" else "",
...
        step.pop("importantShunt", None)
```

改成

```python
            "optStep": "" if node == "nodeJudge" else "1",
            "importantShunt": ",".join(str(t) for t in r["to"]),
```

并删掉 `step.pop("importantShunt", None)` 那一行（连同上方注释）。

**核对基准**（平台导出件 `流程导出_用车流程_v1.0.json`）：
```
开始        optStep=1  importantShunt=2
申请人      optStep=1  importantShunt=3
审批×3      optStep=1  importantShunt=4/5/6
通知执行    optStep=1  importantShunt=7
结束        optStep=1  importantShunt=''
判断(2支)   optStep='' importantShunt='6,5'
```


## P3 · 节点默认开启「退回」（2026-11-25）

**需求**：导入后每个流程节点的「退回设置 → 允许退回」默认是关的，要逐个开。

**补丁位置**：`scripts/build_export.py` 的 `build_steps()`，`step.update({...})` 里加

```python
            "isCanReturn": node not in ("nodeStart", "nodeFirst", "nodeEnd", "nodeJudge"),
```

其余退回项保持平台默认：`returnTrend=0`（退回申请人）、`CanReturnStepID=""`（具体步骤无限制）、
`returnFillBackMode=9` / `returnNotifyAffectedDone=9`（跟系统开关）、`isReturnNeedComment=False`（退回意见非必填）。

平台字段名：退回开关 = `isCanReturn`（不是 `isCanReject`，那个是「不同意」按钮）。

## P4 · 09 步骤表判定规则 + 执行动作折叠（2026-11-26）

**需求来源**：用户拿平台「09 流程步骤表」截图（列：步骤名称 / 步骤说明 / 执行人 / 下一步骤）+ 一份 `TemplateSchema` XML，要求直接出包。三轮纠正后固化成规则。

**四条硬规则**（详见 `references/action-icons.md`）

1. 类型**按图标判**，不按名字猜：绿箭头=执行动作、红人/红箭头=通知执行、窗口+▼=判断、红勾剪贴板=审批、红圈=结束。特别注意「归档/存档」两条反例：修缮流程 `12 归档处理`（红箭头）是通知执行，议题流程 `12 议题归档`（绿箭头）是执行动作。
2. 「下一步骤」列属于**同一行左侧**的步骤名：有值照抄（可跳号），为空默认接下一级。
3. 跳号越过、且**没有任何入边**的行 = 未启用 → 节点、连线、表单意见框都不生成；不臆造并行分支、不硬串串行。
4. 执行动作**不生成步骤**：只做连线文字。

**补丁位置**

1. 新增 `references/action-icons.md`（对照表 + 09 识别流程）。
2. `scripts/flow_types.py` → `_RULES` 重排，按红字改判：

```python
    ("action",  ("通知申请人或执行动作",)),                    # 绿箭头 → 执行动作
    ("notice",  ("请选择是否需要", "请选择是否", "是否需要")),   # 必须排在「会签/审批」前
    ("notice",  ("多选择", "多选审批", "多人选择")),            # 多选择审批 → 通知执行
    ("action",  ("存档", "归档", "备案存", "入档")),            # 文件夹 → 执行动作
```

3. `scripts/build_export.py`
   - `fold_action_nodes(rows)`：出包前删 `action` 节点、前驱直连后继、步骤名写 `FlowStepCon.note`；相邻同名去重。
   - `strip_no()`：`actualName` / `nextActualName` 一律去层级序号（`label` 优先，老 spec 只有 `name` 时兜底）。
   - `build_steps()` 的 `named_branch`：判断出线文字 = `edgeLabels` → 折叠的动作名 → 分支节点名；两支都无分支名才写「是/否」。
4. `scripts/build_flowchart.py`：`fold_action_rows()` 渲染前折叠动作；`place_action_texts(..., boxes)` 避框避字；走线三档（同列短线 / 外侧沟槽 / 下-横-下过 `free_lane()`），回退边（目标在上方）走左侧沟槽。
5. `scripts/build_forms.py`：`lcell()` 把 `hideWhen` 同时写到标签格；`ROW_TYPES` 补 `radio` / `checkbox`。
6. `SKILL.md` 硬约束三条、`references/flow-export.md` 两节、`references/field-rules.md`「选项含其他补输入框」。

**验收口径**：导出包里 `ActionTypeID==4` 必须为 0 个；被折叠的步骤名出现在对应连线 `note` 里；`actualName` 不含 `1 `、`5.1.1 ` 这类序号；每条连线两端都在节点表里（无孤岛、无死胡同）。

## 无法通过本技能实现的部分（记下来，别再试）

- **流程「权限分配」页（授权对象 / 监控权限 13 项 / 知会权限）不在 `流程导出_*.json` 里**。
  逐键比对平台导出件与本地产物：`FlowSet` 108 键、`FlowSetVersion` 101 键、`FlowSetVersionPart` 42 键**完全一致**（只差 ID/名称/时间戳），全文件搜不到「流程管理员」，也没有 13 位权限布尔数组。
  导出件里唯一与权限有关的只有**附件权限**（`FlowParticipant` 2 条 + `FlowExtraOperation` 2 条，`tabCode=AttachAuthor`），这两处本地生成器已经与平台一致。
  → 权限分配只能在平台「编辑流程 → 权限分配」里配，或等平台提供单独的权限导出格式。
