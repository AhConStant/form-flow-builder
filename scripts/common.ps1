[CmdletBinding()]
param()

$Script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$Script:SkillName = 'form-flow-builder'
$Script:WorkbuddySkillsDir = Join-Path $env:USERPROFILE '.workbuddy\skills'
$Script:InstallDir = Join-Path $WorkbuddySkillsDir $SkillName
$Script:BackupRoot = Join-Path $WorkbuddySkillsDir '.backup'

function Get-LocalVersion {
    $versionFile = Join-Path $RepoRoot 'VERSION'
    if (Test-Path -LiteralPath $versionFile) {
        return (Get-Content -LiteralPath $versionFile -Raw).Trim()
    }
    return '0.0.0'
}

function Get-SkillVersion {
    # 本仓库打包的上游技能包版本（与仓库版本号是两套编号）
    $f = Join-Path $RepoRoot 'SKILL_VERSION'
    if (Test-Path -LiteralPath $f) {
        return (Get-Content -LiteralPath $f -Raw).Trim()
    }
    return 'unknown'
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Backup-CurrentSkill {
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        return $null
    }

    Ensure-Directory $BackupRoot
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupDir = Join-Path $BackupRoot "$SkillName-$stamp"
    Copy-Item -LiteralPath $InstallDir -Destination $backupDir -Recurse -Force
    return $backupDir
}

function Copy-RepoToInstallDir {
    Ensure-Directory $InstallDir

    # 仓库管理文件不进技能目录；scripts/ 单独处理——里面既有技能运行脚本（必须复制），
    # 也有仓库管理脚本（install/rollback 等，不复制）。
    $excludeNames = @('.git', '.github', 'scripts', 'RELEASES.md', 'README.md', 'VERSION', 'SKILL_VERSION')
    $sourceItems = Get-ChildItem -LiteralPath $RepoRoot -Force | Where-Object {
        $excludeNames -notcontains $_.Name
    }

    foreach ($item in $sourceItems) {
        Copy-Item -LiteralPath $item.FullName -Destination $InstallDir -Recurse -Force
    }

    # 技能运行必需脚本（少了这些，技能装上不能生成任何表单）
    $runtimeScripts = @(
        'build_forms.py',
        'build_export.py',
        'build_flowchart.py',
        'render_web_preview.py',
        'validate_form.py',
        'scan_gray_hints.py',
        'flow_types.py',
        'doc2docx.ps1'
    )
    $srcScripts = Join-Path $RepoRoot 'scripts'
    $dstScripts = Join-Path $InstallDir 'scripts'
    Ensure-Directory $dstScripts
    foreach ($name in $runtimeScripts) {
        $src = Join-Path $srcScripts $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination $dstScripts -Force
        } else {
            Write-Warning "仓库缺少技能运行脚本：scripts\$name"
        }
    }
}

function Resolve-Tag {
    param([string]$Version)
    if ([string]::IsNullOrWhiteSpace($Version)) { return $null }
    $tag = "v$Version"
    git -C $RepoRoot tag --list $tag
    return $tag
}
