[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

git -C $RepoRoot fetch --tags --prune 2>$null | Out-Null

$tags = git -C $RepoRoot tag --list 'v*' |
    ForEach-Object { [PSCustomObject]@{ Tag = $_; Version = ($_ -replace '^v', '') } } |
    Sort-Object Version -Descending

if (-not $tags) {
    Write-Host '暂无可列出的版本标签。'
    exit 0
}

$tags | Format-Table -AutoSize Tag, Version
