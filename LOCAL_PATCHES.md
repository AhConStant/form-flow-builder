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

## P5 · 判断条件 StepCondition + isValidate（2026-11-27）

**需求来源**：解析平台真实导出件 `流程导出_422信息系统用户操作权限申请_v1.0.json`（FlowID 86）后确认：
结构与本生成器逐键一致，唯一影响功能的差异是**判断节点的条件规则为空**（`StepCondition` 0 条、连线 `ConContent` 全空），
导入后要在平台手工配分支规则。用户要求把这条和 `isValidate` 一起做进生成器。

**平台写法**（`references/flow-export.md` 有完整字段表）

| 条件项数 | 连线 `ConContent` | `ConContentDesc` |
|---|---|---|
| 1 个 | `[1]` / `![1]`（取反） | ` 是 ` / ` 【取反】 是 ` |
| ≥ 2 个 | ~~留空~~ → 见 P6：`[1] Or [2]` | 各值文本用「 / 」连（P6 改为「 【或者】 」） |

条件行 35 键，左值 `FormVariable`（`KM0004_Value` + `<%#myField\人员类别(值)%>`），右值 `ListVariable` / `ConstantVariable` / `SQLVariable`。

**补丁位置**

1. `scripts/flow_types.py` 新增 `alt_of(node)` / `expand_conditions(graph)`：
   `judge.conditions[].to` 与 `else` 自动补成 `edges`（没写也能跑），并按条件顺序把该判断的出线排到前面。
2. `scripts/build_export.py`
   - 新增 `cond_blank()`（35 键空模板，键序与平台一致）、`field_code_map(web)`（chkName → 字段码/控件类型）、
     `_left_of` / `_right_of` / `_cond_label`、`build_conditions(...)`。
   - `build_conditions` 按**绘图号**配对（`actualName` 允许重名，三条分支都叫「科主任审批」时按名字会串），
     条件的 `to` 写成执行动作时用 `fold_action_nodes` 返回的 `redirect` 穿透到后继。
   - `build_steps(..., web=None)` 返回 `conditions`；出线文字回填时**用户 `edgeLabels` 优先**，
     条件覆盖自动生成的折叠动作名与「是/否」。
   - `fold_action_nodes` 第三返回值 `redirect`：`{action 名: [折叠后绘图号]}`。
   - `patch_skeleton(..., conditions)` 写入 `FlowExportData.StepCondition`；
     `FlowSet.isValidate` / `FlowSetVersion.isValidate` 一并置 `true`（平台导出件都是 true）。
   - 自检输出加判断条件条数；未配条件的判断单独提示。
3. `scripts/build_flowchart.py`
   - 新增 `cond_labels(graph)` / `resolve_cond_labels(...)`：条件文字画到判断出线上，目标若是执行动作先穿透。
   - 新增按绘图号索引的 `EDGE_LABEL_D`：**同一层三分支节点同名时，名字键会互相覆盖**，draw 键才唯一。
   - 有条件文字的边不再重复画执行动作名。
   - 判断的「正下方」分支（中心差 ≤10px）改走**底顶点直下**——原来从右顶点出会让横段横穿菱形下半部、文字糊在菱形上。
   - 分支文字每行至少 12 字（原来按横段宽度算，横段为 0 时折成 6 字竖条）。
4. `references/spec-format.md` 新增「判断条件」一节；`references/flow-export.md` 新增「StepCondition」一节并修正「ConContent 为空」的解释；`SKILL.md` 判断条件速查补两行。

**spec 写法**

```json
{"name": "5 判断人员类别", "type": "judge", "x": 460, "y": 420,
 "conditions": [
   {"field": "人员类别", "value": "医技药人员", "to": "6 医务科初审"},
   {"field": "人员类别", "value": ["护理人员", "行政后勤人员"], "to": "7 相关职能科审批"}]}
```

是否判断用 `else` 更贴近平台：`{"conditions":[{...,"to":"9 ..."}], "else": {"to":"10 ...","label":"非新入岗人员"}}`。

**验收口径**：有 `conditions` 的判断，`StepCondition` 条数 = 条件值个数；只有 1 条时出线 `ConContent` 为 `[1]`/`![1]`，
否则为空且 Desc 用「 / 」连；`FlowSet.isValidate == true`；流程图判断出线显示条件文字而非执行动作名。

## P6 · 条件步骤 ConContent 必须写全 + processPrev 全前驱（2026-11-27）

