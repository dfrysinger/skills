$ErrorActionPreference = "Stop"

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $actualJson = ConvertTo-Json $Actual -Compress
    $expectedJson = ConvertTo-Json $Expected -Compress
    if ($actualJson -ne $expectedJson) {
        throw "$Label failed. Expected $expectedJson, got $actualJson"
    }
}

function Assert-NoChild {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$LauncherArguments
    )

    Remove-Item $script:capturePath -Force -ErrorAction SilentlyContinue
    & $script:pwsh -NoProfile -ExecutionPolicy Bypass -File $script:scriptPath `
        @LauncherArguments 2>$null
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        throw "$Label unexpectedly succeeded"
    }
    if (Test-Path -LiteralPath $script:capturePath) {
        throw "$Label launched copilot"
    }
}

function New-Workspace {
    param([Parameter(Mandatory = $true)][string]$SessionId)

    $workspace = Join-Path $script:copilotHome "session-state\$SessionId\workspace.yaml"
    New-Item -ItemType Directory -Path (Split-Path $workspace) -Force | Out-Null
    Set-Content -LiteralPath $workspace -Encoding utf8 -Value "name: hotel"
    return $workspace
}

$root = Join-Path ([IO.Path]::GetTempPath()) "copilot-agent-test-$PID"
$capturePath = Join-Path $root "capture.json"
$captureScript = Join-Path $root "capture.mjs"
$fakeCopilot = Join-Path $root "copilot.cmd"
$copilotHome = Join-Path $root "copilot-home"
$scriptPath = Join-Path $PSScriptRoot "copilot-agent.ps1"
$pwsh = Join-Path $PSHOME "pwsh.exe"
$windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$originalPath = $env:PATH
$originalCapture = $env:FAKE_COPILOT_CAPTURE
$originalExit = $env:FAKE_COPILOT_EXIT
$originalMachine = $env:COPILOT_AGENT_MACHINE
$originalCopilotHome = $env:COPILOT_HOME
$defaultWorkspaceRoot = $null

$hotelId = "ab7c0c56-f5b8-5e16-9d9e-49808182c874"

try {
    New-Item -ItemType Directory -Path $root | Out-Null
    Set-Content -LiteralPath $captureScript -Encoding utf8 -Value @'
import { writeFileSync } from "node:fs";
writeFileSync(process.env.FAKE_COPILOT_CAPTURE, JSON.stringify(process.argv.slice(2)));
process.exit(Number(process.env.FAKE_COPILOT_EXIT ?? "0"));
'@
    Set-Content -LiteralPath $fakeCopilot -Encoding ascii -Value @'
@echo off
node "%~dp0capture.mjs" %*
'@

    $env:PATH = "$root;$originalPath"
    $env:FAKE_COPILOT_CAPTURE = $capturePath
    $env:FAKE_COPILOT_EXIT = "0"
    $env:COPILOT_AGENT_MACHINE = "surface-pro"
    $env:COPILOT_HOME = $copilotHome

    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new hotel `
        -p "wait for mailbox" --model "gpt 5"
    if ($LASTEXITCODE -ne 0) {
        throw "new mode exited with $LASTEXITCODE"
    }
    Assert-Equal `
        -Actual (Get-Content $capturePath -Raw | ConvertFrom-Json) `
        -Expected @(
            "--session-id=$hotelId",
            "--name=hotel",
            "-p",
            "wait for mailbox",
            "--model",
            "gpt 5"
        ) `
        -Label "new mode deterministic arguments"

    if (Test-Path -LiteralPath $windowsPowerShell) {
        Remove-Item $capturePath -Force
        & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $scriptPath `
            new hotel -p "wait for mailbox" --model "gpt 5"
        if ($LASTEXITCODE -ne 0) {
            throw "Windows PowerShell 5.1 mode exited with $LASTEXITCODE"
        }
        Assert-Equal `
            -Actual (Get-Content $capturePath -Raw | ConvertFrom-Json) `
            -Expected @(
                "--session-id=$hotelId",
                "--name=hotel",
                "-p",
                "wait for mailbox",
                "--model",
                "gpt 5"
            ) `
            -Label "Windows PowerShell 5.1 deterministic arguments"
    }

    Remove-Item $capturePath -Force
    New-Workspace $hotelId | Out-Null
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath resume hotel --no-remote
    if ($LASTEXITCODE -ne 0) {
        throw "resume mode exited with $LASTEXITCODE"
    }
    Assert-Equal `
        -Actual (Get-Content $capturePath -Raw | ConvertFrom-Json) `
        -Expected @("--session-id=$hotelId", "--no-remote") `
        -Label "resume mode exact-ID arguments"

    Assert-NoChild "duplicate new" @("new", "hotel")

    Remove-Item (Split-Path (Split-Path (Join-Path $copilotHome "session-state\$hotelId\workspace.yaml"))) `
        -Recurse -Force
    Assert-NoChild "missing resume" @("resume", "hotel")

    $longName = "a" * 100
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new $longName
    if ($LASTEXITCODE -ne 0) {
        throw "100-character agent name exited with $LASTEXITCODE"
    }
    $longArguments = Get-Content $capturePath -Raw | ConvertFrom-Json
    if ($longArguments[1] -ne "--name=$longName") {
        throw "100-character agent name did not pass through exactly"
    }

    $differentMachineHome = Join-Path $root "different-machine-home"
    $env:COPILOT_HOME = $differentMachineHome
    $env:COPILOT_AGENT_MACHINE = "surface-book"
    Remove-Item $capturePath -Force
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new hotel
    if ($LASTEXITCODE -ne 0) {
        throw "different-machine vector exited with $LASTEXITCODE"
    }
    $differentMachineArguments = Get-Content $capturePath -Raw | ConvertFrom-Json
    if ($differentMachineArguments[0] -eq "--session-id=$hotelId") {
        throw "different machine derived the hotel@surface-pro session ID"
    }

    $env:COPILOT_HOME = $copilotHome
    $env:COPILOT_AGENT_MACHINE = "surface-pro"
    Remove-Item $capturePath -Force
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new india
    if ($LASTEXITCODE -ne 0) {
        throw "different-name vector exited with $LASTEXITCODE"
    }
    $differentNameArguments = Get-Content $capturePath -Raw | ConvertFrom-Json
    if ($differentNameArguments[0] -eq "--session-id=$hotelId") {
        throw "different name derived the hotel@surface-pro session ID"
    }

    $literalMarker = Join-Path $root "must-not-exist"
    $literalArgument = '$(New-Item ' + $literalMarker + ')'
    Remove-Item $capturePath -Force
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new juliett `
        --prompt $literalArgument
    if ($LASTEXITCODE -ne 0) {
        throw "literal argument vector exited with $LASTEXITCODE"
    }
    Assert-Equal `
        -Actual (Get-Content $capturePath -Raw | ConvertFrom-Json) `
        -Expected @(
            "--session-id=2ee99bb5-9419-57c8-af4a-380cc43d8042",
            "--name=juliett",
            "--prompt",
            $literalArgument
        ) `
        -Label "literal argument pass-through"
    if (Test-Path -LiteralPath $literalMarker) {
        throw "extra arguments were evaluated as a command"
    }

    $defaultName = "copilot-agent-test-$PID"
    Remove-Item $capturePath -Force
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new $defaultName
    if ($LASTEXITCODE -ne 0) {
        throw "default-home setup vector exited with $LASTEXITCODE"
    }
    $defaultSessionArgument = (Get-Content $capturePath -Raw | ConvertFrom-Json)[0]
    $defaultSessionId = $defaultSessionArgument.Substring("--session-id=".Length)
    $defaultCopilotHome = Join-Path `
        ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)) ".copilot"
    $defaultWorkspaceRoot = Join-Path $defaultCopilotHome "session-state\$defaultSessionId"
    New-Item -ItemType Directory -Path $defaultWorkspaceRoot -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $defaultWorkspaceRoot "workspace.yaml") `
        -Encoding utf8 -Value "name: $defaultName"
    $env:COPILOT_HOME = $null
    Remove-Item $capturePath -Force
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath resume $defaultName
    if ($LASTEXITCODE -ne 0) {
        throw "default COPILOT_HOME resume exited with $LASTEXITCODE"
    }
    Assert-Equal `
        -Actual (Get-Content $capturePath -Raw | ConvertFrom-Json) `
        -Expected "--session-id=$defaultSessionId" `
        -Label "default COPILOT_HOME workspace"

    $env:COPILOT_HOME = $copilotHome
    foreach ($invalidName in @(
        "Hotel",
        "hotel other",
        ("a" * 101),
        "hotel`n",
        "hotel`r`n"
    )) {
        Assert-NoChild "invalid name '$invalidName'" @("new", $invalidName)
    }

    foreach ($invalidMachine in @(
        "Surface-Pro",
        "surface pro",
        ("a" * 129),
        "surface-pro`n",
        "surface-pro`r`n"
    )) {
        $env:COPILOT_AGENT_MACHINE = $invalidMachine
        Assert-NoChild "invalid machine '$invalidMachine'" @("new", "hotel")
    }
    $env:COPILOT_AGENT_MACHINE = $null
    Assert-NoChild "missing machine" @("new", "hotel")

    $env:COPILOT_AGENT_MACHINE = "surface-pro"
    foreach ($reserved in @(
        "--name", "--name=other", "--resume", "--resume=other",
        "--session-id=00000000-0000-0000-0000-000000000000",
        "--config-dir=C:\other", "-nHOTEL", "-rhotel"
    )) {
        Assert-NoChild "reserved argument '$reserved'" @("new", "hotel", $reserved)
    }

    $env:COPILOT_HOME = "relative\copilot-home"
    Assert-NoChild "relative COPILOT_HOME" @("new", "hotel")

    $copilotHomeFile = Join-Path $root "copilot-home-file"
    Set-Content -LiteralPath $copilotHomeFile -Encoding utf8 -Value "not a directory"
    $env:COPILOT_HOME = $copilotHomeFile
    Assert-NoChild "file COPILOT_HOME" @("new", "hotel")

    $env:COPILOT_HOME = $copilotHome
    $env:FAKE_COPILOT_EXIT = "23"
    Remove-Item $capturePath -Force -ErrorAction SilentlyContinue
    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $scriptPath new hotel 2>$null
    if ($LASTEXITCODE -ne 23) {
        throw "child exit code was not propagated: $LASTEXITCODE"
    }

    Write-Output "copilot-agent PowerShell tests passed"
} finally {
    $env:PATH = $originalPath
    $env:FAKE_COPILOT_CAPTURE = $originalCapture
    $env:FAKE_COPILOT_EXIT = $originalExit
    $env:COPILOT_AGENT_MACHINE = $originalMachine
    $env:COPILOT_HOME = $originalCopilotHome
    if ($defaultWorkspaceRoot) {
        Remove-Item $defaultWorkspaceRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
}
