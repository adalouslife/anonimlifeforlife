FROM python:3.10-slim

# Set working directory
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy repo
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Create uploads dir
RUN mkdir -p /app/uploads

# Default command
CMD ["python", "handler.py"]
