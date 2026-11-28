# spec.json 格式

生成器的唯一输入。一份 spec 可含多个流程，一次产出全部文件。

```json
{
  "output_dir": "流程表单",
  "require_all": true,
  "fields_per_row": 2,
  "forms": [
    {
      "base": "01发文流程",
      "title": "发文稿纸",
      "fields": [
        { "label": "签发", "type": "approve" },
        { "label": "缓急", "type": "radio", "options": ["普通", "急件", "特急"] },
        { "label": "项目年度预算(万元)", "type": "inputNum", "decimal": 2 },
        { "label": "备注说明", "type": "static", "variant": "section", "text": "备注说明" }
      ],
      "nodes": [
        { "name": "部门负责人审批", "approver": "发起部门负责人",
          "condition": "无", "approveField": "部门领导意见" }
      ]
    }
  ]
}
```

## 顶层

| 键 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `output_dir` | 否 | 当前目录/流程表单 | 可用 `--out` 覆盖 |
| `require_all` | 否 | `true` | 全局默认必填 |
| `fields_per_row` | 否 | `2` | 短字段每行个数，`2` 或 `3`；可用 `--per-row` 覆盖 |
| `forms` | 是 | — | 流程数组 |

## forms[]

| 键 | 必填 | 说明 |
|---|---|---|
| `base` | 是 | 输出文件前缀，同时是流程标识（如 `01发文流程`） |
| `title` | 是 | 表单标题 = Web 标题行文字 |
| `cols` | 否 | Web 视图列数，默认 **6**（平台标准）。源表是 7 列（如「申请人 + 跨4列输入 + 申请科室 + 输入」）时写 `7`，`row` 的 `colspan` 总和不能超过它 |
| `modCode` | 否 | **业务模块编码**（导出包 `FlowSet.modCode`/`modeCode`）。公文类必写，按导出件实证取：收文 `docRec`、**党组发文 `doc`**；不写落平台默认 `wm`（通用），公文属性在列表里都不显示。~~`docSend`~~ 是早期推断值，已废弃 |
| `modeDes` | 否 | 业务模块大类，默认 `wm`（公文）；收文/发文导出件里都是 `wm` |
| `flowKindID` | 否 | 流程分类 ID：表单流程 `9`（默认）、**收文 `17`**（801 实测）、**党组发文 `24`**（党组发文实测）。不同公文模块编号不同，不要按「公文=17」套 |
| `bookmarks` | 否 | 公文「表单字段 → 公文属性」映射，见下方「公文流程」。`[{"label":"公文标题","formField":"Title","value":false}]`，`value:true` 时另出一条 `KM00xx_Value`（选项字段用） |
| `fields` | 是 | 字段数组，顺序即表单顺序 |
| `nodes` | 否 | 流程节点清单，写进 `(配置清单).md` |
| `graph` | 否 | 显式流程图：`{"nodes":[{"name","type","x","y"}],"edges":[["A","B"],...]}`。节点给了 `x`/`y` 就按坐标排（复杂分支推荐），否则按分层自动布局。与 `flow` 二选一，优先 `graph` |
| `graph.nodes[].conditions` | 否 | **判断条件**，写进导出包的 `StepCondition`，导入后分支规则直接可用。见下方「判断条件」 |
| `graph.nodes[].else` | 否 | 判断的「其余情况」出口：`"10 结束"` 或 `{"to":"10 结束","label":"非新入岗人员"}`，对应连线 `![1]`（取反） |
| `graph.nodes[].formField` | 否 | **指定该节点绑哪个意见框**（`FlowFormSet`）。平台允许意见框名 ≠ 步骤名，也可以是表单里没有的流程意见字段（801 收文：`各院领导阅知、责任科室阅办` → `传阅意见`）。不写则按步骤名全等/宽松匹配 |
| `graph.nodes[].parallel` | 否 | `true` = 这个节点的多条出线是**并行**（会签），导出时自动插「分流(nodeIsShunt/14) → 各分支 → 合流(nodeToConverg/15)」。**默认不插**：09 流程里「同意 / 返回修改」「有协同科室 / 无协同科室」都是二选一，拓扑上无法和并行区分（707 实测自动插会多 4 个节点）。退回边（目标在上方/名字含「返回/退回/终止」）始终直连，不进分流 |
| `flow` | 否 | 显式动作序列，覆盖「按 approve 推主线」。字符串按名称自动判类型，也可写 `"条件判断:判断送审科室"` 强制类型；**判断节点后紧跟的两项即左右分支**，再往后是汇聚点。例：`["开始","申请人","判断送审科室","通知执行","科室考核意见","结束"]` |

