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

## P8 · 流程必须以「开始 → 申请人」开头（2026-11-27）

**现象**：408 流程 09 表第 2 行叫「申请人声明」，我直接把它当成申请人节点（改名成「申请人」），
用户看到流程图是「开始 → 申请人声明」缺申请人；我先改成「开始 → 申请人」又吞掉了第 2 行，
用户纠正：「要保留开始-申请人，然后从 2 的序号开始生成后面的步骤」。

**口径**（用户原话）：**「开始」之后先补一个真正的「申请人」节点，截图第 2 行仍按原序号原样生成**。
即 开始 → 申请人 → 2 申请人声明 →（2.1 / 2.2）→ 3 …
第 2 行不吞、不改名；截图没有发起行时才只补申请人。

**补丁**：
1. `scripts/build_export.py` 自检新增硬校验：`nodeStart` 的唯一后继必须是 `nodeFirst` 且 `actualName=="申请人"`，
   否则 `FAIL` 并提示「流程开头必须是 开始 → 申请人（当前 …）」。
2. `SKILL.md` 09 步骤表规则段补同一句，并补「判断节点下一步骤为空时，默认出口接下一级、另一条才跨级」。

**实例**：408 新增 `申请人`（first）插在「1 开始」与「2 申请人声明」之间；
`2 申请人声明` 恢复原名、按图标判 `notice`（窗口+红人+蓝箭头），2.1 承诺 / 2.2 不同意 两条出线保持不变；
`判断是否信息网络中心人员` 的条件从「数据使用科室=信息网络中心」换成**角色 SQL**
（`priUserRole` 里 `priRole.name LIKE '%信息网络中心%'` + `<@#SYS://TaskID@>` 取当前用户）。

## P9 · 09 规则清单全量定稿（23 条）

**日期**：2026-11-27　**版本**：1.2.4　**性质**：文档固化（无逻辑改动）

**背景**：用户 2026-11-27 要求把 09 截图生成的规则全部列出来核对，逐条确认后回复
「1/2/3/4 是对的，5 不需要」——即 23 条规则全部生效，「执行人/步骤说明写入 note」明确不做。

**补丁**：
1. `references/action-icons.md` 新增「09 规则清单（23 条）」：A 读表 R1–R10、B 开头 R11–R12、
   C 类型 R13–R15、D 连边与条件 R16–R23，每条标来源（用户确认 / 平台实测），
   并附 408 流程的核对示例（17 步 / 22 连线 / 3 条件 / ActionTypeID=4 为 0 / FlowFormSet 空）。
2. `SKILL.md` 09 段补 R9：「步骤说明」「执行人」两列**不写入导出包、也不写进连线 note**，
   只用于判断节点性质；并指向上述 23 条清单。
3. `build_export.py` 自检处注释按 1.2.3 的最终口径重写（补独立申请人节点、第 2 行原样保留），
   避免注释把人带回「把第 2 行改名」的旧口径。

**注意**：改这 23 条中任何一条前先问用户；它们同时被 `build_export.py` 自检和 `build_flowchart.py` 依赖。

## P10 · Web 视图列数可配（`cols`，默认 6）

**日期**：2026-11-27　**版本**：1.3.0　**性质**：新增能力（向后兼容）

**背景**：605 保卫设备维修安装申请表的源视图是 **7 列**（`申请人(1) + 输入(4) + 申请科室(1) + 输入(1)`），
生成器原来把列数写死 6，`row` 组一写就报「自定义行超出 6 列」。

**补丁**：
1. `build_forms.table_ncols()`：`n = int(form.get("cols") or 6)`，再按重复表列数取最大。
   不写 `cols` 时行为不变（408 / 202 回归仍为 6 列）。
2. `references/spec-format.md` 的 `forms[]` 增 `cols`（Web 列数，默认 6）；
   `SKILL.md` 布局段补「源表确实是 7 列时写 `"cols": 7`」。
3. 其余逻辑无需改：`web_cols(ncols)`、`auto_row_heights(rows, ncols)`、合并字母都按 ncols 算。

