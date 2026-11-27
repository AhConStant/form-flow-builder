# form-flow-builder

WorkBuddy 表单流程制作专用技能仓库。用于把 Word/Excel 表格、截图或流程梳理文档转换为平台可导入的双端表单 JSON（移动视图 + Web 视图），并生成字段清单、流程节点清单与流程图。

当前发布版本：**1.2.2**（仓库版本）
对应技能包版本：**1.19.1**（见 `SKILL_VERSION`、`CHANGELOG.md`）

> **两套版本号别混**：`VERSION` / `RELEASES.md` 记的是**本仓库**的发布；
> `SKILL_VERSION` / `CHANGELOG.md` 记的是所打包的**上游技能包**。仓库版本涨、技能包版本不一定涨。

## 仓库内容

```text
├── SKILL.md              # 技能主说明与触发规则
├── README.md             # 仓库安装、更新、回退说明
├── RELEASES.md           # 本仓库发布记录
├── VERSION               # 本仓库版本号
├── SKILL_VERSION         # 对应的上游技能包版本
├── LOCAL_PATCHES.md      # 相对上游技能包的本地修改（升级上游时逐条复查）
├── USAGE.md              # 技能使用说明（README 只讲仓库安装/更新/回退）
├── assets/               # 骨架、默认值、模板与示例规格
├── references/           # 字段、Schema、流程导出、公式、源文件解析规则
└── scripts/              # 生成、校验、预览、流程图、扫描脚本
```

## 安装

### 方式一：脚本安装（Windows / WorkBuddy）

在仓库根目录运行：

```powershell
pwsh -File scripts/install.ps1
```

默认安装到：

```text
%USERPROFILE%\.workbuddy\skills\form-flow-builder
```

安装前会备份现有技能到：

```text
%USERPROFILE%\.workbuddy\skills\.backup\form-flow-builder-<时间戳>
```

### 方式二：指定版本安装

先列出远端可用版本：

```powershell
pwsh -File scripts/list-versions.ps1
```

安装指定版本，例如 1.0.0：

```powershell
pwsh -File scripts/install.ps1 -Version 1.0.0
```

### 方式三：手动安装

1. 下载或克隆仓库。
2. 复制仓库根目录下的全部内容。
3. 粘贴到 `%USERPROFILE%\.workbuddy\skills\form-flow-builder`。
4. 重启 WorkBuddy 后加载技能。

## 更新检查

运行：

```powershell
pwsh -File scripts/check-update.ps1
```

脚本会对比本地 `VERSION` 与远端最新标签/提交，并显示：

- 当前本地版本；
- 远端最新版本；
- 是否有更新；
- 建议安装的版本；
- 更新摘要（以 `RELEASES.md` 当次条目为准）。

更新不会自动覆盖本地；需要你确认后再执行安装脚本。

## 更新流程

后续每次更新必须遵守：

1. 在 `RELEASES.md` 新增一个版本条目；
2. 明确写明新增、修复、变更、移除内容；
3. 更新 `VERSION` 文件；
4. 提交 Git，并打对应版本标签，例如 `v1.0.0`；
5. 推送提交与标签到远端仓库。

提交信息示例：

```text
release: form-flow-builder 1.0.1

- 修复审批框误绑默认值问题
- 补充 Web 视图跨列合并校验规则
- 更新字段规则参考文档
```

## 回退旧版本

如果新版本有问题，可以一键回退到历史标签版本。

列出可回退版本：

```powershell
pwsh -File scripts/list-versions.ps1
```

回退到指定版本，例如 1.0.0：

```powershell
pwsh -File scripts/rollback.ps1 -Version 1.0.0
```

脚本会：

1. 备份当前本地技能；
2. 从对应 Git 标签检出文件；
3. 覆盖安装到 WorkBuddy 技能目录；
4. 记录回退时间和版本。

## 版本编号规则

仓库版本与技能包版本是两套编号，互不覆盖：

| 文件 | 记什么 | 什么时候改 |
|---|---|---|
| `VERSION` | 本仓库发布版本 | 每次发布仓库新版本 |
| `RELEASES.md` | 本仓库的发布记录 | 每次发布仓库新版本 |
| `SKILL_VERSION` | 所打包的上游技能包版本 | 上游技能包升级时 |
| `CHANGELOG.md` | 上游技能包自身的版本历史 | 不手改，随上游同步 |
| `LOCAL_PATCHES.md` | 相对上游包改了什么 | 打补丁/销补丁时 |

- `1.0.0`：首个稳定发布版。
- 修复缺陷：修订号 +1，如 `1.0.1`。
- 新增兼容能力：次版本 +1，如 `1.1.0`。
- 破坏性调整：主版本 +1，如 `2.0.0`。

## 安全与边界

- 不要把密钥、Token、客户敏感信息、内部连接提交到仓库。
- 具体项目的流程规格、导出 JSON、客户名称、手机号、项目编号默认不入库。
- 如需补充样本，先脱敏后放入 `examples/`。
