# Mirror Pond - Dockerfile
# Build:
#   docker build -t mirror-pond:latest .
#
# Run (with model mounted from host):
#   docker run --rm -p 7777:7777 \
#     -v /path/to/models:/models \
#     -e MODEL_PATH=/models/your_model.gguf \
#     mirror-pond:latest

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_PATH=/models/your_model.gguf \
    PORT=7777

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

COPY mirror_pond.py ./
COPY requirements.txt ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

EXPOSE 7777

CMD ["sh", "-c", "python mirror_pond.py --model ${MODEL_PATH} --port ${PORT}"]
