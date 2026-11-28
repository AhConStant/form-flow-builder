# 版本记录

> 本文件是**上游技能包**的版本历史（最新 1.19.2），不是本仓库的发布版本。
> 本仓库的发布版本见 `VERSION` / `RELEASES.md`（当前 1.0.2）；仓库版本与技能包版本的对应关系见 `SKILL_VERSION`。

## 1.19.2 · 2026-11-27

### 修复 · 并行分支缺「分流 / 合流」结构节点

- **并行会签导出后流程图不对**：原来只把两条出线挂在同一个节点上，平台不认并行，导入后缺结构、
  节点也没有 `Shunt*` 属性。新增 `build_export.insert_shunt_converg()`：
  非判断节点出线 >1 自动插「分流（`nodeIsShunt`/14）」，入线 >1 自动插「合流（`nodeToConverg`/15）」，
  并写好 `ShuntFirstID` / `ShuntParentID` / `shuntChildren` / `shuntLayer`、`processPrev` / `processTo`。
- `flow_types.TYPE_META` 新增 `shunt` / `converg`；`classify()` 的 `_SPECIAL` 认「分流」「合流」
  （原来「分流」会命中条件判断的关键词）。
- `importantShunt` 改为**穿过结构节点**写业务上的下一步（新增 `business_next()`）：
  保卫科负责人审批写 `"6,7"`（分支）、人事科会签写 `"8"`（合流之后），不写分流/合流的 DrawID。
- 分流/合流按实测另设一套默认键 `SHUNT_CONVERG_OVERRIDES`（无人员结构节点）：
  `singleApprove=0`、`agreePercent=0.0`、`selUserRange=2`、`unFinishedActive=1`、
  `isCanAssist=False`、`isCanDirectDelivery=True`、`flowTriggerSetMode=0`…；
  且导出件里去掉 `note` 键、`nodeIcon` 不带普通节点那个尾随空格。
- `processPrev` 多前驱写全（合流是 `"6,7"`，原来只写第一个前驱）。
- 终端摘要改按「业务链路」打印（`_chain_rows()` 把结构节点折回连线），不再出现「结束 → 分流」这种顺序。

### 验证

- 用停车优惠申请表的 spec 重新生成，与用户平台改好的导出件逐键比对：
  **除号段（DrawID/StepID/FlowID）与坐标 `nodeStyle` 外零差异**，节点集合与连线拓扑完全一致。

## 1.19.1 · 2026-11-24

### 新增 · 现成双视图原样入包

- `build_export.py` 新增 **`--mobile-view` / `--web-view`**：用户已经做好表单、直接给
  `(移动视图).txt` + `(Web视图).txt` 时，两份视图**原样**嵌进流程包（`mainView` 与
  `templateViewList` 各处一起替换），**不重建控件、不跑 normalize_element、不做 expand_ranges**。
  实测两份文件来自更新的平台版本（`datetimepicker` / `selectUser` / `borderCss` / `isMultiple`），
  按本技能模板规范化反而会改坏，所以照抄。
- 该模式的自检改成**嵌入一致性核对**（`sheet` / `template` / 每个 `templateViewList` 解回来与源文件逐一相等），
  不再用本技能的键名白名单挑刺（否则会被 `datetimepicker` 这类新键判 FAIL）。
- 给了现成视图还带 `--table-name` 直接报错：表单已定稿，重复表名在视图里。

### 新增 · 意见框标题与步骤名不一致时不生成表单设置

- `form_set_ok(steps, web)`：按**去重后的名字**比意见框标题与流程步骤名
  （去掉人名括号和 `·N` 序号；同名节点可复用同一个意见框——源流程里「院长书记审批」出现 18 次）。
  有任何一边对不上 → `FlowFormSet` 留空，并在终端列出「缺意见框的步骤 / 多出的意见框」。
- 依据：用户口径「审批意见框的标题描述和流程步骤的名称不一样的时候不用设置表单设置」——
  硬绑只会绑错，导入后还得逐个人工改。

## 1.19.0 · 2026-11-24

- **Word 灰色字体 = 字段控件提示文字**（用户口径，反复确认）：灰字所在格生成可填写的
  `input`/`textarea`，灰字原文写 `placeholder`（Web 单元格 + 移动端 `properties.placeholder`/`description`），
  **不再生成 `static` 固定说明**。
- 新增 `scripts/scan_gray_hints.py`：扫描 `word/document.xml` 中显式浅灰 RGB 与 Word 主题灰
  （`background1/2 + themeShade/themeTint`），同一段落连续灰 run 合并，输出
  `{table,row,col,label,hint}`；本次组织表实测扫出 5 条。
- `build_forms.py` 的 `field_flags()` 支持 `bind: "none"`：显式关闭默认值绑定，
  避免「药品领用科室/成本核算部门」等命中部门关键词后把灰字 `placeholder` 覆盖成「默认：申请人部门」。
- 同步 `SKILL.md`、`README.md`、`references/field-rules.md`、`source-parsing.md`、`spec-format.md`。
- 本包脚本已包含此前从 1.18.3 备份对齐的能力：`flow_types.py` 的执行动作 `nodeAction/ActionTypeID=4`、
  `build_flowchart.py` 的 `graph.edgeLabels` 连线文字、`build_export.py` 的 `fit_con_name` 连线名截断。

## 文档增补（未打包） · 2026-11-23

