FROM python:3.10-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Only what we really need for Serverless
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler + optional VPS proxy helper
COPY handler.py vps_client.py ./

# Start the Runpod Serverless poller
CMD ["python", "-u", "handler.py"]