**实例**：`spec_保卫设备维修安装申请.json` 写 `"cols": 7`，产出 Web 13 行、`A1:G1`/`B2:E2` 合并正确、校验通过。

## P11 · 同名同执行人步骤合并 + 公共段后补判断（R24）

**日期**：2026-11-27　**版本**：1.3.1　**性质**：规则新增（生成器逻辑不变，靠 spec 组织实现）

**背景**：707 预算调整申请表有 5 条归口分支，每支 6~9 步，其中后半段五支完全重复
（财务科初审 / 业务临床科室分管院领导审批 / 院领导审批各出现 5 次），图上一片重复列。
用户 2026-11-27 晚定规则：**名称相同 + 执行人相同 → 合并为一个步骤，并在其后加一层判断**。

**规则（已写入 `references/action-icons.md` R24 / R24a / R24b）**：
1. 名称相同 **且** 执行人相同 → 合并成一个公共步骤，各分支独有步骤走完后汇入。
2. 合并后后续去向不同 → 在公共步骤**后面**加判断（同一字段枚举 + `else`）再分流。
3. 名称相同但执行人不同 → **不合并**（707 的财务科审批 / 财务科分管在 4.6 写「规划财务部（运营管理部）」，单独留节点）。
4. 只合并**公共段**，不把中间位置的同名步骤跨层提前。

**707 实施结果**：65 节点 / 49 步 → **47 节点 / 34 步**，`ActionTypeID=4` 为 0，5 判断 / 17 条件（条件数 1.3.2 校准后）。

| 合并组 | 原 | 后 | 处理 |
|---|---|---|---|
| 财务科初审 | 5 | 1 | 5 支直接汇入 |
| 业务临床科室分管院领导审批 | 5 | 1 | 5 支汇入 |
| 院领导审批 | 5 | 1 | 5 支汇入 |
| 财务科审批 | 5 | 2 | 4 合 1 + 规划财务部 1，中间加「6 判断财务科审批执行人」 |
| 财务科分管院领导审批 | 5 | 2 | 4 合 1 + 规划财务部 1 |
| 通知申请科室及归口管理科室 | 4 | 4 | 执行人各不相同，不合并 |

新增判断：`6 判断财务科审批执行人`（保卫科 vs 其他）、`8 判断归口管理部门分管院领导`
（5 个归口各一支）、`11 判断后续办理`（4 个通知 + 财务科直接归档，5 支）。
其中 8/11 的财务科最初写成 `else`，1.3.2 按平台导出件改成显式 `[5]`（R25）。

**布局注意**：公共段主轴放在 600（不是 532），否则「判断4 → 5 财务科初审」是**同列长边**（542px），
会被 `build_flowchart` 判成外侧沟槽、绕到画布最左边。只要 `abs(sx-tx) >= 1` 且 `<= w_cv*0.5`，就走「下-横-下」。

## P12 · 判断条件写法按平台导出件校准（多条取反 `!([1] or …)`、R25 一值一条件）

**日期**：2026-11-28　**版本**：1.3.2　**性质**：缺陷修复 + 规则新增

**背景**：用户 2026-11-28 上传平台导出的 707 包（「这份是对的」）。逐字段比对确认：
34 节点 / 50 连线、`FlowStepPart`、`FlowParticipant` / `FlowExtraOperation`、表单 `sheet` 全部逐字节相同，
**只有三处条件写法不同**（外加坐标）。说明结构设计没问题，问题在条件表达。

| # | 原实现 | 平台导出件 | 处理 |
|---|---|---|---|
| 1 | `Draw13` / `Draw21` 的财务科用 `![1] And ![2] And ![3] And ![4]` 排除法 | 显式 `[5]` + 一条 `StepCondition` | 补 2 条条件（15 → 17），新增 **R25** |
| 2 | 多条取反 `![1] And ![2] And …` | `!([1] or [2] or [3] or [4] or [5])` | `build_conditions()` 改写法 |
| 3 | `ConContentDesc` 直接抄 `note`（「【取反】 归口管理部门判断错误」） | ` 【取反】（ 医学装备科 【或者】 … ）` | 按条件重算，`note` 保留业务描述 |

