# Dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt

# Speed + reliability
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Ensure logs are flushed promptly (important for tests)
ENV PYTHONUNBUFFERED=1

# 👉 IMPORTANT: start the RunPod serverless worker, not FastAPI
CMD ["python", "worker.py"]
