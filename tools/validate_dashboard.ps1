param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment was not found: $Python"
}

Push-Location $ProjectRoot
try {
    & $Python -m compileall -q qa_observer dashboard
    if ($LASTEXITCODE -ne 0) { throw "Python compileall failed." }

    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose static validation failed." }

    $Targets = @(
        "tests/test_dashboard_e2e_scenarios.py",
        "tests/test_grafana_alerting.py",
        "tests/test_overview_dashboard.py"
    )
    if ($Full) {
        $Targets = @("tests")
    }

    & $Python -m pytest @Targets -q
    if ($LASTEXITCODE -ne 0) { throw "Dashboard validation tests failed." }
}
finally {
    Pop-Location
}