**改动**：
- `scripts/build_export.py` `build_conditions()`：`all_idx` 多于一条时
  `con = "!(%s)" % " or ".join(...)`、`desc = " 【取反】（ %s ）" % " 【或者】 ".join(item_labs)`；
  单条仍是 `![n]` / ` 【取反】 说明 `。
- 新增温和告警：`else` 文字不含「其他/其它/错误/否/不/无/未/空/异常」时，
  提示「像是字段的一个具体取值，应写成显式条件（R25）」。
- `_gen_707.py`：`8 判断归口管理部门分管院领导`、`11 判断后续办理` 各补一条
  `{"field": "归口部门", "value": "财务科", ...}`，删掉对应 `else`。

**核对结果**（与用户导出件比，忽略坐标/主键）：
`FlowStep` 全字段 0 差异、`FlowStepCon` 集合相等、`StepCondition` 集合相等且字段全等、
`ConContent` / `ConContentDesc` 全等；唯一残留差异是 `(21,22)` 的 `note` 前导空格（用户手工输入痕迹，不照抄）。

**经验**：判断的 `else` 只能表示「枚举之外/错误」，**不能拿来表示枚举里的某个值**。
即使几条线汇到同一个目标，那个值也要有自己的一条条件——否则导出件里显示成「【取反】 财务科」，
看流程的人会理解成「排除财务科」。

## P13 · 意见框可与步骤名不同（`formField`）+ 801 收文流程解析

**日期**：2026-11-28　**版本**：1.3.3　**性质**：能力新增（兼容）

**背景**：用户给了一份平台导出的 `801收文流程(2022年版)_v1.0.json`，说「后面给 09 公文流程时按这个规则生成」。
解析发现它带 **2 条 `FlowFormSet`**（此前所有包都是空的，只能手工绑）：

| Draw | 步骤名 | fieldCode / fieldName | 说明 |
|---|---|---|---|
| 3 | 医院办公室拟办意见（审批） | 医院办公室拟办意见 | 与步骤同名 |
| 5 | 各院领导阅知、责任科室阅办（**通知**） | **传阅意见** | 不同名，且表单 sheet 里没有这个控件 |

→ 结论：`FlowFormSet.fieldCode` 是**流程意见字段名**，不要求表单有同名控件，也不要求等于步骤名；
通知节点同样能绑。

**改动**：
- 新增 `declared_form_fields(form)`：读 `graph.nodes[].formField` → `{actualName: 意见框名}`。
- `form_set_ok(steps, web, form=None)`：声明过的节点不再要求表单里有同名意见框；
  有声明时不再因「表单多出别的意见框」判不通过。
- `build_form_set()`：`fix = declared.get(actualName)` 优先，其次 `match_opinion()`；
  `code_of.get(title, title)` 兜底（声明了但表单没有 → fieldCode 就用名字，与 801 一致）。
- 回归：707 重跑，17 条件 / 50 连线 / ConContent 全一致（它不生成 FlowFormSet，行为不变）。

**801 其余观察（不照抄）**：
- 执行动作保留成 `nodeAction`（ActionTypeID=4）——与本项目 R15（折叠）冲突，以 R15 为准；
- `optStep` 只有审批写 "1"；`ActionTypeID` 老映射（申请人 -1、结束 1）；`layer` 全 0；图标全绿；
- 节点配置字段与现行骨架只差平台默认值（`singleApprove` 10→0、`agentOneFinishedNotify` 0→9 等），无业务信息。

