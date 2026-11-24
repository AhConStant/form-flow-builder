# 平台表单模板 XML（TemplateSchema）解读

> **什么时候读这份**：源文档是平台导出的 `.xml`（根标签 `<TemplateSchema>`），而不是 Word/Excel/截图，也不是本技能产出的视图 txt / 流程导出 JSON。
> 这套 XML 是**表单模板**导出件，和本技能生成的 **sheet 视图 JSON** 是两套东西；先按本文读懂，再翻译成 spec，**不要把 XML 当导入件交出去**。

---

## 一、定位：别混用

| | 模板 XML（本文） | 本技能产出的 sheet |
|---|---|---|
| 根 | `<TemplateSchema>` | 数组 / `sheet` 对象 |
| 内容 | `DataMappings` + `Views[].ViewHtml`（整段 HTML TABLE） | `rows/cells/styles` 栅格 + `bindTable` |
| 导入位置 | 平台表单设计器的模板存档/导入 | 平台视图导入（贴移动/Web 视图） |
| 布局 | 真 HTML `TABLE`，`width/height/colSpan/rowSpan` | 行列坐标 + 合并区间 |
| 绑定 | `ref="myField\字段名"` | `ref` / `bindTable` + 字段名 |

**能搬过去的**：字段清单、选项原文、必填与提示、默认值语义、公式、意见栏、按节点分视图的习惯。
**不能搬的**：HTML 属性原样写进 sheet、把 XML 当视图导入、把 `myField\字段名` 当 sheet 的 ref 语法。

---

## 二、结构骨架

```
TemplateSchema
├─ DataMappings
│   └─ DataMapping@DataSourceID
│       └─ myField@TableName="udf_xxx"          ← 物理表，udf_ 前缀
│           └─ <中文字段名 type="varchar|text|datetime" FieldName="拼音列名" length="50"/>
└─ Views
    └─ View × N
        ├─ Name            视图名（申请视图 / 调入意见 / 调出意见）
        ├─ IsDefault       True 只有一个
        ├─ Type            Browser
        ├─ JSScript        视图级 jQuery，可空
        └─ ViewHtml/HTML/HEAD(STYLE)+BODY   ← 全部控件写在这段 HTML 里
```

列名规则：中文名转**拼音首字母**，冲突加数字后缀（`所属科室 SSKS` / `送审科室 SSKS1`；`医生人数 YSRS` / `药师人数 YSRS1`）。
建 spec 时**字段名照抄中文标签**，列名只用于和平台数据字典核对，不要写进 spec。

---

## 三、属性字典 → spec 映射

| XML 属性 | 平台含义 | 样本写法 | 翻译成 spec |
|---|---|---|---|
| `ref="myField\字段"` | 绑定字段；**没有 ref 就不入库** | 几乎所有控件 | 有 ref 才建字段；注意附件例外 |
| `allownull="false"` + `errorTipsOnNull` | 必填 + 提示语 | `请填写申请日期！` | `require: true`；提示语可放 `placeholder`，spec 无专用键 |
| `def="SYS://人员姓名/人员部门/当前日期"` | 系统默认值 | 申请日期、申请人 | `bind: user/dept/date` 或按字段名自动判定（`电话/手机/联系方式 → phone`） |
| `udfreadonly="true"` | 只读回显 | 审批视图大量使用 | spec 无视图级权限键 → 写进配置清单「逐视图只读/必填」 |
| `udfNoEnabled="true"` | 禁用（比只读更硬） | 义诊的申请人/科室 | 同上，标为禁用 |
| `udfhide="true"` | 整控件隐藏 | 意见栏背后的取值 input | 不建可见字段 |
| `udfhide="[myField\X]!='值'"` | 条件显示 | 上午/下午时段、其他地点 | `hideWhen`，判断项要带 `(值)`：`"{上下午(值)}!='上午'"` |
| `customtype="date" datetype="date\|time"` | 日期 / 时间控件 | 义诊起止时间 | `datepicker`；`datetype="time"` 只出时分 |
| `formula="sum([a]+[b])"` | 计算式 | 人数合计、放号校验 | `calc`，改成 `{字段名}` 占位；只有 input/inputNum/inputNumDisplay 支持 |
| `expression="^-?\d+$"` | 正则校验 | 医生/护士人数 | **spec 无对应键**，记入待确认，导入后到平台补 |
| `condition` + `errortipsonexpression` | 隐藏字段上的条件校验 | 放号方式必填 | 同上；也可建隐藏辅助字段的思路写进配置清单 |
| `fieldlabel="图文"` | 单选项**存储值**；旁边文字才是展示文案 | 送审科室长选项 | `options`；展示≠存储时用 `[{label,value}]` 显式写 |
| `fieldlabelForChecked="1"` / `ForNoChecked="0"` | 多选存 1/0 | 预约放号 | `checkbox` 选项值写 `"1"/"0"` |
| `name="myField\X"` | 单选归组；**必填只写第一个选项** | 稿件类别 | spec 里一个字段一个 options，无需逐项标必填 |
| `customtype="approve"` + `approveref` | 意见栏/批注 | 3 个审批节点 | `approve` 字段；注意 bindData 占号、审批栏前不插控件 |
| `class="attachment" type="file"` | 附件；**无需 ref** | 稿件上传 | `attachment`，不要给它编字段名 |
| `linkcode="sqr_xxx"` | 表单/外部数据关联码 | 义诊表 25 处 | 语义待确认，写进待确认清单 |
| `AsFlowTitle="false"` | 不作为流程标题 | 113 处 | spec 无对应键；流程标题在平台流程设计器配 |
| `customtype="datapreview"` | 按钮（如「开始办理」） | 义诊门禁页 | spec 无按钮控件；属视图脚本，写进配置清单 |

