[CmdletBinding()]
param(
    [Parameter()]
    [string]$Label = "manual",

    [Parameter()]
    [string]$BackupRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectName = Split-Path $projectRoot -Leaf
$projectRootPrefix = $projectRoot.TrimEnd('\') + '\'

function Get-ProjectRelativePath {
    param([Parameter(Mandatory)][string]$FullName)

    $fullPath = [System.IO.Path]::GetFullPath($FullName)
    if (-not $fullPath.StartsWith($projectRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "프로젝트 루트 밖의 파일은 백업할 수 없습니다: $fullPath"
    }
    return $fullPath.Substring($projectRootPrefix.Length)
}

if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $workspaceParent = Split-Path $projectRoot -Parent
    $BackupRoot = Join-Path $workspaceParent (Join-Path "_backups" $projectName)
}

$backupRootFull = [System.IO.Path]::GetFullPath($BackupRoot)
if ($backupRootFull.TrimEnd('\') -eq $projectRoot.TrimEnd('\')) {
    throw "백업 위치는 프로젝트 루트와 달라야 합니다."
}

$invalidChars = [System.IO.Path]::GetInvalidFileNameChars()
$safeLabelChars = foreach ($char in $Label.Trim().ToCharArray()) {
    if ($invalidChars -contains $char -or [char]::IsWhiteSpace($char)) { '-' } else { $char }
}
$safeLabel = (-join $safeLabelChars).Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel)) {
    $safeLabel = "manual"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveName = "{0}-{1}-{2}.zip" -f $projectName, $timestamp, $safeLabel
New-Item -ItemType Directory -Path $backupRootFull -Force | Out-Null
$archivePath = Join-Path $backupRootFull $archiveName
$checksumPath = "$archivePath.sha256"

$excludedDirectories = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".pytest_tmp", ".runtime", "node_modules", "logs", "reports",
    "data", "user_Docs", "backups", "_backups"
) | ForEach-Object { [void]$excludedDirectories.Add($_) }

$excludedExtensions = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(".pyc", ".pyo", ".pyd", ".log", ".tmp", ".bak") |
    ForEach-Object { [void]$excludedExtensions.Add($_) }

function Test-IsExcludedFile {
    param([System.IO.FileInfo]$File)

    $relativePath = Get-ProjectRelativePath -FullName $File.FullName
    $segments = $relativePath -split '[\\/]'
    foreach ($segment in $segments[0..([Math]::Max(0, $segments.Length - 2))]) {
        if ($excludedDirectories.Contains($segment)) {
            return $true
        }
    }

    if ($excludedExtensions.Contains($File.Extension)) {
        return $true
    }

    $name = $File.Name
    if ($name -ieq ".env" -or $name -ieq "secrets.toml") {
        return $true
    }
    if ($name -like ".env.*" -and $name -notin @(".env.example", ".env.sample", ".env.template")) {
        return $true
    }

    return $false
}

$files = @(
    Get-ChildItem -LiteralPath $projectRoot -Recurse -File -Force |
        Where-Object { -not (Test-IsExcludedFile -File $_) } |
        Sort-Object FullName
)

if ($files.Count -eq 0) {
    throw "백업할 파일을 찾지 못했습니다."
}

$manifestFiles = [System.Collections.Generic.List[object]]::new()
$totalSourceBytes = [long]0
foreach ($file in $files) {
    $relativePath = (Get-ProjectRelativePath -FullName $file.FullName).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $totalSourceBytes += $file.Length
    $manifestFiles.Add([ordered]@{
        path = $relativePath
        size_bytes = $file.Length
        sha256 = $hash
    })
}

$manifest = [ordered]@{
    schema_version = 1
    created_at = (Get-Date).ToString("o")
    source_root = $projectRoot
    project = $projectName
    label = $Label
    excluded = @(
        "secret files (.env*, secrets.toml; examples/templates are retained)",
        "virtual environments and dependency caches",
        "runtime, logs, reports, data, and user_Docs",
        "Git metadata and nested backup directories"
    )
    file_count = $manifestFiles.Count
    total_bytes = $totalSourceBytes
    files = $manifestFiles
}
$manifestJson = $manifest | ConvertTo-Json -Depth 6

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

try {
    $fileStream = [System.IO.File]::Open(
        $archivePath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
    try {
        $archive = [System.IO.Compression.ZipArchive]::new(
            $fileStream,
            [System.IO.Compression.ZipArchiveMode]::Create,
            $false
        )
        try {
            foreach ($file in $files) {
                $entryName = (Get-ProjectRelativePath -FullName $file.FullName).Replace('\', '/')
                [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $file.FullName,
                    $entryName,
                    [System.IO.Compression.CompressionLevel]::Optimal
                )
            }

            $manifestEntry = $archive.CreateEntry("backup-manifest.json")
            $manifestStream = $manifestEntry.Open()
            try {
                $writer = [System.IO.StreamWriter]::new(
                    $manifestStream,
                    [System.Text.UTF8Encoding]::new($false)
                )
                try {
                    $writer.Write($manifestJson)
                }
                finally {
                    $writer.Dispose()
                }
            }
            finally {
                $manifestStream.Dispose()
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    finally {
        $fileStream.Dispose()
    }

    $verifyArchive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $expectedEntryCount = $files.Count + 1
        if ($verifyArchive.Entries.Count -ne $expectedEntryCount) {
            throw "ZIP 검증 실패: 예상 항목 $expectedEntryCount, 실제 항목 $($verifyArchive.Entries.Count)"
        }
        if (-not ($verifyArchive.Entries | Where-Object FullName -eq "backup-manifest.json")) {
            throw "ZIP 검증 실패: backup-manifest.json이 없습니다."
        }
    }
    finally {
        $verifyArchive.Dispose()
    }

    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(
        $checksumPath,
        "$archiveHash  $archiveName`n",
        [System.Text.UTF8Encoding]::new($false)
    )

    [pscustomobject]@{
        Archive = $archivePath
        Checksum = $checksumPath
        FileCount = $files.Count
        SourceBytes = $manifest.total_bytes
        ArchiveBytes = (Get-Item -LiteralPath $archivePath).Length
        Sha256 = $archiveHash
    }
}
catch {
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    if (Test-Path -LiteralPath $checksumPath) {
        Remove-Item -LiteralPath $checksumPath -Force
    }
    throw
}
