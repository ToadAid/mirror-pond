# setup.ps1 — Installer for Mirror Pond (Windows)

param(
    [string]$ModelPath = ".\your_model.gguf",
    [int]$Port = 7777
)

Write-Host "🪞 Mirror Pond — Windows Installer" -ForegroundColor Green
Write-Host "Model: $ModelPath"
Write-Host "Port : $Port"
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python not found. Install Python 3.9+." -ForegroundColor Red
    exit 1
}

Write-Host "📦 Creating virtualenv .venv..." -ForegroundColor Cyan
python -m venv .venv

$venvActivation = ".\venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivation)) {
    $venvActivation = ".\.venv\Scripts\Activate.ps1"
}

. $venvActivation

Write-Host "⬆️  Upgrading pip..." -ForegroundColor Cyan
pip install --upgrade pip

if (-not (Test-Path ".\requirements.txt")) {
    Write-Host "❌ requirements.txt missing." -ForegroundColor Red
    exit 1
}

Write-Host "📥 Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host ""
Write-Host "✨ Setup complete." -ForegroundColor Green
Write-Host "Run manually:"
Write-Host "  .\.venv\Scripts\activate"
Write-Host "  python mirror_pond.py --model `"$ModelPath`" --port $Port"
Write-Host ""
Write-Host "🚀 Launching now..." -ForegroundColor Green
python mirror_pond.py --model "$ModelPath" --port $Port