## 判断条件（graph.nodes[].conditions）

判断节点（`type: "judge"`）写条件后，导出包里会落成 `StepCondition`，导入平台不用再手工配分支规则：

```json
{
  "name": "5 判断人员类别", "type": "judge", "x": 460, "y": 420,
  "conditions": [
    {"field": "人员类别", "value": "医技药人员", "to": "6 医务科初审"},
    {"field": "人员类别", "value": ["护理人员", "行政后勤人员"], "to": "7 相关职能科审批"}
  ]
}
```

| 键 | 必填 | 说明 |
|---|---|---|
| `field` | 是 | 表单字段的 `label`（单选/多选/下拉/数字/文本都行，字段必须在本表单里） |
| `value` | 是 | 取值。给数组 = 拆成多条条件（平台里是 jIdentity `[1]` `[2]`…，同一出口的文字用「 / 」拼） |
| `to` | 是 | 这条条件走向哪个节点。**写在执行动作上也行**（图上折叠的那种），会自动穿到它的后继节点 |
| `op` | 否 | `eq`（默认）/ `ne` / `gt` / `lt` / `ge` / `le`，也认 `=` `!=` `>` `<` |
| `label` / `note` | 否 | 分支文字，默认取 value |

两种典型写法：

1. **分类**（一个值一个出口）：每个值一条条件，出线条数 = 不同 `to` 的个数。
   **枚举里有几个值就写几条**，哪怕其中几条线汇到同一目标（707 的财务科 → `[5]`）；
   用 `else` 或排除法（`![1] And ![2]`）去表达某个具体枚举值，导入后会显示成
   「【取反】 财务科」，运行时容易误读成排除该值（用户 2026-11-28 校准）。
2. **是否判断**：一条条件 + `else` 兜底 —— 平台里就是 `[1]` / `![1]`（取反），最贴近平台原生态。
   `else` 只留给真正的「其他 / 错误 / 未匹配」。

```json
{"name": "6 判断是否新入岗员工", "type": "judge",
 "conditions": [{"field": "申请原因", "value": "新入岗人员", "to": "6.1.1 新入岗员工医保物价科处理"}],
 "else": {"to": "7 系统管理员处理", "label": "非新入岗人员"}}
```

注意事项：

- **一条边挂多个条件时 `ConContent` 写 `[1] Or [2]`**（按 jIdentity 顺序用 ` Or ` 连），`ConContentDesc` 各值用「 【或者】 」连；
  **多条条件取反**写 `!([1] or [2] or [3])`（小写 `or`、外层括号），说明文字 ` 【取反】（ A 【或者】 B ）`
  —— 707 平台导出件实测，别再写 `![1] And ![2]`；
  **别留空**——留空等于平台「条件步骤」没绑，分支不会自动走（用户 2026-11-27 反馈）；
- `to` 写了但 `edges` 里没写这条边，生成器会自动补边，并按条件顺序排出线顺序；
- 用户用 `edgeLabels` 显式写了文字的分支，文字保留、`ConContent` 仍由条件补上；
- 条件要字段码（`KM0012_Value`），**必须有 Web 视图**才生成；只出移动视图那次跑不出来（会告警）；
- 参考实现：`references/flow-export.md` 的「StepCondition」一节。

