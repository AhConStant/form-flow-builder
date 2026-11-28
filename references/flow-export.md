# 平台流程导出 JSON（流程图解析）

平台「流程设计器 → 导出」得到的文件，两个顶层键：

```
{ "FlowExportData": {...}, "TemplateData": {...} }
```

`TemplateData` 是表单模板，画流程图用不到。`FlowExportData` 里有几十个分节，**只有 3 个跟流程图有关**：

| 键 | 类型 | 用途 |
|---|---|---|
| `FlowStep` | list | 节点数组，一个元素 = 画布上一个节点 |
| `FlowStepCon` | list | 连线（含条件、按钮文案） |
| `FlowParticipant` | list | 附件作者（流程级）+ **各节点执行人**（`tabCode: FixedUser`，带 StepID/DrawID） |

## FlowStep 里要用的字段

单节点 200 个字段，画图只需要这几个：

| 字段 | 含义 | 例 |
|---|---|---|
| `DrawID` | 画布节点序号（连线按它引用） | `3` |
| `StepID` | 节点业务 ID | `64546` |
| `stepName` | 节点模板名 | `审批` |
| `actualName` | **画布上显示的名字** | `科室考核意见` |
| `node` | 节点类型：`nodeStart` / `nodeFirst` / `nodeApprove` / `nodeEnd` | `nodeApprove` |
| `nodeStyle` | 画布坐标 `left:460px;top:340px;` | |
| `processTo` | 后继 `DrawID`（多个用逗号分隔） | `4` |
| `processPrev` | 前驱 `DrawID`，**多个用逗号分隔**（汇聚点写成 `3,5,6`，只写第一条平台会认为别的来线没接上） | `2` |
| `shuntNext` / `shuntLayer` | 是否分流/分支；非 0 表示有分支 | `0` |

> `stepName` 是模板名（都是「审批」），**名字要用 `actualName`**。

## FlowStepCon（可选）

`DrawID` → `NextDrawID` 的连线，带 `tabCode`（`nodeStart` / `nodeFirst` / `nodeApprove`）、
`ConContent`（条件表达式，空 = 无条件）、`nextStepName`（按钮/分支名）。
做线性主线时用 `FlowStep.processTo` 就够；要画条件分支时才需要读 `ConContent`。

## 实测样例（代住院总医师排班备案审批表 v1.0）

| DrawID | actualName | node | nodeStyle |
|---|---|---|---|
| 1 | 开始 | nodeStart | left:460px;top:100px; |
| 2 | 申请人 | nodeFirst | left:460px;top:220px; |
| 3 | 科室考核意见 | nodeApprove | left:460px;top:340px; |
| 4 | 医务科审核报备意见 | nodeApprove | left:460px;top:460px; |
| 5 | 结束 | nodeEnd | left:460px;top:580px; |

规律：**竖直排布，top 每次 +120，left 固定**；节点宽约 176、审批节点右上角带「审」徽标。

## TemplateData：导出包里同时装着两个视图

`TemplateData` 不是表单模板那么简单，**Web 视图和移动视图都在里面**：

| 键 | 内容 |
|---|---|
| `mainTableName` | 主表名 `wx_XXXXXXXX_Form_0000000123`（重复表是它的 `_0001/_0002`） |
| `mainView.sheet` | **Web 视图（Luckysheet JSON）**，但存成**字符串**，要 `json.loads` 一次 |
| `mainView.template` | **移动视图**，同样是字符串，形如 `{"elements":[...],"script":""}` |
| `templateViewList` | 视图清单（数据定义 / 主视图，各有 ViewID） |
| `templateData` | 表单元信息：`name`、`TemplateID`、`CDate` |

> 两个字段都是 JSON 字符串，直接 `["sheet"]["name"]` 会报 `'str' object has no attribute`。

