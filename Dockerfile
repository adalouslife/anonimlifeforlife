# Use RunPod's serverless Python base image
FROM runpod/serverless:py3.10

# Faster, quieter pip
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (better cache)
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Bring in the worker code
COPY . /app

# Healthcheck to surface startup issues quickly
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import runpod; import handler" || exit 1

# Start the serverless handler (poller)
CMD ["python", "-u", "handler.py"]
