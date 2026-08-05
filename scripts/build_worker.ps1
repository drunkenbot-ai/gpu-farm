param([switch]$Clean, [switch]$Installer)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($Clean) { Remove-Item -LiteralPath build,dist -Recurse -Force -ErrorAction SilentlyContinue }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean worker.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Worker EXE: $root\dist\GPUFarmWorker.exe"
if ($Installer) {
  $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) is required to build the installer." }
  & $iscc.Source "$root\installer\GPUFarmWorker.iss"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host "Installer: $root\dist\installer"
}
