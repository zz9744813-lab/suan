param(
  [string]$Python = "python",
  [switch]$SkipFrontend,
  [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Step($Name) {
  Write-Host "`n==> $Name" -ForegroundColor Cyan
}

if (-not $SkipBackend) {
  Step "Backend pytest full-flow suite"
  Push-Location $Backend
  try {
    & $Python -m pytest app/tests/test_00_smoke_contract.py app/tests/test_01_health_openapi.py app/tests/test_02_projects_api.py app/tests/test_03_chapters_api.py app/tests/test_04_tasks_command_center.py app/tests/test_05_study_api.py app/tests/test_06_chapter_pipeline_e2e.py app/tests/test_07_worker_control_retry_cancel.py app/tests/test_08_reader_review_discussion.py app/tests/test_09_memory_consolidation.py app/tests/test_10_deepstudy_graph.py app/tests/test_11_model_provider_failover.py app/tests/test_12_sse_audit.py app/tests/test_13_export_search.py app/tests/test_14_performance_smoke.py -q
  } finally {
    Pop-Location
  }
}

if (-not $SkipFrontend) {
  Step "Frontend build"
  Push-Location $Frontend
  try {
    npm ci
    npm run build
  } finally {
    Pop-Location
  }
}

Step "Full-flow checks completed"
