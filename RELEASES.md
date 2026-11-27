# 版本更迭记录

本仓库使用语义化版本：`主版本.次版本.修订号`。

- 主版本：不兼容的结构调整、口令变更或安装方式变更。
- 次版本：新增能力、新增参考文档、兼容现有用法。
- 修订号：缺陷修复、脚本稳定性、规则补充。

## 1.3.4 - 2026-11-28

公文表单三件套：**业务模块 / 数据选取控件 / 公文属性书签**。

用户给了 09 公文表单截图（左上角红框「发文信息」）并明确：这类截图 = 公文表单，
业务模块要选「发文流程」，截图里带「选取」的格子要做成数据选取控件、设置照 801 收文导出件。

- **业务模块**：`build_export.patch_skeleton()` 支持 `form.modCode`/`modeDes`/`flowKindID`，
  同时写进 `FlowSet` 与 `FlowSetVersion`。收文 `docRec`、发文 `docSend`，公文流程 `FlowKindID=17`
  （普通表单仍是 `wm`/`9`，既有流程行为不变）。
- **数据选取控件**：`build_forms.py` 新增字段类型 `selectData`（`SheetType:"selectData"`、
  `buttonType:"selectdata"`、`selDataSet{dataTable,dataMapping,isMutilSelect,filterCondition,orderField}`），
  结构与 801 导出件逐键一致；`mapTo` 指目标字段，生成时取它的 bindData 当 `MapField`。
  只在 Web 端出（移动端仍用纯文本），`validate_form.py` 同步放行 `selectData` 与
  `buttonName`/`selDataSet` 两个键。
- **补位格**：新增字段类型 `blank`，把一行补齐到最后一列（平台要求封口，不能留空半行）。
- **公文属性书签**：`build_export.build_bookmarks()` 按 spec 的 `bookmarks` 生成
  `TemplateData.docUsedBookmarkList`（`Title`/`DocType`/`Urgent`/`Secret`/`AttNum`/`CcGov`/
  `Keyword`/`Adjunct`/`UserName`/`CDate`，`value:true` 追加 `_Value` 的 `UrgentID`/`SecretID`）；
  `templateData.isFromFlow` 置 `true`。
- **公文发文流程重出**：表单按新截图重排（首行「流程选用/办理时限/急件」、8 个选取按钮、
  相关公文「＋添加」、经办人/起草日期），导出包 `modCode=docSend`、`FlowKindID=17`、书签 12 条。
- 文档：`references/spec-format.md` 新增「公文流程」小节与 `selectData`/`blank` 字段说明；
  `references/flow-export.md` 新增「业务模块编码」「公文属性书签」两节；`SKILL.md` 口令段补公文口径。

## 1.3.3 - 2026-11-28

解析平台导出的 **801 收文流程（2022 年版）**，补上「意见框可不与步骤同名」的绑定能力。

- `build_export.py` 新增 `graph.nodes[].formField`：指定该节点绑哪个意见框，允许与步骤名不同、
  也允许绑表单里没有的流程意见字段（801 实测：`各院领导阅知、责任科室阅办` → `传阅意见`）。
  不写 `formField` 时行为与 1.3.2 完全一致（步骤名全等/宽松匹配，R23）。
- `form_set_ok()` 增加 `form` 参数：有显式声明时，不再因「表单里多出别的意见框」判不通过。
- `references/flow-export.md` 新增「公文类流程实例（801 收文流程）」：7 节点结构、两份 FlowFormSet、
  FlowParticipant 的 `FixedUser` 节点执行人结构（`LeaderOfDept`/`User` + DepID/UserID）、
  公文表单三种未支持控件（`docword` 取号 / `selectData` 数据选取 / `datetimepicker` 时间选择）。
- 澄清 `FlowParticipant` 有两类：附件作者（流程级）与**节点执行人**（`tabCode: FixedUser`，带 StepID/DrawID）；
  后者暂不自动写（DepID/UserID 是环境主键），仍按 R9 列清单让用户在设计器配。
- `SKILL.md`、`references/spec-format.md` 补 `formField` 说明。

**注意**：801 是老版本流程（2022 年），其「执行动作保留成节点 / optStep 只给审批 / 申请人 ActionTypeID=-1」
是历史特征，**不覆盖** R15（执行动作必须折叠）与现行键值写法。

## 1.3.2 - 2026-11-28

按平台导出件校准判断条件写法：**多条取反 `!([1] or [2] …)`、一值一条件（R25）**。

