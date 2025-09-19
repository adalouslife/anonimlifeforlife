# handler.py
import base64
import io
import time
import requests
import runpod

# -------- Configuration via ENV (with safe defaults) ----------
import os
VPS_BASE = os.getenv("VPS_BASE", "https://anon.donkeybee.com").rstrip("/")
VPS_TOKEN = os.getenv("VPS_TOKEN", "dev-local-secret-change-me")
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "15"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "300"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.5"))
MAX_POLL_SECONDS = int(os.getenv("MAX_POLL_SECONDS", "180"))

# -------- Helpers --------------------------------------------
def _err(msg, **extra):
    out = {"error": msg}
    out.update(extra)
    return out

def _upload_bytes(img_bytes: bytes) -> str:
    """POST to VPS /Upload, return image_id (str)."""
    files = {
        "file": ("input.jpg", io.BytesIO(img_bytes), "application/octet-stream")
    }
    headers = {"X-Auth-Token": VPS_TOKEN}
    url = f"{VPS_BASE}/Upload"

    # a couple retries for transient edge cases
    for attempt in range(3):
        try:
            r = requests.post(
                url,
                files=files,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            r.raise_for_status()
            image_id = r.text.strip()
            if not image_id:
                raise RuntimeError("Empty image_id returned.")
            return image_id
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))

def _poll_status(image_id: str) -> dict:
    """GET /query/{id} until ready or timeout; returns parsed JSON."""
    headers = {"X-Auth-Token": VPS_TOKEN}
    url = f"{VPS_BASE}/query/{image_id}"

    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        r = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, 30))
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "ready":
            return data
        if data.get("status") == "error":
            return data
        time.sleep(POLL_INTERVAL)
    return {"status": "timeout", "message": "Polling timed out."}

def _download_result(image_id: str) -> bytes:
    headers = {"X-Auth-Token": VPS_TOKEN}
    url = f"{VPS_BASE}/download/{image_id}"
    r = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    r.raise_for_status()
    return r.content

def _bytes_from_input(job_input: dict) -> bytes:
    """Support 'image_b64' or 'image_url'."""
    if not isinstance(job_input, dict):
        raise ValueError("Input must be an object.")

    # 1) base64 direct
    b64 = job_input.get("image_b64") or job_input.get("image_base64")
    if b64:
        # allow data URLs
        if b64.startswith("data:"):
            b64 = b64.split(",", 1)[-1]
        return base64.b64decode(b64)

    # 2) fetch from URL
    url = job_input.get("image_url")
    if url:
        r = requests.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        return r.content

    raise ValueError("Provide either 'image_b64' or 'image_url'")

# -------- RunPod handler -------------------------------------
def handler(job):
    """
    Expected input:
    {
      "image_url": "https://...png"      // OR
      "image_b64": "<base64>"
    }

    Output on success:
    {
      "ok": true,
      "image": "<base64_png>",
      "image_id": "<id>",
      "elapsed_sec": 12.3
    }
    """
    start_time = time.time()

    try:
        img_bytes = _bytes_from_input(job.get("input", {}))
    except Exception as e:
        return _err(f"Invalid input: {e}")

    try:
        image_id = _upload_bytes(img_bytes)
    except Exception as e:
        return _err("Upload to VPS failed", details=str(e))

    # poll
    status = _poll_status(image_id)
    if status.get("status") != "ready":
        return _err("Processing failed or timed out", status=status, image_id=image_id)

    # download
    try:
        result_bytes = _download_result(image_id)
    except Exception as e:
        return _err("Download failed", details=str(e), image_id=image_id)

    # return base64 png
    b64_png = base64.b64encode(result_bytes).decode("utf-8")
    return {
        "ok": True,
        "image": b64_png,
        "image_id": image_id,
        "elapsed_sec": round(time.time() - start_time, 2),
    }

# IMPORTANT: start the RunPod serverless worker
runpod.serverless.start({"handler": handler})
