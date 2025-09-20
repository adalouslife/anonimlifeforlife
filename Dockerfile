# Dockerfile (Serverless worker)
FROM python:3.10-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (better cache)
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Bring in worker code
COPY . /app

# Optional healthcheck (safe)
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import handler" || exit 1

# Start RunPod poller/handler
CMD ["python", "-u", "handler.py"]