用户上传了一份平台导出的 707 导出件（「这份是对的」），逐字段比对结果：
34 节点 / 50 连线 / `FlowStepPart` / `FlowParticipant` / `FlowExtraOperation` / 表单 `sheet` 全部相同，
只差三处条件写法 + 坐标。三处已全部按导出件修正：

- `build_export.build_conditions()`：多条条件的「其他情况」出口由 `![1] And ![2] …`
  改为平台实测写法 **`!([1] or [2] or …)`**（小写 `or` + 外层括号），
  `ConContentDesc` 同步写「 【取反】（ A 【或者】 B ）」；单条取反仍是 `![1]` / 「 【取反】 说明 」。
- 新增告警：`else` 出口的文字若是字段枚举里的具体取值（不含「其他/错误/否/无/未/空」等兜底词），
  提示改成显式条件（**R25 一值一条件**）。
- 707 spec：`8 判断归口管理部门分管院领导`、`11 判断后续办理` 的「财务科」由排除法
  （`![1] And ![2] And ![3] And ![4]`）改为显式 `[5]`，条件数 15 → **17**。
  导出件核对：`StepCondition` 集合、`ConContent`、`ConContentDesc`、`note` 与平台差异归零（只剩坐标/主键）。
- 文档：`references/action-icons.md` 规则清单 24 → **25 条**（R25 + 707 导出件校准记录，
  R18/R19/R20 按实测更新）；`SKILL.md` 判断段、`references/spec-format.md` 同步。

## 1.3.1 - 2026-11-27

09 规则新增 **R24：同名同执行人步骤合并 + 公共段后补判断**（707 实测 49 步 → 34 步）。

- 多条分支里步骤名称相同、执行人也相同的步骤合并成一个公共步骤；各分支独有前置步骤走完后汇入。
- 合并后后续去向不同时，在公共步骤**后面**加一层判断（同一字段枚举 + `else`）再分流。
- 名称相同但执行人不同（含「财务科 / 规划财务部」这类新旧部门名）不合并，各留节点。
- `references/action-icons.md` 规则清单 23 条 → **24 条**（R24 / R24a / R24b + 707 合并对照表）。
- `SKILL.md` 09 段补合并口径；`LOCAL_PATCHES.md` 新增 P11（含「公共段主轴不能与判断同列」的布局坑）。
- **生成器逻辑零改动**：合并靠 spec 的图组织实现，不上自动合并算法（同名同执行人要人工判断部门改名）。

## 1.3.0 - 2026-11-27

新增 `cols`：Web 视图列数可指定（默认 6），支持 7 列源表。

- `build_forms.table_ncols()` 从 `form["cols"]` 取默认列数（`int(form.get("cols") or 6)`），
  再按重复表列数取最大值；不写 `cols` 的表单行为与之前完全一致（回归核对 408 / 202 仍为 6 列）。
- `references/spec-format.md` 的 `forms[]` 增 `cols` 说明；`SKILL.md` 布局段补一句。
- 实例：605 保卫设备维修安装申请表是 7 列（申请人标签 + 跨 4 列输入 + 申请科室标签 + 输入），
  写 `"cols": 7` 后 `A1:G1`、`B2:E2` 合并正确，Web 视图校验通过。

## 1.2.4 - 2026-11-27

09 规则全量核实、固化成文（纯文档，无生成逻辑改动）。

- `references/action-icons.md` 新增「09 规则清单（23 条）」：读表 R1–R10、开头 R11–R12、类型 R13–R15、
  连边与条件 R16–R23，每条标注来源（用户确认 / 平台实测），并附 408 流程的核对示例。
- 用户 2026-11-27 16:09 逐条确认「1/2/3/4 是对的，5 不需要」：
  重复结束合并（R8）生效；「执行人/步骤说明写入连线 note」明确**不做**（R9）。
- `SKILL.md` 09 段补 R9 并指向 23 条清单；`build_export.py` 自检注释按「补独立申请人节点、第 2 行原样保留」重写。

## 1.2.3 - 2026-11-27

流程开头硬规则 + 判断条件可用角色 SQL。

- `build_export` 自检新增：**流程必须以「开始 → 申请人」开头**（`nodeStart` 唯一后继 = `nodeFirst` 且 `actualName=申请人`），
  不满足直接 FAIL；截图第 2 行（「2 申请人声明」等）**仍按原序号原样生成**，补申请人≠吞掉第 2 行。
- `SKILL.md` 补同一规则，并明确判断节点「下一步骤」为空时默认出口接下一级、另一条出口才跨级。
- 408 信息数据提取流程：「判断申请人是否为信息网络中心人员」条件改为角色 SQL
  （`SELECT COUNT(*) FROM priUserRole … priRole.name LIKE '%信息网络中心%' … <@#SYS://TaskID@>`）。