- `references/diagram-hbx.md` 补连线文字：hbx 的 `Link/ActivityLink/Description` 才是**连线显示文字**，
  `Expression` 是分支条件，两者分开；只解析 Expression 会漏掉「提交」这类连线标注。
  写入导出包时把 Description 落到 `FlowStepCon` 四字段（`tools/apply_edge_labels.py` + spec `graph.edgeLabels`），
  源为空就留空、不编「同意/不同意」。连线端点映射用 `ActivityId → Node/Text`，
  不用 `Origin/DestinationActivityName`（那是动作名「处理」，会对不上）。
  依据：义诊 hbx 6 条连线 5 条 `Description=提交`、Expression 全空。

- 新增 `references/template-schema-xml.md`：平台**表单模板导出件** `<TemplateSchema>` 的解读参考。
  - 明确定位：模板 XML ≠ 本技能的 sheet 视图 JSON，不能互相替代、不能直接导入。
  - 属性字典 → spec 映射：ref / allownull+errorTipsOnNull / SYS:// 默认值 / udfreadonly / udfNoEnabled /
    udfhide（含 `[ref]!='值'` 条件式）/ customtype=date|approve|datapreview / formula / expression /
    fieldlabel / fieldlabelForChecked / linkcode / AsFlowTitle；明确标出 spec 无对应键的项。
  - 意见栏三件套：可见 approve DIV + 隐藏 `udfvaluetype="approvevalue"` input + `udfvaluetype="approvetemplate"` 模板。
  - 三个真实套路：须知门禁页（隐藏必填空控件当闸门）、按审批节点拆视图（逐视图只读/必填矩阵）、
    无重复表时用后缀 2..5 展开固定明细（先问固定行还是可增行，并主动问是否补总价公式）。
  - 六条模板检查清单（丢 ref / 金额无公式 / 明细写死 / 字段建而不用 / 隐藏仍必填 / 单选必填首项）。
- 依据三份真实样本归纳：稿件发布审核表（`udf_xgjfb`）、举办门诊线下义诊活动备案（`udf_jbmzxxyzhdbab`）、
  院内固定资产调拨单（`udf_gdzc`，3 视图）。
- 新增 `references/diagram-hbx.md`：平台**流程设计器源文件** `.hbx`（`<Diagram Version="14">`）的解读参考。
  - 明确定位：hbx ≠ 流程导出 JSON ≠ 表单模板 XML ≠ sheet 视图，四者各管一层。
  - 结构：Node@Id（绘图序号）vs ActivityId（GUID）、ActivityType 内嵌 XML 需二次解析、
    Link/Origin@Id+Destination@Id 与 ActivityLink/Expression、隐藏的 ActivityProcessMark 跳过。
  - 节点类别与「节点数 ≠ 意见栏数」；分支表达式宏 `myField` / `SYS://` / `UDFΛSQL` / `PrivilegeΛSQL`
    （明确不是 sheet 的 `hideWhen` JS 语法）。
  - **意见栏 ↔ 收意见审批节点一一对应且顺序一致**（义诊 hbx 与表单模板 XML 交叉验证）；
    动作/通知节点不配意见栏。
  - 风险清单：多 TemplateId（患者表 3 个）、退回重审环路（休假表 3 个，主线表达不了）、同名条件节点重复。
- 依据三份真实流程图归纳：门诊患者信息更改申请（12 节点/11 连线）、举办门诊线下义诊活动备案（7/6）、
  全院职工休假报备（69/126，22 条件节点、47 种表达式）。
- `SKILL.md`「第 1 步」新增 XML + hbx 两条分支与资源表条目；`README.md` 目录同步。
  **未改生成器、未改口令流程，v1.17.1 产物行为不变。**

## 1.17.1 · 2026-11-23

- **两段式定稿**（用户口径）：
  **第一段** = 只出 `流程导出_{base}_v1.0_移动视图.json`（移动视图 + 流程图，`sheet` 空、`FlowFormSet` 空）；
  **第二段** = 拿到 `bindTable` 后**只补 Web 视图这一份 sheet**（`{base}(Web视图).txt`，单独导入同一个表单），
  **不重打整包、不重建移动视图、不覆盖第一段产物**。
- 生成器新增 **`--web-only`**：跳过 `build_mobile`，只写 `(Web视图).txt`；配合第一段导出包使用。
  未给表名时明确报「--web-only 仍需先给表名」，不会误产出移动端。
- **单独交付的 `(Web视图).txt` 写盘自动去掉顶层 `events`**（那是流程导出包内嵌 sheet 的形态；
  实测平台单独导出的 Web 视图没有这个键）。`build_export.py` 嵌进包里的那份 `sheet` 仍保留 `events:"{}"`，两种形态各归各位。
- 文档同步：`SKILL.md`（第 0 步、口令表两行、硬约束 2 条、第 4 步两段式）、`README.md`（1/2 节命令）、
  `references/spec-format.md`（命令 + 输出说明）、`references/field-rules.md`、`references/mobile-schema.md`。
- 回归（真实表单：2 张重复表 / 4 个审批栏 / 7 节点）：
  - 第一段 `build_export.py` → exit 3，`sheet` 空、移动 24 控件、FlowStep 7，自检 OK；
  - 第二段 `build_forms.py --table-name ... --web-only` → **只出 1 个文件**（Web txt），25 行 / 28 合并 / 4 审批 / 18 样式，
    顶层无 `events`，校验 1/1 通过；
  - 反向回归：`build_export.py --table-name ...` 仍能出整包（包内 `sheet` 带 `events`、`FlowFormSet` 43 条），
    自检「Web 25 行 / 移动 24 控件 / 流程图 7 节点」OK。

## 1.17.0 · 2026-11-23

