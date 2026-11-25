# form-flow-builder · 表单流程制作技能

把 Word/Excel 表格、截图或流程梳理文档里的表单，转成平台可导入的**移动视图 + Web 视图 JSON**，并附字段清单与流程节点清单。

- 版本：1.19.1（2026-11-24）
- 适用：Cordis / DSH 技能目录，也可单独用 Python 跑脚本

## 环境要求

| 依赖 | 说明 |
|---|---|
| Python 3.10+ | 只需标准库；`render_web_preview.py` 另需 pillow（可选） |
| pillow | 仅预览 PNG 用，缺了会自动跳过 |
| Word COM | 仅 `scripts/doc2docx.ps1` 需要，Windows + 已装 Word |

> 如果系统没有 `python`，用任意 Python 3.10+ 解释器执行脚本即可，脚本内部按相对路径找模板。

## 安装

把压缩包解到工作区的技能目录，保持目录名 `form-flow-builder`：

```
<workspace>/.agents/skills/form-flow-builder/
├─ SKILL.md
├─ assets/
├─ references/
└─ scripts/
```

放好后新开一轮会话，技能即可被识别（触发词：表单流程制作、做表单、建流程表单、表单 JSON、移动视图、Web 视图…）。

## 快速开始

### 先说清要哪一种："生成表单" 还是 "生成表单流程"

| 口令 | 命令 | 产出 | 不出 |
|---|---|---|---|
| **生成表单** | `build_forms.py` | **只有** `(移动视图).txt` + `(Web视图).txt` | 配置清单、流程图、导出 JSON（要清单加 `--notes`，要图单独跑 `build_flowchart.py`） |
| **生成表单流程** | `build_export.py` | **只有一个** `流程导出_xxx_v1.0.json`（Web + 移动 + 流程图；骨架内置） | 任何 txt、配置清单 |

### 1. 没有重复表

```bash
python scripts/build_forms.py spec.json
```

一条命令产出 `{base}(移动视图).txt`、`{base}(Web视图).txt`（默认只有这两个），并自动跑校验。要配置清单加 `--notes`。

> 生成器写文件前会先在内存校验 Web 视图（含**表格封口**与**空半行**）；不通过直接 FAIL，不会落盘。

### 2. 有重复表（两段式）

```bash
# 第一段：出「移动视图 + 流程图」的导出包（sheet 为空，退出码 3）
python scripts/build_export.py spec.json

# 第二段：回填表名，只补 Web 视图这一份 sheet（单独导入同一个表单）
python scripts/build_forms.py spec.json --table-name "字段名=wx_XXXX_Form_0000000123_0001" --web-only
```

- 表名**每张表单、每次生成都要重新要**，不要复用；spec 里写的 `tableName` 会被忽略。
- 多个重复表：`--table-name "字段名=wx_..._0001"`，每个重复一次。
- 第二段拿到表名后**只生成 `(Web视图).txt`**：不重建移动视图、不覆盖第一段产物、不重打整包；写盘自动去掉顶层 `events`（单独导出形态）。
- 第一段**不要**再多出 `(移动视图).txt` / SVG 流程图——一个导出包就够。
- 序号列移动端不生成（平台自带），Web 端只保留列头并写 `showNumber` = 序号列位置。

### 3. 校验

```bash
python scripts/validate_form.py "流程表单/01发文流程(Web视图).txt"
```

全部 OK 再交付；有 FAIL 就修。

### 4. 流程图（跟着审批意见栏走）

```bash
# 由 spec 推主线：开始 → 申请人 → 每个 approve 字段 → 结束
python scripts/build_flowchart.py spec.json --out 流程表单

# 由平台流程导出还原，用来核对两者是否一致
python scripts/build_flowchart.py "流程导出_xxx.json" --from-export --out 流程表单

# 生成表单流程：一个 JSON 装 Web + 移动 + 流程图（骨架用内置的）
python scripts/build_export.py spec.json --out 导出

# 有重复表时同样要先给表名
python scripts/build_export.py spec.json --table-name "明细=wx_..._0001" --out 导出
```

产出 `{base}(流程图).svg` 与同名 `.html`（内嵌 SVG，可直接预览/转发）。两条路产出的 SVG
**逐字节一致**即说明表单意见栏与平台流程节点完全对齐。导出文件的字段说明见
`references/flow-export.md`。

## spec.json 最小示例

```json
{
  "output_dir": "流程表单",
  "require_all": true,
  "fields_per_row": 3,
  "forms": [
    {
      "base": "01发文流程",
      "title": "发文稿纸",
      "fields": [
        { "label": "姓名", "type": "input" },
        { "label": "申请科室", "type": "selectDep" },
        { "label": "申请日期", "type": "datepicker" },
        { "label": "签发", "type": "approve", "require": false }
      ],
      "nodes": [
        { "name": "部门负责人审批", "approver": "发起部门负责人",
          "condition": "无", "approveField": "签发" }
      ]
    }
  ]
}
```

重复表字段：

```json
{
  "label": "进修明细",
  "type": "table",
  "columns": [
    { "label": "序号", "type": "input", "auto": true, "require": false },
    { "label": "开始时间", "type": "datepicker" },
    { "label": "学习单位", "type": "input" }
  ]
}
```

完整字段说明见 `references/spec-format.md`。

## 目录