## fields[]

| 键 | 必填 | 说明 |
|---|---|---|
| `label` | 是 | 字段名，照抄源文档 |
| `type` | 是 | 15 类控件之一，或 `static` / `label` / `selectData` / `blank` |
| `options` | 单选/多选/下拉必填 | 字符串数组，自动转 `[{label,value}]` |
| `require` | 否 | 单字段覆盖全局必填 |
| `range` | 否 | 时间范围：写 `true` 时把 `XX起止时间` 自动拆成 `XX开始时间` + 结束控件，中间放原字段名当标题（**不用「至」、结束控件不出标签**，两控件等宽）。字段名含「起止」且类型是 datepicker 时**默认就拆**，不必显式写；写了 `row` 会保留，起止可与科室排进同一行 |
| `bind` | 否 | 强制指定默认值绑定：`user`/`dept`/`date`/`login`/`phone`，覆盖按字段名的自动判定（如「科别」不会命中「科室」关键词，写 `bind: "dept"`）；`bind: "none"` 明确关闭默认值绑定，让源 Word 灰字 `placeholder` 不被「默认：申请人部门」覆盖 |
| `decimal` | 否 | `inputNum` / `inputNumDisplay` 小数位 |
| `calc` | 否 | 计算式（→ 属性 `autoCalc`），用 `{字段名}` 占位：`"datediff({开始时间},{结束时间})+1"`、`"sum({费用明细\\金额})"`、`"join({总价})"`。**只有 `input`/`inputNum`/`inputNumDisplay` 支持**，写错类型生成器直接报错。语法见 `formulas.md` |
| `hideWhen` | 否 | 条件隐藏（→ 属性 `hideFormula` + `isHidden=true`），JS 表达式：`"{是否市内(值)}!='是'"`、`"('[tableKey\\经费来源(值)]').indexOf('其他')==-1"`。单选/多选判断要带 `(值)` |
| `format` | 否 | 仅 `inputNumDisplay`：`"￥"` 小写金额、`"RMB"` 大写金额、留空 = 普通数字 |
| `snFormula` | 否 | 仅 `sn`：编号格式，默认 `"[Date:YY]-[NO:____]"`（`[Date:YY]` 两位年、`[NO:____]` 流水位数） |
| `placeholder` | 否 | 自定义占位提示；源 Word 的灰色字体原文写这里（移动端可同时用 `description` 承载同一句） |
| `description` | 否 | 移动端字段说明 |
| `uploadMode` | 否 | `attachment` 上传模式，默认取 label |
| `text` / `variant` | `static` 用 | `variant`: `section`（居中带框）、`note`（左对齐带框）、`plain`（无框，Word 正文里的「说明」用这个） |
| `text` | `label` 用 | 说明正文，`\n` 分行；移动端写进 `description`（末尾补 `\n`），Web 端逐行静态行 |
| `columns` | `table` 必填 | 列定义数组，见下 |
| `tableName` | `table` 不要写 | 每次生成用 `--table-name` 传入；spec 里写了也会被忽略 |
| `showNumber` | `table` 选填 | 序号列位置（1 起）：序号在第一列写 `1`；不写时自动取「序号」列；没有序号列留空/`false` |
| `row` | 否 | 同一 `row` 值的连续字段/静态文字排成一行，格子数与表格列对齐（如「科室 + 排班起止 + 至 + 结束」）。用于一行多段，不走两两分组 |
| `hideLabel` | 否 | 仅 `row` 内有效：不显示该字段标签，控件单独占一格 |
| `colspan` | 否 | 仅 `row` 内有效：控件/文字跨列数，默认 1 |
| `labelColspan` | 否 | 仅 `row` 内有效：标签跨列数，默认 1（长标签、手工对齐表格列时用） |
| `height` | 否 | 指定该字段所在行的行高（像素），覆盖自动估算；平台实测不够高时用 |
| `lineHeights` | `static` 用 | 逐行指定高度数组，对应 `text` 每个换行，如 `[28, 54, 54]` |
| `fullRow` | 否 | 整行：标签占 A 列、控件合并到最后一列（短类型也能整行，如「拟定进修单位」） |
| `mapTo` | `selectData` 必填 | 选取结果写回哪个字段（写字段名）。生成时取它的 `bindData` 当 `selDataSet.dataMapping[].MapField` |
| `dataTable` | `selectData` 必填 | 数据源表/视图名：科室用 `priDepartment`、单位通讯录用 `DocUnit`、人员用 `priUser`、主题词用 801 里的 `wx_6TLN4FG3_Form_0000000088` |
| `dataField` | `selectData` 必填 | 源表里显示的列：科室 `DepName`、单位 `Name`、人员 `UserName`、主题词 `KM0001` |
| `buttonName` | 否 | 按钮名，默认「选择+目标字段名」（平台把它写进 `chkName`/`approveName`） |
| `multi` | 否 | 是否多选（`selDataSet.isMutilSelect`），科室/单位/主题词一般 `true` |
| `filter` | 否 | 过滤条件，默认 `IsDeleted=0` |
| `orderField` | 否 | 排序字段：科室默认 `pcsortidscope`，其它 `id` |
| `text` | `selectData` 否 | 单元格显示文字，默认 `选取`（照源表单截图） |
| `text` | `blank` 否 | 补位空格内容，默认空串。只用于把一行补齐到最后一列（平台要求「封口」，不能留空半行） |