> **坑：`templateViewList` 里每个视图都自带一份完整的 `sheet` + `template`**（主视图、数据定义各一份）。
> 只换 `mainView` 不换这里，旧表单的字段和 `bindTable` 会留在包里——实测残留过 30 处旧重复表名。
> 另外 `isMain` 在骨架里是**布尔** `True/False`，不是字符串，判断时别直接比 `"True"`。
> `mainView.ViewID` 要等于 `isMain=True` 那条的 `ViewID`。

### 实测：回写后哪里会变（重要）

把生成的表单导进平台、再导出回来，逐字节比对过：

- **Web 视图完全一致**：`styles` / `cols` / `rows` / `merges` / `tables` / `approves` 全部相同，不需要加工。
- **移动视图会被规范化**，每个元素：
  - 顶层多两个键 `oldTableKey`、`oldTableName`（位置在 `name` 与 `properties` 之间），共 9 个键；
  - `properties` 多一个 `isBuildByCode`（值 `false`），且**所有键按字母序重排**；
  - 普通控件 67 个属性、`approve` 70 个、`table` 67 个。
- 我们提交 7 键 / 66 属性的形态**平台照样接受**，只是回写时会补成上面这份形状。

## 节点类型（不只审批一种）

平台的动作列表里，**「动作名称」是用户随手起的，「动作类型」才是语义**。实测对照（来自设计器动作清单）：

| 动作名称（示例） | 动作类型 |
|---|---|
| 审批、科室初审意见、主管院领导审核意见、职能科审核意见、主管领导审批、健教科审批、初审意见、科主任审批意见、主管部门审批、主管领导审批意见 | **审批** |
| 通知执行、稿件发布执行、资料制作情况 | **通知执行** |
| 判断送审科室 | **条件判断** |
| 多选择审批、科主任审批意见多选择、主管部分审批多选择 | **多选择审批** |
| 空步骤 | 通知申请人或执行动作 |
| 存档 | 存档 |
| 生成处理签 | 生成处理签 |

> 注意「稿件发布执行」「资料制作情况」这类**看着像业务审批、实际是通知执行**的名字——
> 不能只看「意见/审批」二字，要按动作类型判。

### 类型 ↔ 画布/编码（`scripts/flow_types.py`）

| 类型 | `node` | `ActionTypeID` | 形状 | 编码来源 |
|---|---|---|---|---|
| 审批 | `nodeApprove` | 2 | 圆角矩形 + 「审」徽标 | 实测 |
| 通知执行 | `nodeNotice` | 3 | 绿色矩形 + 喇叭 | 实测 |
| 条件判断 | `nodeJudge` | 6 | 菱形（暖色） | 实测 |
| 开始 / 申请人 / 结束 | `nodeStart` / `nodeFirst` / `nodeEnd` | 0 | 胶囊 / 矩形 / 胶囊 | 实测 |
| 多选择审批 | `nodeApprove` | 2 | 矩形 + 「多」徽标 | 推断（仍按审批写） |
| 存档 | — | — | 灰色矩形 | **未实测** |
| 生成处理签 | — | — | 紫色矩形 | **未实测** |
| 通知申请人或执行动作 | — | — | 青色矩形 | **未实测** |

**判定顺序**（先判特殊、再判通用，否则「科主任审批意见多选择」会被判成审批）：

```
条件判断 → 多选择 → 存档 → 生成处理签 → 空步骤 → 审批 → 通知执行 → 兜底
```

**兜底规则（用户明确要求）**：名称判不出类型时，**先按「通知执行」处理**——
画布画成绿色通知节点，导出时写 `nodeNotice` / `ActionTypeID=3`，并在输出里回一条告警。

### spec 里怎么描述流程

默认是按 `approve` 字段推主线；要显式写判断/通知，就在 form 上加 `flow`：

```json
"flow": ["开始", "申请人", "判断送审科室", "通知执行", "科室考核意见", "结束"]
```

