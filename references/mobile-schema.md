# 移动视图 JSON 规范

## 顶层结构

顶层是**控件数组**，一个元素 = 一个控件。元素键顺序固定（顺序错会导致平台导入异常）：

```
children, class, icon, id, name, properties, type
```

生成方式：从 `assets/mobile_view_template.txt` 里同名 `type` 的控件 `copy.deepcopy`，只改 `id` / `properties`。
**不要手写控件对象**——手写必然丢键或改键序。

## 控件白名单（16 类，与模板一致）

| type | 用途 | 移动端渲染 |
|---|---|---|
| `input` | 单行文本 | 输入框 |
| `label` | 静态说明块（说明段落） | 文本块，文字在 `description` |
| `textarea` | 多行文本 / 长说明 / 多列明细兜底 | 多行框 |
| `inputNum` | 数字（金额、份数、人数） | 数字键盘 |
| `inputNumDisplay` | 数字格式（小写/大写金额、只读汇总） | 数字展示，靠 `displayFormat` 区分 |
| `sn` | 流水号（自动编号） | 只读编号 |
| `datepicker` | 日期 / 时间 | 日期选择 |
| `radio` | 单选（枚举 2–5 项） | 单选组 |
| `checkbox` | 多选 | 多选组 |
| `singleCheckbox` | 单个勾选框（"含周末""是否…"） | 勾选框 |
| `select` | 下拉（枚举 > 5 项） | 下拉 |
| `selectDep` | 部门 / 科室选择 | 组织选择 |
| `approve` | 审批意见栏（每栏 = 一个审批节点意见） | 意见框 |
| `attachment` | 附件上传 | 上传控件 |
| `table` | 重复表（多行明细） | 子表 |
| `selectData` | 数据选取（从 DocUnit/priDepartment/主题词表挑值回填目标字段） | 按钮，点开选数据 |

### selectData（移动端，2026-11-28 按 801 收文导出件补入）

`class` = `form_layout_tool_selectData`、`name` = `数据选取`。与 Web 端的三点差异：

1. **没有** `bindData` / `SheetType`，取值靠 `selDataSet.dataMapping[].MapField` 指回目标字段的 `KM00xx`。
2. `label` 与 `buttonName` 写**同一个按钮名**（801 实测：`选择来文单位`），不要写「选取」——
   移动端把 `label` 当行标题，写「选取」屏幕上就是一串分不清的「选取」。
3. `isRequire` = `false`（按钮本身不参与必填），`onlySelectData` = `true`。

`selDataSet` 与 Web 端**同构**（`dataTable`/`dataMapping[{DataField,DataTpe,IsShowColumn,MapField,MapFieldName,Name}]`/
`filterCondition`/`isMutilSelect`/`orderField`），由 `build_sel_dataset()` 一份代码同时供两端。
`MapField` 取自 Web 视图发的字段号，所以生成顺序必须是**先 Web 后移动**。

## properties

- 键集合必须与模板同类型控件**完全一致**（当前模板 66 个键），不得增删、不得改序。
- 类型专属扩展键（模板已带，直接用）：

| type | 专属键 |
|---|---|
| `approve` | `approveKey`、`approveOptions`、`approveDefaultOption` |
| `attachment` | `uploadMode` |
| `singleCheckbox` | `chkSelectValue`、`chkUnSelectValue` |
| `sn` | `snFormula`、`snMode` |
| `inputNumDisplay` | `autoCalc`（模板已带） |
| `selectData` | `selDataSet`（模板已带；`label`=`buttonName`、`onlySelectData:true`） |

- **按需出现的可选键**（模板基准里没有，出现即合法，必须按字母序插入；写法见 `formulas.md`）：

| 键 | 出现条件 | 取值 |
|---|---|---|
| `autoCalc` | 字段带 `calc`，**仅** `input`/`inputNum`/`inputNumDisplay` | 平台公式串，如 `sum([tableKey\费用明细\金额])` |
| `hideFormula` | 字段带 `hideWhen` | JS 表达式，如 `[tableKey\是否市内(值)]!='是'`；同时 `isHidden: true` |
| `snFormula` / `snMode` | 仅 `sn` | `[Date:YY]-[NO:____]`；`snMode` = 元素自身 `id` |

- 高频业务属性：

