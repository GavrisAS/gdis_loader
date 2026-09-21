$ErrorActionPreference = "Stop"

function Assert-NativeExitCode {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

uv sync --locked
Assert-NativeExitCode "uv sync --locked"
uv run ruff check .
Assert-NativeExitCode "ruff check"
uv run ruff format --check .
Assert-NativeExitCode "ruff format --check"
uv run ty check
Assert-NativeExitCode "ty check"
uv run pytest
Assert-NativeExitCode "pytest"
uv run python -c "from PySide6 import QtCore, QtWidgets; print(QtCore.qVersion())"
Assert-NativeExitCode "PySide6 import"

uv run pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name GDIS_DataLoader `
  --paths src `
  --add-data "config.example.toml;." `
  src/gdis_loader/__main__.py
Assert-NativeExitCode "PyInstaller"

$Executable = "dist/GDIS_DataLoader/GDIS_DataLoader.exe"
if (-not (Test-Path $Executable)) {
    throw "PyInstaller did not create $Executable"
}
& $Executable --smoke-test
Assert-NativeExitCode "Frozen GUI smoke-test"

$ZipPath = "dist/GDIS_DataLoader-windows-x64.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path "dist/GDIS_DataLoader" -DestinationPath $ZipPath
Write-Host "Created $ZipPath"