- 字符串写法按名称自动判类型；要强制类型写 `"条件判断:判断送审科室"`。
- **判断节点后面紧跟的两项 = 左右分支**，再往后的节点是两支的汇聚点。
- 导出（`build_export.py`）会用同一份布局填 `nodeStyle` / `processTo`，保证图和包一致。

## 分支怎么表达
- `processTo` 是**逗号分隔的多个 DrawID**（如 `"8,10"`），`importantShunt` 存同一份目标列表；
- `FlowStepCon` 里对应有两条连线，`tabCode` 都是源节点的类型（`nodeJudge`）；
- **`ConContent` 为空 = 这条分支没有引用条件项**：平台「条件步骤」是空的，运行时不会自动分流
  （2026-11-27 用户反馈「条件因子有了、条件步骤没生成」就是这里空着）。一条边挂多个条件时
  **按 `[1] Or [2]` 串起来**，不能留空——留空时 `ConContentDesc` 只是显示文字，不参与判断。
  判断节点只做分流、没设条件表达式时两条分支全空，画图时**不要自己编「是/否」标签**，
  直接在输出里提示「分支条件为空」。要让它导入即能跑，就在 spec 里给判断节点写 `conditions`（见下）。
- 判断分支的连线文字（`FlowStepCon.note`）取值顺序：`graph.edgeLabels`（手写）→ 折叠掉的执行动作步骤名 →
  分支节点自己的名字（`label`，即「包含院领导、中层干部、护士长，转院领导审批」这类条件句）。
  **只有「两支 + 两条都没有语义分支名」的简单是非判断才写「是/否」**；
  同一个判断里不能一条写全句、另一条写「是」，那是自相矛盾（用户 2026-11-26 指出）。
  实现见 `build_export.build_steps()` 里的 `named_branch`。

### StepCondition：判断条件（2026-11-27 实测 422 / 403 导出件）

平台把判断规则存在 `FlowExportData.StepCondition`（35 键，一行 = 一个条件项），**与连线 `ConContent` 的 `[n]` 对应**：

| 键 | 值 | 说明 |
|---|---|---|
| `DrawID` / `StepID` | 判断节点的号 | 写判断节点自己的，不是目标的 |
| `jIdentity` | `[1]` `[2]` … | 条件序号，连线 `ConContent` 用它引用 |
| `compareType` | `eq` / `lt` / `ne` / `gt` … | |
| `leftVarType` | `FormVariable` | 左值 = 表单字段 |
| `leftVarCode` | `KM0004_Value` | 单选/多选/下拉带 `_Value` 后缀，普通字段不带 |
| `leftVarName` | `<%#myField\人员类别(值)%>` | 字段名后面同样带 `(值)` |
| `leftDescription` | `表单变量：人员类别(值)` | |
| `rightVarType` | `ListVariable` / `ConstantVariable` / `SQLVariable` | |
| `rightVarCode` / `rightVarName` | `医技药人员` | 集合变量的码 = 名 |
| `rightDescription` | `集合变量：【人员类别】医技药人员` | |
| `tabCode` / `variFilterType` | `BaseJudge` / `Default` | 固定 |

三种右值实测都有实例：`ListVariable`（选项值，最常用）、`ConstantVariable`（`leftVarCode=0`、
`leftVarName=<@%Int://0@>`、`compareType=lt`）、`SQLVariable`（`rightVarCode` 存整段 SQL，数角色条数）。

连线侧写法（2026-11-27 实测 403 平台件）：

| 场景 | `ConContent` | `ConContentDesc` |
|---|---|---|
| 一条边挂 **1 个**条件 | `[3]` | ` 新入职初次添加权限 ` |
| 一条边挂 **多个**条件 | `[1] Or [2]`（` Or ` 分隔，顺序=jIdentity） | 各值用「 【或者】 」连：` 遗失 【或者】 损坏（…） ` |
| 取反支（else / 否） | `![1]`（多条件时推得 `![1] And ![2]`，未实测） | ` 【取反】 是 ` |
| 没有条件（人工选分支） | 空 | 分支文字 |