- 依平台**成对导出件**（`12(移动视图).txt`、`12(Web视图).txt`、`流程导出_13434_v1.0.json`）反推，把 Web 视图与流程导出包的结构差异全部补齐：
  - **Web 单元格补公式**：`autoCalc`、`hideFormula`（平台实测 Web 格也带，但**没有 `isHidden`**）；
    `decimal` 只写在「带计算式的 inputNum」上；`inputNumDisplay` 的 `SheetType`/`buttonType` 由 `inputNum`/`inputnum`
    改为 **`inputNumDisplay`/`inputnumdisplay`**，并追加 `displayFormat` + `approveDisplayFormat`（￥ / RMB）。
  - **重复表数据格样式 14 → 17**（带框 + `#f2f2f2` 灰底）：`styles` 在模板 17 个之后追加第 18 条；
    跨列加宽时**被覆盖的格子**写 `{style: 17, bindTable}`；序号列也走 17。
  - **移动元素补 `oldTableKey`/`oldTableName`**（平台 9 键，`name` 之后；`build_forms.platform_keys`）。
  - **Web 顶层 `events: "{}"` 保留**（包内嵌形态；单独导出的 Web 视图没有、`rows.len` 是 99 而不是 100，两种都认）。
  - **流程节点改用平台完整默认键集**：新增 `assets/flow_node_defaults.json`（FlowStep 200 键 / 审批 201 键，FlowStepPart 96），
    `build_steps` 以它为底再覆盖 ID/名称/坐标/连线；开始、申请人、结束节点去掉 `note`。
  - **新增 `FlowFormSet`（表单设置）**：申请人节点 = 全部非审批字段（单选/多选/下拉加 `_Value`、数字格式加 `_Label`、
    重复表列带 `parentCode`、说明块占号）+ 每个审批节点一条自己的意见栏（`isComment: true`）。
  - **新增视图绑定**：`FlowSetVersion.DefaultFormViewID / NotifyAuthFormViewID / NotifyUserFormViewID / OtherUserFormViewID`
    = 「主视图」ViewID（`TemplateID + 702`）。
  - `normalize_element` 不再补 `isBuildByCode`（平台回写会丢掉）；`FlowSet` / `FlowSetVersion` 补 `note` 键。
- **SKILL.md 新增「第 0 步」**：收到 Word / Excel / 截图，**先问「有没有重复表」**；有 → 先出移动视图 + 流程图，
  拿到表名后**第二段只出 Web 视图（一份 sheet）**，不再打整包。
- 校验器同步放宽（否则会被自己的规则拦）：`CELL_KEYS` 增 `autoCalc / hideFormula / isHidden / decimal / displayFormat /
  approveDisplayFormat`；`BT_ALIAS` 允许 `inputNum` 配 `inputnumdisplay`；`bindField` 允许中文列名；
  `styles` 允许在模板之后追加；跨列覆盖格允许 `style + bindTable`；`events` 改可选且必须在最后。
- 回归：`12(移动视图)` 逐控件比对 **0 差异**；`12(Web视图)` 仅 `rows.len`（99 vs 100）不同；
  `流程导出_13434` 对比 sheet 顶层键一致、FlowStep/FlowStepPart 键数与顺序一致、FlowSet/FlowSetVersion 键数一致。

## 1.16.0 · 2026-11-22

- 依平台设计器实测导出件（`3333(移动视图).txt`，15 控件）补齐 **4 项能力**，白名单 13 类 → **15 类**：
  - 新增移动控件 **`sn`（流水号）**：专属键 `snFormula`（默认 `[Date:YY]-[NO:____]`）、`snMode`（**必须 = 元素自身 id**，写错编号不生效）。
  - 新增移动控件 **`inputNumDisplay`（数字格式）**：`displayFormat` 实测只有 `￥`（小写金额）/ `RMB`（大写金额）/ 空；取值靠 `autoCalc: join(...)`。
  - 新增 **自动计算 `autoCalc`**：spec 写 `calc`，`{字段名}` → `[tableKey\字段名]`；**仅 `input`/`inputNum`/`inputNumDisplay` 支持**（平台实测只有这 3 类带该键），其他类型生成器直接报错。
    重复表列级 `calc` 的 `{列名}` 自动补成 `[tableKey\表名\列名]`。
  - 新增 **条件隐藏 `hideFormula`**：spec 写 `hideWhen`（JS 表达式，单选/多选判断要带 `(值)`），同时置初始 `isHidden: true`。
- `properties` 新增键一律**按字母序插入**（`put_prop()`）：平台回写就是字母序，两边键序从此一致。
- 校验器放松并加严（`validate_form.py`）：
  - 顶层放行可选键 `bindData`（已绑字段）、`oldTableKey`/`oldTableName`/`isBuildByCode`（平台回写件）——此前遇到带 `bindData` 的真实导出件会误判 FAIL；
  - `properties` 从「与模板逐字节相同」改为「基准键不缺 + 无臆造键 + 提示字母序」，可选键仅限 `autoCalc`/`hideFormula`/`snFormula`/`snMode`/`isBuildByCode`；
  - 新增硬校验：`sn.snMode` = 自身 id、`snFormula` 非空、`inputNumDisplay.displayFormat ∈ {空,￥,RMB}`；
  - 重复表列也按基准键校验（此前只查 label/type）。
