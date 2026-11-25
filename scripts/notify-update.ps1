[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

git -C $RepoRoot fetch --tags --prune 2>$null | Out-Null

$localVersion = Get-LocalVersion
$latestTag = git -C $RepoRoot tag --list 'v*' |
    ForEach-Object { [PSCustomObject]@{ Tag = $_; Version = ($_ -replace '^v', '') } } |
    Sort-Object Version -Descending |
    Select-Object -First 1

if (-not $latestTag) {
    Write-Host '远端暂无版本标签。'
    exit 0
}

if ($localVersion -eq $latestTag.Version) {
    Write-Host "form-flow-builder 已是最新版本：$localVersion"
    exit 0
}

$message = "form-flow-builder 有新版本 $($latestTag.Version)，当前本地版本 $localVersion。确认后可运行 install.ps1 更新。"
Write-Host $message -ForegroundColor Yellow

try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message, 'form-flow-builder 更新提醒') | Out-Null
} catch {
    Write-Host '弹窗不可用，已在终端输出更新提醒。'
}
