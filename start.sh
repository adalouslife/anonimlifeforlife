#!/bin/bash
set -e

echo "[INFO] Starting anonymizer worker..."
# Ensure uploads dir exists
mkdir -p /app/uploads

# Start RunPod handler
python3 handler.py
