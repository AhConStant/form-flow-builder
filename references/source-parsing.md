# 源文档解析

目标：从用户给的 Word / Excel / 截图 / PDF 里，**准确拿到字段名、顺序、分组、括号提示、必填星号**。

## 一、定位真正要建的表单

"流程梳理"类文档通常一个流程一份，正文是流程说明，**末尾的「流程表单」表格才是要建的表单**。不要拿流程步骤描述去当字段。

一份文档里可能出现多个表格（流程说明表、职责表、表单）。判定：表头含"序号/字段名称/填写内容/备注"，或紧跟在"流程表单"标题下。

**同一个 `w:tbl` 里也可能并排两张明细表**——Word 里常见"上表 3 行、接着又是一行表头"的写法。
检测：逐行扫，**表头行出现第二次**（该行单元格再次全是短名词、且与首行表头特征同构，如又出现「序号」）即在此处切分。
（实测例子：一个 `w:tbl` 里 R00–R03 是「序号/担任人/职称/…」，R04 又起「序号/姓名/性别/工号/…」，实为两张表。）
处理：拆成两个 `table` 字段，各自要 `bindTable`，且**列数必须一致**（见 `field-rules.md`）。

## 二、.docx 解析（无 python-docx 时）

```python
import zipfile, re
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

def read_docx(path):
    xml = zipfile.ZipFile(path).read("word/document.xml")
    root = ET.fromstring(xml)
    paras = ["".join(t.text or "" for t in p.iter("{%s}t" % NS["w"]))
             for p in root.iter("{%s}p" % NS["w"])]
    tables = []
    for tbl in root.iter("{%s}tbl" % NS["w"]):
        grid = [int(g.get("{%s}w" % NS["w"])) for g in tbl.iter("{%s}gridCol" % NS["w"])]
        rows = []
        for tr in tbl.findall("w:tr", NS):
            cells = []
            for tc in tr.findall("w:tc", NS):
                txt = "".join(t.text or "" for t in tc.iter("{%s}t" % NS["w"]))
                span = 1
                vm = tc.find(".//w:gridSpan", NS)
                if vm is not None:
                    span = int(vm.get("{%s}val" % NS["w"]))
                cells.append((txt.strip(), span))
            rows.append(cells)
        tables.append({"grid": grid, "rows": rows})
    return paras, tables
```

要点：
- `gridSpan` = 横向合并跨度，`vMerge` 存在 = 纵向合并（续行是空文本）。
- 拿到的单元格文本要去掉换行与全角空格；括号提示保留原文。

### 灰色字体 = 字段控件的提示文字

Word 表格里**浅灰色的字不是固定值、也不是静态说明**，而是填表提示：要写到对应字段控件的提示文字里，
不要把灰色字当内容文本生成出来（否则用户无法填写）。

- 识别：扫描 `w:rPr/w:color`，显式浅灰 RGB（R=G=B 且 `0x70~0xD9`，如 `BFBFBF`），
  或 Word 主题灰（`themeColor=background1/2`、`text1/2` 且带 `themeShade/themeTint`，如 `background1 + shade BF`）。
  同一段落内连续的灰色 run 拼成一条提示，跨段落不合并。
- 落位：源表左列是字段名、右列是灰字时，右列建**可输入控件**（`input` / `textarea`），
  灰字放 `placeholder`；移动端同时写 `description`，字段名仍用左列原文。
- 字段名含「部门/科室」会触发自动默认值，`ph` 会被「默认：申请人部门」覆盖；
  这类提示字段必须写 `bind: "none"` 关闭默认值绑定。
- 工具：`python scripts/scan_gray_hints.py 输入.docx --json` 直接列出 `{row, col, label, hint}`，
  别靠肉眼从截图抄。

## 三、.doc 解析

本机可能没有 LibreOffice / WPS / pandoc。用 Word COM 先转 .docx：

```powershell
powershell -File scripts/doc2docx.ps1 -Src "D:\工作\某流程梳理" -OutDir "D:\工作\某流程梳理\_converted"
```

坑（实测）：
1. **单实例连续 Open 会卡死** → 每个文件新建一个 Word 实例，`finally` 里 Quit + ReleaseComObject。
2. 用 `Documents.OpenNoRepairDialog($path, $false, $true, $false, "")`，不要 `Open`（修复弹窗会阻塞）。
3. 部分老 .doc 需要显式空密码参数（第 5 个 `""`）才能打开。
4. 转换件用完删掉，不进交付目录。

## 四、.xlsx 解析（无 openpyxl 时）

```python
import zipfile, re
from xml.etree import ElementTree as ET

def read_xlsx(path, sheet="sheet1"):
    z = zipfile.ZipFile(path)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(ns + "si"):
            shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
    root = ET.fromstring(z.read("xl/worksheets/%s.xml" % sheet))
    cells = {}
    for c in root.iter(ns + "c"):
        ref, t = c.get("r"), c.get("t")
        v = c.find(ns + "v")
        val = v.text if v is not None else ""
        if t == "s" and val != "":
            val = shared[int(val)]
        cells[ref] = val
    merges = [m.get("ref") for m in root.iter(ns + "mergeCell")]
    return cells, merges
```

要点：`t="s"` 是共享字符串索引，必须二次查表；`mergeCells` 告诉你哪些格子是合并出来的，别重复计字段。

## 五、截图

规格：截图**只用来定字段名、顺序、格式、分组（哪些字段同一行）**。

- 不要按截图量列宽/行高再反写 JSON —— 用户标准是沿用模板（`cols={"len":26}`，非标题行不写 `height`）。
- 截图里的红 `*` 只作参考，必填仍按"全部必填"执行。
- 截图里的统计信息（"共 18 项"）可以和最终控件数对账，是低成本的自检手段。
- 需要目视核对布局时，用 `scripts/render_web_preview.py` 把 JSON 渲染成 PNG 并排比，**不要用预览图反推边框样式**（预览器不区分无框样式）。

## 六、字段清单落地

解析完先输出一张表再动手写 spec：

| # | 字段名称 | 原始提示 | 推断控件 | 必填 | 同行分组 |
|---|---|---|---|---|---|

拿不准的控件类型在这一步就问用户，别留到生成完再改。