- 回归：**平台真实导出件 `3333(移动视图).txt` 现在 1/1 通过**（此前因 `bindData` 必 FAIL）；示例表单 2/2 通过；新示例 `forms_spec.formulas.example.json` 双端通过、`build_export` 自检 OK（Web 11 行 / 移动 13 控件 / 流程 3 节点）；故意写错 `snMode`/`displayFormat` 能被抓出。
- 新增 `references/formulas.md`（引用语法、datediff/sum/join、大小写金额、条件隐藏、流水号、落库后键数）；
  同步 `SKILL.md`（硬约束 + 判断条件速查 + 资源表）、`references/mobile-schema.md`（白名单 15 类、可选键、平台回写两种形态）、
  `references/spec-format.md`（`calc`/`hideWhen`/`format`/`snFormula`，列级同理）、`references/field-rules.md`（判定表 4 行）、`README.md`。
- 说明：`sn` / `inputNumDisplay` 的 **Web 端按钮类型无平台实测样本**，暂按 `input` / `inputnum` 出（SheetType 分别为 `input` / `inputNum`），
  导入后需在设计器里确认这两格的控件类型。

## 1.15.4 · 2026-11-22

- 按用户要求改 **重复表两段式的第二段**：拿到 `bindTable` 后**只补 Web 视图，移动视图沿用第一段**，不再重复 build。
  - `build_forms.py`：第二段检测到移动视图 txt 已存在时跳过 `build_mobile`、不覆盖移动 txt，只生成 `(Web视图).txt`（打印「移动=沿用第一段」）；没有第一段产物（一次性给表名）时仍正常出双端。
  - `build_export.py`：第二段若存在第一段的 `..._v1.0_移动视图.json`，直接复用其中的移动视图 `template`（元素 id 也保持一致），只 `build_web` 补 Web。
  - 依据：移动端重复表元素不携带 `bindTable`，两段的移动视图完全一致，复用安全。
- 回归：`build_forms` 第二段移动 txt mtime 未变（未覆盖）、只出 Web；`build_export` 第二段打印「复用第一段移动视图」、自检 OK；一次性给表名（无第一段）仍出移动+Web。
- 文档同步：`SKILL.md`（硬约束 + 第 4 步两段式）、`README.md`。

## 1.15.3 · 2026-11-22

- 按用户标准改 **起止行的 Web 版式（不再用「至」字）**：
  原来是 `XX开始日期 | 控件 | 至 | XX结束日期 | 控件`；现在是
  **`XX开始日期` | 开始控件 | `XX起止日期`（原字段名，居中标题） | 结束控件（无标签）**。
  - **结束控件 `hideLabel`**：不再生成「XX结束日期」这一格标题（移动端字段名保留，仍带标签）。
  - **原字段名进中间当标题**：`申请担任住院总起止日期` 直接显示在两组日期之间，与 Word 原表一致。
  - 列宽：整组 = 标签 1 + 控件 k + 标题 t + 控件 k（`range_row_spans()`）——
    6 列 2/1/2、7 列 2/2/2、8 列 3/1/3、9 列 3/2/3，两个日期控件始终等宽、整行铺满。
  - 行里还有科室等短字段（显式 `row` 同排）时，先扣掉它们占的列再按上式排；最少需 4 列。
- 删除 `range_ctrl_span()` 的「余列给开始标签」分支（标题吸收了奇偶差，`labelColspan` 保留给手工行用）。
- 回归：示例表单 2/2、`build_export` 自检 OK、6–9 列版式断言通过、重复表两段式 3→0。
- 文档同步：`SKILL.md`（硬约束 + 速查表）、`references/field-rules.md`、`references/web-schema.md`、
  `references/spec-format.md`、`README.md`。

## 1.15.2 · 2026-11-22

- 按用户规则改 **余列归属**：「至」是分隔符，**固定 1 列**，不再吸收奇数列余数。
  除不尽的 1 列按顺序给：①同一行里的其他控件（显式 `row` 与起止同排，如科室）→ ②行里没有其他控件时给「开始」标签。
  - 自动展开（行内只有起止）：6 列 = 标签2/日期1/至1/标签1/日期1、7 列 = 1/2/1/1/2、
    8 列 = 2/2/1/1/2、9 列 = 1/3/1/1/3、10 列 = 2/3/1/1/3。两个日期控件始终**等宽**。
  - 显式 `row` 与科室同排：8 列 = 科室1+控件2 + 开始标签1 + 日期1 + 至1 + 结束标签1 + 日期1；
    9 列 = 科室1+控件1 + 日期2/2 + 至1（余列为 0，不额外加宽）。
- 新增 spec 键 **`labelColspan`**（仅 `row` 内）：标签跨列，生成器把余列并给「开始」标签时写 2；
  `place_row_group()` 登记标签合并，被覆盖格仍是填充格，封口校验照旧通过。
- `expand_ranges()` 改为**保留 spec 里显式写的 `row`**（此前会被覆盖成 `rng0`），起止才能和科室排进同一行；
  同排列数不足时给可读报错（「只剩 N 列（同行的其他字段占了 M 列，至少需 5 列）」）。
  `range_spans()` 拆成 `range_ctrl_span(budget)` + `row_field_span(f)`。
- 回归：示例表单 2/2 通过、`build_export` 自检 OK、流程图 OK、重复表两段式 3→0、手工 8 列 `row` 组仍为 1/1/1/2/1/2。
- 文档同步：`SKILL.md`（硬约束 + 速查表）、`references/field-rules.md`、`references/web-schema.md`、
  `references/spec-format.md`（`range` + `labelColspan`）、`README.md`。

## 1.15.1 · 2026-11-22