## 1.2.2 - 2026-11-27

修正流程图「穿框告警」的误报。

- `build_flowchart.find_crossings()` 跳过 `ty < sy - 6` 的**回退边**：这类边渲染时走画布左侧沟槽，
  实际不穿框，但按「两点中点」估算会稳定误报（如 408 流程「病案统计室负责人审核 → 执行人复核」
  报穿过「二级审核」）。
- 同排节点的普通连线也会被当成回退边绕大 U，排版时把上下游错开 80px 以上即可。

## 1.2.1 - 2026-11-27

修正 1.2.0 里对平台「条件步骤」写法的误判——**导入后分支不自动走**的问题。

### 修复 · 连线 ConContent 必须写全

1.2.0 按 422 导出件认定「条件项 ≥2 时 `ConContent` 留空」，实际那份是生成器自己的产物被导回去、
平台只照抄。用户在平台点完「条件步骤」再导出的 403 件里，平台写的是：

| 场景 | `ConContent` | `ConContentDesc` |
|---|---|---|
| 一条边 1 个条件 | `[3]` | ` 条件名 ` |
| 一条边多个条件 | `[1] Or [2]` | ` A 【或者】 B ` |
| 取反支 | `![1]` | ` 【取反】 是 ` |

→ 生成器改为按边归组写全 `ConContent`；`edgeLabels` 写了分支文字时**文字保留、条件绑定照样补**。

### 修复 · processPrev 写全部前驱

汇聚点原来只写第一条入边（`2` 而不是 `2,4`），平台会认为其它来线没接上。现在按升序逗号串写全集。

### 对齐 · 骨架补 flowCode / udfName

`FlowSet` / `FlowSetVersion` 与平台导出件键集合完全一致（各补两个空键）。

### 验收 · 与平台件逐字段零差异

胸牌流程重出后，除 ID / 视图 HTML / 时间戳外，与用户从平台导出的
`流程导出_403胸牌申办、补办及门禁权限申请流程_v1.0.json` **完全一致**。

## 1.2.0 - 2026-11-27

把平台真实导出件里「判断节点带条件规则」的写法吃进生成器：**判断出线不再是空条件，导入后分支直接能跑**。

### 新增 · 判断条件 StepCondition

- spec 里给判断节点写 `conditions`（一条一个值，`to` 指目标）和 `else`（其余情况），
  导出包生成 `FlowExportData.StepCondition`（35 键，与平台导出件逐键一致）：
  左值 `FormVariable`（`KM0004_Value` / `<%#myField\人员类别(值)%>`），右值 `ListVariable`（选项值）/
  `ConstantVariable`（常量）/ 预留 `SQLVariable`（角色 SQL 计数）。
- 连线条件按平台规则写：**只有一个条件项**时 `ConContent` 为 `[1]` / `![1]`（取反）；
  ~~**条件项 ≥ 2** 时留空、`ConContentDesc` 用「 / 」拼各值（平台自己就这么写，别硬给每支塞 `[2]`）~~
  **这条口径是错的，已被 1.2.1 修正：多条件要写 `[1] Or [2]`。**
- `conditions[].to` 可以写在**执行动作**上（图里折叠掉的那种），生成器会自动穿到它的后继节点；
  边没在 `edges` 里写也会自动补，并按条件顺序排出线顺序（`flow_types.expand_conditions()`）。

### 修复 · 判断分支的三处渲染问题

- **三分支节点同名时连线文字串台**：`actualName` 可以重名（三条分支都叫「科主任/护士长（护士）审批」），
  按名字配对会让三支拿到同一句文字。导出侧改用**绘图号**配对，流程图侧新增 `EDGE_LABEL_D` 按 draw 索引。
- **判断「正下方」的分支横穿菱形**：原来一律从右顶点出线，目标在正下方时会先右下再折回，
  横段从菱形下半部穿过、分支文字糊在菱形上；中心差 ≤10px 时改走底顶点直下。
- **分支文字被折成 6 字竖条**：折行原来只看横段宽度（为 0 时每行 6 字），改为每行至少 12 字。

### 对齐 · isValidate

- `FlowSet.isValidate` / `FlowSetVersion.isValidate` 一并置 `true`（平台导出件都是 true），
  导入后不会卡在「流程未验证」。

### 文档

- `references/spec-format.md` 新增「判断条件」；`references/flow-export.md` 新增「StepCondition」并修正
  「`ConContent` 为空 = 没配条件」的解释；`SKILL.md` 判断条件速查补两行；`LOCAL_PATCHES.md` 新增 P5。

