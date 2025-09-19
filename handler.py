import base64
import io
import os
import time
from typing import Dict, Any, Optional

import requests
from PIL import Image
import runpod

# ----- Config -----
VPS_BASE = os.environ.get("VPS_BASE", "https://anon.donkeybee.com").rstrip("/")
VPS_TOKEN = os.environ.get("VPS_TOKEN", "dev-local-secret-change-me")
HEADERS = {"X-Auth-Token": VPS_TOKEN}

# Polling settings
POLL_INTERVAL_SEC = 1.5
MAX_WAIT_SEC = 120


def _upload_bytes(img_bytes: bytes) -> str:
    files = {"file": ("input.jpg", img_bytes, "image/jpeg")}
    r = requests.post(f"{VPS_BASE}/Upload", files=files, headers=HEADERS, timeout=60)
    r.raise_for_status()
    image_id = r.text.strip()
    # Some servers might echo with newline; ensure clean hex-ish id
    return image_id


def _download_image_b64(image_id: str) -> str:
    r = requests.get(f"{VPS_BASE}/download/{image_id}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    # Return as data URL base64 (PNG)
    return "data:image/png;base64," + base64.b64encode(r.content).decode("utf-8")


def _poll_until_done(image_id: str) -> Dict[str, Any]:
    """Returns JSON from /query/{id}"""
    start = time.time()
    while True:
        r = requests.get(f"{VPS_BASE}/query/{image_id}", headers=HEADERS, timeout=30)
        r.raise_for_status()
        j = r.json()
        # Expect e.g. {"status":"processing"/"done"/"error", ...}
        status = j.get("status", "").lower()
        if status in ("done", "error"):
            return j
        if (time.time() - start) > MAX_WAIT_SEC:
            raise TimeoutError(f"Timeout waiting for cloaking (id={image_id}). Last status={status}")
        time.sleep(POLL_INTERVAL_SEC)


def _read_image_url(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def _read_image_b64(data_url_or_raw_b64: str) -> bytes:
    s = data_url_or_raw_b64
    if s.startswith("data:image"):
        s = s.split(",", 1)[1]
    raw = base64.b64decode(s)
    # Normalize to JPEG bytes for upload (Fawkes binary usually accepts common formats)
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception:
        # If it's already a valid JPEG/PNG, just send as-is
        return raw


def _normalize_input(job_input: Dict[str, Any]) -> bytes:
    if not job_input:
        raise ValueError("Missing input payload.")
    if "image_b64" in job_input and job_input["image_b64"]:
        return _read_image_b64(job_input["image_b64"])
    if "image_url" in job_input and job_input["image_url"]:
        return _read_image_url(job_input["image_url"])
    raise ValueError("Provide either 'image_url' or 'image_b64' in input.")


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected inputs (one of):
    { "image_url": "https://..." }
    { "image_b64": "data:image/...;base64,..." } or raw base64

    Returns:
    {
      "status": "COMPLETED",
      "image_id": "<id>",
      "image_b64": "data:image/png;base64,...",
      "meta": { "poll_payload": {...} }
    }
    """
    try:
        job_input = job.get("input", {})
        img_bytes = _normalize_input(job_input)

        # 1) Upload
        image_id = _upload_bytes(img_bytes)

        # 2) Poll
        poll_json = _poll_until_done(image_id)
        if poll_json.get("status", "").lower() == "error":
            # Bubble up server error details
            return {
                "status": "FAILED",
                "error": poll_json.get("error", "Unknown error from VPS"),
                "image_id": image_id,
                "meta": {"poll_payload": poll_json}
            }

        # 3) Download result
        image_b64 = _download_image_b64(image_id)

        return {
            "status": "COMPLETED",
            "image_id": image_id,
            "image_b64": image_b64,
            "meta": {"poll_payload": poll_json}
        }
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP error: {e}", "meta": {}}
    except Exception as e:
        return {"status": "FAILED", "error": str(e), "meta": {}}


# Start the RunPod serverless loop (per docs)
runpod.serverless.start({"handler": handler})
