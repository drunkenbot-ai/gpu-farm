param([switch]$Clean)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($Clean) { Remove-Item -LiteralPath build,dist -Recurse -Force -ErrorAction SilentlyContinue }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean worker.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Worker EXE: $root\dist\GPUFarmWorker.exe"
