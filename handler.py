import base64
import io
import os
import time
from typing import Any, Dict, Optional

import requests
from PIL import Image
import runpod


# ---------- Config from environment ----------
VPS_BASE = os.environ.get("VPS_BASE_URL", "").rstrip("/")
VPS_TOKEN = os.environ.get("VPS_AUTH_TOKEN", "")

# Simple safety: fail fast if misconfigured at runtime.
def _require_env():
    if not VPS_BASE or not VPS_TOKEN:
        raise RuntimeError(
            "Missing VPS_BASE_URL or VPS_AUTH_TOKEN env. "
            "Set them on your RunPod endpoint."
        )

# ---------- Helpers ----------
def fetch_bytes_from_url(url: str, timeout: int = 30) -> bytes:
    headers = {
        # Some hosts 403 without a UA; this keeps it friendly.
        "User-Agent": "Mozilla/5.0 (compatible; RunPodWorker/1.0)",
        "Accept": "*/*",
    }
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        # Limit very large files to 25 MB to avoid blowing memory
        max_bytes = 25 * 1024 * 1024
        chunks = []
        size = 0
        for chunk in r.iter_content(1024 * 64):
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Image too large (>25MB).")
        return b"".join(chunks)

def b64_to_bytes(data_b64: str) -> bytes:
    # Allow both raw base64 and data URLs
    if data_b64.startswith("data:image"):
        data_b64 = data_b64.split(",", 1)[1]
    return base64.b64decode(data_b64)

def bytes_to_b64(img_bytes: bytes) -> str:
    return base64.b64encode(img_bytes).decode("utf-8")

def ensure_image_bytes(img_bytes: bytes) -> bytes:
    """
    Sanity check that bytes are a readable image. Also normalizes to PNG
    so we always return something consistently decodable.
    """
    with Image.open(io.BytesIO(img_bytes)) as im:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

def vps_upload(image_bytes: bytes, content_type: str = "image/png") -> str:
    """
    POST multipart to VPS /Upload -> returns IMAGE_ID (32 hex chars).
    """
    _require_env()
    up_url = f"{VPS_BASE}/Upload"
    headers = {"X-Auth-Token": VPS_TOKEN}
    files = {"file": ("upload.png", image_bytes, content_type)}
    r = requests.post(up_url, headers=headers, files=files, timeout=60)
    r.raise_for_status()
    image_id = r.text.strip()
    if len(image_id) < 16:
        raise RuntimeError(f"Unexpected Upload response: {r.text}")
    return image_id

def vps_poll_ready(image_id: str, max_wait: int = 60) -> str:
    """
    Poll /query/{id} until READY or FAILED or timeout.
    Returns final status string.
    """
    _require_env()
    qry_url = f"{VPS_BASE}/query/{image_id}"
    headers = {"X-Auth-Token": VPS_TOKEN}
    start = time.time()
    while True:
        r = requests.get(qry_url, headers=headers, timeout=15)
        r.raise_for_status()
        status = r.text.strip().upper()
        if status in ("READY", "FAILED"):
            return status
        if time.time() - start > max_wait:
            raise TimeoutError("Timed out waiting for VPS to finish.")
        time.sleep(1.0)

def vps_download(image_id: str) -> bytes:
    _require_env()
    dl_url = f"{VPS_BASE}/download/{image_id}"
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.get(dl_url, headers=headers, timeout=60)
    r.raise_for_status()
    return r.content

# ---------- RunPod handler ----------
def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inputs accepted:
      - ping: true                   -> test-only, returns {"pong": true}
      - image_b64 / imageBase64      -> base64 image
      - image_url / fileUrl          -> URL to fetch image
      - return_b64 (bool, default True)
    Output:
      {
        "status": "COMPLETED" | "FAILED",
        "id": "<IMAGE_ID or empty>",
        "download_url": "<VPS download url or empty>",
        "image_b64": "<base64 or empty>",
        "error": "<message if failed>"
      }
    """
    inp = job.get("input") or {}

    # ---- Zero-dependency test path so RunPod 'Testing' can pass without network
    if inp.get("ping") is True:
        return {"pong": True}

    try:
        _require_env()  # ensure env present in real runs

        # Accept common key variants
        image_b64 = inp.get("image_b64") or inp.get("imageBase64")
        image_url = inp.get("image_url") or inp.get("fileUrl")
        return_b64 = bool(inp.get("return_b64", True))

        if not image_b64 and not image_url:
            raise ValueError("Provide image_b64 (or imageBase64) OR image_url (or fileUrl).")

        if image_b64:
            raw = b64_to_bytes(image_b64)
        else:
            raw = fetch_bytes_from_url(image_url)

        # Sanity + normalize to PNG
        img_bytes = ensure_image_bytes(raw)

        # Upload -> ID
        image_id = vps_upload(img_bytes, content_type="image/png")

        # Poll -> READY
        status = vps_poll_ready(image_id, max_wait=90)
        if status != "READY":
            return {
                "status": "FAILED",
                "id": image_id,
                "download_url": f"{VPS_BASE}/download/{image_id}",
                "image_b64": "",
                "error": f"VPS status: {status}"
            }

        # Download result
        out_bytes = vps_download(image_id)

        out = {
            "status": "COMPLETED",
            "id": image_id,
            "download_url": f"{VPS_BASE}/download/{image_id}",
            "image_b64": bytes_to_b64(out_bytes) if return_b64 else ""
        }
        return out

    except Exception as e:
        return {
            "status": "FAILED",
            "id": "",
            "download_url": "",
            "image_b64": "",
            "error": str(e)
        }

# Start the serverless worker
runpod.serverless.start({"handler": handler})
