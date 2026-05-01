$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process cmd.exe -ArgumentList "/k", "cd /d `"$scriptDir`" && run_vlm_review_service.cmd"
Start-Sleep -Seconds 2
Start-Process cmd.exe -ArgumentList "/k", "cd /d `"$scriptDir`" && run_feishu_command_bridge.cmd"
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptDir\run_cloudflared_tunnel.ps1`""

Write-Host "Started notebook stack:"
Write-Host "  1. VLM review service"
Write-Host "  2. Feishu command bridge"
Write-Host "  3. cloudflared tunnel"

