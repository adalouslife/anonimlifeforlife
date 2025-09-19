FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY handler.py .
ENV VPS_BASE=https://anon.donkeybee.com
ENV VPS_TOKEN=dev-local-secret-change-me
CMD ["python", "-m", "runpod"]
