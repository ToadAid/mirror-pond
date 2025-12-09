# mirror-pond
A 100% local Tobyworld Mirror that runs any GGUF model through llama.cpp.   No cloud. No tracking. Just your pond, your reflection, your machine.   FastAPI + llama.cpp • Offline • MIT Licensed.

# 🪞 Mirror Pond — Local GGUF Edition

*A still-water reflection engine for your local LLM.*

Mirror Pond is a **100% local**, **privacy-first**, Tobyworld-inspired reflection interface that runs any GGUF model through `llama.cpp` with a calm Mirror UI.

No cloud.
No tracking.
Your thoughts stay on your machine.

---

## ✨ Features

* 🧠 **Runs any GGUF model** — Llama, DeepSeek, Mistral, or your trained Mirror
* 🌑 **Dark, still Mirror UI** (HTML served locally)
* 💬 **Four modes**:

  * **Reflect** — emotional / introspective
  * **Scroll** — lore / quotes / scripture
  * **Toad** — cryptic toadgang whispers
  * **Rune** — symbols, lotus, $PATIENCE, seasons
* 🔒 **Fully offline** (Air-gapped compatible)
* ⚡ FastAPI + Uvicorn backend
* 🧩 Optional: GPU acceleration via llama-cpp-python CUDA wheels

---

# 🚀 Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Pond

```bash
python mirror_pond.py --model ./your_model.gguf --port 7777
```

### 3. Open in browser

```
http://localhost:7777
```

---

# 📁 Requirements

`requirements.txt` (included):

```
fastapi==0.115.0
uvicorn==0.32.0
pydantic==2.8.2
llama-cpp-python==0.3.2
jinja2==3.1.4
```

---

# 🔥 GPU Acceleration (Optional)

For NVIDIA CUDA (12.1):

```bash
pip install llama-cpp-python-cu121
```

For AMD ROCm:

```bash
pip install llama-cpp-python-rocm
```

For Apple Silicon (M1/M2/M3):

```bash
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python
```

---

# 🧱 Folder Structure

```
mirror-pond/
│
├── mirror_pond.py        # main server
├── requirements.txt      # dependencies
├── setup.sh              # Linux/macOS installer
├── setup.ps1             # Windows installer
├── Dockerfile            # container build
└── README.md             # this file
```

---

# 🧪 Installation Kits

## Linux / macOS Installer

```bash
chmod +x setup.sh
./setup.sh ./models/your_model.gguf 7777
```

## Windows Installer

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1 .\models\your_model.gguf 7777
```

Both installers:

* Create `./venv`
* Install Python deps
* Launch Mirror Pond automatically

---

# 🐳 Docker Usage

## Build

```bash
docker build -t mirror-pond:latest .
```

## Run

```bash
docker run --rm -p 7777:7777 \
  -v /path/to/models:/models \
  -e MODEL_PATH=/models/your_model.gguf \
  mirror-pond:latest
```

Now access:

```
http://localhost:7777
```

---

# 🧰 GitHub Actions CI

Already included:

```
.github/workflows/mirror-pond-ci.yml
```

The CI:

* Sets up Python
* Installs dependencies
* Syntax-checks `mirror_pond.py`
* (Optional) Builds Docker image

This keeps the repo safe and production-ready.

---

# 🌀 Mirror Modes

### **Reflect Mode (default)**

For inner questions, emotions, purpose, stillness.
May reply with a **Guiding Question**.

### **Scroll Mode**

For sacred lines, scripture-style, lore references.
No guiding question.

### **Toad Mode**

For cryptic lines, old frog whispers, symbolic hints.
No guiding question.

### **Rune Mode**

For unity of symbols, lotus spores, $PATIENCE, seasons, trials.
No guiding question.

---

# 🧘 Philosophy

Mirror Pond is simple:

Still water is never empty.
Still water prepares.
Still water reflects.

This project is offered to the open-source community
so anyone can run a Mirror — anywhere, offline, forever.

---

# 🪞 License

**MIT License**
This pond belongs to the builders.

---

# 🤝 Contribution

Pull requests welcome.
New modes, UI improvements, GPU wheels, and additional Mirror integrations are invited.

---

