[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "start", "stop", "status", "restart")]
    [string]$Action = "start",

    [Parameter(Position = 1)]
    [string]$AgentName = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$RuntimeEnvFile = Join-Path $ProjectRoot ".env"
$WorkspaceEnvFile = Join-Path $WorkspaceRoot ".env"
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PidFile = Join-Path $RuntimeDir "agents.json"
$DefaultStartTimeoutSeconds = 45

$Agents = @(
    @{ Name = "interpreter"; Module = "agents.interpreter"; Port = 6101 },
    @{ Name = "retriever";   Module = "agents.retriever";   Port = 6102 },
    @{ Name = "summarizer";  Module = "agents.summarizer";  Port = 6103 },
    @{ Name = "evaluator";   Module = "agents.evaluator";   Port = 6104 },
    @{ Name = "critic";      Module = "agents.critic";      Port = 6105 },
    @{ Name = "improver";    Module = "agents.improver";    Port = 6106 }
)

function Import-DotEnv {
    $EnvFile = if (Test-Path -LiteralPath $RuntimeEnvFile) {
        $RuntimeEnvFile
    }
    elseif (Test-Path -LiteralPath $WorkspaceEnvFile) {
        $WorkspaceEnvFile
    }
    else {
        $null
    }

    if (-not $EnvFile) {
        throw ".env was not found in the VOC runtime or workspace root. Run '.\scripts\agents.cmd init', then enter your real API keys."
    }

    foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) { continue }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }

    $required = @("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY")
    $missing = @($required | Where-Object {
        $currentValue = [Environment]::GetEnvironmentVariable($_, "Process")
        [string]::IsNullOrWhiteSpace($currentValue) -or $currentValue.StartsWith("YOUR_")
    })
    if ($missing.Count -gt 0) {
        throw "Required values are missing from .env: $($missing -join ', ')"
    }
}

function Get-PythonExecutable {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }

    $parentVenvPython = Join-Path (Split-Path -Parent $ProjectRoot) ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $parentVenvPython) { return $parentVenvPython }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Python was not found. Create the .venv first."
}

function Test-TcpPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(250) -and $client.Connected
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Get-AgentStartTimeoutSeconds {
    $configured = [Environment]::GetEnvironmentVariable("VOC_AGENT_START_TIMEOUT_SECONDS", "Process")
    $seconds = 0
    if (-not [string]::IsNullOrWhiteSpace($configured) -and
        [int]::TryParse($configured, [ref]$seconds) -and
        $seconds -ge 15 -and
        $seconds -le 180) {
        return $seconds
    }
    return $DefaultStartTimeoutSeconds
}

function Read-AgentState {
    if (-not (Test-Path -LiteralPath $PidFile)) { return @() }
    try { return @(Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json) }
    catch { return @() }
}

function Get-AgentDefinition {
    param([string]$Name)
    $definition = $Agents | Where-Object { $_.Name -eq $Name.ToLowerInvariant() } | Select-Object -First 1
    if (-not $definition) {
        throw "Unknown Agent: $Name. Allowed values: $($Agents.Name -join ', ')"
    }
    return $definition
}

function Write-AgentState {
    param([object[]]$State)
    $items = @($State)
    if ($items.Count -eq 0) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }
    $items | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
}

function Initialize-Env {
    if (Test-Path -LiteralPath $RuntimeEnvFile) {
        Write-Host "VOC runtime .env already exists; it was not overwritten."
        return
    }
    if (Test-Path -LiteralPath $WorkspaceEnvFile) {
        Write-Host "Workspace .env already exists and will be used; no duplicate file was created."
        return
    }
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ".env.example") -Destination $RuntimeEnvFile
    Write-Host "VOC runtime .env was created. Replace all YOUR_* placeholders with newly issued keys."
}