`ConContent` 是**真正的判断表达式**，`ConContentDesc` 只是画布/详情里给人看的文字。
早前从 422 导出件得出「条件项 ≥2 就留空」是错的——那份是生成器自己的产物被导回来，
用户在平台里手工点完「条件步骤」再导出（403 件）才露出真实写法 `[1] Or [2]`。
`FlowStepCon.note` 不受影响，多条件仍可写「A / B」。

spec 侧写法见 `spec-format.md` 的「判断条件」；`build_export.build_conditions()` 负责生成条件行与连线文字，
`flow_types.expand_conditions()` 负责把 `conditions[].to` 补成边并按条件顺序排出线顺序。
条件的目标可以写在执行动作上（图里折叠的那种），生成器会穿到它的后继节点。

> `isValidate`：平台导出件里 `FlowSet` / `FlowSetVersion` 都是 `true`（流程已验证），
> 生成器已对齐；骨架默认 `false`，导入后可能卡在「未验证」。

## 并行分支：分流 / 合流结构节点（1.19.2 / 本地 1.3.5）

多个节点**同时**处理（会签、并行审批）时，不能只把两条线挂在同一个节点上——平台不认，
导入后流程图里没有并行结构，节点属性也缺 `Shunt*` 一组键。必须显式插两个结构节点
（2026-11-27 用户平台实测，停车优惠申请表）：

```text
保卫科负责人审批 → 分流 → [人事科会签 | 财务科会签] → 合流 → 分管院领导审批
```

| 项 | 分流 | 合流 |
|---|---|---|
| `node` / `ActionTypeID` | `nodeIsShunt` / 14 | `nodeToConverg` / 15 |
| `optStep` | 空串 | 空串 |
| `importantShunt` | 各分支 DrawID（`"6,7"`） | 汇聚目标 DrawID（`"8"`） |
| `ShuntParentID` | 空 | **分流节点的 DrawID**（`"10"`） |
| `shuntChildren` / `shuntLayer` | `false` / `0` | `true` / `1` |

并行分支上的业务节点（分流与合流之间）要补：
`ShuntFirstID`=自身 DrawID、`ShuntParentID`=分流 DrawID、`shuntChildren=true`、`shuntLayer=1`；
`processPrev` 改成分流、`processTo` 改成合流。连线条数比「一点多线」多 2 条，`FlowStepPart` 也各补一条。

两条最容易漏的：

- **`importantShunt` 要穿过结构节点**、写业务上的下一步：保卫科负责人审批写 `"6,7"`（分支），
  人事科会签写 `"8"`（合流之后那个节点），**不要**写分流/合流的 DrawID（`business_next()` 负责展平）。
- **分流/合流用的是另一套默认键**（无人员、无表单的结构节点）：`singleApprove=0`、`agreePercent=0.0`、
  `selUserRange=2`、`unFinishedActive=1`、`isCanAssist=False`、`isCanDirectDelivery=True`、
  `flowTriggerSetMode=0`、`flowToNoticeMode=1`、`flowToCirMode=1` 等；
  导出件里**没有 `note` 键**，`nodeIcon` 也不带普通节点那个尾随空格。

### 只在显式标记时插（`graph.nodes[].parallel: true`）

上游 1.19.2 按「非判断节点出线 >1」自动插，套到 09 流程上会出事：
审批节点的两条出线绝大多数是「同意 / 返回修改」，或者「有协同科室 / 无协同科室」这类**二选一**，
拓扑上和并行一模一样。707 实测自动插：34 节点被撑到 **38**，多出 2 个坐标重合的合流。

所以本地改成**默认关闭、标了才插**：

```json
{"name": "12 院领导签发", "type": "approve", "x": 1160, "y": 1610, "parallel": true}
```

标记后仍只把同时满足三条的分支算并行：目标在下方（y 更大）、目标名/连线文字不含
返回/退回/终止/结束/不同意 等例外出口词、至少两条。退回边保持**直连**，不塞进分流。