| 键 | 含义 | 取值 |
|---|---|---|
| `label` | 字段显示名 | 照抄源表，不改写 |
| `isRequire` | 是否必填 | bool，默认 `true` |
| `defVal` | 默认值绑定 | `currentUserName`（申请人/姓名）、`departmentName`（科室/部门）、`currentDateTime`（申请日期/时间）、`loginID`（工号）、`mobile`（电话/手机/联系方式/联系电话） |
| `decimal` | 小数位 | `inputNum` 金额用 `2` |
| `placeholder` | 占位提示 | `approve` 填 label |
| `description` | 字段下方说明 | 承接源表括号提示、默认值说明 |
| `options` | 选项 | `[{"label":"是","value":"是"}]`，`selectDep` 置 `[]` |

## label（静态说明块，移动端承载说明段落）

- 模板 `label` 沿用 **66 键属性全集**（键序与其他控件一致），只改 `label`、`description`、`isRequire=false`、`isHtmlStyle=true`。
- `description` 承载说明正文，多行用 `\n` 分隔，**末尾补一个 `\n`**（平台实测形态）。
- 字段名（`label`）= 说明标题（如「说明」），正文放 `description`，不要把标题重复进正文。
- Web 端同一字段渲染为**逐行静态行**（style 16），所以 `text` 里写换行即可双端一致。
- `static` 与 `label` 的区别：`static` 只出 Web（分节标题、表内注、行内布局碎片），`label` 双端都出。

## 重复表（table）

- 父控件：`type: "table"`，`properties.label` = 字段名，`isRequire: false`（必填落在列上），`isMultiple: true`。
- `children` = 列定义数组，由 spec 的 `columns` 生成；**序号列（自动列）不在移动端生成**，平台会自动带序号，`children` 只放其余列。
- 列元素键顺序 `id, name, properties, type, showLabel`，**没有 `class` / `icon`**。
- 列 `properties` 从模板同类型控件 deepcopy，改 `label` / `isRequire` / `options`，`showLabel` = 列名。
- 移动端不写重复表名（`bindTable` 只存在于 Web 视图）；所以有重复表时第一段先出导出包（移动 + 流程图）、拿到表名后第二段只补 Web sheet。
- `properties.col` 模板默认 `6`，无明确指示不要改。

## 平台回写后的形状（实测，不用怕）

平台导出件有两种形态，都不用改造，校验器两种都收：

**（A）设计器直接导出的草稿/成品**（实测 `3333(移动视图).txt`）

- 顶层仍是 **7 键** `children, class, icon, id, name, properties, type`；
- **已绑数据库字段**的元素多一个 `bindData`（值 = 字段编码，如 `KM0014`），位置在 `type` 之后；未绑字段的元素没有这个键；
- `properties` 已按字母序排，并按需补 `autoCalc` / `hideFormula` / `snFormula` / `snMode`（见上表）。

**（B）平台回写件**

- 顶层在 `name` 与 `properties` 之间插入 `oldTableKey`、`oldTableName`（普通控件都是空串）；
- `properties` 增加 `isBuildByCode: false`，同样按字母序重排。

我们提交的 7 键 / 66 属性形态平台**照样收**。校验器已放行 `bindData`、`oldTableKey`、`oldTableName`、`isBuildByCode` 与上面 4 个可选属性键，属性只校验「基准键不缺 + 无臆造键 + 提示字母序」，不再要求与模板逐字节相同。

## 编码（硬要求）
- UTF-8 **with BOM**（`\xef\xbb\xbf`），否则平台读入中文乱码。
- `json.dumps(..., ensure_ascii=False, separators=(",",":"))` —— 紧凑单行，不缩进、不转义中文。
- 每个控件 `id` 用 `uuid4` 生成，全表唯一。

## 校验清单

1. 文件头 3 字节为 BOM，JSON 可解析，单行。
2. 每个元素 7 个基准键且顺序正确；可选键 `bindData`/`oldTableKey`/`oldTableName` 允许出现。
3. `type` 在白名单内（16 类）。
4. `properties` 基准键不缺、无臆造键（可选键仅限 `autoCalc`/`hideFormula`/`snFormula`/`snMode`/`isBuildByCode`）。
5. `id` 非空且唯一。
6. `isRequire` 是布尔值。
7. `table` 的列不含 `class`/`icon`，且含 `showLabel`。
8. `sn` 的 `snMode` = 元素自身 `id`；`inputNumDisplay` 的 `displayFormat` ∈ `{空, ￥, RMB}`。
9. `selectData` 的 `label` = `buttonName`、`onlySelectData` = `true`、`selDataSet.dataMapping` 非空且 `MapField` 为 `KM00xx`。

`scripts/validate_form.py` 已覆盖以上全部检查。