**FlowParticipant 结构**（801 有 5 条节点执行人）：
```json
{"StepID":510,"DrawID":3,"partOptionCode":"LeaderOfDept","partOptionName":"某部门负责人",
 "description":"某部门负责人：医院办公室（采购办）","DepID":72,"depName":"医院办公室（采购办）","tabCode":"FixedUser"}
{"StepID":511,"DrawID":4,"partOptionCode":"User","partOptionName":"用户",
 "description":"具体某个用户：张霞","UserID":1004,"userName":"张霞","tabCode":"FixedUser"}
```
`UserID`/`DepID` 是环境内主键，本地拿不到；只写名字能否被平台接受未验证 → 暂不自动写，仍列清单让用户配。

**公文表单未支持控件**（09 用到再补）：`docword` 取号、`selectData` 数据选取（`selDataSet.dataTable` 指向目标表）、
`datetimepicker` 时间选择（`dateTimeType: "datetime"`）。

## P14 · 公文表单：业务模块 + 数据选取控件 + 公文属性书签

**日期**：2026-11-28　**版本**：1.3.4　**性质**：能力新增（兼容）

**背景**：用户发来 09 公文表单截图（Web 版公文发文稿纸，左上角红框「发文信息」），
明确三条：①这类截图就是「09 公文表单截图」；②左上角写「发文信息」→ 流程 JSON 的业务模块要选「发文流程」；
③截图里带「选取」的格子要做成数据选取控件，设置照 801 收文导出件。

**1. 业务模块（`modCode`）**

平台导出件里是 `FlowSet.modCode` / `modeCode` / `modeDes` + `FlowKindID`：

| 流程 | modCode | modeDes | FlowKindID |
|---|---|---|---|
| 801 收文 | `docRec` | `wm` | 17 |
| 707 普通表单 | `wm` | `wm` | 9 |
| 发文（本次） | `docSend` | `wm` | 17 |

不写就落 `wm`/`9`，导入后流程挂在「通用」下、公文属性列表不显示。
`docSend` 是从 `docRec` 推的（平台里没有第二个样本），导入后若业务模块显示不对，改 spec 一行即可。
`FlowKindID=17` 同理（801 是 17，公文类沿用）。

**2. 数据选取控件（`selectData`）**

801 五个选取格的结构（逐键照抄）：

```json
{"style":8,"text":"选取","buttonType":"selectdata","bindData":"KM00xx","placeholder":"请输入",
 "buttonName":"选择主办科室","chkName":"…","approveName":"…","options":[],"required":false,
 "localDep":true,"showSign":false,"onlyShowSelected":false,"imageScale":"scale",
 "imageOption":"upload","onlySelectData":true,
 "selDataSet":{"canEditLinkText":false,
   "dataMapping":[{"DataField":"DepName","DataTpe":"string","IsShowColumn":true,
                   "MapField":"KM0014","MapFieldName":"主办科室","Name":"主办科室"}],
   "dataSource":0,"dataTable":"priDepartment","filterCondition":"IsDeleted=0",
   "isAddToRepeatTable":false,"isMutilSelect":true,"orderField":"pcsortidscope","table":""},
 "SheetType":"selectData"}
```

- `text` 写 `选取`（源表单截图里的按钮字），`buttonName` 写「选择XX」；
- 按钮格**自己占一个 bindData 号**（801 里 `选择来文单位` 是 KM0022，取值仍写 `<MapField>`）；
- `dataTable` 取值：科室 `priDepartment`、单位 `DocUnit`、主题词 `wx_6TLN4FG3_Form_0000000088`、
  人员 `priUser`（后两个照 801 推，人员表未实测）；
- `orderField`：`priDepartment` 用 `pcsortidscope`，其它 `id`。

**3. 补位格（`blank`）**

平台要求每行补到最后一列（否则 `validate_form` 报空半行）。源表单里「主题词」「主办科室」
的选取按钮在行中间，右边是空白格 → 用 `blank` 补齐，`blank` 只在 Web 出、移动端跳过。

**4. 公文属性书签（`docUsedBookmarkList`）**

801 有 14 条，把表单字段绑到公文模块标准属性。生成器按 spec 的 `bookmarks` 出：

```json
"bookmarks": [{"label":"公文标题","formField":"Title"},
              {"label":"紧急程度","formField":"Urgent","value":true}]
```

