$ErrorActionPreference = "Stop"

function Stop-Launcher {
    param([Parameter(Mandatory = $true)][string]$Message)

    [Console]::Error.WriteLine($Message)
    exit 2
}

if ($args.Count -lt 1) {
    Stop-Launcher "Usage: copilot-agent.ps1 [new|resume|open] <name> [copilot arguments]"
}

$firstArgument = [string]$args[0]
$secondArgumentStartsOption = $args.Count -ge 2 -and [string]$args[1] -match "^-"
if ($args.Count -ge 2 -and
    -not $secondArgumentStartsOption -and
    $firstArgument -in @("new", "resume", "open")) {
    $Mode = $firstArgument
    $Name = [string]$args[1]
    $CopilotArguments = [string[]]@($args | Select-Object -Skip 2)
} else {
    $Mode = "open"
    $Name = $firstArgument
    $CopilotArguments = [string[]]@($args | Select-Object -Skip 1)
}

if ($Name -cnotmatch "\A[a-z0-9][a-z0-9._-]{0,99}\z") {
    Stop-Launcher "Agent name must be a lowercase mailbox-safe name of 1-100 characters."
}

$machine = $env:COPILOT_AGENT_MACHINE
if ([string]::IsNullOrWhiteSpace($machine) -or
    $machine -cnotmatch "\A[a-z0-9][a-z0-9._-]{0,127}\z") {
    Stop-Launcher "COPILOT_AGENT_MACHINE must be a lowercase mailbox-safe name of 1-128 characters."
}

foreach ($argument in $CopilotArguments) {
    if ($argument -match "^--(?:name|resume|session-id|config-dir)(?:=|$)" -or
        $argument -match "^-(?:n|r)") {
        Stop-Launcher "Copilot argument '$argument' would override launcher-owned identity or storage."
    }
}

$copilotHome = $env:COPILOT_HOME
if ([string]::IsNullOrWhiteSpace($copilotHome)) {
    $userHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $copilotHome = Join-Path $userHome ".copilot"
} elseif ($copilotHome -cnotmatch "\A(?:[A-Za-z]:[\\/]|\\\\)") {
    Stop-Launcher "COPILOT_HOME must be an absolute path."
}
$copilotHome = [IO.Path]::GetFullPath($copilotHome)
if (Test-Path -LiteralPath $copilotHome -PathType Leaf) {
    Stop-Launcher "COPILOT_HOME must be a directory path."
}

$separator = [char]0
$payload = "dfrysinger-skills/windows-agent-session/v1${separator}${machine}${separator}${Name}"
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $hash = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($payload))
} finally {
    $sha256.Dispose()
}
$uuidBytes = [byte[]]$hash[0..15]
$uuidBytes[6] = ($uuidBytes[6] -band 0x0f) -bor 0x50
$uuidBytes[8] = ($uuidBytes[8] -band 0x3f) -bor 0x80
$hex = ([BitConverter]::ToString($uuidBytes) -replace "-", "").ToLowerInvariant()
$sessionId = @(
    $hex.Substring(0, 8)
    $hex.Substring(8, 4)
    $hex.Substring(12, 4)
    $hex.Substring(16, 4)
    $hex.Substring(20, 12)
) -join "-"

$workspacePath = Join-Path $copilotHome "session-state\$sessionId\workspace.yaml"
$workspaceExists = Test-Path -LiteralPath $workspacePath -PathType Leaf

if ($Mode -eq "new" -and $workspaceExists) {
    Stop-Launcher "Agent '$Name' already exists for machine '$machine'; use 'resume'."
}
if ($Mode -eq "resume" -and -not $workspaceExists) {
    Stop-Launcher "Agent '$Name' does not exist for machine '$machine'; use 'new'."
}

$effectiveMode = $Mode
if ($Mode -eq "open") {
    $effectiveMode = if ($workspaceExists) { "resume" } else { "new" }

    if ($CopilotArguments -notcontains "--allow-all-tools") {
        $CopilotArguments = @("--allow-all-tools") + $CopilotArguments
    }

    $hasInitialPrompt = $false
    foreach ($argument in $CopilotArguments) {
        if ($argument -match "^(?:-i|-p|--interactive(?:=|$)|--prompt(?:=|$))") {
            $hasInitialPrompt = $true
            break
        }
    }
    if (-not $hasInitialPrompt) {
        $readyMarker = "READY_$($Name.ToUpperInvariant())"
        $initialPrompt = "Initialize as $Name@$machine, then remain available for mailbox messages. Reply with exactly $readyMarker."
        $CopilotArguments += @("-i", $initialPrompt)
    }
}

$identityArguments = @("--session-id=$sessionId")
if ($effectiveMode -eq "new") {
    $identityArguments += "--name=$Name"
}

& copilot @identityArguments @CopilotArguments
exit $LASTEXITCODE
