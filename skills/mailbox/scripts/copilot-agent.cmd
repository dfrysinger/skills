@echo off
setlocal
if not defined COPILOT_AGENT_LAUNCHER set "COPILOT_AGENT_LAUNCHER=%USERPROFILE%\.copilot\installed-plugins\_direct\dfrysinger--skills\skills\mailbox\scripts\copilot-agent.ps1"
if not exist "%COPILOT_AGENT_LAUNCHER%" (
  echo Missing deterministic Windows agent launcher: %COPILOT_AGENT_LAUNCHER% 1>&2
  exit /b 2
)
"%SystemRoot%\System32\where.exe" pwsh >nul 2>&1
if %ERRORLEVEL% equ 0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%COPILOT_AGENT_LAUNCHER%" %*
) else (
  if not exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
    echo Missing PowerShell host required by deterministic Windows agent launcher. 1>&2
    exit /b 2
  )
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%COPILOT_AGENT_LAUNCHER%" %*
)
exit /b %ERRORLEVEL%
