# setup.ps1 — GPU-first installer for Mirror Pond (Windows, NVIDIA CUDA)

param(
    [string]$ModelPath = ".\your_model.gguf",
    [int]$Port = 7777,
    [int]$GpuLayers = -1
)

Write-Host "🪞 Mirror Pond — Windows GPU Installer" -ForegroundColor Green
Write-Host "Model: $ModelPath"
Write-Host "Port : $Port"
Write-Host "GPU  : $GpuLayers layers (-1 = as many as possible)"
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python not found. Please install Python 3.9+ and ensure 'python' is in PATH." -ForegroundColor Red
    exit 1
}

Write-Host "📦 Creating virtualenv .venv..." -ForegroundColor Cyan
python -m venv .venv

$venvActivation = ".\venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivation)) {
    $venvActivation = ".\.venv\Scripts\Activate.ps1"
}
if (-not (Test-Path $venvActivation)) {
    Write-Host "❌ Could not find virtualenv activation script." -ForegroundColor Red
    exit 1
}

Write-Host "📦 Activating venv..." -ForegroundColor Cyan
. $venvActivation

Write-Host "⬆️  Upgrading pip..." -ForegroundColor Cyan
pip install --upgrade pip

if (-not (Test-Path ".\requirements.txt")) {
    Write-Host "❌ requirements.txt missing in current directory." -ForegroundColor Red
    exit 1
}

Write-Host "📥 Installing base dependencies from requirements.txt..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "🧠 Enforcing GPU build of llama.cpp (CUDA 12.1 wheel if possible)..." -ForegroundColor Cyan

# Remove any existing CPU build
pip uninstall -y llama-cpp-python | Out-Null

# Use official CUDA 12.1 wheel index
$env:CMAKE_ARGS = "-DGGML_CUDA=on"

try {
    pip install --force-reinstall --no-cache-dir `
        llama-cpp-python `
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
    Write-Host "✅ Installed llama-cpp-python with CUDA (cu121 wheel)." -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Failed to install CUDA wheel; falling back to CPU build." -ForegroundColor Yellow
    pip install --force-reinstall --no-cache-dir llama-cpp-python
}

Write-Host ""
Write-Host "✨ Setup complete." -ForegroundColor Green
Write-Host "You can run manually later with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "  python mirror_pond.py --model `"$ModelPath`" --port $Port --gpu-layers $GpuLayers" -ForegroundColor Yellow
Write-Host ""
Write-Host "🚀 Launching Mirror Pond now..." -ForegroundColor Green

python mirror_pond.py --model "$ModelPath" --port $Port --gpu-layers $GpuLayers
