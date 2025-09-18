FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY handler.py /app/handler.py

# Run the RunPod worker (not uvicorn)
CMD ["python", "-u", "-m", "runpod", "--handler-path", "handler.py"]