## 1.1.0 - 2026-11-26

本轮把「09 流程步骤表截图 → 流程图」的判定规则固化进技能本体：**按图标定类型、执行动作不进节点、没用到的步骤不生成**。

### 新增

- `references/action-icons.md`：**流程步骤图标 → 判定类型对照表**（以用户红字标注为准），
  含「09 步骤表截图识别流程」六条口径：
  ① 按图标判类型，不按步骤名里的「归档/审批/会签」猜；② 「下一步骤」列属于同一行左侧的步骤名，有值照抄（可跳号）、为空默认接下一级；
  ③ 跳号越过且**无入边**的行 = 未启用，不生成；④ 不臆造并行分支，只有用户明确说并行才做两条线；
  ⑤ 无前驱的重复结束节点合并为一个结束；⑥ 同一判断的两支不要一条写全句、另一条写「是」。
- **执行动作（`action`）不生成流程步骤**：`build_export.fold_action_nodes()` 在出包前删掉动作节点，
  前驱直连后继（多出线各自展开），原步骤名写进连线 `FlowStepCon.note` / `ConContentDesc`。
  导出包 `ActionTypeID=4` 必须为 0 个，导入平台后流程图里不会多出绿色方框。
- `SKILL.md` 三条硬约束：09 步骤表没用到的步骤一律不生成；判定为执行动作的步骤导出时不生成节点；选项含「其他」必须补输入框。

### 修复

- **多选择审批被判成审批**：`flow_types._RULES` 按红字改为 通知执行（`notice`）。
- **存档/归档按名字被判成执行动作或通知执行**：名字不算数，一律看图标——绿箭头=执行动作、红人/红箭头=通知执行。
  「请选择是否需要…」类（窗口+人+红斜箭头）此前被判成判断，改为通知执行；判断只认「窗口+▼」。
- **步骤名带层级序号**：`build_export.strip_no()`、`build_flowchart.strip_no()` 统一去掉 `1 `、`5.1.1 ` 这类前缀，
  避免「图上有序号、包里没有」。
- **判断分支连线文字自相矛盾**：取值顺序改为 `graph.edgeLabels` → 折叠掉的执行动作名 → 分支节点名，
  只有「两支且都没语义分支名」的简单是非判断才写「是/否」。
- **相邻同名执行动作连写两次**：`fold_action_nodes()` 折叠时去重，不再出现「不同意，退回申请 → 不同意，退回申请」。

### 变更

- `scripts/build_flowchart.py` 重写执行动作排版：渲染前折叠动作为连线文字（`fold_action_rows()`），
  文字垫画布色底片、横线抬到线上方、竖线居中压线，与节点矩形相交时沿边滑开（`place_action_texts(..., boxes)`）；
  走线分三档（同列短线直连 / 长边与跨半幅走外侧沟槽 / 其余「下-横-下」过避障），回退边统一走左侧沟槽。
- `scripts/build_forms.py` 新增 `lcell()`：`hideWhen` 同时写到**标签格**，避免条件不满足时留下「有标签没控件」的空行；
  自定义行（`row`）类型白名单补 `radio` / `checkbox`。
- `references/field-rules.md`：必填规则改为**源文件优先**（`TemplateSchema` 的 `allownull="false"` 才算必填，
  单选组任一选项 false 即整组必填，源文件无必填信息时才默认全必填）；新增「选项含『其他』补输入框」一节。
- `references/flow-export.md` 补判断分支连线文字取值顺序、步骤名不带层级序号两节。
- `LOCAL_PATCHES.md` 新增 P4（09 判定规则与执行动作折叠）。

### 移除

- 无。

## 1.0.2 - 2026-11-25

### 修复

- **安装脚本漏拷技能脚本**：`common.ps1` 的排除名单里有整个 `scripts` 目录，装完技能里没有 `build_forms.py` 等生成器，
  只能手动补。改为排除仓库管理文件、按白名单复制技能运行脚本（8 个：生成/导出/流程图/预览/校验/灰字扫描/类型库/Word 转换）。
  此前同事安装后「技能目录里 5 个 Python 脚本还是旧版、与 SKILL.md 不匹配」就是这个问题。
- **仓库版本与技能包版本混在一起看不懂**：`VERSION`（仓库）与 `CHANGELOG.md`（上游技能包）编号体系不同，
  安装时只打印 `1.0.1`，容易被当成技能包版本。新增 `SKILL_VERSION` 记录上游包版本，安装输出同时打印两者，
  `README` 补「两套版本号」对照表，`CHANGELOG.md` 顶部注明它不是仓库版本记录。
