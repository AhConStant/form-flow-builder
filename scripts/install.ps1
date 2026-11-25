[CmdletBinding()]
param(
    [string]$Version
)

. (Join-Path $PSScriptRoot 'common.ps1')

if ($Version) {
    $tag = Resolve-Tag -Version $Version
    if (-not $tag) {
        Write-Error "未找到版本标签：v$Version"
        exit 1
    }
    git -C $RepoRoot checkout $tag
}

$backup = Backup-CurrentSkill
Copy-RepoToInstallDir

$installedVersion = Get-LocalVersion
$skillVersion = Get-SkillVersion
Write-Host "安装完成：$SkillName 仓库版本 $installedVersion（技能包 $skillVersion）"
Write-Host "说明：仓库版本用于本仓库发布管理，技能包版本对应上游技能（见 CHANGELOG.md）。"
Write-Host "安装目录：$InstallDir"
if ($backup) {
    Write-Host "旧版本备份：$backup"
}

if ($Version) {
    git -C $RepoRoot checkout main
}
