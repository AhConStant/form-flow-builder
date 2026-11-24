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
| `FlowParticipant` | list | 各节点审批人范围（可选，画图不用） |

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
| `processPrev` | 前驱 `DrawID` | `2` |
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
- **`ConContent` 为空 = 这条分支没有配置条件**。实测这份导出里两条分支的 `ConContent`/`ConContentDesc` 全空，
  说明判断节点只做了分流、没设条件表达式，画图时**不要自己编「是/否」标签**，直接在输出里提示「分支条件为空」。

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
  `ConContent` 为空 = 无条件分支。
- `FlowStepPart` 每个 StepID 一条，放节点级高级设置（超时、回填、签名等），键比 FlowStep 少。
- `FlowParticipant`（`所有人` / `流程发起人`）与 `FlowExtraOperation`（附件权限）是**流程级**的，不带 StepID。

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