function Show-Status {
    param([string]$Name = "")
    $state = Read-AgentState
    $targets = if ($Name) { @(Get-AgentDefinition -Name $Name) } else { $Agents }
    foreach ($agent in $targets) {
        $saved = $state | Where-Object { $_.name -eq $agent.Name } | Select-Object -First 1
        $processRunning = $false
        if ($saved) {
            $processRunning = $null -ne (Get-Process -Id $saved.pid -ErrorAction SilentlyContinue)
        }
        $portOpen = Test-TcpPort -Port $agent.Port
        $status = if ($processRunning -and $portOpen) { "RUNNING" }
                  elseif ($portOpen) { "PORT IN USE" }
                  elseif ($processRunning) { "STARTING/FAILED" }
                  else { "STOPPED" }
        $startedAt = if ($saved -and $saved.started_at) { $saved.started_at } else { "-" }
        "{0,-12} port={1} pid={2} started_at={3} status={4}" -f $agent.Name, $agent.Port, $(if ($saved) { $saved.pid } else { "-" }), $startedAt, $status
    }
}

function Start-OneAgent {
    param([string]$Name)
    $agent = Get-AgentDefinition -Name $Name
    Import-DotEnv
    $python = Get-PythonExecutable
    $state = Read-AgentState
    $saved = $state | Where-Object { $_.name -eq $agent.Name } | Select-Object -First 1
    $processRunning = $saved -and ($null -ne (Get-Process -Id $saved.pid -ErrorAction SilentlyContinue))
    $portOpen = Test-TcpPort -Port $agent.Port

    if ($processRunning -and $portOpen) {
        Write-Host "[RUNNING] $($agent.Name) is already running (PID $($saved.pid), port $($agent.Port))."
        return
    }
    if ($portOpen) {
        throw "Port $($agent.Port) is already in use by an unmanaged process. It was not stopped."
    }
    if ($processRunning) {
        throw "$($agent.Name) process exists but port $($agent.Port) is not ready. Stop it before starting again."
    }

    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $stdout = Join-Path $LogDir "$($agent.Name).out.log"
    $stderr = Join-Path $LogDir "$($agent.Name).err.log"
    $process = Start-Process -FilePath $python `
        -ArgumentList @("-u", "-m", $agent.Module) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru
    $entry = [pscustomobject]@{
        name = $agent.Name
        module = $agent.Module
        port = $agent.Port
        pid = $process.Id
        started_at = (Get-Date).ToString("o")
    }
    $newState = @($state | Where-Object { $_.name -ne $agent.Name }) + @($entry)
    Write-AgentState -State $newState

    $startTimeoutSeconds = Get-AgentStartTimeoutSeconds
    Write-Host "[STARTING] $($agent.Name) (PID $($process.Id), port $($agent.Port), timeout ${startTimeoutSeconds}s)"
    $deadline = (Get-Date).AddSeconds($startTimeoutSeconds)
    do {
        if (Test-TcpPort -Port $agent.Port) {
            Write-Host "[RUNNING] $($agent.Name) (PID $($process.Id), port $($agent.Port))"
            return
        }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)

    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Write-AgentState -State @($state | Where-Object { $_.name -ne $agent.Name })
    throw "$($agent.Name) failed to start. Check .runtime\logs\$($agent.Name).err.log."
}

function Stop-OneAgent {
    param([string]$Name)
    $agent = Get-AgentDefinition -Name $Name
    $state = Read-AgentState
    $saved = $state | Where-Object { $_.name -eq $agent.Name } | Select-Object -First 1
    if (-not $saved) {
        if (Test-TcpPort -Port $agent.Port) {
            throw "Port $($agent.Port) is used by an unmanaged process. It was not stopped."
        }
        Write-Host "[STOPPED] $($agent.Name) is already stopped."
        return
    }

    $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $saved.pid -Force
        Write-Host "[STOPPED] $($agent.Name) (PID $($saved.pid))"
    }
    Write-AgentState -State @($state | Where-Object { $_.name -ne $agent.Name })

    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and (Test-TcpPort -Port $agent.Port)) {
        Start-Sleep -Milliseconds 200
    }
    if (Test-TcpPort -Port $agent.Port) {
        throw "Managed process was stopped, but port $($agent.Port) is still in use by another process."
    }
}

function Stop-Agents {
    $state = Read-AgentState
    foreach ($saved in $state) {
        $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $saved.pid -Force
            Write-Host "[STOPPED] $($saved.name) (PID $($saved.pid))"
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Start-Agents {
    Import-DotEnv
    $python = Get-PythonExecutable

    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $state = Read-AgentState
    $alreadyRunning = @()
    $started = @()
    try {
        foreach ($agent in $Agents) {
            $saved = $state | Where-Object { $_.name -eq $agent.Name } | Select-Object -First 1
            $processRunning = $saved -and ($null -ne (Get-Process -Id $saved.pid -ErrorAction SilentlyContinue))
            $portOpen = Test-TcpPort -Port $agent.Port

            if ($processRunning -and $portOpen) {
                $alreadyRunning += $saved
                Write-Host "[RUNNING] $($agent.Name) is already running (PID $($saved.pid), port $($agent.Port))."
                continue
            }
            if ($portOpen) {
                throw "Port $($agent.Port) is already in use by an unmanaged process. It was not stopped."
            }
            if ($processRunning) {
                throw "$($agent.Name) process exists but port $($agent.Port) is not ready. Stop it before starting again."
            }

            $stdout = Join-Path $LogDir "$($agent.Name).out.log"
            $stderr = Join-Path $LogDir "$($agent.Name).err.log"
            $process = Start-Process -FilePath $python `
                -ArgumentList @("-u", "-m", $agent.Module) `
                -WorkingDirectory $ProjectRoot `
                -RedirectStandardOutput $stdout `
                -RedirectStandardError $stderr `
                -WindowStyle Hidden `
                -PassThru
            $started += [pscustomobject]@{
                name = $agent.Name
                module = $agent.Module
                port = $agent.Port
                pid = $process.Id
                started_at = (Get-Date).ToString("o")
            }
            Write-Host "[STARTING] $($agent.Name) (PID $($process.Id), port $($agent.Port))"
        }

        Write-AgentState -State @($alreadyRunning + $started)

        $startTimeoutSeconds = Get-AgentStartTimeoutSeconds
        $deadline = (Get-Date).AddSeconds($startTimeoutSeconds)
        $lastReady = -1
        do {
            $ready = @($Agents | Where-Object { Test-TcpPort -Port $_.Port }).Count
            if ($ready -ne $lastReady) {
                Write-Host "[READY] $ready / $($Agents.Count) agents"
                $lastReady = $ready
            }
            if ($ready -eq $Agents.Count) { break }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)

        $failed = @($Agents | Where-Object { -not (Test-TcpPort -Port $_.Port) })
        if ($failed.Count -gt 0) {
            throw "Agents failed to start within ${startTimeoutSeconds}s: $($failed.Name -join ', '). Check .runtime\logs."
        }
        Write-Host "All 6 agents are running."
        Show-Status
    }
    catch {
        foreach ($item in $started) {
            Stop-Process -Id $item.pid -Force -ErrorAction SilentlyContinue
        }
        Write-AgentState -State @($alreadyRunning)
        throw
    }
}

switch ($Action) {
    "init"    {
        if ($AgentName) { throw "The init action does not accept an Agent name." }
        Initialize-Env
    }
    "start"   { if ($AgentName) { Start-OneAgent -Name $AgentName } else { Start-Agents } }
    "stop"    { if ($AgentName) { Stop-OneAgent -Name $AgentName } else { Stop-Agents } }
    "status"  { Show-Status -Name $AgentName }
    "restart" {
        if ($AgentName) { Stop-OneAgent -Name $AgentName; Start-OneAgent -Name $AgentName }
        else { Stop-Agents; Start-Agents }
    }
}
