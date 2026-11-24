# Web 视图 JSON 规范

Luckysheet 风格表格 JSON：一份表单 = 一个表格，标题行 + 数据行。控件挂在单元格上。
标准 6 列；**有超过 6 列的重复表时，整张表按最宽的重复表列数变宽（7 列→A:G）**。

## 顶层（键顺序固定）

```
name, freeze, styles, merges, rows, cols, autofilter, approves, sns, tables, dics, sqlDics, events
```

| 键 | 取值 | 规则 |
|---|---|---|
| `name` | `sheet1` | 沿用模板 |
| `freeze` | `A1` | 沿用模板 |
| `styles` | 模板 17 个 + 可选第 18 个 | 模板样式原样复用；**有重复表时在末尾追加第 18 个**（`#f2f2f2` 灰底，数据格用 `style: 17`） |
| `cols` | `{"0":{"width":150},...,"len":26}` | 生成器按实际列数写，每列 150，`len` 固定 26 |
| `rows` | 见下 | 行号字符串键 + `"len":100` |
| `merges` | `["A1:G1", ...]` | A1 记法，与单元格 `merge` 属性双写 |
| `approves` | `[{"approveName":..,"approveMode":..}]` | 必须与 approve 单元格一一对应 |
| `tables` | 重复表元数据数组 | 没有重复表时为 `[]` |
| `events` | 字符串 `"{}"` | 不是对象 |

## rows

```
"rows": {"0": {...}, "1": {...}, ..., "len": 100}
```

- 行 0 = 标题行：`height ≥ 100`，单元格 `style: 13`（方正小标宋简体 24，居中换行），合并 `A1:最后列1`。
- **行高自动适配文字**：按单元格文字、列宽、字号估算行数，行高 = 行数×(字号+8)+8，再乘 1.3 的安全系数；低于 40 用默认行高。长标签、长表头、多行说明都自动加高。
- **审批意见栏（approve）默认行高 80**：整行从 80 起；标签在 A 列（150）折行后按行数继续抬高（3 行起才超过 80）。spec 显式写 `height` 时以 `height` 为准。
- 平台实测仍不够时，在 spec 用 `height`（整行）或 static 的 `lineHeights`（逐行）指定，指定值优先于自动估算。
- 重复表表头行同样适用自动行高。
- 每行 `cells` 必须凑满 `"0"`–`"n-1"` 全部列，缺的列补**填充格** `{"style": 2}`（标题行填充格用 `{"style": 13}`）。缺格会导致导入错列。

## 单元格

### 标签格（字段名）

```json
{"style": 5, "text": "项目名称"}
```

### 控件格（键顺序）

```
style, merge, text, buttonType, bindData, placeholder, chkName, approveName,
options, required, localDep, showSign, onlyShowSelected, imageScale,
imageOption, onlySelectData, SheetType
```

类型扩展键：

| type | 追加键 | 说明 |
|---|---|---|
| `approve` | `approveMode` | 且 `showSign: true` |
| `attachment` | `uploadMode` | 且**不含 `text` 键**（按钮类） |
| `datepicker` | `dateTimeType: "date"` | 日期型 |
| `singleCheckbox` | `chkSelectValue: "true"`, `chkUnSelectValue: "false"` | |
| `inputNum`（带计算式） | `decimal: 2` | **只有带 `autoCalc` 的 inputNum 才写 `decimal`**，普通数字格不写 |
| `inputNumDisplay` | `displayFormat`, `approveDisplayFormat`, `autoCalc` | 取值 `"￥"` / `"RMB"`；`required: false` |
| 任意（带 `calc`） | `autoCalc: "sum([tableKey\费用明细\金额])"` | 自动计算，**Web 端也写**（平台实测） |
| 任意（带条件隐藏） | `hideFormula: "[tableKey\是否市内(值)]!='是'"` | 只写 `hideFormula`，**Web 端没有 `isHidden`** |

`bindData` 从 `KM0001` 起自增，全表唯一（**重复表数据格不写 `bindData`**）。

编号按**表单字段顺序**发，不是按单元格数：**重复表不占号**，但 `label` 说明块**占一个号**
（Web 端这一行是纯文字、没有控件格，号只占不写）。漏占一位，后面所有审批栏就整体前移一位，
平台导入后意见框会绑错。实测：说明块占 `KM0004` 时，其后的「科室考核意见」必须是 `KM0005`。
`static`（分节标题、表内注等纯 Web 装饰）不占号。

默认值绑定键 `defaultVal`：`currentUserName`（申请人/姓名）、`departmentName`（科室/部门）、`currentDate`（申请日期/时间）、`loginID`（工号）、`mobile`（电话/手机/联系方式/联系电话）。

### buttonType ↔ SheetType 映射（固定，不可自创）

