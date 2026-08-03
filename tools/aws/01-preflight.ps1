param(
    [string]$Profile = "JohnNa-QA",
    [string]$Region = "ap-northeast-2",
    [string]$Bucket = "voc-qa-evidence-johnna-20693005"
)

$ErrorActionPreference = "Stop"

function Resolve-AwsCli {
    $command = Get-Command aws -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $userInstall = Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2\aws.exe"
    if (Test-Path -LiteralPath $userInstall) { return $userInstall }
    throw "AWS CLI v2 was not found."
}

$awsCli = Resolve-AwsCli
$identity = (& $awsCli sts get-caller-identity --profile $Profile --region $Region --output json | ConvertFrom-Json)
if ($identity.Arn -notmatch ":user/JohnNa-QA$") {
    throw "The caller must be IAM user JohnNa-QA. Do not use a root or different session."
}

$location = (& $awsCli s3api get-bucket-location --bucket $Bucket --profile $Profile --output json | ConvertFrom-Json).LocationConstraint
$publicAccess = (& $awsCli s3api get-public-access-block --bucket $Bucket --profile $Profile --output json | ConvertFrom-Json).PublicAccessBlockConfiguration
$encryption = (((& $awsCli s3api get-bucket-encryption --bucket $Bucket --profile $Profile --output json | ConvertFrom-Json).ServerSideEncryptionConfiguration.Rules).ApplyServerSideEncryptionByDefault.SSEAlgorithm -join ",")
$versioning = (& $awsCli s3api get-bucket-versioning --bucket $Bucket --profile $Profile --output json | ConvertFrom-Json).Status
$accountId = $identity.Account
$budget = (& $awsCli budgets describe-budget --account-id $accountId --budget-name "VOC-QA-Monthly-5USD" --profile $Profile --output json | ConvertFrom-Json).Budget

[pscustomobject]@{
    Caller = "JohnNa-QA"
    Region = $location
    PublicAccessBlocked = [bool]($publicAccess.BlockPublicAcls -and $publicAccess.IgnorePublicAcls -and $publicAccess.BlockPublicPolicy -and $publicAccess.RestrictPublicBuckets)
    Encryption = $encryption
    Versioning = $versioning
    MonthlyBudget = "$($budget.BudgetLimit.Amount) $($budget.BudgetLimit.Unit)"
} | Format-List
