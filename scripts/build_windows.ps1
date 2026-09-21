$ErrorActionPreference = "Stop"

uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest

uv run pyinstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name GDIS_DataLoader `
  --add-data "config.example.toml;." `
  src/gdis_loader/__main__.py

$ZipPath = "dist/GDIS_DataLoader-windows-x64.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path "dist/GDIS_DataLoader" -DestinationPath $ZipPath
Write-Host "Created $ZipPath"