| 业务类型 | buttonType | SheetType |
|---|---|---|
| 单行文本 | `input` | `input` |
| 多行文本 | `textarea` | `textarea` |
| 数字 | `inputnum` | `inputNum` |
| 部门选择 | `depselect` | `selectDep` |
| 附件 | `upload` | `attachment` |
| 审批意见 | `approve` | `approve` |
| 日期 | `time` | `datepicker` |
| 下拉 | `select` | `select` |
| 单选 | `radio` | `radio` |
| 多选 | `checkboxgroup` | `checkbox` |
| 勾选框 | `checkbox` | `singleCheckbox` |
| 数字格式（￥/RMB） | `inputnumdisplay` | `inputNumDisplay` |

## 重复表（关键）

一张重复表占 **两行**：

1. **表头行**：每个列一个标签格，`{"style": 15, "text": "列名"}`。
2. **数据行**：每个列一个控件格，键顺序：

```
style, bindTable, text, buttonType, placeholder, chkName, approveName,
options, required, localDep, showSign, onlyShowSelected, imageScale,
imageOption, onlySelectData, SheetType, bindField
```

- 数据格样式 = `{"style": 17}`（带框 + `#f2f2f2` 灰底），**不是 14**；表头仍是 15。
- `bindTable` = 平台重复表全名（`wx_XXXXXXXX_Form_0000000123_0001`），同一张表的所有数据格都一样。
  导入时平台会重建表并换新号段（实测 163 → 167），包里的表名只是占位。
- 跨列加宽时，**被覆盖的格子也写 `{"style": 17, "bindTable": "wx_..."}`**（只有这两个键）。
- `bindField` = 列字段编码，从 `KC0001` 起按列顺序自增；**自动列（序号）不写 `bindField`**，且 `required: false`。
- **序号显示**（`tables[].showNumber`）= **序号所在列的位置（1 起）**：
  - 序号在第 1 列写 `"1"`，在第 3 列写 `"3"`；没有序号列写 `""`。
  - 开启时该列数据格只写 `{"style": 14, "bindTable": "wx_..."}`，
    **没有 `SheetType` / `bindField` / `text`**，编号由平台自动生成。
  - 不要写 `true` / 布尔值；只有列位置数字或空串两个合法形态。
- 数据格**不写 `bindData`、不写 `merge`**。
- 顶层 `tables` 每条：

```json
{"tableRange": "A5:G5", "bindTable": "wx_..._0001", "showNumber": "1",
 "isPagination": false, "pageSize": "", "addRowOption": "normal",
 "rowLimit": "", "sortOption": "normal"}
```

  - `tableRange` 指向**数据行**（单行），不是表头行。
  - `showNumber`：序号列位置（`"1"` 起）；没有序号列写 `""`。
  - 键顺序固定，不能少键；没有分页/行数限制就留空串。
- 表头行不算合并；数据行也不合并。重复表区之外的宽字段合并到最后一列。

## 合并

- 单元格 `merge: [行跨-1, 列跨-1]`；跨 2 列写 `[0,1]`，跨 n 列写 `[0,n-1]`。
- 同时在 `merges` 里写 A1 记法：`"B2:C2"`。
- 合并区**被覆盖的格子必须存在**（填充格 `{"style":2}`），否则导入缺格。
- 合并区不能重叠；重复表两行不写合并。

## 样式编号语义（模板 17 个）

| 编号 | 用途 |
|---|---|
| 13 | 标题（居中 + 方正小标宋简体 24 + 自动换行） |
| 5 | 首数据行标签格（居中 + 四边框 + 自动换行） |
| 6 | 首数据行控件格（上/右/下框） |
| 7 | 其余行标签格（居中 + 上/左/右框 + 自动换行） |
| 8 | 其余行控件格（右/下框） |
| 14 | 重复表数据格（四边框、左对齐） |
| 15 | 重复表表头（居中 + 四边框 + 自动换行） |
| 16 | 静态说明（四边框、左对齐、折行） |
| 2 | 无框（填充格） |
| 3 / 4 | 灰底 / 白底（备用） |
| 1 / 0 | 居中 12 号 / 居中（备用） |

## 布局规则（用户标准）

1. **一行最多 3 个字段**。
2. 宽字段独占整行：标签 A 列，控件 `B:最后列`。
   宽字段 = `textarea` / `approve` / `attachment` / `radio` / `checkbox` / `table`；
   其他短类型也可在 spec 加 `fullRow: true` 强制整行（如「拟定进修单位」）。
3. 短字段两两一行（默认）：`A 标签 + B:C 控件`，`D 标签 + E:F 控件`；7 列时 G 列留填充格。
   末行不足 per_row 个字段时，按本行实际字段数平均分配列宽、铺满整行，避免右侧空半行（无边框填充）。
