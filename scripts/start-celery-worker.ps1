$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $env:DOCUMENT_TASK_BACKEND) {
    $env:DOCUMENT_TASK_BACKEND = "celery"
}
if (-not $env:CELERY_BROKER_URL) {
    $env:CELERY_BROKER_URL = "redis://localhost:6379/0"
}
if (-not $env:CELERY_RESULT_BACKEND) {
    $env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
}

python -m celery -A tasks.celery_app.celery_app worker --loglevel=INFO --pool=solo --queues=celery