- 修 **自动展开的起止日期/时间两框不等宽**（违反 1.14.1「组内必须等宽」硬约束）：
  `expand_ranges()` 原写死 `end_span = max(2, ncols - 4)`，把整行剩余列全给了「结束」——
  6 列表格出 **1 列 / 2 列**，8 列表格出 **1 列 / 4 列**（实测 `E3:H3`，宽度差 4 倍）。
  触发条件：起止那一行只有「开始 / 至 / 结束」三个元素（自动展开后行里没有科室等短字段）。
- 新增 `range_spans(ncols)`：一组固定占「开始标签 1 + 开始控件 k + 至 t + 结束标签 1 + 结束控件 k = ncols」，
  `t = ncols - 2 - 2k`，取能让 `t ∈ {1,2}` 的最大 k —— **两个日期框永远等宽**，奇数余数由「至」吸收，整行铺满不留空半行。
  实测：6 列 1/2/1、7 列 2/1/2、8 列 2/2/2、9 列 3/1/3、10 列 3/2/3，全部通过校验器。
- 手工 `row` 组（科室 + 起止 + 至 + 结束，8 列 1/1/1/2/1/2）不受影响，回归通过。
- 文档同步：`SKILL.md`（硬约束 + 速查表）、`references/field-rules.md`（时间范围 + 布局判定）、
  `references/web-schema.md`（布局规则第 8 条）、`README.md`。

## 1.15.0 · 2026-11-22

- **两个口令的产出收窄（用户标准）**：
  - **「生成表单」** = `build_forms.py` → **只有** `(移动视图).txt` + `(Web视图).txt`。
    配置清单改为 `--notes` 才出；流程图不再随口令生成（要图单独跑 `build_flowchart.py`）；仍不出导出 JSON。
  - **「生成表单流程」** = `build_export.py` → **只有**一个 `流程导出_{base}_v1.0.json`，不出任何 txt。
- **两段式覆盖两个口令**：有重复表时先出移动端，拿到 `bindTable` 再补 Web。
  `build_export.py` 新增两段式支持：不带 `--table-name` 时产出
  `流程导出_{base}_v1.0_移动视图.json` —— `sheet`（Web）为空串，`elements`（移动）与 `FlowStep`（流程图）齐全，
  退出码 **3**；拿到表名后重跑才出完整包（自检会校验 Web 行数 / 移动控件数 / 流程图节点数）。
- 文档同步：`SKILL.md`（口令表 + 第 4 步两段式 + 第 6 步交付口径）、`README.md`、
  `references/spec-format.md`（命令与输出清单）。

## 1.14.1 · 2026-11-22

- 把 1.14.0 的排版规则**提炼成一句可复用的判断**：**「起止日期/时间是一组填写框，组内必须等宽」**。
  - 组 = `开始` + `至` + `结束`，整组占**连续的列**、不跨行拆开；
  - 组内每个日期控件列数相同（各 2 列；列数不够就统一降为各 1 列），**绝不一个 1 列一个 2 列**——
    宽度不等会让填表人误以为两个框填的是不同粒度；
  - 标签与「至」各 1 列，剩余列全给科室。
- 表述同步：`SKILL.md`（硬约束 + 判断条件速查）、`references/field-rules.md`、`references/web-schema.md`（第 8 条）、`README.md`。

## 1.14.0 · 2026-11-22

- 新增**排版规则：一行里多个日期/时间控件「等宽优先」**（用户标准）：
  - 每个日期控件占 **2 列**，彼此列数**必须一致**（不许一个 1 列一个 2 列）；
  - 标签与「至」各 1 列，**剩下的列全给科室**这类短字段；
  - 8 列表格的算法：科室标签 1 + 科室控件 1 + 「排班起止时间」1 + 开始 2 + 「至」1 + 结束 2 = 8；
  - 列数不足 8（如 6 列）时，日期统一降为各 1 列，**不为凑宽而拆行**。
- `colspan`/`hideLabel` 只影响 Web 布局，移动端控件数量与顺序不变。
- 文档同步：`SKILL.md`（硬约束 + 判断条件速查新增两行）、`references/field-rules.md`（布局判定）、
  `references/web-schema.md`（布局规则第 8 条）、`README.md`。

## 1.13.1 · 2026-11-22

- 修 **`bindData` 漏号**：`label` 说明块（如「注：以上两项…」）在 Web 端是纯文字行、没有控件格，
  生成器原先没给它发号，导致其后所有审批栏的 `bindData` 整体**前移一位**——
  实测：说明块应占 `KM0004`，「科室考核意见」应为 `KM0005`，而输出是 `KM0004`。
  现在 `place_static()` 遇到 `label` 先 `nb()` 占号再写行；`static`（纯 Web 装饰）与重复表仍不占号。
- 编号规则写进文档：`references/web-schema.md`（bindData 段落）、`SKILL.md`（硬约束）、`README.md`。

## 1.13.0 · 2026-11-22

- 新增**审批栏顺序告警**（实测踩坑后补的）：移动视图在审批意见栏**之前**出现说明块（`label`）时，
  `build_forms.py` 会在终端打印告警，并写进 `(配置清单).md` 的「待确认项」——提示**导入后要在表单设计器里重绑审批框**。
  - 实测经过：一张表里加「注：…」的 `label` 后，两个意见框在移动端从第 6/7 位变第 7/8 位，
    平台按控件顺序自动配对「第 N 个意见框 ↔ 第 N 个审批节点」，两个框整体错位。
  - 排查结论：文件侧 `approveKey` 一直是正确的（与 `assets/mobile_view_reference.txt` 的 approve 控件 69 个属性逐个相等），
    Web 视图在该改动前后**逐字节一致**（`rows`/`merges`/`tables`/`approves` 全等），所以错位只可能来自移动端元素顺序。
  - `static` 只出 Web、不占移动端顺序，不触发告警（已验证：注放在审批栏之后或无说明块时不误报）。
