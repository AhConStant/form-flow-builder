# 把 legacy .doc / .docx 统一转成 .docx，便于用 python zipfile 解析表格
#
# 用法（PowerShell）:
#   .\doc2docx.ps1 -Src "D:\工作\武汉船舶\流程梳理\流程梳理" -OutDir "D:\工作\武汉船舶\_converted"
#
# 关键坑（实测）：
#   1. Word COM 单实例连续 Open 多个文件会卡死 —— 必须每个文件新建/释放一个实例。
#   2. 用 Documents.OpenNoRepairDialog，不要用 Open（避免修复弹窗阻塞）。
#   3. 老 .doc 可能带加密标记，第 5 个参数传显式空密码 ""。
#   4. SaveAs2 第二参数 16 = wdFormatDocumentDefault(.docx)。
#   5. finally 里必须 Quit + ReleaseComObject，否则残留 WINWORD.EXE 进程。

param(
    [Parameter(Mandatory = $true)][string]$Src,
    [string]$OutDir = (Join-Path $Src "_converted")
)

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$files = Get-ChildItem -Path $Src -Include *.doc, *.docx -File -Recurse
if (-not $files) { Write-Output "没有找到 doc/docx：$Src"; exit 1 }

foreach ($f in $files) {
    if ($f.Extension -eq ".docx") {
        Copy-Item $f.FullName (Join-Path $OutDir $f.BaseName + ".docx") -Force
        Write-Output "COPY $($f.Name)"
        continue
    }
    $word = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        $doc = $word.Documents.OpenNoRepairDialog($f.FullName, $false, $true, $false, "")
        $out = Join-Path $OutDir ($f.BaseName + ".docx")
        $doc.SaveAs2($out, 16)
        $doc.Close(0)
        Write-Output "OK   $($f.Name) -> $out"
    }
    catch {
        Write-Output "FAIL $($f.Name): $($_.Exception.Message)"
    }
    finally {
        if ($word) {
            $word.Quit()
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
            [GC]::Collect()
        }
    }
}
Write-Output "DONE -> $OutDir"
