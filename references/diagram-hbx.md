# 流程设计器文件（.hbx）解读

> **什么时候读这份**：用户给的是 `.hbx`（根标签 `<Diagram Version="14">`），或要据流程图核对节点、审批顺序、分支条件、退回环路时。
> 这是**流程设计器源文件**，既不是 `references/flow-export.md` 讲的平台流程导出 JSON，也不是表单模板 XML（TemplateSchema），
> 更不是本技能产出的 sheet 视图。三份各管一层，别混用。

---

## 一、定位

| 文件 | 管什么 | 什么时候有 |
|---|---|---|
| `.hbx` | 流程图：节点、连线、分支条件、节点坐标 | 流程设计器里打开/保存的源文件 |
| `TemplateSchema.xml` | 表单模板：字段、控件、视图、意见栏 | 表单设计器导出 |
| `流程导出_*.json` | 平台运行态：FlowSet / FlowStep / FlowFormSet / sheet | 平台流程导出 |

**能搬过去的**：节点名与前后顺序、哪些是收意见的审批节点、分支条件文案、退回环路、TemplateId。
**不能搬的**：绘图属性（Color/Brush/Pen/Point）原样进 spec；分支表达式直接当 `hideWhen`（语法不同）。

---

## 二、结构骨架

```
Diagram@Version="14"
├─ Nodes    Node × N
│    ├─ Text / ToolTip / Bounds / Visible / Shape     ← 显示层
│    └─ Activity                                      ← 业务层
│         ├─ ActivityId（32 位 GUID，业务身份）
│         ├─ ActivityName / ActivityCode / Description
│         ├─ ActivityType = 一段 XML 字符串（ActivityTypeName + Type）
│         └─ TemplateId
├─ Links    Link × M
│    ├─ Origin@Id / Destination@Id                    ← 指向 Nodes 的绘图 Id
│    ├─ ActivityLink
│    │    ├─ LinkId / LinkMark / LinkCodeName
│    │    ├─ Origin/DestinationActivityId + Name
│    │    ├─ Description                               ← 连线显示文字（如「提交」）
│    │    └─ Expression                                ← 分支条件
│    └─ Points/Point                                  ← 折线坐标
├─ Properties  99 个全局绘图默认值
└─ Resources   画刷/字体
```

- `Node@Id` 是**绘图序号**，`Activity/ActivityId` 才是业务 GUID；连线两端两套 ID 都记，核对优先用 GUID。
- `ActivityType` 必须**二次解析**那段 XML 字符串，取 `Type`（`Process/Start/Approve/End`）与 `ActivityTypeName`。
- **连线文字在 `Link/ActivityLink/Description`，条件在 `Expression`，两者分开**：义诊 hbx 6 条连线里
  5 条 `Description="提交"`、`Expression` 全空，只解析 Expression 会把连线文字全丢掉。
  生成流程导出包时，把每条连线的 `Description` 写进 `FlowStepCon` 的
  `ConContent` / `ConContentDesc` / `stepBtnName` / `note`（用 `tools/apply_edge_labels.py`，
  spec 的 `graph.edgeLabels` 留档）；源表 Description 为空就留空，不要编「同意/不同意」。
- **映射连线端点用 `Origin/DestinationActivityId` → `Nodes/Activity/ActivityId` → `Node/Text`**，
  不要用 `Origin/DestinationActivityName`：后者存的是动作名（如「处理」），不是节点显示名，直接拿来配连线会对不上。
- `ActivityProcessMark` 是 `Visible=False` 的流程名标记，**解析时跳过**，但它的 ToolTip/Text 可作流程名。
- 解析工具：`tools/parse_hbx.py`（stdlib），输出逐节点/逐连线报告与机读 JSON。

---

## 三、节点类别

| Class | 含义 | 是否配意见栏 |
|---|---|---|
| `ActivityStart` / `ActivityEnd` | 开始 / 结束 | 否 |
| `ActivityApprove` | 审批/处理节点，也可能是「申请人填报」「经办人执行」等**动作节点** | **只有收意见的才配** |
| `ActivityCondition` | 条件判断，常带多条 Expression 出边 | 否 |
| `ActivityNotification` | 通知 | 否 |
| `ActivityAuto` | 自动处理 | 否 |
| `ActivityArchive` | 归档 | 否 |
| `ActivityProcessMark` | 隐藏流程标记 | 否，跳过 |