**需求来源**：用户把 403 胸牌流程导进平台后反馈「条件因子设置有了，但条件步骤设置还是没有生成」，
导出的 `流程导出_403胸牌申办、补办及门禁权限申请流程_v1.0.json` 里能看到平台真实写法。
逐字段比对：`StepCondition` 35 键**完全一致**，只有两处不同 →

1. **连线 `ConContent` 空着**。P5 里按 422 件得出的「条件项 ≥2 就留空」是**错的**——
   422 那份是我们自己的产物被导回去，平台只是照抄。403 件里用户在平台点完「条件步骤」后，
   平台写的是 `[1] Or [2]` / `[3]` / `[4] Or [5]`，Desc 也从「 / 」变成了「 【或者】 」。
   → `ConContent` 是**真正的判断表达式**，留空 = 条件步骤没绑、分支不会自动走；
   `ConContentDesc` 只是显示文字。
2. **`processPrev` 只写了第一条前驱**（汇聚点 `2` 应为 `2,4`、`14` 应为 `14,17`）。
   平台导出件里是**全部前驱逗号分隔**（`3,5,6`），少写平台会认为其它来线没接上。

**补丁位置**

1. `scripts/build_export.build_conditions()`
   - 先记下每个条件项的序号（`jIdentity` 的 `[n]`），按出线归组：
     一条边一个条件 → `[3]`；多个 → `" Or ".join("[n]")`；取反支 → `![n]`
     （多条件的「其他情况」按单条取反推得 `![1] And ![2]`，**未实测**，会打告警让用户核对）。
   - `ConContentDesc` 多条件用 `" 【或者】 "` 连接，单条件仍是 ` 条件名 `。
   - 两条出线的是非判断、没写 `else` 时，第二支仍写 `![1]`（保持原行为）。
2. `scripts/build_export.build_steps()`
   - `prev` 改成 `sorted({...})` 全集，`processPrev = ",".join(...)`。
   - 用户 `edgeLabels` 写了分支文字时：**文字保留，但 `ConContent` 仍由条件补上**
     （原来整条跳过，导致「护理人员 / 行政后勤人员」那支条件绑不上）。
3. `assets/flow_export_skeleton.json`：`FlowSet` / `FlowSetVersion` 补 `flowCode` / `udfName` 两个空键
   （平台导出件有，键序按字母序），整包键集合与平台件对齐。
4. 文档：`references/flow-export.md`（ConContent 表 + processPrev）、`references/spec-format.md`、`SKILL.md` 同步改正。

**验收口径**：与平台件逐字段比对，除 ID / 视图 HTML / 时间戳外**零差异**；
`胸牌` 判断边为 `[1] Or [2]` `[3]` `[4] Or [5]`；`权限` 为 `[1]` `[2] Or [3]` `![1]`。
脚本化自检：每条 `processPrev` == 所有入边源 DrawID 升序逗号串。

## P7 · 穿框告警不再把「回退边」算进去（2026-11-27）

**现象**：408 信息数据提取流程里，「12 病案统计室负责人审核 → 10 执行人复核」是**回退边**
（目标在上方），渲染时走画布左侧沟槽再水平进入目标，实际并不穿框；
但 `find_crossings()` 用「两点中点」估算路径，中点正好落在两节点之间的「11 二级审核」方框里，
每次生成都报一条 `· 连线 … 穿过「二级审核」`。

**补丁**：`scripts/build_flowchart.find_crossings()` 在判断前先跳过 `ty < sy - 6`（向上回退）的边，
与 `render_canvas()` 里「回退边一律走左侧沟槽」的分支保持一致。

**另一处**（同样机制、但不是靠跳过能解决的）：源节点与目标在同一行的普通连线（如
「10 执行人复核 → 11 二级审核」）也会被当成回退边，走「下-横-上」的大 U。
排版时把这类节点错开 40px 以上即可（10 的 y 比 11 高 80）。

## 无法通过本技能实现的部分（记下来，别再试）

- **流程「权限分配」页（授权对象 / 监控权限 13 项 / 知会权限）不在 `流程导出_*.json` 里**。
  逐键比对平台导出件与本地产物：`FlowSet` 108 键、`FlowSetVersion` 101 键、`FlowSetVersionPart` 42 键**完全一致**（只差 ID/名称/时间戳），全文件搜不到「流程管理员」，也没有 13 位权限布尔数组。
  导出件里唯一与权限有关的只有**附件权限**（`FlowParticipant` 2 条 + `FlowExtraOperation` 2 条，`tabCode=AttachAuthor`），这两处本地生成器已经与平台一致。
  → 权限分配只能在平台「编辑流程 → 权限分配」里配，或等平台提供单独的权限导出格式。
