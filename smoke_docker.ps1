param(
  [int]$Port = 8080,
  [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseUrl = "http://127.0.0.1:$Port"

function Step($Name) {
  Write-Host "`n==> $Name" -ForegroundColor Cyan
}

Step "Build and start docker compose"
Push-Location $Root
try {
  docker compose up -d --build

  Step "Wait for frontend/backend health"
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 5
      if ($health.status -eq "ok") {
        Write-Host "Docker smoke passed: $BaseUrl/api/health"
        exit 0
      }
    } catch {
      Start-Sleep -Seconds 3
    }
  } while ((Get-Date) -lt $deadline)

  throw "Timed out waiting for $BaseUrl/api/health"
} finally {
  docker compose logs --tail=80 backend frontend
  docker compose down
  Pop-Location
}