### table 的 columns[]

| 键 | 必填 | 说明 |
|---|---|---|
| `label` | 是 | 列名，照抄源表 |
| `type` | 否 | 列控件类型，默认 `input`；可用 `input/textarea/radio/checkbox/singleCheckbox/select/datepicker/inputNum/selectDep` |
| `require` | 否 | 默认 `true` |
| `options` | 单选/多选/下拉必填 | 字符串数组 |
| `calc` | 否 | 列级计算式：`{列名}` 自动补成 `[tableKey\表名\列名]`，如 `"{单价}*{数量}"`；仅 `input`/`inputNum` 列可用 |
| `hideWhen` | 否 | 列级条件隐藏，语法同主表字段 |
| `auto` | 否 | `true` = 序号列（如「序号」）：移动端不生成该列（平台自带），Web 端保留列头并写 `showNumber`；列名叫「序号」时自动视为序号列 |
| `range` / 列名含「起止」 | 否 | 列类型为 `datepicker` 且列名含「起止」时**自动拆成相邻两列** `XX开始时间` + `XX结束时间`：一列只能挂一个控件，放不下「开始 至 结束」。该表列数 +1，其他重复表按加宽规则对齐最宽表 |

> 重复表**每次都要重新向用户要平台表名**；第二段用 `--table-name` + `--web-only` 回填，只出 Web sheet；
> 不要复用上一张表单的表名，也不要把表名写死在 spec 里。

## 公文流程（09 公文表单截图 → 发文/收文）

公文类表单跟普通表单的差别只有三处，其余照旧：

1. **业务模块**：截图左上角红框是 `发文信息` → 业务模块 = 发文流程；`收文信息` → 收文流程。
   编码按导出件实证：**收文 `docRec` + `flowKindID 17`**、**党组发文 `doc` + `flowKindID 24`**。
   `docSend` 是早期推断值（任何导出件都没出现），已废弃；行政发文编码未知，需导出件确认。
2. **数据选取控件**：截图里带「选取」按钮的格子，一律写成 `selectData` 字段（不是静态文字）。
   结构照平台导出件（801 收文流程），落成 `SheetType:"selectData"` + `buttonType:"selectdata"` +
   `selDataSet{dataTable,dataMapping[{DataField,MapField,MapFieldName,Name}],isMutilSelect,...}`。
   单元格文字写 `选取`，`bindData` 自己占一个号（平台按格发号，不影响取值）。
