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

    $excludeNames = @('.git', '.github', 'scripts', 'RELEASES.md', 'README.md', 'VERSION')
    $sourceItems = Get-ChildItem -LiteralPath $RepoRoot -Force | Where-Object {
        $excludeNames -notcontains $_.Name
    }

    foreach ($item in $sourceItems) {
        Copy-Item -LiteralPath $item.FullName -Destination $InstallDir -Recurse -Force
    }
}

function Resolve-Tag {
    param([string]$Version)
    if ([string]::IsNullOrWhiteSpace($Version)) { return $null }
    $tag = "v$Version"
    git -C $RepoRoot tag --list $tag
    return $tag
}
