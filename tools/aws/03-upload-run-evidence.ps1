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
$evidenceRoot = Join-Path $repositoryRoot "reports\voc_quality_runs\$RunId\evidence"
$allowedNames = @("step10_acceptance.json", "step10_acceptance.md")
$files = @()
$secretPattern = "(?i)(AKIA|ASIA)[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._-]{20,}"

foreach ($name in $allowedNames) {
    $path = Join-Path $evidenceRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required evidence file was not found: $path"
    }
    $item = Get-Item -LiteralPath $path
    if ($item.Length -gt 5MB) {
        throw "Evidence file exceeds the 5 MB limit: $name"
    }
    if ((Get-Content -Raw -Encoding utf8 -LiteralPath $path) -match $secretPattern) {
        throw "Potential secret detected; upload stopped: $name"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    $key = "voc-quality-runs/$RunId/evidence/$name"
    $files += [pscustomobject]@{
        name = $name
        key = $key
        size_bytes = $item.Length
        sha256 = $hash
    }
}

$manifest = [ordered]@{
    schema_version = "1.0"
    run_id = $RunId
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    bucket = $Bucket
    prefix = "voc-quality-runs/$RunId"
    files = $files
}
$manifestPath = Join-Path $evidenceRoot "aws_s3_manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $manifestPath

foreach ($file in $files) {
    $path = Join-Path $evidenceRoot $file.name
    $contentType = if ($file.name.EndsWith(".json")) { "application/json" } else { "text/markdown" }
    & $awsCli s3api put-object `
        --bucket $Bucket `
        --key $file.key `
        --body $path `
        --content-type $contentType `
        --server-side-encryption AES256 `
        --metadata "sha256=$($file.sha256),run-id=$RunId" `
        --profile $Profile `
        --region $Region *> $null
    if ($LASTEXITCODE -ne 0) { throw "S3 upload failed: $($file.name)" }
}

$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
$manifestKey = "voc-quality-runs/$RunId/manifest.json"
& $awsCli s3api put-object `
    --bucket $Bucket `
    --key $manifestKey `
    --body $manifestPath `
    --content-type "application/json" `
    --server-side-encryption AES256 `
    --metadata "sha256=$manifestHash,run-id=$RunId" `
    --profile $Profile `
    --region $Region *> $null
if ($LASTEXITCODE -ne 0) { throw "Manifest upload failed." }

Write-Output "Uploaded evidence for $RunId"
Write-Output "Manifest: s3://$Bucket/$manifestKey"