公文发文实测（12 院领导签发 → 13 知会 / 14 分发，另有 12.1 返回拟稿人修改）：
`12.processTo = "17,15"`（分流 + 申请人复核）、`分流 → 13,14`、`合流 → 16 结束`，
13/14 的 `ShuntFirstID` 分别是自身、`ShuntParentID` 都指向 17，退回边不受影响。

**判断节点（`nodeJudge`）的多出线是条件分支，不插分流合流。**

## 步骤名不带层级序号

平台导入后自己按结构编号，`actualName` / 连线 `nextActualName` 里再带一遍 `1 `、`5.1.1 ` 就重复了。
`graph.nodes` 有 `label` 用 `label`；**老 spec 只有 `name`（带序号）时，`build_export.strip_no()` 兜底去掉序号**，
`build_flowchart.py` 同理（画布节点名 = `label` 或 `strip_no(name)`）。
两处都要改，只改导出不改流程图会出现「图上有序号、包里没有」。

## FlowStepPart 有残留，别拿它数节点

实测：`FlowStep` 只有 6 个节点，`FlowStepPart` 却有 **10 条**（`StepID` 64554–64563）——
画布上删掉的节点，`FlowStep` 删了但 `Part` 留着。**节点数以 `FlowStep` 为准**，`Part` 只按 `StepID` 关联查询。

## 画布坐标不是单列

线性流程是 `left` 固定、`top` 每次 +120；一旦有分支就变成散点：

| DrawID | 节点 | nodeStyle |
|---|---|---|
| 1 | 开始 | left:460px;top:100px; |
| 2 | 申请人 | left:460px;top:220px; |
| 9 | 判断 | left:460px;top:320px; |
| 10 | 审批 | left:261px;top:460px; |
| 8 | 通知执行 | left:660px;top:460px; |
| 7 | 结束 | left:480px;top:640px; |

渲染规则（`build_flowchart.py --from-export` 已实现）：
- 坐标当**左上角**用，画布按 min/max 加 46px 内边距；菱形比矩形窄，左侧补 `(176-150)/2` 保持同列视觉居中；
- 连线走**正交折线**：源节点底部 → 下探 30+16×分支序号 → 横移到目标中心 X → 落到目标顶部；
- 多条入边汇聚到同一节点时共用目标顶部中心，横线相交不影响阅读；
- 「审」徽标在节点右上角，分支走线净空要 ≥30px，否则会压住徽标。

## 复杂流程怎么排版（`graph` + 分层布局）

`flow` 数组只够表达「一个判断分两支」。遇到**三路分支、嵌套判断**（判断后某支里还有判断）要写 `graph`：

```json
{"nodes":[{"name":"判断是否需要职能科会签","type":"judge","x":560,"y":330}, ...],
 "edges":[["判断是否需要职能科会签","相关职能科会签"], ["判断是否需要职能科会签","主管院长审批"], ...]}
```

- **给了 x/y 就按坐标排**（推荐，复杂流程必须手工排，否则会被拉成一条竖线）；
- 不给 x/y 时走 `layout_graph()` 分层：层级 = 从开始的最长路径，同层左右展开。梯度布局对**只有一个主链的多分支**容易退化成单列，所以优先手工坐标；
- 跨层长边（跳过中间层）自动绕画布外侧沟槽走，不穿过中间节点；
- 判断菱形 184×96，比矩形宽 176 更宽一点；手工排版时按 176 的列宽留位即可，渲染会自动补齐居中。

### 排版自检（防节点叠在一起）

`build_flowchart.py` 出图前会做两道几何检查，**重叠直接判失败、不写文件**：

| 检查 | 触发条件 | 处理 |
|---|---|---|
| 节点重叠 | 任意两个节点矩形相交 | 打印「节点重叠：「A」与「B」坐标冲突」，退出码 1，不落盘 |
| 连线穿框 | 连线中点落在无关节点内 | 只提示「连线 A→B 穿过「C」」，不阻断 |
| 节点重名 | `graph.nodes` 里名字重复 | 直接报错——边是按名字连的，重名会连错 |

