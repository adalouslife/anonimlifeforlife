FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY handler.py /app/handler.py

# Defaults; override in RunPod -> Environment
ENV VPS_BASE="https://anon.donkeybee.com"
ENV VPS_TOKEN="dev-local-secret-change-me"
ENV CONNECT_TIMEOUT=15
ENV READ_TIMEOUT=300
ENV POLL_INTERVAL=1.5
ENV MAX_POLL_SECONDS=180

CMD ["python", "-u", "handler.py"]
