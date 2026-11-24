<#
.SYNOPSIS
    Dump a Render PostgreSQL database to a local custom-format backup file.

.DESCRIPTION
    Prompts for the Render external database URL without putting it in the shell
    history, then runs pg_dump inside a throw-away PostgreSQL container. The URL
    is passed as an environment variable and removed afterwards.

    The pg_dump image major version must be >= the server major version; a newer
    server makes pg_dump abort with "server version mismatch". The script therefore
    reads the server version first and picks `postgres:<major>-alpine` on its own.
    Render has already moved databases between majors, so never assume one.

    Alongside the dump it writes `<dump>.info` (image tag and server version) so
    scripts/verify-db-backup.ps1 can restore with the matching pg_restore.

    Run from any directory; the script writes the dump into the repository root.

.PARAMETER OutputFile
    Backup file name relative to the repository root. Defaults to a timestamped
    name. Existing files are never overwritten.

.PARAMETER PostgresImage
    Override the pg_dump client image. Leave empty to auto-detect from the server
    version (recommended). If you pass one, it must be the same major version or
    newer than the server.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/render-db-backup.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/render-db-backup.ps1 `
        -OutputFile chesspulse-before-renewal.dump
#>
[CmdletBinding()]
param(
    [string]$OutputFile = "chesspulse-render-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump",
    [string]$PostgresImage = ""
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

    # psql is used only to read the server version. A 16 client can query an 18
    # server; pg_dump is the tool that refuses to dump a newer server.
    # The shell script is piped through stdin: PowerShell 5.1 mangles nested quotes
    # in native arguments, and the URL must never appear on a command line anyway.
    $probeImage = if ($PostgresImage) { $PostgresImage } else { "postgres:16.9-alpine" }
    # PowerShell pipes CRLF to a native process's stdin; the trailing `#` line
    # absorbs the stray CR instead of corrupting the last argument.
    $versionNum = (('psql "$PGURL" -tAc "show server_version_num"' + "`n#") |
        docker run --rm -i -e PGSSLMODE=require -e PGURL $probeImage sh -s 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $versionNum -notmatch '^\d{5,6}$') {
        throw "Could not read the server version. Pass -PostgresImage explicitly " +
        "(the pg_dump image must be the server major version or newer)."
    }

    $serverMajor = [int]([int]$versionNum / 10000)
    $image = if ($PostgresImage) { $PostgresImage } else { "postgres:$serverMajor-alpine" }
    Write-Host "Server major version: $serverMajor; pg_dump image: $image"

    if (-not $PostgresImage) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Pulling $image ..."
            docker pull $image
            if ($LASTEXITCODE -ne 0) {
                throw "Could not pull $image."
            }
        }
    }

    $outDir = Split-Path -Parent $outPath
    $outName = Split-Path -Leaf $outPath

    ('pg_dump --no-owner --no-privileges -Fc -f "/backup/$OUTFILE" "$PGURL"' + "`n#") |
    docker run --rm -i `
        -e PGSSLMODE=require `
        -e PGURL `
        -e "OUTFILE=$outName" `
        -v "${outDir}:/backup" `
        $image `
        sh -s

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

    # The dump header records the pg_dump major version; a restore must use the
    # same or a newer client. Keep that fact next to the file, not in chat.
    Set-Content -Path "$outPath.info" -Encoding ASCII -Value @(
        "image=$image"
        "server_version_num=$versionNum"
        "created=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    )

    Write-Host "Backup written: $($item.FullName) ($($item.Length) bytes)"
    Write-Host "Metadata: $outPath.info"
    Write-Host "Keep both out of git; verify with scripts/verify-db-backup.ps1 -DumpFile `"$outName`""
}
finally {
    Remove-Item Env:PGURL -ErrorAction SilentlyContinue
    Pop-Location
}
