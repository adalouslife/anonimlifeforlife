FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
COPY handler.py .
# Defaults; override in Runpod Hub env config
ENV VPS_BASE=http://127.0.0.1:8000
ENV VPS_TOKEN=dev-local-secret-change-me
ENV TIMEOUT_S=180
ENV POLL_EVERY=2.0
CMD ["python", "-u", "handler.py"]
