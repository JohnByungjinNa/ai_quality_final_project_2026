param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$Profile = "JohnNa-QA",
    [string]$Region = "ap-northeast-2",
    [string]$Bucket = "voc-qa-evidence-johnna-20693005"
)

$ErrorActionPreference = "Stop"
if ($RunId -notmatch "^RUN-[0-9]{8}-[0-9]{6}-[0-9]{6}-[0-9a-f]{4}$") {
    throw "Invalid Run ID."
}

$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsCli = if ($awsCommand) { $awsCommand.Source } else { Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2\aws.exe" }
if (-not (Test-Path -LiteralPath $awsCli)) { throw "AWS CLI v2 was not found." }
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$manifestPath = Join-Path $repositoryRoot "reports\voc_quality_runs\$RunId\evidence\aws_s3_manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Local manifest was not found: $manifestPath"
}
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("voc-qa-verify-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
    $remoteManifestPath = Join-Path $tempRoot "manifest.json"
    & $awsCli s3api get-object `
        --bucket $Bucket `
        --key "voc-quality-runs/$RunId/manifest.json" `
        --profile $Profile `
        --region $Region `
        $remoteManifestPath *> $null
    if ($LASTEXITCODE -ne 0) { throw "Failed to download the S3 manifest." }
    $localManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
    $remoteManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $remoteManifestPath).Hash.ToLowerInvariant()
    if ($localManifestHash -ne $remoteManifestHash) { throw "Manifest SHA-256 mismatch." }
    Write-Output "PASS manifest.json $remoteManifestHash"

    $manifest = Get-Content -Raw -Encoding utf8 -LiteralPath $remoteManifestPath | ConvertFrom-Json
    foreach ($file in $manifest.files) {
        $downloadPath = Join-Path $tempRoot $file.name
        & $awsCli s3api get-object `
            --bucket $Bucket `
            --key $file.key `
            --profile $Profile `
            --region $Region `
            $downloadPath *> $null
        if ($LASTEXITCODE -ne 0) { throw "S3 download verification failed: $($file.name)" }
        $remoteHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $downloadPath).Hash.ToLowerInvariant()
        if ($remoteHash -ne $file.sha256) {
            throw "SHA-256 mismatch: $($file.name)"
        }
        if ((Get-Item -LiteralPath $downloadPath).Length -ne $file.size_bytes) {
            throw "File size mismatch: $($file.name)"
        }
        Write-Output "PASS $($file.name) $remoteHash"
    }
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
