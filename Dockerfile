# Dockerfile
FROM python:3.10-slim

# System deps (curl useful for debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Code
COPY handler.py /app/handler.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Env knobs (override in RunPod console as needed)
ENV VPS_BASE="https://anon.donkeybee.com"
ENV VPS_TOKEN="dev-local-secret-change-me"
ENV CONNECT_TIMEOUT=15
ENV READ_TIMEOUT=300
ENV POLL_INTERVAL=1.5
ENV MAX_POLL_SECONDS=180

# Start RunPod worker
CMD ["/app/start.sh"]
