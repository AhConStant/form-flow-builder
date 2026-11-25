# 版本更迭记录

本仓库使用语义化版本：`主版本.次版本.修订号`。

- 主版本：不兼容的结构调整、口令变更或安装方式变更。
- 次版本：新增能力、新增参考文档、兼容现有用法。
- 修订号：缺陷修复、脚本稳定性、规则补充。

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