**节点数 ≠ 意见栏数**：先剔除 Start/End/Condition/Notification/Auto/Archive，再剔除「填报/执行/修改」类动作节点，剩下的才是收意见节点。

---

## 四、分支条件表达式（平台宏，不是 JS）

条件写在 `Link/ActivityLink/Expression`，用 `「 」` 包住单个条件，多个用制表符 + `and/or` 串接：

| 宏 | 含义 | 例子 |
|---|---|---|
| `<%#myField\字段名%>` | 表单字段当前值 | `「"<%#myField\职务%>" = "大科主任"` |
| `<@#SYS://变量名@>` | 系统变量 | `<@#SYS://InitiatorDepFullPath@>`（发起人部门全路径） |
| `<$#iOffice10.UDFΛselect …>` | 业务库 SQL | `select count(*) from udfzxxjsqb where JQLX='事假'` |
| `<$#iOffice10.PrivilegeΛSELECT …>` | 权限库 SQL | `SELECT top 1 [是否中层干部] …` |

平台还会用 `.Contains(...)`、`Not … or …`。**这与 sheet 的 `hideWhen` JS 不是同一套语法**，
不要把 `「…」` 宏写进 spec；应抄进配置清单，让用户在平台流程设计器里配分支。

---

## 五、与意见栏的交叉验证（重要）

义诊样本的 `.hbx` 与 `TemplateSchema.xml` 是同一张表的两半，可直接互核：

| hbx 审批节点 | XML 意见栏 |
|---|---|
| 科室负责人意见 | `myField\科室负责人意见` |
| 门诊部经办人备案意见 | `myField\门诊部经办人备案` |
| 门诊部负责人意见 | `myField\门诊部负责人意见` |

**名字一致、顺序也一致**；而 `申请人填报`、`挂号处经办人执行` 两个动作节点没有意见栏。

→ 规则：**意见栏字段 ↔ 流程图里「收意见」的审批节点一一对应，顺序按流程走向；动作/通知节点不配意见栏。**
这与技能硬约束「审批栏之前不要插控件，平台按控件顺序自动配第 N 个意见框」吻合。
**用户同时给了表单模板和流程图时，先做这个核对，能在导入前抓出意见框错位。**

---

## 六、三份样本与风险点

| 流程 | 有效节点 | 连线 | 条件连线 | 分支节点 | TemplateId |
|---|---|---|---|---|---|
| 门诊患者信息更改申请 | 12 | 11 | 0 | 0 | **3 个不同 ID** |
| 举办门诊线下义诊活动备案 | 7 | 6 | 0 | 0 | 1 |
| 全院职工休假、因私出国（境）报备申请表 | 69 | 126 | 52 | 50 | 1 |

生成配置清单时要检查：

1. **多 TemplateId**：患者表里有 3 个，分别对应「开始+提交+结束」「中段审核」「信息口审核」三段。
   可能是多表单拼流程，也可能是复制残留；视图绑定按 TemplateID 算，必须让用户确认。
2. **退回环路**：休假表有 3 个真实环（人力资源处审核 → 其他人审核 → 回到自己）。
   从 spec 推主线只能得到一条代表路径，**环路要显式写进配置清单**，否则用户以为流程是单线。
3. **同名节点重复**：`职务判断`×4、`是否属于麻醉科`×2、`判断假期类型及天数`×2 等。
   这些是绘图分开、GUID 不同的独立节点，不是重复数据；配置条件时容易漏改其中一份，要逐个列出。
4. **条件连线多**：大表 47 种表达式，逐条抄进配置清单比写进 spec 更合适。

样本与产物在本工作区（`C:\Users\LHH\WorkBuddy\2026-11-23-01-42-02\`）：
`流程解析/学习笔记.md`、`流程解析/流程图解析报告.md`、`流程解析/*.parsed.json`、`tools/parse_hbx.py`。
