<#
.SYNOPSIS
    Restore a ChessPulse dump into a throw-away PostgreSQL container and verify it.

.DESCRIPTION
    Starts a temporary PostgreSQL container of the same major version that produced
    the dump, restores the dump with pg_restore, checks that `alembic_version` is
    readable and counts the public tables, then removes the container.

    A newer pg_restore can read an older archive, but an older one cannot read a
    newer archive ("unsupported version (1.16) in file header"). The image is taken
    from `<dump>.info` written by scripts/render-db-backup.ps1, so the check runs on
    the same major version as the source database.

    This does not touch the local application database and needs no `.env`; only
    Docker is required.

.PARAMETER DumpFile
    Path to a custom-format dump produced by scripts/render-db-backup.ps1 or
    `pg_dump -Fc`.

.PARAMETER PostgresImage
    Override the restore image. Defaults to the `image=` value in `<dump>.info`.
    Must be the same major version as the dump or newer.

.PARAMETER TestDatabase
    Name of the throw-away database inside the temporary container.

.PARAMETER KeepTestDatabase
    Keep the container running for inspection instead of removing it.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/verify-db-backup.ps1 `
        -DumpFile .\chesspulse-render-20261124-120000.dump

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/verify-db-backup.ps1 `
        -DumpFile .\chesspulse-render-20261124-120000.dump -PostgresImage postgres:18-alpine
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpFile,

    [string]$PostgresImage = "",
    [string]$TestDatabase = "chesspulse_restore_test",
    [switch]$KeepTestDatabase
)

# Docker and pg_restore write progress/warnings to stderr. Under Windows
# PowerShell 5.1 that is a non-terminating NativeCommandError, so use Continue
# and check $LASTEXITCODE explicitly after every native command.
$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$container = "chesspulse-restore-test"
Push-Location $repoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker is not installed or not on PATH."
    }

    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running. Start Docker Desktop and retry."
    }

    if (-not (Test-Path $DumpFile)) {
        throw "Dump not found: $DumpFile"
    }
    $dumpPath = (Resolve-Path $DumpFile).Path
    $dumpDir = Split-Path -Parent $dumpPath
    $dumpName = Split-Path -Leaf $dumpPath

    $image = $PostgresImage
    if (-not $image) {
        $infoPath = "$dumpPath.info"
        if (Test-Path $infoPath) {
            $line = Get-Content $infoPath | Where-Object { $_ -like 'image=*' } | Select-Object -First 1
            if ($line) {
                $image = $line.Substring(6).Trim()
            }
        }
    }
    if (-not $image) {
        throw "Unknown restore image: $dumpPath.info is missing. Pass -PostgresImage " +
        "(same major version as the dump or newer, for example postgres:18-alpine)."
    }

    docker rm -f $container *> $null

    docker run -d --name $container `
        -e POSTGRES_HOST_AUTH_METHOD=trust `
        -e POSTGRES_DB=$TestDatabase `
        -v "${dumpDir}:/backup:ro" `
        $image | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start the temporary container from $image."
    }

    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        docker exec $container pg_isready -U postgres -d $TestDatabase *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        throw "The temporary PostgreSQL container did not become ready."
    }

    docker exec $container pg_restore -U postgres -d $TestDatabase `
        --no-owner --no-privileges "/backup/$dumpName"
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE. Container '$container' was kept for inspection."
    }

    $version = (docker exec $container psql -U postgres -d $TestDatabase `
            -tAc "select version_num from alembic_version;").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
        throw "Restore completed but alembic_version could not be read. Container '$container' was kept for inspection."
    }

    $tables = (docker exec $container psql -U postgres -d $TestDatabase `
            -tAc "select count(*) from information_schema.tables where table_schema = 'public';").Trim()

    Write-Host "Restore OK: image=$image, alembic=$version, public tables=$tables"

    if ($KeepTestDatabase) {
        Write-Host "Container kept: $container (connect with: docker exec -it $container psql -U postgres -d $TestDatabase)"
    }
    else {
        docker rm -f $container *> $null
    }
}
finally {
    if ($KeepTestDatabase -eq $false -and (docker ps -a --filter "name=^$container$" --format '{{.Names}}')) {
        # A failure path: keep the container so the error can be inspected, and
        # say so instead of silently leaving an orphan.
        Write-Host "Temporary container '$container' was kept for inspection (remove with: docker rm -f $container)"
    }
    Pop-Location
}