- 文档同步：`SKILL.md`（硬约束 + 第 6 步交付检查）、`references/field-rules.md`（第八节流程节点）、`README.md`。

## 1.12.0 · 2026-11-22

- **重复表列里的起止时间改为自动拆两列**（原规定是「一列只能挂一个控件、不拆、占位提示写清格式」）：
  `{"label": "代住院总排班起止时间", "type": "datepicker"}` → 相邻两列
  `代住院总排班开始时间` / `代住院总排班结束时间`。表里加不了「至」列（一个数据格只能挂一个控件），
  所以用两列表达范围；命名规则与主表一致（前缀不动，`起止` → `开始`/`结束`，后缀保留）。
- 拆列在 `table_ncols()` **之前**执行：主表的时间范围按最终列数排版（`结束` 的 `colspan` 自动跟着列数走），
  不会留空半行；该表列数 +1 后，其他重复表按 1.11.0 的加宽规则对齐最宽表。
- 文档同步：`SKILL.md`（硬约束 + 判断条件速查）、`references/field-rules.md`（时间范围条目）、
  `references/spec-format.md`（`columns` 表新增 `range`/「起止」行）。

## 1.11.0 · 2026-11-22

- **多张重复表列数不齐改为自动加宽**（原先是直接报错）：整表按最宽者排版，缺 N 列就从**右侧**挑 N 个
  非序号列，各设为 `span=2`（表头与数据格都登记合并，被覆盖格补边框样式保证封口）。
  8+7 → 备注占两列；8+6 → 时长、备注各占两列。移动端列数不变。
- 校验器配套放宽：被合并覆盖的数据格（非左上锚点）不再要求带 `bindTable`。

## 1.10.0 · 2026-11-22

- **时间范围自动拆分**：`{"label":"排班起止时间","type":"datepicker"}` 自动变成
  `排班开始时间` + `至` + `排班结束时间` 两个日期控件，同一行；也支持显式 `"range": true`。
  命名规则：前缀不动，`起止` → `开始`/`结束`，后缀保留（时间/日期）。移动端出两个日期控件，Web 端「至」为 1 列静态文字。
- 修 **`place_row_group` 跨列控件不登记合并**：自定义行里 `colspan>1` 的控件只写了 `cell.merge`、没写进 `merges[]`，
  导致右侧成无边框填充格（空半行 + 未封口）。范围行用到 `colspan` 才暴露，已修。
- 重复表列里的起止不拆（一列只能挂一个控件），文档已注明。
- `住院总上岗` 的 spec 同步改成单个 `申请担任住院总起止日期` 字段。

## 1.9.3 · 2026-11-22

代码自检（静态扫描 + 全链路回归 + 逐函数审读）后修的问题：

- **`build_export` 缺 `--table-name`**：含重复表的表单跑「生成表单流程」直接失败（`重复表未绑定表名`）。
  已补参数与应用逻辑，多表写 `--table-name 字段名=表名`。
- **判断节点分支数不检查**：判断只有 1 条（或 0 条）出边时静默成一条直线。现在流程图与导出都会提示
  「判断节点「X」只有 N 条分支」。
- **配置清单漏流程节点**：spec 用 `graph`/`flow` 时，清单里的「流程节点」段是空的（只按 approve 字段倒推）。
  现在按动作类型列全节点，并注明分支见 `graph.edges`。
- 删除死代码：`build_forms.flags()`（已被 `field_flags` 取代）、`build_flowchart.from_export()`（逻辑已内联）。
- 修重复提示：`flow` 路径下「判断分支数」提示被打印两次。

## 1.9.2 · 2026-11-22

- **修坐标解析**：`layout_from_steps` 的正则被写坏（`\s` 变成 `//s`），`--from-export` 时所有节点坐标解析成 (0,0)，
  画出来全部叠在一起。已修（这也是排查「会不会叠加」时实测出来的）。
- 新增**排版自检**：出图前算节点矩形两两求交，**重叠即失败**（退出码 1、不写文件）；连线穿框只提示；节点重名直接报错。
- `build_export` 增加坐标重复检查（两节点 x/y 完全相同 → 告警「导入后会叠在一起」）。
- 补回被误删的 `flow_types.layout_graph()`（无坐标 graph 的分层布局）与 `assert_unique()`。

## 1.9.1 · 2026-11-22

- 修 **流程名称**：平台导入弹窗里的「流程名称」读的是 `FlowExportData.FlowSet.name`，之前只改了 `FlowSetVersion.name`，
  导致导入后仍显示骨架里那张表的名字。现在 `FlowSet.name` / `FlowSetVersion.name` / `templateData.name` 三处统一写成当前表单名。

## 1.9.0 · 2026-11-22

- **交付口令改名**：「导出表单」→**「生成表单」**，「导出流程」→**「生成表单流程」**；
  SKILL.md 口令表、`description` 触发词、README 同步（CHANGELOG 旧条目保留历史原样）。
- **格式参考与骨架内置**，用户不必再上传样例文件：
  - `assets/mobile_view_reference.txt`（22 控件成品，含 label/approve/textarea/datepicker/inputNum）
  - `assets/web_view_reference.txt`（21 行成品，含审批栏 80、无框说明、多次合并）
  - `assets/flow_export_skeleton.json`（流程导出结构骨架 35 KB）
  - `build_export.py` 的 `--base-export` 改为**可选**，默认用内置骨架；只有跨环境复刻时才让用户给导出件。

