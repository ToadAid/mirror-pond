#!/usr/bin/env bash
# setup.sh — GPU-first installer for Mirror Pond (Linux/macOS, NVIDIA CUDA)

set -e

MODEL_PATH="${1:-./your_model.gguf}"
PORT="${2:-7777}"
GPU_LAYERS="${3:--1}"

echo "🪞 Mirror Pond — Linux/macOS GPU Installer"
echo "Model: $MODEL_PATH"
echo "Port : $PORT"
echo "GPU  : $GPU_LAYERS layers (-1 = as many as possible)"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python3 not found. Please install Python 3.9+."
  exit 1
fi

echo "📦 Creating virtualenv .venv..."
python3 -m venv .venv

echo "📦 Activating venv..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "⬆️  Upgrading pip..."
pip install --upgrade pip

if [ ! -f requirements.txt ]; then
  echo "❌ requirements.txt missing in current directory."
  exit 1
fi

echo "📥 Installing base dependencies from requirements.txt..."
pip install -r requirements.txt

echo "🧠 Enforcing GPU build of llama.cpp (CUDA 12.1 wheel if possible)..."
# Remove any existing CPU build (if present)
pip uninstall -y llama-cpp-python || true

# Use official prebuilt CUDA wheel index
export CMAKE_ARGS="-DGGML_CUDA=on"

if pip install --force-reinstall --no-cache-dir \
    llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121; then
  echo "✅ Installed llama-cpp-python with CUDA (cu121 wheel)."
else
  echo "⚠️ Failed to install CUDA wheel; falling back to CPU build."
  pip install --force-reinstall --no-cache-dir llama-cpp-python
fi

echo ""
echo "✨ Setup complete."
echo "You can run manually later with:"
echo "  source .venv/bin/activate"
echo "  python mirror_pond.py --model \"$MODEL_PATH\" --port $PORT --gpu-layers $GPU_LAYERS"
echo ""
echo "🚀 Launching Mirror Pond now..."
python mirror_pond.py \
  --model "$MODEL_PATH" \
  --port "$PORT" \
  --gpu-layers "$GPU_LAYERS"
