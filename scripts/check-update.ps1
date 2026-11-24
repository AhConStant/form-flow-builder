[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

git -C $RepoRoot fetch --tags --prune 2>$null | Out-Null

$localVersion = Get-LocalVersion
$latestTag = git -C $RepoRoot tag --list 'v*' |
    ForEach-Object { [PSCustomObject]@{ Tag = $_; Version = ($_ -replace '^v', '') } } |
    Sort-Object Version -Descending |
    Select-Object -First 1

$remoteVersion = if ($latestTag) { $latestTag.Version } else { 'unknown' }

Write-Host "本地版本：$localVersion"
Write-Host "远端版本：$remoteVersion"

if ($latestTag -and $localVersion -ne $latestTag.Version) {
    Write-Host "发现新版本：$($latestTag.Tag)" -ForegroundColor Yellow
    Write-Host "确认后可执行：pwsh -File scripts/install.ps1 -Version $($latestTag.Version)"
    exit 0
}

Write-Host "当前已是最新版本。" -ForegroundColor Green