## 1.8.0 · 2026-11-22

- 流程图支持**复杂图**：spec 新增 `graph`（nodes 可带 x/y + edges），三路以上分支、嵌套判断都能排；
  不给坐标时走 `layout_graph()` 分层布局（最长路径分层 + 同层左右展开）。
- 跨层长边（跳过中间层）改走**画布外侧沟槽**，不再穿过中间节点。
- 判断菱形加宽到 184×96，长标签不再溢出菱形。
- 修 **连线缺失**：`draw_edge` 之前只画到折线倒数第二点，两点直边（最常见）会退化成「只有箭头没有线」。
- `build_export`：`stepName` 统一取**实际写入的 node 编码对应类型名**（存档兜底成通知执行时 stepName 也写「通知执行」，不再自相矛盾）。
- 动作链路文本支持 3 条以上分支（原来只列前两条）。

## 1.7.0 · 2026-11-22

- 新增 **`scripts/flow_types.py`**：动作名称 → 动作类型 → node 编码 / 画布形状 / 自动布局。
  - 覆盖平台 7 类动作：审批、多选择审批、通知执行、条件判断、存档、生成处理签、通知申请人或执行动作；
    另有 开始/申请人/结束 三个特殊名。
  - 判定顺序「条件判断 → 多选择 → 存档 → 处理签 → 空步骤 → 审批 → 通知」，避免「科主任审批意见多选择」被判成审批。
  - **兜底：判不出来按「通知执行」**（用户规则），导出写 `nodeNotice`/`ActionTypeID=3` 并回告警。
  - 只有 审批(2)/通知(3)/判断(6)/起止(0) 是实测编码；存档、处理签、空步骤、多选择标注为推断/未实测。
- `build_flowchart.py`：新增 多选/存档/处理签/空步骤 四种配色；spec 支持 `flow` 数组，判断节点自动布局成左右分支再汇聚。
- `build_export.py`：按动作类型写 `node`/`ActionTypeID`/`stepName`，`processTo` 支持多目标（分支）；
  主表名改为尾部号段自增并保留前导零（`..._0000000564` → `..._0000000565`）。
- 修：`action_type=0` 曾被 `or` 兜底成 3，导致 开始/申请人/结束 的 ActionTypeID 错写成通知执行。

## 1.6.0 · 2026-11-22

- 流程图支持**判断（分支）与通知执行**节点：`nodeJudge` 画菱形、`nodeNotice` 画绿色矩形带喇叭，审批仍带「审」徽标。
- `--from-export` 改为**按画布坐标渲染**（原来只沿 `processTo` 串主线、遇分支只画第一条）：
  正交折线、多条入边汇聚到同一节点、分支走线留 30px 净空避开徽标；菱形窄于矩形，左缘补差保持同列居中。
- 解析结论写进 `flow-export.md`：节点类型 ↔ `ActionTypeID`（0 起止/2 审批/3 通知/6 判断）、
  分支目标在 `processTo` 与 `importantShunt`、**`ConContent` 为空表示分支没配条件**、
  **`FlowStepPart` 会残留已删节点**（6 个节点 10 条 Part，数节点只认 `FlowStep`）。
- 修 bug：网格层 `width="100%%"` 未参与格式化，导致 `url(#g50)`/`url(#g10)` 两层背景一直没生效，画布是纯色底。

## 1.5.1 · 2026-11-22

- 写入**交付口令**（`SKILL.md` 顶部，优先于其他流程判断）：
  - 「**导出表单**」= `build_forms.py` → 移动视图 + Web 视图 + 配置清单 + 流程图，**明确不生成流程导出 JSON**；
  - 「**导出流程**」= `build_export.py --base-export …` → **一个** `流程导出_{base}_v1.0.json`，内含 sheet(Web) + elements(移动) + FlowStep(流程图)，不再单独出 txt。
  - 两个口令都要求先解析完 Word、spec 就绪、重复表 `bindTable` 到位；「导出流程」还必须有平台导出件当骨架，没有就问用户要，不许凭空造。
- `description` 触发词补上「导出表单」「导出流程」；README 增加口令对照表。

## 1.5.0 · 2026-11-22

- 新增 **`scripts/build_export.py`**：按平台「流程导出」格式打包，一个 JSON 同时装下
  Web 视图（`TemplateData.mainView.sheet`）、移动视图（`mainView.template.elements`）、流程图（`FlowExportData.FlowStep`）。
  - 两处 `sheet` / `template` 按平台规则写成 **JSON 字符串**；输出紧凑单行、无 BOM。
  - 移动元素自动规范化成平台回写后的形状（9 顶层键 + `properties.isBuildByCode` + 字母序）。
  - 生成后自动回抽 `sheet`/`elements` 过校验器、核对节点数，自检不过返回 1。
  - ID 段可传 `--flow-id` / `--template-id` / `--table`，默认给占位号段。
  - 踩坑修正：`templateViewList` 里每视图各存一份 `sheet`/`template`，必须一起替换（否则旧表单的字段与重复表名残留 30 处）；`isMain` 是布尔不是字符串；`mainView.ViewID` 必须等于 `isMain=True` 那条的 `ViewID`。
- 实测回写差异（写进 `flow-export.md` / `mobile-schema.md`）：Web 视图逐字节不变；移动视图被补
  `oldTableKey`/`oldTableName`/`isBuildByCode` 并按键名排序；我们提交的 7 键/66 属性平台照样接受。

## 1.4.1 · 2026-11-22

