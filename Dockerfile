# Small, fast, no build tools needed
FROM python:3.10-slim

# Prevents Python from buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install CA certificates + curl (handy for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY handler.py vps_client.py ./

# Runpod looks for the handler automatically when we start the serverless runtime.
# No CMD needed—Runpod injects the entrypoint. Keeping default.