`build_export.py` 另外检查**坐标重复**（两个节点 x/y 完全一样），命中会在告警里提示
「导入后画布上会叠在一起」。

排版自带的安全边界（自动布局时不会重叠）：
- `flow` 模式：主线 x=460，左右分支 x=261 / 660；节点宽 176、菱形 184，横向最小间隙 ≥ 11px。
- `graph` 自动分层：同层 `gap_x=200`、层间 `gap_y=140`，节点最高 98px → 纵向至少留 42px。
- 手工坐标（`graph.nodes` 带 x/y）不受上面约束，**靠上面的重叠检查兜底**。

## FlowStepCon / FlowStepPart / 其余分节

- `FlowStepCon.tabCode` = **源节点的类型**（`nodeStart`/`nodeFirst`/`nodeApprove`），`DrawID → NextDrawID` 连线；
  `ConContent` 为空 = 无条件分支（人工选分支；有条件的判断必须写 `[n]` / `[n] Or [m]`）。
- `FlowStepPart` 每个 StepID 一条，放节点级高级设置（超时、回填、签名等），键比 FlowStep 少。
- `FlowParticipant` 有两种：**附件作者**（`tabCode: ExtraOperation_AttachAuthor`，`所有人` / `流程发起人`，不带 StepID）
  与**节点执行人**（`tabCode: FixedUser`，带 StepID / DrawID，见下方「公文类流程实例」）；
  `FlowExtraOperation`（附件权限）是流程级的。

## 用法

```bash
# 由表单字段（approve）推主线
python scripts/build_flowchart.py spec.json --out 流程表单

# 由平台导出还原真实流程（用于核对生成结果）
python scripts/build_flowchart.py "流程导出_xxx.json" --from-export --out 流程表单

# 打包成平台导出格式（一个 JSON 装 Web + 移动 + 流程图）
python scripts/build_export.py spec.json --base-export "流程导出_模板.json" --out 导出
```

前两条产出的 SVG 应当**逐字节一致**；`build_export.py` 生成完会自动把包里的 `sheet`
和 `elements` 抽出来重新过一遍校验器，再核对流程图节点数——自检不过会返回非 0。

## 公文类流程实例（801 收文流程 2022 年版，用户 2026-11-28 提供）

规模：7 节点 / 6 连线 / 0 判断 / 0 条件，纯线性。

| Draw | actualName | node | ActionTypeID | 执行人（FlowParticipant） |
|---|---|---|---|---|
| 1 | 开始 | nodeStart | 0 | — |
| 2 | 申请人 | nodeFirst | -1 | — |
| 3 | 医院办公室拟办意见 | nodeApprove | 2 | 某部门负责人：医院办公室（采购办） |
| 4 | 分发各院领导、责任科室 | nodeNotice | 3 | 张霞 / 曾慧燕 / 林艳仙（3 个具体用户） |
| 5 | 各院领导阅知、责任科室阅办 | nodeNotice | 3 | 某部门负责人：医院办公室（采购办） |
| 6 | 归档 | nodeAction | 4 | — |
| 7 | 结束 | nodeEnd | 1 | — |

**三个「老版本特征」，不要照抄**：

1. 执行动作保留成 `nodeAction`（`ActionTypeID=4`）——本项目 R15 要求折叠（用户 2026-11-26 两次强调），冲突时以 R15 为准。
2. `optStep` 只有审批节点写 `"1"`，开始/申请人/通知/结束都是空串。
3. `ActionTypeID` 老映射：申请人 `-1`、结束 `1`（新包按 0 写，平台按 `node` 判类型，不影响）。
   节点图标也全是绿色（新包按类型配色），`layer` 全 0。

### 0. 业务模块编码（`modCode` / `modeCode` / `modeDes`）

