$ErrorActionPreference = "Stop"

uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run python -c "from PySide6 import QtCore, QtWidgets; print(QtCore.qVersion())"

uv run pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name GDIS_DataLoader `
  --paths src `
  --add-data "config.example.toml;." `
  src/gdis_loader/__main__.py

$Executable = "dist/GDIS_DataLoader/GDIS_DataLoader.exe"
if (-not (Test-Path $Executable)) {
    throw "PyInstaller did not create $Executable"
}
& $Executable --smoke-test
if ($LASTEXITCODE -ne 0) {
    throw "Frozen GUI smoke-test failed with exit code $LASTEXITCODE"
}

$ZipPath = "dist/GDIS_DataLoader-windows-x64.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path "dist/GDIS_DataLoader" -DestinationPath $ZipPath
Write-Host "Created $ZipPath"
