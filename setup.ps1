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

Write-Host "🧠 Enforcing GPU build of llama.cpp (CUDA)..." -ForegroundColor Cyan

# Remove CPU-only wheel if present
pip uninstall -y llama-cpp-python | Out-Null

# Try CUDA 12.1 wheel (adjust to cu124 if needed for your CUDA)
try {
    pip install llama-cpp-python-cu121
    Write-Host "✅ Installed llama-cpp-python-cu121 (CUDA GPU wheel)." -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Failed to install llama-cpp-python-cu121. Falling back to CPU llama-cpp-python (will be slower)." -ForegroundColor Yellow
    pip install llama-cpp-python
}

Write-Host ""
Write-Host "✨ Setup complete." -ForegroundColor Green
Write-Host "You can also run manually later with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "  python mirror_pond.py --model `"$ModelPath`" --port $Port --gpu-layers $GpuLayers" -ForegroundColor Yellow
Write-Host ""
Write-Host "🚀 Launching Mirror Pond now on GPU (if available)..." -ForegroundColor Green

python mirror_pond.py --model "$ModelPath" --port $Port --gpu-layers $GpuLayers
