# Use a small, stable Python base
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Where we write final images inside the container
    OUTPUT_DIR=/app/uploads \
    # Your public base URL (domain) that serves files from OUTPUT_DIR
    OUTPUT_BASE_URL=https://anon.donkeybee.com \
    # Public path prefix mapped by your reverse-proxy/Caddy to /app/uploads
    OUTPUT_PUBLIC_PREFIX=/download

WORKDIR /app

# System packages: add-only what’s necessary for Pillow wheels & runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# App code
COPY handler.py logic.py ./

# Writable output directory in the image
RUN mkdir -p ${OUTPUT_DIR}

# Runpod serverless will execute the module; no webserver needed
CMD ["python", "handler.py"]
