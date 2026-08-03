param(
    [string]$Profile = "JohnNa-QA",
    [string]$Region = "ap-northeast-2",
    [string]$Bucket = "voc-qa-evidence-johnna-20693005"
)

$ErrorActionPreference = "Stop"
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsCli = if ($awsCommand) { $awsCommand.Source } else { Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2\aws.exe" }
if (-not (Test-Path -LiteralPath $awsCli)) { throw "AWS CLI v2 was not found." }
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$configRoot = Join-Path $repositoryRoot "config\aws"
$lifecyclePath = Join-Path $configRoot "voc-qa-lifecycle.json"
$policyPath = Join-Path $configRoot "voc-qa-bucket-policy.json"

& $awsCli s3api head-bucket --bucket $Bucket --profile $Profile 2>$null
if ($LASTEXITCODE -ne 0) {
    & $awsCli s3api create-bucket `
        --bucket $Bucket `
        --region $Region `
        --create-bucket-configuration "LocationConstraint=$Region" `
        --object-ownership BucketOwnerEnforced `
        --profile $Profile
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the S3 bucket." }
}

& $awsCli s3api put-public-access-block --bucket $Bucket --profile $Profile `
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure S3 Public Access Block." }

& $awsCli s3api put-bucket-encryption --bucket $Bucket --profile $Profile `
    --server-side-encryption-configuration "Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256},BucketKeyEnabled=false}]"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure default S3 encryption." }

& $awsCli s3api put-bucket-versioning --bucket $Bucket --profile $Profile `
    --versioning-configuration "Status=Enabled"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure S3 versioning." }

& $awsCli s3api put-bucket-lifecycle-configuration --bucket $Bucket --profile $Profile `
    --lifecycle-configuration "file://$lifecyclePath"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure the S3 lifecycle." }

& $awsCli s3api put-bucket-policy --bucket $Bucket --profile $Profile `
    --policy "file://$policyPath"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure the TLS-only bucket policy." }

& $awsCli s3api put-bucket-tagging --bucket $Bucket --profile $Profile `
    --tagging "TagSet=[{Key=Project,Value=VOC-Quality},{Key=Environment,Value=training},{Key=Owner,Value=JohnNa-QA},{Key=ManagedBy,Value=aws-cli}]"
if ($LASTEXITCODE -ne 0) { throw "Failed to configure S3 bucket tags." }

Write-Output "S3 configuration applied: $Bucket"
