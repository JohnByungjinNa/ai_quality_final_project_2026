param(
    [string]$Profile = "JohnNa-QA",
    [string]$Region = "ap-northeast-2",
    [string]$Bucket = "voc-qa-evidence-johnna-20693005"
)

$ErrorActionPreference = "Stop"
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsCli = if ($awsCommand) { $awsCommand.Source } else { Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2\aws.exe" }
if (-not (Test-Path -LiteralPath $awsCli)) { throw "AWS CLI v2 was not found." }
$events = (& $awsCli cloudtrail lookup-events `
    --lookup-attributes "AttributeKey=ResourceName,AttributeValue=$Bucket" `
    --profile $Profile `
    --region $Region `
    --max-results 50 `
    --output json | ConvertFrom-Json).Events

$managementEvents = @(
    "CreateBucket",
    "PutBucketPublicAccessBlock",
    "PutBucketEncryption",
    "PutBucketVersioning",
    "PutBucketLifecycle",
    "PutBucketPolicy",
    "PutBucketTagging"
)

$events |
    Where-Object { $managementEvents -contains $_.EventName } |
    Select-Object EventTime, EventName, Username, EventId |
    Sort-Object EventTime |
    Format-Table -AutoSize

Write-Output "Note: PutObject and DeleteObject are S3 data events and are not included in default Event history."
