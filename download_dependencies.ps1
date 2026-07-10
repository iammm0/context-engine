# PowerShell脚本：下载GitHub依赖到本地vendor目录
# 用于在构建Docker镜像前预先下载依赖，避免构建时从GitHub拉取

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir = Join-Path $ScriptDir "vendor"

Write-Host "开始下载GitHub依赖到本地..." -ForegroundColor Green

# 创建vendor目录
if (-not (Test-Path $VendorDir)) {
    New-Item -ItemType Directory -Path $VendorDir | Out-Null
}

# 下载 PaddleOCR
$PaddleOCRDir = Join-Path $VendorDir "PaddleOCR"
if (Test-Path $PaddleOCRDir) {
    Write-Host "PaddleOCR 已存在，跳过下载" -ForegroundColor Yellow
    Write-Host "如需更新，请删除 $PaddleOCRDir 后重新运行此脚本" -ForegroundColor Yellow
} else {
    Write-Host "正在克隆 PaddleOCR..." -ForegroundColor Cyan
    Push-Location $VendorDir
    try {
        git clone --depth 1 https://github.com/PaddlePaddle/PaddleOCR.git
        Write-Host "PaddleOCR 下载完成" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "所有依赖下载完成！" -ForegroundColor Green
Write-Host "Now you can run: docker build -t context-engine ." -ForegroundColor Green