---

## 四、意见栏三件套（固定搭配）

```html
<DIV customtype="approve" displayformat="意见内容-空格------"
     expandformat="--姓名-空格-时间---" approveref="myField\科室负责人意见" writemsg="false">
  <INPUT style="DISPLAY:none" ref="myField\科室负责人意见" udfhide="true" udfvaluetype="approvevalue"/>
  <DIV udfhide="true" udfvaluetype="approvetemplate">
    <DIV class="defaultFormat"><SPAN class="approvecommentspan">{{意见内容}}</SPAN></DIV>
    <DIV class="extendFormat">
      <SPAN class="approveuserNamespan">{{姓名}}</SPAN>
      <SPAN class="approvedatetimespan">{{时间}}</SPAN>
    </DIV>
  </DIV>
</DIV>
```

**可见 DIV（容器属性） + 隐藏 input `udfvaluetype="approvevalue"`（真实取值） + 隐藏 DIV `udfvaluetype="approvetemplate"`（{{意见内容}}/{{姓名}}/{{时间}}）**，缺一不可。每个审批节点配一条，`approveref` 指向该节点自己的意见字段。

---

## 五、三个真实套路

### A. 须知门禁页（义诊备案）
两张表叠在同一视图：`table1`（须知 + 「我已知悉」单选 + 按钮）默认显示，正式表 `DISPLAY:none`；点按钮才 hide/show。
**土办法关键**：按钮无法做必填校验，于是在旁边放一个**隐藏的必填空控件**（`allownull=false` + `errorTipsOnNull="请点击下一步"`），
JS 点击时 `$("#yanzheng").val("已阅")` 写值才放行。另有 `#yzrq` 的 `blur` 联动算星期写回 `#yzrqxq`（有 ref，值入库）。

→ 翻译到 spec：须知做 `static`（或 `label`），已阅做单选 `require: true`；**按钮与 JS 门禁 spec 表达不了**，必须写进配置清单让用户在平台视图里手工加。

### B. 按审批节点拆视图（资产调拨单，3 个视图）
同一字段在不同视图权限不同：

| 字段 | 申请视图 | 调入意见 | 调出意见 |
|---|---|---|---|
| 调入意见 | 只读 | 必填可写 | 只读 |
| 调出意见 | 只读 | 只读 | 可写 |
| 审核人1/2 | 只读 | 必填 | 只读 |

→ spec 无「视图级权限」键；把这张矩阵写进配置清单，交付时说明在平台表单设计器逐视图配。

### C. 无重复表时后缀展开固定明细（资产调拨单）
没有重复表控件，用 **5 组固定字段**模拟 5 行：
`卡片号编号/规格品名/单位/数量/单价/总价`，再 `…2 / …3 / …4 / …5`。
栅格是「表头两行合并（卡片号 rowSpan=2、金额 colSpan=2 罩住单价+总价）+ 5 行数据」。

→ 翻译时**先问用户**：固定 5 行就照抄成 30 个普通字段（字段名带数字后缀）；可增行就建 `table` 重复表。
后缀方案的 `总价/总价2..5` 在样本里**没有公式**，要主动问是否补 `calc: "{单价}*{数量}"`。

---

## 六、读模板时的检查清单

这些是三份真实样本里出现过的问题，遇到同类 XML 先扫一遍：

1. **控件丢 ref**：样本中两个审批视图的标题区申请日期是裸 INPUT（无 `ref`，只有 `def="SYS://当前日期"`）→ 不回显且被默认值顶成今天。
2. **金额无公式**：`总价` 系列裸 input，要人工算。
3. **明细写死行数**：后缀 2..5 超过 5 行办不了。
4. **字段建而不用**：义诊表 48 个字段里 18 个没进任何视图（工作量统计、结果评价类）→ 疑似漏做后续视图，要问用户。
5. **互斥隐藏字段仍必填**：上午/下午时段靠 `udfhide` 互斥但都 `allownull=false`，平台若对隐藏控件仍校验会拦提交，须实测提示用户。
6. **单选必填只写首项**：这是平台正常写法，别误判成后两项可空。

---

## 七、样本索引

真实样本与解析产物在本工作区（`C:\Users\LHH\WorkBuddy\2026-11-23-01-42-02\`）：

| XML | 物理表 | 字段 | 视图 |
|---|---|---|---|
| `桌面/稿件发布审核表.xml` | `udf_xgjfb` | 10 | 1 |
| `桌面/举办门诊线下义诊活动备案.xml` | `udf_jbmzxxyzhdbab` | 48 | 1（JS 门禁） |
| `桌面/院内固定资产调拨单.xml` | `udf_gdzc` | 40 | 3 |

解析器 `tools/parse_templates.py`（stdlib）可把更多同类 XML 拆成「字段映射 + 逐控件清单 + 栅格图 + 机读 JSON」；
结论见 `解析/学习笔记.md`，逐控件明细见 `解析/解析报告.md`。