- spec 新增 `bind` 键：强制默认值绑定 `user`/`dept`/`date`/`login`/`phone`，覆盖按字段名的自动判定。
  解决「科别」「所在单位」这类不含「科室/部门」关键词、但确实要带 `departmentName` 的字段。
- `flags()` 拆出 `field_flags(f)`：先看 `bind`，再落回字段名推断；移动端、Web 端、配置清单三处同步。

## 1.4.0 · 2026-11-22

- 新增 **`scripts/build_flowchart.py`**：按表单的审批意见栏生成流程图（SVG + HTML），样式对齐平台流程设计器（网格底、青绿箭头、圆角胶囊、审批节点右上角「审」徽标、节点内对勾）。
  - `spec.json` 模式：开始 → 申请人 → 每个 `approve` 字段（按字段顺序）→ 结束，不手画。
  - `--from-export` 模式：读平台流程导出 JSON（`FlowExportData.FlowStep` 的 `actualName`/`node`/`processTo`）还原真实流程，用于核对。
  - 两条路产出应逐字节一致；不一致即表单意见栏与平台节点没对齐。
- 新增 `references/flow-export.md`：流程导出 JSON 的解析笔记（只 3 个分节与流程图有关、`actualName` 才是画布显示名、`nodeStyle` 坐标规律 top 每次 +120）。
- 交付步骤增加「附流程图 + 与导出比对」。

## 1.3.0 · 2026-11-22

- 静态说明新增 **`variant: "plain"`（style 2 无框）**：Word 正文里的「说明」段落本来就不在表格框内，Web 端不再套四边框，与 Word 版式一致；表内注/分节标题仍用 `note`/`section`（带框）。
- 校验器：**全宽单格无框说明行**（style 2、`A:最后列`、有文字）跳过封口/空半行判定，并在结果里输出「提示: 行X 为无框说明行」；只跨部分列的无框行仍判 FAIL，不会放宽表格完整性检查。
- 生成器内联校验同步：`提示:` 视为不阻断（此前会被当成 FAIL、拒绝写文件）。
- **多张重复表**：同一个 `w:tbl` 里并排两张明细表时，生成器校验「每张表列数 == 整表列数」，不齐直接给出可操作报错（改回单列 / 补空列 / 拆表），不再产出右侧空列、封不了口的 JSON。
- **报错改成一行结论**：`main()` 捕获 `ValueError` / `FileNotFoundError`，不再抛 Python 堆栈。
- 文档整理：`field-rules.md`（label/plain/审批 80/多表对齐/单列起止取舍）、`source-parsing.md`（表头出现两次=两张表）、`SKILL.md`（硬约束、执行流程、速查表）、`README.md`（版本与关键规则）同步。

## 1.2.1 · 2026-11-22

- Web 端**审批意见栏行高默认 80**：`approve` 整行从 80 起（原来按文字估算只有 40 左右）；标签在 A 列折行过多时按行数继续抬高（`approve_row_height`，≥3 行才超过 80）。spec 显式写 `height` 仍优先。

## 1.2.0 · 2026-11-22

- 移动端新增 **`label` 控件**（第 13 类，`form_layout_tool_label` / `t_label_black`）：说明段落两端都出——移动端正文写进 `properties.description`（`\n` 分行、末尾补 `\n`），Web 端仍逐行静态行。`static` 保持只出 Web（分节标题、表内注、行内碎片）。
- 修复 `row` 内**静态文字 `colspan` 不生成合并**的缺陷：跨列不写 merge 会让右侧留无边框填充格，触发「空半行 / 表格未封口」校验失败。
- 校验器：重复表列类型改用独立白名单 `TABLE_COL_TYPES`，`label` 不能当列。

## 1.1.1 · 2026-11-22

- 新增 **表格封口 / 空半行** 校验：每行左/右边框必须闭合；内容提前结束、右侧只剩无边框填充（style 2）的判 FAIL。
- 短字段末行按实际字段数平均分配列宽、铺满整行，生成器不再产出空半行。
- 生成器改为**写文件前先在内存校验 Web 视图**，校验不通过直接 FAIL、不落盘，避免先出文件再返工。

## 1.1.0 · 2026-11-22

- 重复表改为两段式：先移动端 → 每次重新索取 `bindTable` → 再 Web；spec 里的 `tableName` 忽略，未绑定时删除旧 Web 并生成 `(待绑定重复表).md`。
- Web 重复表：`tables[].tableRange` 指向数据行，`bindTable` + `bindField`（KC0001 起），`showNumber` = 序号列位置（1 起）；序号列数据格只留 `style` + `bindTable`。
- 移动端序号列不生成（平台自带）。
- 新增布局能力：`row` / `hideLabel` / `colspan`（一行多段）、`fullRow`（任意字段整行）。
- 标题、重复表表头、字段标签：居中 + 自动换行。
- 行高按文字自动适配（×1.3 安全系数），支持 `height` 整行、`lineHeights` 逐行指定；静态说明逐行生成并带四边框。
- 默认值改为平台实际键：移动 `defVal` / Web `defaultVal`；姓名→`currentUserName`、工号→`loginID`、科室/部门→`departmentName`、申请日期→`currentDateTime`/`currentDate`、电话/手机/联系方式→`mobile`。
- 校验器同步：`defaultVal`、`showNumber`、序号样式格、重复表覆盖、行高正整数、模板 17 样式。

## 1.0.0 · 2026-11-21

- 首版：spec → 移动视图 + Web 视图 + 配置清单；6 列标准布局、12 类移动控件、审批栏、静态说明、校验器与 PNG 预览。
