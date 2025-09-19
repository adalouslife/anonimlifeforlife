# slim Python, no GPUs needed for validation tests
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# only copy what we need first to leverage layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# now copy code
COPY handler.py vps_client.py ./

# runpod will start our handler loop; no ports exposed, no webserver
CMD ["python","-u","-c","import handler; handler._boot()"]
