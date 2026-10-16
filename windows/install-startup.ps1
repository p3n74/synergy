# Register HomeSynergy in the interactive logon session and open the LAN port
# on the Private firewall profile only.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    $Python = (Get-Command py -ErrorAction SilentlyContinue).Source
    if (-not $Python) {
        throw "Install Python 3 on Windows, then run this script again."
    }
    $Argument = "-3 -m homesynergy.win_agent"
} else {
    $Argument = "-m homesynergy.win_agent"
}

$ConfigDir = Join-Path $env:USERPROFILE ".homesynergy"
if (-not (Test-Path (Join-Path $ConfigDir "config.json"))) {
    throw "Copy the Mac config to $ConfigDir\config.json first."
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument $Argument -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable
Register-ScheduledTask -TaskName "HomeSynergy" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName "HomeSynergy"

$Existing = Get-NetFirewallRule -DisplayName "HomeSynergy" -ErrorAction SilentlyContinue
if ($Existing) {
    Remove-NetFirewallRule -DisplayName "HomeSynergy"
}
New-NetFirewallRule -DisplayName "HomeSynergy" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 24864 -Profile Private | Out-Null
Write-Host "HomeSynergy starts at logon and is listening on TCP 24864 (Private networks)."
