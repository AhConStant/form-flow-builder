/* =============================================================================
   全部流程 —— 流程权限（wmFlowCtl）遍历补录脚本（不带 name 条件）
   -----------------------------------------------------------------------------
   场景：批量导入表单/流程后，wmFlowCtl 没有对应流程的权限记录，
         导致流程"没有流程权限"。本脚本遍历 wmFlowSet 中所有有效流程，
         按标准模板补两条（先补 -1，再补 10）：
           RoleID = -1 ：仅 ReadFlag=1（全员可查看）
           RoleID = 10 ：AdminFlag=1 / WriteFlag=1 / ReadFlag=1（管理 + 编辑 + 查看）
   范围：wmFlowSet  IsDeleted=0 and IsUse=1（无 name 条件）
         wmFlowCtl  IsDeleted=0 and RoleID in ('-1',10) and FlowID=@FlowID
   说明：ID 为自增列，不写入；CDate 取当前时间，CUserName 取 N'系统'（与模板一致）
         脚本幂等：按角色逐个判断，缺哪条补哪条，重复执行不会产生重复数据
   环境：SQL Server；执行前请先在 SSMS 中选中目标数据库（脚本不含 USE 语句）
   ============================================================================= */

SET NOCOUNT ON;
SET XACT_ABORT ON;

/* -----------------------------------------------------------------------------
   ① 预览：列出权限不全的流程（只读，不修改数据）
      若结果为空，说明所有流程都已具备 RoleID=-1 / 10 两条记录，无需补录
   -------------------------------------------------------------------------- */
SELECT f.FlowID,
       f.Name,
       CASE WHEN EXISTS (SELECT 1 FROM dbo.wmFlowCtl c
                         WHERE c.IsDeleted = 0 AND c.FlowID = f.FlowID AND c.RoleID = 10)
            THEN 1 ELSE 0 END AS Has_Role10,
       CASE WHEN EXISTS (SELECT 1 FROM dbo.wmFlowCtl c
                         WHERE c.IsDeleted = 0 AND c.FlowID = f.FlowID AND c.RoleID = -1)
            THEN 1 ELSE 0 END AS Has_RoleMinus1
FROM dbo.wmFlowSet f
WHERE f.IsDeleted = 0 AND f.IsUse = 1
  AND (NOT EXISTS (SELECT 1 FROM dbo.wmFlowCtl c
                   WHERE c.IsDeleted = 0 AND c.FlowID = f.FlowID AND c.RoleID = 10)
       OR NOT EXISTS (SELECT 1 FROM dbo.wmFlowCtl c
                      WHERE c.IsDeleted = 0 AND c.FlowID = f.FlowID AND c.RoleID = -1))
ORDER BY f.FlowID;

/* -----------------------------------------------------------------------------
   ② 遍历补录
   -------------------------------------------------------------------------- */
DECLARE @FlowID    int;
DECLARE @FlowName  nvarchar(400);
DECLARE @Now       datetime      = GETDATE();
DECLARE @Operator  nvarchar(400) = N'系统';
DECLARE @Touched   bit;

DECLARE @FlowTotal   int = 0;   -- 遍历流程数
DECLARE @Insert10    int = 0;   -- 新增 RoleID=10 条数
DECLARE @InsertM1    int = 0;   -- 新增 RoleID=-1 条数
DECLARE @FlowTouched int = 0;   -- 实际发生补录的流程数

DECLARE curFlow CURSOR LOCAL FAST_FORWARD FOR
    SELECT FlowID, Name
    FROM dbo.wmFlowSet
    WHERE IsDeleted = 0 AND IsUse = 1   -- 无 name 条件
    ORDER BY FlowID;

BEGIN TRY
    BEGIN TRAN;

    OPEN curFlow;
    FETCH NEXT FROM curFlow INTO @FlowID, @FlowName;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @FlowTotal += 1;
        SET @Touched = 0;

        /* 检查当前流程的权限数据（条件按要求原样保留） */
        IF NOT EXISTS (
            SELECT 1
            FROM dbo.wmFlowCtl
            WHERE IsDeleted = 0 AND RoleID IN ('-1', 10) AND FlowID = @FlowID
        )
            PRINT N'[' + CAST(@FlowID AS nvarchar(20)) + N'] ' + @FlowName
                  + N'：无权限数据，按模板补录';

        /* ---- RoleID = -1（全员查看）---- */
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

            SET @InsertM1 += 1;
            SET @Touched = 1;
        END;

        /* ---- RoleID = 10（管理 + 编辑 + 查看）---- */
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

            SET @Insert10 += 1;
            SET @Touched = 1;
        END;

        IF @Touched = 1 SET @FlowTouched += 1;

        FETCH NEXT FROM curFlow INTO @FlowID, @FlowName;
    END;

    CLOSE curFlow;
    DEALLOCATE curFlow;

    COMMIT;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'curFlow') >= 0
    BEGIN
        CLOSE curFlow;
        DEALLOCATE curFlow;
    END;

    IF @@TRANCOUNT > 0 ROLLBACK;

    PRINT N'执行失败：' + ERROR_MESSAGE();
    THROW;
END CATCH;

PRINT N'----------------------------------------';
PRINT N'遍历流程数：' + CAST(@FlowTotal AS nvarchar(20));
PRINT N'新增 RoleID=-1 ：' + CAST(@InsertM1 AS nvarchar(20)) + N' 条';
PRINT N'新增 RoleID=10 ：' + CAST(@Insert10 AS nvarchar(20)) + N' 条';
PRINT N'发生补录的流程数：' + CAST(@FlowTouched AS nvarchar(20));
PRINT N'----------------------------------------';

/* -----------------------------------------------------------------------------
   ③ 复核：各流程当前的权限记录条数（正常应为 2，即 RoleID=-1 与 10 各一条）
   -------------------------------------------------------------------------- */
SELECT f.FlowID,
       f.Name,
       COUNT(c.ID) AS CtlRows,
       SUM(CASE WHEN c.RoleID = 10 THEN 1 ELSE 0 END) AS Role10Rows,
       SUM(CASE WHEN c.RoleID = -1 THEN 1 ELSE 0 END) AS RoleMinus1Rows
FROM dbo.wmFlowSet f
LEFT JOIN dbo.wmFlowCtl c
       ON c.FlowID = f.FlowID AND c.IsDeleted = 0 AND c.RoleID IN ('-1', 10)
WHERE f.IsDeleted = 0 AND f.IsUse = 1
GROUP BY f.FlowID, f.Name
ORDER BY f.FlowID;
