<#
Start the local dashboard and qa-observer services from the project root.
PowerShell 7 or newer is recommended. The script reuses healthy services, or
restarts the dashboard when -Restart is provided. Logs are written beneath
logs\local_services.
#>

param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EntryPoint = Join-Path $ProjectRoot "dashboard\streamlit_app.py"
$LogDir = Join-Path $ProjectRoot "logs\local_services"
$ObserverUrl = "http://127.0.0.1:8010"
$ObserverPort = 8010

function Test-ObserverHealth {
    try {
        $Health = Invoke-RestMethod `
            -Method Get `
            -Uri "$ObserverUrl/health" `
            -TimeoutSec 2 `
            -ErrorAction Stop
        return (
            $Health.status -eq "healthy" -and
            $Health.storage.writable -eq $true -and
            $Health.scheduler.running -eq $true -and
            -not $Health.scheduler.last_error_type
        )
    }
    catch {
        return $false
    }
}

function Get-PortListener {
    param([int]$Port)

    return Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    & taskkill /PID $ProcessId /T /F 2>$null | Out-Null
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-QaObserver {
    if (Test-ObserverHealth) {
        $ExistingListener = Get-PortListener -Port $ObserverPort
        return [pscustomobject]@{
            Status = "reused"
            PID = if ($ExistingListener) { $ExistingListener.OwningProcess } else { $null }
        }
    }

    $ExistingListener = Get-PortListener -Port $ObserverPort
    if ($ExistingListener) {
        throw "Port $ObserverPort is occupied by PID $($ExistingListener.OwningProcess), but qa-observer health is not normal. Refusing to start another writer process."
    }

    $ObserverStdout = Join-Path $LogDir "qa-observer.stdout.log"
    $ObserverStderr = Join-Path $LogDir "qa-observer.stderr.log"
    $ObserverArguments = @(
        "-m", "uvicorn", "qa_observer.app:app",
        "--host", "127.0.0.1",
        "--port", "$ObserverPort"
    )
    $ObserverStartParameters = @{
        FilePath = $Python
        ArgumentList = $ObserverArguments
        WorkingDirectory = $ProjectRoot
        RedirectStandardOutput = $ObserverStdout
        RedirectStandardError = $ObserverStderr
        WindowStyle = "Hidden"
        PassThru = $true
    }
    $ObserverProcess = Start-Process @ObserverStartParameters

    $Deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $Healthy = Test-ObserverHealth
    } until ($Healthy -or $ObserverProcess.HasExited -or (Get-Date) -gt $Deadline)

    if (-not $Healthy) {
        if (-not $ObserverProcess.HasExited) {
            Stop-ProcessTree -ProcessId $ObserverProcess.Id
        }
        throw "qa-observer did not become healthy. Check $ObserverStderr and logs\qa_observer\qa-observer.log."
    }

    # Concurrent launcher calls can race before the port is bound. Report the
    # actual listener PID so callers never assume their candidate process won.
    $ActiveListener = Get-PortListener -Port $ObserverPort
    return [pscustomobject]@{
        Status = "started"
        PID = if ($ActiveListener) { $ActiveListener.OwningProcess } else { $ObserverProcess.Id }
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment was not found: $Python"
}

$StreamlitAvailable = & $Python -c "import importlib.util; print(importlib.util.find_spec('streamlit') is not None)"
if ($StreamlitAvailable -ne "True") {
    throw "Streamlit is not installed in the project virtual environment. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}
$StreamlitVersion = & $Python -c "import streamlit; print(streamlit.__version__)"
if ([version]$StreamlitVersion -lt [version]"1.59.0") {
    throw "Streamlit 1.59.0 or newer is required. Installed: $StreamlitVersion"
}

$DashboardStatus = "started"
$Listener = Get-PortListener -Port 8501
if ($Listener) {
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
    if ($Process.CommandLine -notmatch "streamlit" -or $Process.CommandLine -notmatch "streamlit_app\.py") {
        throw "Port 8501 belongs to an unrelated process. Refusing to stop PID $($Listener.OwningProcess)."
    }
    if (-not $Restart) {
        $DashboardStatus = "reused"
    }
    else {
        $ParentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($Process.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($ParentProcess -and $ParentProcess.CommandLine -match "streamlit" -and $ParentProcess.CommandLine -match "streamlit_app\.py") {
            Stop-Process -Id $ParentProcess.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
        $Deadline = (Get-Date).AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 250
            $StillListening = Get-PortListener -Port 8501
        } until (-not $StillListening -or (Get-Date) -gt $Deadline)
        if ($StillListening) {
            throw "Port 8501 did not close after stopping the previous dashboard process."
        }
        $Listener = $null
    }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Child processes inherit this value. The dashboard and telemetry emitters use
# the same observer endpoint without changing the caller's global environment.
$env:QA_OBSERVER_URL = $ObserverUrl
$Observer = Start-QaObserver

$Started = $null
$Stdout = Join-Path $LogDir "streamlit.stdout.log"
$Stderr = Join-Path $LogDir "streamlit.stderr.log"
$Arguments = @(
    "-m", "streamlit", "run", $EntryPoint,
    "--server.address=127.0.0.1",
    "--server.port=8501",
    "--server.headless=true",
    "--server.runOnSave=true"
)

$StartParameters = @{
    FilePath = $Python
    ArgumentList = $Arguments
    WorkingDirectory = $ProjectRoot
    RedirectStandardOutput = $Stdout
    RedirectStandardError = $Stderr
    WindowStyle = "Hidden"
    PassThru = $true
}
if ($DashboardStatus -ne "reused") {
    $Started = Start-Process @StartParameters

    $Deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $Listener = Get-PortListener -Port 8501
    } until ($Listener -or $Started.HasExited -or (Get-Date) -gt $Deadline)
}

if (-not $Listener) {
    throw "Dashboard did not start. Check $Stderr"
}

[pscustomobject]@{
    Status = "running"
    DashboardStatus = $DashboardStatus
    URL = "http://127.0.0.1:8501"
    PID = $Listener.OwningProcess
    ObserverStatus = $Observer.Status
    ObserverURL = $ObserverUrl
    ObserverPID = $Observer.PID
    Python = $Python
    Streamlit = $StreamlitVersion
}
