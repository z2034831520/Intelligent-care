$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $scriptDir ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        if ($line.StartsWith("export ")) { $line = $line.Substring(7) }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { return }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim("'`"")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$port = if ($env:FEISHU_COMMAND_BRIDGE_PORT) { $env:FEISHU_COMMAND_BRIDGE_PORT } else { "19100" }
$cloudflared = if ($env:CLOUDFLARED_PATH) { $env:CLOUDFLARED_PATH } else { "cloudflared" }

Write-Host "Starting cloudflared tunnel -> http://127.0.0.1:$port"
& $cloudflared tunnel --url "http://127.0.0.1:$port"