`FlowSet` 与 `FlowSetVersion` 上各有一组：

| 字段 | 801 收文 | 707 普通表单 | 含义 |
|---|---|---|---|
| `modCode` | `docRec` | `wm` | **业务模块编码**（收文 = docRec，发文 = docSend） |
| `modeCode` | `docRec` | `wm` | 同上，平台两处都读 |
| `modeDes` | `wm` | `wm` | 大类，公文固定 `wm` |
| `FlowKindID` | `17` | `9` | 流程分类：公文 17、普通表单 9 |

不写就落 `wm`/`9`，导入后流程挂在「通用」下，公文属性（文号/密级/主题词）列表里都不显示。

### 0.1 公文属性书签（`TemplateData.docUsedBookmarkList`）

801 有 14 条，把表单字段绑到公文模块的标准属性：

| BookMark | FormField | 说明 |
|---|---|---|
| 公文标题 | `Title` | 流程标题/公文标题 |
| 公文种类 | `DocType` | |
| 紧急程度 | `Urgent` | 另有一条 `紧急程度(值)` → `UrgentID`，落 `KM0008_Value` |
| 密级 | `Secret` | 另有一条 `密级(值)` → `SecretID` |
| 附件份数 | `AttNum` | |
| 主题词 | `Keyword` | |
| 抄送机关 | `CcGov` | |
| 附件说明 | `Adjunct` | |
| 登记人/经办人 | `UserName` | |
| 登记时间 | `CDate` | |
| 来文字号 | `ZiHao` / 收文编号 `BianHao` | 收文专用 |

结构：`{"BookMark","DataMapOption","DataMapField":"KM00xx","FlowID","FormField","FormOption","ID","IsApprove":false,"IsMain":true,"IsMonitor":false,"ModeRelationID":0}`；
`_Value` 那条多 `ApproveForName`/`ApproveModCode`/`Descript`/`ModeCode`/`ParentUID` 五个空键。
生成器按 spec 的 `bookmarks` 出（`value:true` 追加 `_Value`），见 `spec-format.md`。

**两处值得吸收**：

### 1. 意见框可以和步骤名不同（FlowFormSet）

801 两条绑定：`医院办公室拟办意见`（与步骤同名）、`各院领导阅知、责任科室阅办` → **`传阅意见`**（不同名）。
后者节点类型是**通知**，且表单 sheet 里**没有**「传阅意见」这个控件 —— 说明 `FlowFormSet.fieldCode`
是流程意见字段名，不要求表单里有同名控件。

→ 生成器已支持：spec 节点写 `"formField": "传阅意见"` 即可显式绑定（不写仍按步骤名全等/宽松匹配，R23）。
显式声明后，`form_set_ok()` 不再因「表单里有别的意见框」而判不通过。

### 2. 节点执行人可以写进包（FlowParticipant）

```json
{"StepID": 510, "DrawID": 3, "partOptionCode": "LeaderOfDept", "partOptionName": "某部门负责人",
 "description": "某部门负责人：医院办公室（采购办）",
 "DepID": 72, "depName": "医院办公室（采购办）", "depLevel": 1, "tabCode": "FixedUser"}
{"StepID": 511, "DrawID": 4, "partOptionCode": "User", "partOptionName": "用户",
 "description": "具体某个用户：张霞", "UserID": 1004, "userName": "张霞", "tabCode": "FixedUser"}
```

`partOptionCode` 枚举：`AllUser` / `Initiator`（附件作者）、`LeaderOfDept` / `User`（节点执行人；
部门负责人用 `DepID` + `depName`，具体用户用 `UserID` + `userName`）。
**暂不自动写**：`UserID` / `DepID` 是环境内主键，本地拿不到；只写名字能否被平台接受未验证 →
仍按 R9 在回复里列「建议执行人」清单，让用户在流程设计器里配。

### 公文表单常见控件（`selectData` 已支持，其余两项待补）

