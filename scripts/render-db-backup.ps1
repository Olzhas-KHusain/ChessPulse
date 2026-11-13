<#
.SYNOPSIS
    Dump a Render PostgreSQL database to a local custom-format backup file.

.DESCRIPTION
    Prompts for the Render external database URL without putting it in the shell
    history, then runs pg_dump inside a throw-away PostgreSQL container. The URL
    is passed as an environment variable and removed afterwards.

    Run from any directory; the script writes the dump into the repository root.

.PARAMETER OutputFile
    Backup file name relative to the repository root. Defaults to a timestamped
    name. Existing files are never overwritten.

.PARAMETER PostgresImage
    pg_dump client image. Use the same PostgreSQL major version as the Render
    server (the Compose stack uses 16.9).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/render-db-backup.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/render-db-backup.ps1 `
        -OutputFile chesspulse-before-renewal.dump -PostgresImage postgres:17-alpine
#>
[CmdletBinding()]
param(
    [string]$OutputFile = "chesspulse-render-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump",
    [string]$PostgresImage = "postgres:16.9-alpine"
)

# Docker writes progress and connection errors to stderr. Under Windows
# PowerShell 5.1 that is a non-terminating NativeCommandError, so use Continue
# and check $LASTEXITCODE explicitly after every native command.
$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker is not installed or not on PATH."
    }

    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running. Start Docker Desktop and retry."
    }

    $outPath = Join-Path $repoRoot $OutputFile
    if (Test-Path $outPath) {
        throw "Refusing to overwrite an existing file: $outPath"
    }

    $secureUrl = Read-Host "Render external database URL" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
    try {
        $env:PGURL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($env:PGURL)) {
        throw "No database URL was provided."
    }

    docker run --rm `
        -e PGSSLMODE=require `
        -e PGURL `
        -e "OUTFILE=$OutputFile" `
        -v "${repoRoot}:/backup" `
        $PostgresImage `
        sh -c 'pg_dump --no-owner --no-privileges -Fc -f "/backup/$OUTFILE" "$PGURL"'

    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path $outPath)) {
        throw "pg_dump reported success but the backup file is missing: $outPath"
    }

    $item = Get-Item $outPath
    if ($item.Length -le 0) {
        throw "The backup file is empty: $outPath"
    }

    Write-Host "Backup written: $($item.FullName) ($($item.Length) bytes)"
    Write-Host "Keep it out of git; verify it with scripts/verify-db-backup.ps1."
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
    Pop-Location
}
