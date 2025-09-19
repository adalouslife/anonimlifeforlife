FROM python:3.10-slim

# System deps (trusted certs + curl for basic health/debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (better layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY handler.py vps_client.py ./

# RunPod worker MUST start and keep running
# -u = unbuffered logs so you can see output in RunPod logs
CMD ["python", "-u", "handler.py"]
