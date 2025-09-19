FROM python:3.10-slim

WORKDIR /app

# System deps kept minimal to reduce build flakiness
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY . /app

# Python deps
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# A predictable place if you later want local temp files
RUN mkdir -p /app/uploads

# Start the RunPod serverless handler
CMD ["python", "handler.py"]