- **PowerShell 脚本中文乱码、变量名被吞**：7 个 `.ps1` 原为无 BOM 的 UTF-8，Windows PowerShell 5.1 按 GBK 解码，
  安装提示变成 `瀹夎瀹屾垚锛?SkillName`（连 `$SkillName` 都被吞掉）。统一改为 **UTF-8 with BOM**。

### 新增

- **流程节点默认开启「退回」**：审批/通知/动作节点 `isCanReturn=true`（开始、申请人、结束、判断不设）。
  退回类型、具体步骤、意见必填等保持平台默认，不再需要导入后逐个打开开关。

### 变更

- `README` 目录树补 `SKILL_VERSION`、`LOCAL_PATCHES.md`、`USAGE.md` 三项，当前发布版本号改为 1.0.2。
- `LOCAL_PATCHES.md` 新增 P3（退回开关），并标明平台字段名 `isCanReturn`（不是「不同意」的 `isCanReject`）。

### 移除

- 无。

## 1.0.1 - 2026-11-25

### 修复

- **补回 1.0.0 漏掉的四个核心脚本**：`scripts/build_forms.py`、`scripts/build_export.py`、`scripts/build_flowchart.py`、`scripts/render_web_preview.py`。
  根因是 `.gitignore` 里写了 `build_*.py` 和 `render_*.py`，把技能自身的生成器一起忽略了；1.0.0 因此只有校验器、没有生成器，装上跑不了。
- **审批意见框 / 附件不再绑定默认值**：`approve`、`attachment`（含 `sn`/`static`/`label`/`table`）的 `defVal`(移动) / `defaultVal`(Web) 强制留空。
  「部门领导审核」含“部门”二字曾被部门默认值规则命中、绑成 `departmentName`，导致平台前端打不开。
  生成器按控件类型兜底，`default_token()` 的部门排除词补入 审核/领导/批示/签发/会签/核稿/批准/确认/签字。
- **「同意执行」默认选中下一步**：每个步骤补写 `optStep` 与 `importantShunt`。
  非判断节点 `optStep="1"`、判断节点空串；`importantShunt` 为该步骤出线目标的 `DrawID`（多出线按顺序逗号分隔，结束节点空串）。
  此前这两个键被清空/丢弃，导入后审批节点的「同意执行」不选下一步、直接落到「结束」，需逐个手点。
- **生成器侧补上默认值类型拦截**：`field_flags()` 对 `approve`/`attachment`/`sn`/`static`/`label`/`table` 直接返回 `token=None`。
  校验器侧（`validate_form.py`）的「审批/附件带默认值判 FAIL」1.0.0 已包含，本次把它缺失的生成器侧补齐——两边同时兜底。

### 新增

- `LOCAL_PATCHES.md`：记录本仓库相对官方技能包的本地修改（P1 审批默认值守卫、P2 同意执行），以及「流程权限分配无法随 JSON 导出」的比对证据，供升级官方包时逐条复查。
- `USAGE.md`：技能使用说明（环境要求、快速开始、spec 示例、目录、关键规则、平台差异）。
  仓库根 `README.md` 仍保留为安装/更新/回退说明，两者分工不重叠。

### 变更

- `.gitignore` 移除过宽规则 `build_*.py`、`render_*.py`，改为只忽略项目侧产物（`spec_*.json`、`流程导出_*.json`、`run_export_*.py` 等），并在文件内注明原因。
- `SKILL.md` 硬约束新增两条：`optStep`/`importantShunt` 必写；「权限分配」不在流程导出 JSON 里，只能在平台配置。
- 脱敏：`SKILL.md`、`assets/flow_export_skeleton.json`、`assets/web_view_template.txt` 中的真实平台表名统一替换为 `wx_XXXXXXXX_Form_...` 占位。

### 移除

- 无。

## 1.0.0 - 2026-11-24

### 初始发布

- 收纳当前 WorkBuddy 中已生效的 `form-flow-builder` 技能本体。
- 包含技能说明、字段规则、移动端/Web 端 Schema、流程导出参考、公式规则、`.hbx` 与模板 XML 解读参考。
- 包含生成、校验、预览、流程图、灰字提示扫描等脚本。
- 不包含历史备份目录、对话记忆、单次流程规格样本和运行产物。

### 1.0.0 边界说明

- 本仓库只保存可复用技能；具体客户流程、表单元数据、导出 JSON 不作为默认内容入库。
- 如后续补充示例，必须先脱敏，并放在 `examples/` 目录。