`value:true` 会多出一条 `<label>(值)` → `FormField+"ID"`、`DataMapField+"_Value"`。

**5. 公文发文流程重出**

表单按新截图重排 20 行：首行「流程选用 / 办理时限 / 急件」三组、8 个选取按钮、
「相关公文」右侧「＋添加」、「经办人 / 起草日期」同行。导出包 16 节点 / 27 连线 / 4 条件 /
书签 12 条 / `modCode=docSend` / `FlowKindID=17`。

**注意**：`docSend`、`priUser`、`ToGov`（主送机关的公文属性字段名）都属推断，
主送机关暂**没写进书签**（收文没有主送，无样本），等用户确认字段名再补。

## P15 · 并行分支只在显式标记时插「分流 / 合流」（2026-11-28，对应上游 1.19.2）

**问题**：上游 1.19.2 的 `insert_shunt_converg()` 按「非判断节点出线 >1」自动插分流/合流。
09 流程里这类节点几乎都是**二选一**：

- 审批节点 → `[下一步, 返回修改]`（如公文发文 8/9/10/11）；
- `申请部门负责人审批` → `[无协同科室→下一步, 有协同科室→协同科室审批]`（707 的 2.1.1）。

707 实测自动插：34 节点被撑到 **38**，多出 2 个坐标重合的合流，平台里会变成真并行。

**补丁位置**

1. `scripts/build_export.py` → `insert_shunt_converg(rows, labels=None, only=None)`：
   - `only` 为空直接返回（**默认关闭**）；
   - 分支再过滤：`d["y"] <= f["y"] + 1`（往回走=退回边）、名字/连线文字含
     `返回/退回/终止/结束/不同意/作废/撤销/错误` 的都不算并行；
   - 不足 2 条并行分支就跳过；
   - 非并行出线（退回）保持直连：`f["to"] = [分流] + rest`；
   - 分支改接到合流时，把 `(分支名, 原目标名)` 的连线文字搬到 `(分支名, "合流")`。
2. `scripts/build_export.py` → `build_steps()` 里：
   ```python
   _only = {n["name"] for n in ((form.get("graph") or {}).get("nodes") or [])
            if isinstance(n, dict) and n.get("parallel")}
   rows, _parallel, _moved = insert_shunt_converg(rows, labels, only=_only)
   ```
3. spec 侧：真正并行的分叉节点写 `"parallel": true`（公文发文：`12 院领导签发`）。

**核对基准**（公文发文，2026-11-28）：分流 draw=17 parent='' children=False layer=0；
合流 draw=18 parent='17' children=True layer=1 → 16 结束；13/14 的 `ShuntFirstID` 为自身、
`ShuntParentID=17`；`12.processTo = "17,15"`（分流 + 申请人复核，退回边没被吞）。

**上游另外两处不采用**：骨架删 `flowCode`/`udfName`（本地保留）；`build_flowchart.py`
沟槽/回退边/判断横向出口的修正不退回旧写法。

## P16 · 规则清单按适用范围分家（09 专用 / 通用 / 公文，2026-11-28）

用户要求「区分 09 规则和通用规则」。原清单 25 条混在一起，读的时候分不清
「只在读 09 步骤表时生效」和「任何流程都要遵守」。

**处理原则**

- **编号不动**：R1–R25 原样保留（`SKILL.md`、`RELEASES.md`、提交信息都在引用），新增条目续编 R26–R29；
  公文规则用独立前缀 **G1–G3**，不与通用规则混编。
- **只加分区，不改条文**：同一句话不重写，避免生成器自检与文档脱节。

**三区划分**

| 区 | 条数 | 范围 | 条目 |
|---|---|---|---|
| 一、09 专用 | 17 | 只在「09 步骤表截图」时生效（截图权威、序号层级、下一步骤归属、跳号、未启用、开始→申请人、图标判类型、同名合并） | R1–R14、R24、R24a、R24b |
| 二、通用 | 14 | 任何来源的流程都生效（导出包结构、判断条件、连线文字、表单绑定、并行结构、权限边界） | R15–R23、R25–R29 |
| 三、公文 | 3 | 只在公文类流程（收文/发文）生效 | G1：业务模块 `docSend`/`docRec` + `FlowKindID=17`；G2：数据选取控件；G3：公文属性书签 |

