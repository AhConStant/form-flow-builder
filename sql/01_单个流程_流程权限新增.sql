/* =============================================================================
   单个流程 —— 流程权限（wmFlowCtl）新增脚本
   -----------------------------------------------------------------------------
   场景：表单/流程导入后，wmFlowCtl 中没有该流程 RoleID in ('-1',10) 的权限记录，
         导致流程"没有流程权限"。本脚本按标准模板补两条（先补 -1，再补 10）：
           RoleID = -1 ：仅 ReadFlag=1（全员可查看）
           RoleID = 10 ：AdminFlag=1 / WriteFlag=1 / ReadFlag=1（管理 + 编辑 + 查看）
   条件：wmFlowSet  IsDeleted=0 and IsUse=1 and Name=@FlowName
         wmFlowCtl  IsDeleted=0 and RoleID in ('-1',10) and FlowID=@FlowID
   说明：ID 为自增列，不写入；CDate 取当前时间，CUserName 取 N'系统'（与模板一致）
         脚本幂等，可重复执行，已存在的角色不会重复插入
   环境：SQL Server；执行前请先在 SSMS 中选中目标数据库（脚本不含 USE 语句）
   ============================================================================= */

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @FlowName nvarchar(400) = N'流程名称';   -- ← 改成平台里实际的流程名（与 wmFlowSet.Name 完全一致）
DECLARE @Now      datetime      = GETDATE();
DECLARE @Operator nvarchar(400) = N'系统';
DECLARE @FlowID   int;

/* -----------------------------------------------------------------------------
   ① 查询 wmFlowSet 取 FlowID（筛选条件按要求原样保留，不得修改）
   -------------------------------------------------------------------------- */
SELECT TOP (1) @FlowID = FlowID
FROM dbo.wmFlowSet
WHERE IsDeleted = 0 AND IsUse = 1 AND Name = @FlowName
ORDER BY FlowID DESC;

IF @FlowID IS NULL
BEGIN
    RAISERROR(N'未找到流程：%s（需满足 IsDeleted=0 / IsUse=1）', 16, 1, @FlowName);
    RETURN;
END;

PRINT N'目标流程：' + @FlowName + N'，FlowID = ' + CAST(@FlowID AS nvarchar(20));

/* -----------------------------------------------------------------------------
   ② 检查 wmFlowCtl 是否已有权限数据（筛选条件按要求原样保留，不得修改）
   -------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1
    FROM dbo.wmFlowCtl
    WHERE IsDeleted = 0 AND RoleID IN ('-1', 10) AND FlowID = @FlowID
)
    PRINT N'wmFlowCtl 中该流程没有 RoleID in (-1,10) 的数据，按模板新增。';
ELSE
    PRINT N'wmFlowCtl 中该流程已有 RoleID in (-1,10) 的数据，仅补录缺失的角色。';

/* -----------------------------------------------------------------------------
   ③ 补录 RoleID = -1（全员查看）
      字段取值与模板行一致：仅 ReadFlag=1，其余权限位全部为 0
   -------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1
    FROM dbo.wmFlowCtl
    WHERE IsDeleted = 0 AND FlowID = @FlowID AND RoleID = -1
)
BEGIN
    INSERT INTO dbo.wmFlowCtl
    (
        FlowID, UserID, DepID, RoleID,
        AdminFlag, WriteFlag, ReadFlag,
        RejectFlag, IsDeleted, BranchID, ReactivateFlag, ReadRejectFlag,
        CUserID, CUserName, CDate, StationID,
        IsMonitorCanEditForm, IsMonitorCanRedirect, IsMonitorCanAddEditUser, IsMonitorCanEditComment,
        IsMonitorCanDel, IsMonitorCanRestore, IsMonitorCanCompletelyDel, IsMonitorCanAllocate,
        IsMonitorCanManualFlowChild, IsMonitorCanManualOutFlow, IsMonitorCanDiagnostic, IsMonitorCanSimulate,
        IsIncludeSubDep, IsMonitorCanRush, MonitorCanCompletelyDel
    )
    VALUES
    (
        @FlowID, 0, 0, -1,
        0, 0, 1,
        0, 0, 0, 0, 0,
        0, @Operator, @Now, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0
    );

    PRINT N'已新增 RoleID=-1 的权限记录。';
END;

/* -----------------------------------------------------------------------------
   ④ 补录 RoleID = 10（管理 + 编辑 + 查看）
      字段取值与模板行一致：AdminFlag=1 WriteFlag=1 ReadFlag=1
      ReactivateFlag=1，监控类权限除 IsMonitorCanAllocate / IsMonitorCanRush 外为 1
   -------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1
    FROM dbo.wmFlowCtl
    WHERE IsDeleted = 0 AND FlowID = @FlowID AND RoleID = 10
)
BEGIN
    INSERT INTO dbo.wmFlowCtl
    (
        FlowID, UserID, DepID, RoleID,
        AdminFlag, WriteFlag, ReadFlag,
        RejectFlag, IsDeleted, BranchID, ReactivateFlag, ReadRejectFlag,
        CUserID, CUserName, CDate, StationID,
        IsMonitorCanEditForm, IsMonitorCanRedirect, IsMonitorCanAddEditUser, IsMonitorCanEditComment,
        IsMonitorCanDel, IsMonitorCanRestore, IsMonitorCanCompletelyDel, IsMonitorCanAllocate,
        IsMonitorCanManualFlowChild, IsMonitorCanManualOutFlow, IsMonitorCanDiagnostic, IsMonitorCanSimulate,
        IsIncludeSubDep, IsMonitorCanRush, MonitorCanCompletelyDel
    )
    VALUES
    (
        @FlowID, 0, 0, 10,
        1, 1, 1,
        0, 0, 0, 1, 0,
        0, @Operator, @Now, 0,
        1, 1, 1, 1,
        1, 1, 1, 0,
        1, 1, 1, 1,
        0, 0, 0
    );

    PRINT N'已新增 RoleID=10 的权限记录。';
END;

/* -----------------------------------------------------------------------------
   ⑤ 回读确认
   -------------------------------------------------------------------------- */
SELECT ID, FlowID, RoleID, AdminFlag, WriteFlag, ReadFlag,
       IsDeleted, BranchID, ReactivateFlag, CUserName, CDate
FROM dbo.wmFlowCtl
WHERE IsDeleted = 0 AND RoleID IN ('-1', 10) AND FlowID = @FlowID
ORDER BY ID;