3. **书签映射**：`bookmarks` 写进 `TemplateData.docUsedBookmarkList`。**属性名固定、`formField`
   随表单实际字段变**，不是固定那 10 条。两份导出件的并集：

   | 公文属性（`label`） | `formField` | 出处 / 差异 |
   |---|---|---|
   | 标题 | `Title` | 两件一致 |
   | 文号 / 来文字号 | `ZiHao` | 801 叫「来文字号」，党组发文叫「文号」，字段名都是 `ZiHao` |
   | 公文种类 | `DocType` | 801 |
   | 紧急程度 | `Urgent`（+ `value:true` → `UrgentID`） | 801 |
   | 密级 | `Secret`（+ `value:true` → `SecretID`） | 801 |
   | 主送 | **`SendGov`** | 党组发文实测（早期猜的 `ToGov` 是错的） |
   | 抄送 | `CcGov` | 两件一致 |
   | 附件份数 | `AttNum` | 801 |
   | 附件说明 | **`Note`**（党组发文）/ `Adjunct`（801） | 两份字段名不同，按表单实际写 |
   | 主题词 | `Keyword` | 801 |
   | 登记人 / 拟稿人 | `UserName` | 两件同字段名，只是显示名不同 |
   | 登记时间 / 拟稿时间 | `CDate` | 同上 |
   | 收文编号 | `BianHao` | 801 收文专用 |
   | 签发 / 会签 | 空 | 党组发文有这两条，`FormField` 与 `DataMapField` 都是 `null`（只声明属性，不绑字段） |

   选项字段才加 `value:true`（落 `KM00xx_Value`）；**用 `sqlDicType` 字典的下拉不加**
   ——党组发文的紧急程度/密级就是普通 `select` + `sqlDicType`，书签直接写 `KM0003`/`KM0004`。

行内摆位：`selectData` 无标签、只占 `colspan` 格；行末空出来的格子用 `blank` 补满
（如「主题词 + 选取 + blank×2」「主办科室 + 选取 + blank×4」），否则校验报「空半行」。

## 命令

```bash
python scripts/build_forms.py spec.json                        # 只出移动视图 + Web 视图两个 txt
python scripts/build_forms.py spec.json --notes                # 额外出 (配置清单).md
python scripts/build_forms.py spec.json --out "流程表单" --only 01,05 --per-row 3
python scripts/build_forms.py spec.json --mobile-only          # 有重复表：第一段只出移动端（需 txt 时用）
python scripts/build_forms.py spec.json --table-name "wx_..._0001" --web-only   # 第二段：只出 Web 视图这一份 sheet
python scripts/build_forms.py spec.json --table-name "wx_..._0001"  # 回填表名（移动 txt 已存在时自动沿用）
python scripts/build_forms.py spec.json --no-validate     # 跳过校验
python scripts/validate_form.py "流程表单/*.txt"   # 单独校验已有产出

# 表单已定稿（用户给了双视图）→ 原样嵌入流程包，只由 spec 提供流程节点
python scripts/build_export.py spec.json --mobile-view "xx(移动视图).txt" --web-view "xx(Web视图).txt"
#   视图一个控件都不重建；意见框标题与步骤名对不上时 FlowFormSet 自动留空
```

## 输出

每个 `base` 产出：

```
{base}(移动视图).txt     移动视图 JSON（UTF-8 BOM，单行）
{base}(Web视图).txt      Web 视图 JSON（UTF-8 BOM，单行；重复表未绑定时不生成；单独交付形态**不带顶层 events**）
{base}(配置清单).md      仅 --notes 时生成：字段清单 + 重复表列 + 流程节点 + 待确认项
{base}(待绑定重复表).md   仅 --notes 且重复表未绑定时生成，列出要向用户索要的表名
```

生成后脚本自动跑校验，全部 OK 才算完成。有重复表未绑定时退出码为 3。