**本次新编号（原为 SKILL.md 里未编号的硬约束）**

| 新号 | 原位置 | 内容 |
|---|---|---|
| R26 | SKILL.md「并行会签必须插分流/合流」 | 并行结构节点 + `parallel:true` 才插 + 退回边直连 |
| R27 | 「无法实现」章节 | 权限分配不在导出 JSON，只有附件权限 |
| R28 | SKILL.md「审批栏之前不要插控件」 | 移动端顺序错位 |
| R29 | SKILL.md「意见框可以和步骤名不同」 | `formField` 显式绑定 |

**两处口径标注（并非新规则，只是写明来源）**

- R13 的兜底「判不出先按 `notice` 并告警」标为「实现约定，待用户确认」——用户原话只给了图标对应关系。
- G1 的 `docSend` / `FlowKindID=17` 标为「推断值，导入后需平台核对」——无平台导出件佐证。

**R7 的实现细节下放**：「删节点后重排 y、给折叠文字留 ≥60px」写在 R7 单元格的括号里，
不作为独立规则，避免把布局参数当业务规则。

## P17 · 公文编码按导出件实证纠正（`docSend` → `doc`/`24`，2026-11-28）

用户给了「流程导出_党组发文流程_v1.0.json」，是**第一份发文流程的平台导出件**，
直接推翻了 1.3.4 里按对称关系推断的 `docSend` / `FlowKindID=17`。

| 项 | 原推断 | 实证 | 证据 |
|---|---|---|---|
| 收文 `modCode` | `docRec` | `docRec` ✓ | 801 收文 |
| 收文 `FlowKindID` | 17 | 17 ✓ | 801 收文 |
| 发文 `modCode` | `docSend` | **`doc`** | 党组发文 |
| 发文 `FlowKindID` | 17 | **`24`** | 党组发文 |

**结论**：`FlowKindID` 不是「公文=17」，而是**每个公文模块一个编号**；`docSend` 从未存在过。
行政发文（非党组）的编码仍未知，**不许再按对称关系猜**，必须等该流程的导出件。

**顺带纠正的三处**

1. 附件权限 `tabCode` 实际是 **`ExtraOperation_AttachAuthor`**（不是 `AttachAuthor`），
   另有 `ExtraOperation_FormPrint`（表单打印）。
2. 主送机关的公文属性字段名是 **`SendGov`**（早期猜 `ToGov` 错了）。
3. 附件说明在党组发文里叫 **`Note`**，801 收文里叫 `Adjunct` —— 属性名固定、字段名随表单变。

**新增的两类不支持**（记进能力边界）

- `nodeFlowChild`（子流程节点，`ActionTypeID=16`）+ 会签回环（5↔8）；
- `select` + `sqlDicType`（平台内置字典 CommonUrgent / CommonSecret）、功能 `button` + `btnClickMode`。

## 无法通过本技能实现的部分（记下来，别再试）

- **流程「权限分配」页（授权对象 / 监控权限 13 项 / 知会权限）不在 `流程导出_*.json` 里**。
  逐键比对平台导出件与本地产物：`FlowSet` 108 键、`FlowSetVersion` 101 键、`FlowSetVersionPart` 42 键**完全一致**（只差 ID/名称/时间戳），全文件搜不到「流程管理员」，也没有 13 位权限布尔数组。
  导出件里唯一与权限有关的只有**附件权限**（`FlowParticipant` 2 条 + `FlowExtraOperation` 2 条，`tabCode=AttachAuthor`），这两处本地生成器已经与平台一致。
  → 权限分配只能在平台「编辑流程 → 权限分配」里配，或等平台提供单独的权限导出格式。
