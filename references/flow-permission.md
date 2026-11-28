# 流程权限补录（wmFlowCtl）

> 适用场景：表单/流程导入平台后，流程在列表里能看到，但发起人打不开、提示没有权限。
> 平台导入只建表单和流程节点，**不会写 `wmFlowCtl`**，需要事后补两条权限记录。

## 1. 两张表

| 表 | 作用 | 关键列 |
|---|---|---|
| `wmFlowSet` | 流程主表 | `FlowID`、`Name`（= 平台里的流程名）、`IsDeleted`、`IsUse`、`IsValidate` |
| `wmFlowCtl` | 流程权限 | `FlowID`、`RoleID`、`AdminFlag`、`WriteFlag`、`ReadFlag`、`IsDeleted` 等 |

一个正常流程应有**两条**权限记录：

| RoleID | 权限 | 含义 |
|---|---|---|
| `-1` | 仅 `ReadFlag=1` | 全员可查看 |
| `10` | `AdminFlag=1`、`WriteFlag=1`、`ReadFlag=1` | 管理 + 编辑 + 查看 |

两条缺一条就会出问题：只有 `10` 时普通用户看不到流程，只有 `-1` 时没人能编辑。

## 2. 三条规则

### S1 · `wmFlowSet` 只按 `IsDeleted` / `IsUse` 过滤，不带 `IsValidate`

```sql
SELECT TOP (1) @FlowID = FlowID
FROM dbo.wmFlowSet
WHERE IsDeleted = 0 AND IsUse = 1 AND Name = @FlowName   -- 单流程才带 Name
ORDER BY FlowID DESC;
```

**不要加 `IsValidate = 1`**：刚导入的流程经常还是「未验证」状态，加了条件就取不到 FlowID，
脚本会静默跳过，看起来「执行成功但没补上」。批量脚本同理，只写 `IsDeleted = 0 AND IsUse = 1`（不带 name 条件）。

### S2 · 脚本不带 `USE`

SQL 里不写 `USE 库名;`，执行前在 SSMS 顶部的数据库下拉框选中目标库（sqlcmd 用 `-d`）。
同两个脚本可以跨环境（测试库 / 正式库）直接复用，不必改文件。

### S3 · 先插 `RoleID = -1`，再插 `RoleID = 10`；按角色判断

- 插入顺序：**先 -1（只读），后 10（管理+编辑+查看）**，自增 ID 与平台手工建的两条记录一致。
- 判断粒度按角色：`-1` 和 `10` 各自缺失才补，**不要**写成「两条都不存在才补」——
  只剩一条的流程（平台里能见到，例如只建了 `10`）那样永远补不齐。
- 两个判断都带 `IsDeleted = 0`，脚本幂等，可重复执行。

## 3. 字段模板（平台实测两行）

| 列 | RoleID = -1 | RoleID = 10 |
|---|---|---|
| `FlowID` | 目标流程 FlowID | 目标流程 FlowID |
| `UserID` / `DepID` | 0 | 0 |
| `AdminFlag` / `WriteFlag` / `ReadFlag` | 0 / 0 / 1 | 1 / 1 / 1 |
| `RejectFlag` / `IsDeleted` / `BranchID` / `ReadRejectFlag` | 0 | 0 |
| `ReactivateFlag` | 0 | 1 |
| `CUserID` / `StationID` | 0 | 0 |
| `CUserName` | `N'系统'` | `N'系统'` |
| `CDate` | `GETDATE()` | `GETDATE()` |
| `IsMonitorCanEditForm` ~ `IsMonitorCanCompletelyDel` | 0 | 1（`IsMonitorCanAllocate` 例外为 0） |
| `IsMonitorCanManualFlowChild` ~ `IsMonitorCanSimulate` | 0 | 1 |
| `IsIncludeSubDep` / `IsMonitorCanRush` / `MonitorCanCompletelyDel` | 0 | 0 |

`ID` 是自增列不写；`Remark`、`AuxiCode`、`OutCode` 留空（走列默认值）。

## 4. 脚本

| 脚本 | 用途 |
|---|---|
| `sql/01_单个流程_流程权限新增.sql` | 按流程名补一个流程：取 FlowID → 检查 → 补 `-1` / `10` → 回读 |
| `sql/02_全部流程_流程权限遍历补录.sql` | 遍历所有有效流程：① 预览缺权限的流程 → ② 逐个补录 → ③ 复核每流程条数 |

用法：

1. SSMS 选目标库，打开脚本；
2. 单流程脚本改 `@FlowName`（**与平台里流程名完全一致**，含括号、斜杠）；批量脚本不用改；
3. 先跑单流程脚本 ① 的查询确认取到 FlowID，再整段执行；
4. 批量脚本先看 ① 预览结果，确认范围后再执行 ②。

## 5. 校验

```sql
SELECT f.FlowID, f.Name, COUNT(c.ID) AS CtlRows
FROM dbo.wmFlowSet f
LEFT JOIN dbo.wmFlowCtl c
       ON c.FlowID = f.FlowID AND c.IsDeleted = 0 AND c.RoleID IN ('-1', 10)
WHERE f.IsDeleted = 0 AND f.IsUse = 1
GROUP BY f.FlowID, f.Name
HAVING COUNT(c.ID) <> 2;          -- 有结果 = 还没补全
```

## 6. 注意

- **列数随平台版本变**：老库 `wmFlowCtl` 19 列，新版本 35 列（多 `OutCode`、`IsMonitorCan*` 一组）。
  执行前先 `SELECT TOP 1 * FROM dbo.wmFlowCtl` 核对，缺列会直接报「列名无效」。
- **批量脚本会扫全表**：所有 `IsDeleted=0 and IsUse=1` 的流程都会补，包括测试/废弃但没删的流程。
  要收紧范围就加 `AND IsValidate = 1` 或加名称过滤。
- **补的是「有没有权限」这一层**：授权对象、监控权限、知会权限仍在平台「权限分配」页配置（同 R27）。
- 补录前建议备份：`SELECT * INTO wmFlowCtl_bak_20261128 FROM wmFlowCtl;`
- 权限数据不在流程导出 JSON 里（`FlowSet` / `FlowSetVersion` / `FlowSetVersionPart` 均已逐键比对，没有权限位），
  所以只能走数据库这一步，别指望导入包带过来。
