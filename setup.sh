
---

## 3️⃣ setup.sh (Linux / macOS)

```bash
#!/usr/bin/env bash
# setup.sh — Installer for Mirror Pond (Linux/macOS)

set -e

MODEL_PATH="${1:-./your_model.gguf}"
PORT="${2:-7777}"

echo "🪞 Mirror Pond — Linux/macOS Installer"
echo "Model: $MODEL_PATH"
echo "Port : $PORT"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python3 not found. Install Python 3.9+."
  exit 1
fi

echo "📦 Creating venv..."
python3 -m venv .venv

echo "📦 Activating venv..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "⬆️  Upgrading pip..."
pip install --upgrade pip

if [ ! -f requirements.txt ]; then
  echo "❌ requirements.txt missing."
  exit 1
fi

echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✨ Setup complete."
echo "Run manually:"
echo "  source .venv/bin/activate"
echo "  python mirror_pond.py --model \"$MODEL_PATH\" --port $PORT"
echo ""
echo "🚀 Launching now..."
python mirror_pond.py --model "$MODEL_PATH" --port "$PORT"
