param(
    [string]$Profile = "JohnNa-QA",
    [string]$Region = "ap-northeast-2",
    [string]$ExpectedUser = "JohnNa-QA",
    [string]$AccountAlias = "johnna-qa"
)

$ErrorActionPreference = "Stop"
$signInUrl = "https://$AccountAlias.signin.aws.amazon.com/console/"

function Resolve-AwsCli {
    $command = Get-Command aws -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $userInstall = Join-Path $env:LOCALAPPDATA "Programs\Amazon\AWSCLIV2\aws.exe"
    if (Test-Path -LiteralPath $userInstall) {
        return $userInstall
    }

    $installer = Join-Path ([IO.Path]::GetTempPath()) "AWSCLIV2-User.msi"
    Write-Output "Downloading the official AWS CLI v2 user installer."
    Invoke-WebRequest -UseBasicParsing -Uri "https://awscli.amazonaws.com/AWSCLIV2-User.msi" -OutFile $installer
    try {
        $arguments = @("/i", $installer, "/qn", "/norestart")
        $process = Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "AWS CLI installer exit code: $($process.ExitCode)"
        }
    }
    finally {
        if (Test-Path -LiteralPath $installer) {
            Remove-Item -LiteralPath $installer -Force
        }
    }

    if (-not (Test-Path -LiteralPath $userInstall)) {
        throw "AWS CLI v2 installation failed."
    }
    return $userInstall
}

$awsCli = Resolve-AwsCli
& $awsCli --version

Write-Output "IAM sign-in URL: $signInUrl"
Start-Process $signInUrl
Read-Host "Sign in as IAM user $ExpectedUser with MFA, then press Enter"

& $awsCli login --profile $Profile --region $Region
if ($LASTEXITCODE -ne 0) {
    throw "AWS browser login failed."
}

$identity = (& $awsCli sts get-caller-identity --profile $Profile --region $Region --output json | ConvertFrom-Json)
if ($identity.Arn -notmatch ":user/$([regex]::Escape($ExpectedUser))$") {
    & $awsCli logout --profile $Profile
    throw "Unexpected AWS caller. The login cache was removed. Select IAM user $ExpectedUser, not root."
}

& $awsCli configure set region $Region --profile $Profile
Write-Output "PASS caller=$ExpectedUser profile=$Profile region=$Region"
Write-Output "The temporary CLI session can refresh for up to 12 hours. Run aws logout --profile $Profile when finished."

$preflight = Join-Path $PSScriptRoot "01-preflight.ps1"
if (Test-Path -LiteralPath $preflight) {
    & $preflight -Profile $Profile -Region $Region
}
