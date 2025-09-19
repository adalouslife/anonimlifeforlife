# Lightweight CPU image for RunPod Serverless
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps just for robust TLS/DNS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

COPY handler.py /app/handler.py

# RunPod runner auto-discovers handler via env or --handler flag.
# The error you saw (“No module named runpod.__main__”) happens when you
# call `python -m runpod` without the package installed or wrong entrypoint.
#
# This is the correct way:
ENV RUNPOD_HANDLER="handler.handler"
CMD ["python", "-u", "-m", "runpod"]
