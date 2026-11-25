[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

. (Join-Path $PSScriptRoot 'common.ps1')

$tag = Resolve-Tag -Version $Version
if (-not $tag) {
    Write-Error "未找到版本标签：v$Version"
    exit 1
}

$backup = Backup-CurrentSkill
git -C $RepoRoot checkout $tag
Copy-RepoToInstallDir
git -C $RepoRoot checkout main

Write-Host "已回退到版本：$Version"
Write-Host "安装目录：$InstallDir"
if ($backup) {
    Write-Host "回退前备份：$backup"
}
