<#
.SYNOPSIS
    Restore a ChessPulse dump into a temporary local database and verify it.

.DESCRIPTION
    Starts the Compose `db` service, creates a throw-away database, restores the
    dump into it with pg_restore, checks that `alembic_version` is readable and
    counts the public tables, then drops the test database.

    This does not touch the database used by the local application. Run it before
    deleting or replacing any source database.

.PARAMETER DumpFile
    Path to a custom-format dump produced by scripts/render-db-backup.ps1 or
    `pg_dump -Fc`.

.PARAMETER DatabaseUser
    PostgreSQL role used by the local Compose database. Defaults to `chesspulse`.

.PARAMETER TestDatabase
    Name of the throw-away database. Defaults to `chesspulse_restore_test`.

.PARAMETER KeepTestDatabase
    Keep the test database and the copied dump for inspection after a failure.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/verify-db-backup.ps1 `
        -DumpFile .\chesspulse-render-20261114-120000.dump
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpFile,

    [string]$DatabaseUser = "chesspulse",
    [string]$TestDatabase = "chesspulse_restore_test",
    [switch]$KeepTestDatabase
)

# Docker and pg_restore write progress/warnings to stderr. Under Windows
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

    if (-not (Test-Path $DumpFile)) {
        throw "Dump not found: $DumpFile"
    }
    $dumpPath = (Resolve-Path $DumpFile).Path

    if (-not (Test-Path .env)) {
        throw ".env is missing. Copy .env.example to .env and set POSTGRES_PASSWORD first."
    }

    docker compose up -d --wait db
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start the local db service."
    }

    docker compose exec -T db dropdb -U $DatabaseUser --if-exists $TestDatabase
    docker compose exec -T db createdb -U $DatabaseUser $TestDatabase
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the test database $TestDatabase."
    }

    docker compose cp $dumpPath "db:/tmp/chesspulse-restore-test.dump"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy the dump into the db container."
    }

    docker compose exec -T db pg_restore -U $DatabaseUser -d $TestDatabase `
        --no-owner --no-privileges /tmp/chesspulse-restore-test.dump
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE. Test database '$TestDatabase' was kept for inspection."
    }

    $version = (docker compose exec -T db psql -U $DatabaseUser -d $TestDatabase `
            -tAc "select version_num from alembic_version;").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
        throw "Restore completed but alembic_version could not be read."
    }

    $tables = (docker compose exec -T db psql -U $DatabaseUser -d $TestDatabase `
            -tAc "select count(*) from information_schema.tables where table_schema = 'public';").Trim()

    Write-Host "Restore OK: alembic=$version, public tables=$tables"

    if (-not $KeepTestDatabase) {
        docker compose exec -T db dropdb -U $DatabaseUser --if-exists $TestDatabase
        docker compose exec -T db rm -f /tmp/chesspulse-restore-test.dump
    }
    else {
        Write-Host "Test database kept: $TestDatabase"
    }
}
finally {
    Pop-Location
}
