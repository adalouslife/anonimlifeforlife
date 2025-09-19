FROM python:3.10-slim

WORKDIR /app

# System deps (curl handy for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/requirements.txt

COPY handler.py /app/handler.py

# No CMD needed if RunPod overrides entrypoint, but it's fine to set:
CMD ["python", "/app/handler.py"]