```
form-flow-builder/
├─ SKILL.md                    技能主说明
├─ README.md                   本文件
├─ CHANGELOG.md                版本记录
├─ assets/
│  ├─ mobile_view_template.txt 移动视图标准模板（15 类控件）
│  ├─ web_view_template.txt    Web 视图标准模板（17 样式）
│  ├─ forms_spec.example.json  spec 示例
│  ├─ forms_spec.formulas.example.json  计算式/大小写金额/条件隐藏/流水号示例
│  ├─ mobile_view_reference.txt 移动视图成品参考（22 控件）
│  ├─ web_view_reference.txt    Web 视图成品参考（21 行）
│  └─ flow_export_skeleton.json 流程导出 JSON 骨架（build_export 默认骨架）
├─ references/
│  ├─ field-rules.md           控件/必填/默认值/布局判定
│  ├─ formulas.md              计算式/条件隐藏/金额大小写/流水号写法
│  ├─ spec-format.md           spec.json 字段说明
│  ├─ mobile-schema.md         移动视图 JSON 规范
│  ├─ web-schema.md            Web 视图 JSON 规范
│  ├─ source-parsing.md        doc/docx/xlsx/截图解析
│  ├─ flow-export.md           平台流程导出 JSON 解析
│  ├─ template-schema-xml.md   表单模板 XML 解读（属性字典/三套路）
│  └─ diagram-hbx.md           流程设计器 hbx 解读（节点/连线/条件/环路）
└─ scripts/
   ├─ build_forms.py           生成器（重复表两段式）
   ├─ build_flowchart.py       流程图（spec 推主线 / 导出还原）
   ├─ build_export.py          按导出格式打包（Web+移动+流程图）
   ├─ flow_types.py            动作类型判定 / 画布形状 / 自动布局
   ├─ validate_form.py         校验器
   ├─ scan_gray_hints.py       .docx 灰字提示扫描（→ spec.placeholder）
   ├─ render_web_preview.py    JSON → PNG 预览（可选）
   └─ doc2docx.ps1             .doc → .docx（Word COM）
```

## 关键规则（摘要）

- 输出必须 **UTF-8 with BOM + 紧凑单行**。
- 不要手写控件对象，一律从 `assets/` 模板 deepcopy。
- 有重复表：先移动端 → 每次重新索取 `bindTable` → 再 Web。
- 重复表列里的「XX起止时间」同样拆成相邻两列（`XX开始时间` / `XX结束时间`），表宽 +1，其余重复表自动加宽对齐。
- 起止日期/时间是一组填写框：`XX开始日期` + 控件 + **原字段名（`XX起止日期`）当标题** + 控件，两个日期控件等宽；**不用「至」字，也不出 `XX结束日期` 标签**，整组占连续列不跨行；6 列排 2/1/2、8 列排 3/1/3。
- 审批栏之前别插控件：平台按顺序配对「第 N 个意见框 ↔ 第 N 个审批节点」，中间插说明块会让审批框整体错位，导入后必须重绑。
- `bindData` 按字段顺序发号：重复表不占号，`label` 说明块占号（不写单元格）；漏占一位会让后面审批栏整体前移。
- 序号列移动端不生成；Web 端保留列头，`showNumber` = 序号列位置（1 起），无序号为空。
- 标题、表头、字段标签居中 + 自动换行；行高按文字自动适配，可用 `height` / `lineHeights` 指定。
- **审批意见栏 Web 行高默认 80**，标签折行过多时自动抬高。
- 说明分两种：**Word 表格框内**的注/分节标题带四边框（`static`）；**表格框外**的「说明」段落无框（`variant: "plain"`，style 2）。
- 说明要在移动端也显示时用 `label`（正文进 `description`，`\n` 分行），`static` 只出 Web。
- 带公式的字段写 spec 的 `calc`（自动计算）/ `hideWhen`（条件隐藏）/ `format`（`￥` 小写、`RMB` 大写）/ `snFormula`（流水号）；
  公式引用字段**显示名**：`{开始时间}` → `[tableKey\开始时间]`，子表列写 `{子表\列}`。详见 `references/formulas.md`。
- 一个 Word 表里可能并排两张明细表：各建一个 `table`，**列数必须一致**，否则右侧空列、封不了口。
- Word 里的**灰色字体 = 字段提示文字**：写成 `placeholder`（移动端同步 `description`），不要写 `static`；会触发默认值的字段加 `bind: "none"`。
- 用户给了现成 `(移动视图).txt` + `(Web视图).txt` 时，用 `build_export.py --mobile-view ... --web-view ...` **原样嵌入**，不重建控件；意见框标题与步骤名对不上时 `FlowFormSet` 留空。
- 默认值：移动 `defVal`、Web `defaultVal`；姓名/申请人 `currentUserName`、工号 `loginID`、科室/部门 `departmentName`、申请日期 `currentDateTime`/`currentDate`、电话/手机/联系方式 `mobile`。
- 审批节点、审批人、条件分支、审批动作选项不写进 JSON，交付时用配置清单交代。
- 流程图跟着审批意见栏走：一个 `approve` = 一个审批节点，顺序 = 字段顺序，不再手画。

## 平台差异

模板与键名以平台实测导出为唯一基准。平台升级后如出现新控件/新键，替换 `assets/` 两份模板，并同步更新 `build_forms.py` 的 `MOBILE_TYPES` / `WEB_BTN` / `WIDE`、`validate_form.py` 的 `CELL_KEYS`。