| 业务 | SheetType | buttonType | 关键键 |
|---|---|---|---|
| 取号按钮（来文字号「取号」） | `input` | `docword` | `selWordType: "add"`、`bindData` 指向同一字段 |
| 数据选取（选择来文单位/主题词/科室） | `selectData` | `selectdata` | `selDataSet: {dataTable, filterCondition, dataMapping[{DataField, MapField, Name}]}`，`dataTable` 是目标表名或视图。**已在 1.3.4 支持生成**（spec 写 `selectData` 字段） |
| 时间选择（登记时间，含时分） | `datetimepicker` | `time` | `dateTimeType: "datetime"` |

801 收文单共 15 行 6 列：来文字号（带取号）、来文机关（+选取）、公文标题、收文编号/来文日期/收文日期、
公文种类/紧急程度/密级、附件份数、抄送机关、主题词（+选取）、主办/协办/阅文科室（各带选取）、
附件说明、登记人/登记时间、附件文件（`uploadMode: "swfj"`）。

## 限制

- 只画主线：`shuntNext` 非 0 的分支节点会在终端提示「本图只画主线」，分支仍在平台设计器里配。
- 不画会签/条件线/退回线：这些不落在 `FlowStep.processTo` 的线性链上。

## 包里另外两处必须填（2026-11-23 平台实测）

### 1. `FlowFormSet`：节点 × 字段权限（表单设置）

不填 → 流程设计器里每个节点的「表单设置」是空的。平台写法：

| 节点 | 条目 |
|---|---|
| 申请人 | **全部非审批字段**各一条；单选/多选/下拉再加一条 `_Value`（`是否市内(值)`），`inputNumDisplay` 再加一条 `_Label`（`总价小写(文本)`）；说明块（`label` 占号无单元格）也有一条 |
| 每个审批节点 | 只一条，`fieldCode`/`fieldName` = 自己的意见栏名，`isComment: true` |

字段条目固定写法（`tabCode: "FixedFormSet"`、`SortID: 1`）：

```json
{"DrawID": 2, "FlowID": 188, "ID": 2992, "RoleID": 0, "SortID": 1, "StepID": 2411,
 "fieldCode": "KM0001", "fieldName": "科室", "flowVersion": "1.0",
 "isBatchEdit": false, "isCanDel": true, "isComment": false, "isEdit": true,
 "isEmptyFillBack": true, "isHidden": false, "isOpinionRequired": true,
 "isOpinionSummarized": true, "isReadonly": false, "isUse": true,
 "opinionSource": 0, "parentCode": "", "roleCode": "", "roleName": "",
 "tabCode": "FixedFormSet"}
```

重复表列：`fieldCode` = `KC0001…`，**`parentCode` = 该表 bindTable**。

### 2. 视图绑定（`FlowSetVersion`）

| 键 | 值 |
|---|---|
| `DefaultFormViewID` | 「主视图」的 ViewID（= `TemplateID + 702`） |
| `NotifyAuthFormViewID` / `NotifyUserFormViewID` / `OtherUserFormViewID` | 同上 |

留 0 → 节点没有绑定视图。

### 3. 节点字段数（别只写十几个键）

平台 FlowStep 是 **200 键**（审批节点 201，多一个 `note`；开始/申请人/结束没有 `note`），
`FlowStepPart` 96 键、`FlowStepCon` 23 键、`FlowSet` 108、`FlowSetVersion` 101。
默认键集存在 `assets/flow_node_defaults.json`，`build_export.build_steps` 以它为底再覆盖
ID / 名称 / 坐标 / 连线，导入后审批节点的回退、加签、催办、超时等开关才和设计器里建的一致。

### 4. 包内嵌的 `sheet` 与单独导出的 Web 视图不同

- 包内嵌：带 `events: "{}"`、`rows.len = 100`
- 单独导出的 `(Web视图).txt`：没有 `events`、`rows.len = 99`

两种平台都认，生成器按"包内嵌"形态写。
