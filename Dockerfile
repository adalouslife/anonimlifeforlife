FROM python:3.10-slim

# System deps (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py vps_client.py ./

# Runpod Serverless will start the poller via handler.py
CMD ["python", "-u", "handler.py"]