4. 短字段三列一行（可选，`fields_per_row=3`）：`A 标签 + B 控件`、`C 标签 + D 控件`、`E 标签 + F 控件`，不合并。
5. 字段名称 / 顺序 / 格式以源文档为准，**不得增删或臆造**；源表重复行就保留重复。
6. 长标签跨行：如标签占 `A7:A8`、内容在 `B7:F7`、附件在 `B8:F8`。
7. 一行多段（如「科室 + 排班起止 + 至 + 结束 +（不少于6个月）」）：spec 里给这些字段/静态文字相同的 `row`，
   每个字段 1 格标签 + 1 格控件，`hideLabel` 省掉标签、`colspan` 跨列；整行格子数与其他行一致，不合并。
8. **起止日期/时间是一组填写框 → 组内等宽 + 原字段名当标题**：
   `XX开始日期` | 开始控件 | **`XX起止日期`（原字段名，居中标题）** | 结束控件（无标签）。
   整组占**连续的列**、不跨行拆开；两个日期控件列数**必须相同**，绝不能一个 1 列一个 2 列
   ——宽度不等会让填表人以为两个框填不同粒度。**不用「至」字，也不出 `XX结束日期` 标签**
   （结束控件写 `hideLabel`，平台前端不画标签格）。整组 = 标签 1 + 控件 k + 标题 t + 控件 k：
   6 列 → 2/1/2、7 列 → 2/2/2、8 列 → 3/1/3、9 列 → 3/2/3（`range_row_spans()` 实现）。
   行里还有科室等短字段（显式 `row` 同排）时，先扣掉它们的列再按上式排，剩余列给科室。
   `colspan`/`labelColspan`/`hideLabel` 只影响 Web，移动端控件数量与顺序不受影响（移动端仍是
   `XX开始日期` + `XX结束日期` 两个带标签的日期控件）。

## 静态文字

- 分节标题：`{"style": 5, "text": "...", "merge": [0,n-1]}` 整行居中带框。
- 表内说明（Word 表格框内的注、说明）：`{"style": 16, ...}` 整行左对齐带框。
- **表格框外的说明（Word 正文里的「说明」段落）→ `style 2` 无框**，整行 `A:最后列` 合并；
  用 spec 的 `variant: "plain"` 指定。校验器的「封口/空半行」对这类**全宽单格无框行**豁免，
  但只跨部分列的无框行仍会判 FAIL。
- `style 2` 没有 `textwrap`，长说明必须逐行拆开（每行一个字面行），别指望自动折行。
- **长说明（含换行）逐行生成**：每个源文行占一行，各自 `A:最后列` 合并，按字数估行高（28 起）；不要把多行塞进一个单元格，否则平台默认行高会截字。
- 移动端：`static` 一律省略；需要在移动端显示的说明段落用 `label`（见 `mobile-schema.md`）。

## 校验清单

1. BOM、可解析、顶层 13 键顺序正确。
2. `styles` 与模板完全一致；`cols` 的 `len=26`、列宽键 `0..n-1` 齐全；`freeze` 一致；`events == "{}"`。
3. `rows["len"] == 100`，行号 0 起连续。
4. 每行 n 格齐全；行高按文字自动适配（height 为正整数，标题行 ≥100）。
5. `merges` 不重叠，锚点 `merge` 属性与 A1 记法一致，覆盖格存在且无控件。
6. `bindData` 唯一且形如 `KM0001`；重复表数据格没有 `bindData`。
7. `SheetType` 与 `buttonType` 符合映射表，无多余键。
8. `approve` 的 `showSign=true` 且出现在 `approves`；非 approve 的 `showSign=false`。
9. `attachment` 无 `text` 键。
10. 重复表：`tables[]` 键序正确、`tableRange` 指向数据行、`bindTable` 非空、范围内每格 `bindTable` 一致、`bindField` 从 `KC0001` 起不重复；序号列不写 `bindField`；`showNumber` 为序号列位置或 `""`，非空时该列只剩 `style`+`bindTable`。
11. **表格封口 / 空半行**：每行最后一列有右边框、第一列有左边框；行内容必须铺满整行，内容提前结束而右侧是无边框填充（style 2）的判 FAIL。

`scripts/validate_form.py` 已覆盖以上全部检查。

## 平台版本差异提示

若目标平台升级后模板变化（出现 `defaultVal` 单元格键、`label` 静态文字控件、`inputNumDisplay` 等），以平台导出的标准控件文件为新基准，替换 `assets/web_view_template.txt` 与 `assets/mobile_view_template.txt`，并同步更新白名单与 `CELL_KEYS`。**不要凭感觉扩展键名。**
