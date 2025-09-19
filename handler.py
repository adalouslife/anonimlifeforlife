import os
import time
import base64
import mimetypes
import typing as t

import requests
import runpod

# --------------------------
# Config via environment
# --------------------------
VPS_BASE = os.getenv("VPS_BASE", "").rstrip("/")
VPS_TOKEN = os.getenv("VPS_TOKEN", "")

# Safety defaults
UPLOAD_PATH = "/Upload"
QUERY_PATH = "/query/{id}"
DOWNLOAD_PATH = "/download/{id}"

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "60"))
POLL_MAX_SECONDS = int(os.getenv("POLL_MAX_SECONDS", "180"))
POLL_INTERVAL_START = float(os.getenv("POLL_INTERVAL_START", "0.5"))
POLL_INTERVAL_MAX = float(os.getenv("POLL_INTERVAL_MAX", "3.0"))

# --------------------------
# Helpers
# --------------------------
class BadRequest(ValueError):
    pass

def _check_cfg():
    if not VPS_BASE or not VPS_TOKEN:
        raise BadRequest("Missing VPS_BASE or VPS_TOKEN environment variables.")

def _get_bytes_from_url(url: str) -> bytes:
    # simple content-length guard (50MB)
    max_bytes = 50 * 1024 * 1024
    with requests.get(url, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        chunks = []
        total = 0
        for c in r.iter_content(1024 * 32):
            if not c:
                continue
            total += len(c)
            if total > max_bytes:
                raise BadRequest("Image too large (>50MB).")
            chunks.append(c)
        return b"".join(chunks)

def _decode_b64(data_url_or_b64: str) -> bytes:
    # Supports raw base64 or data URL (data:image/png;base64,....)
    if "," in data_url_or_b64 and data_url_or_b64.strip().lower().startswith("data:"):
        data_url_or_b64 = data_url_or_b64.split(",", 1)[1]
    return base64.b64decode(data_url_or_b64)

def _infer_mime_from_name(name: str) -> str:
    mt, _ = mimetypes.guess_type(name)
    return mt or "application/octet-stream"

def _upload_to_vps(img_bytes: bytes, filename: str="upload.png") -> str:
    url = f"{VPS_BASE}{UPLOAD_PATH}"
    files = {
        "file": (filename, img_bytes, _infer_mime_from_name(filename))
    }
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.post(url, files=files, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    image_id = r.text.strip()
    if len(image_id) != 32:
        # Your API prints 32-hex; fallback in case API returns JSON
        try:
            possible = r.json()
        except Exception:
            possible = None
        raise RuntimeError(f"Unexpected upload response: {r.text!r} {possible!r}")
    return image_id

def _poll_status(image_id: str) -> str:
    url = f"{VPS_BASE}{QUERY_PATH.format(id=image_id)}"
    headers = {"X-Auth-Token": VPS_TOKEN}
    t0 = time.time()
    delay = POLL_INTERVAL_START
    while True:
        r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        status = r.text.strip().upper()
        if status in ("READY", "DONE"):
            return status
        if status in ("FAILED", "ERROR"):
            raise RuntimeError(f"VPS reported failure: {status}")
        if time.time() - t0 > POLL_MAX_SECONDS:
            raise TimeoutError("Timed out waiting for VPS result.")
        time.sleep(delay)
        delay = min(POLL_INTERVAL_MAX, delay * 1.5)

def _download_result(image_id: str) -> bytes:
    url = f"{VPS_BASE}{DOWNLOAD_PATH.format(id=image_id)}"
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.content

# --------------------------
# RunPod handler
# --------------------------
def handler(event: dict) -> dict:
    """
    Input payload supports:
      { "image_url": "https://...", ... }
      OR { "image_b64": "iVBORw0..." }   (also accepts data URLs)
      OR { "file_url": "https://..." }   (same as image_url, aliased)
    Optional passthrough:
      "filename": "name.jpg"
    Returns:
      { "status":"COMPLETED", "image_b64":"...", "meta":{...} }
    """
    _check_cfg()

    data = (event or {}).get("input") or {}
    image_url = data.get("image_url") or data.get("file_url")
    image_b64 = data.get("image_b64") or data.get("imageBase64")
    filename = data.get("filename") or "upload.png"

    if not image_url and not image_b64:
        raise BadRequest("Provide either 'image_url' (or 'file_url') or 'image_b64'.")

    # Fetch bytes
    if image_url:
        img_bytes = _get_bytes_from_url(image_url)
        if not os.path.splitext(filename)[1]:
            # try infer extension from URL
            guess_ext = os.path.splitext(image_url.split("?")[0])[1]
            if guess_ext:
                filename = f"upload{guess_ext}"
    else:
        img_bytes = _decode_b64(image_b64)

    # Upload -> poll -> download
    image_id = _upload_to_vps(img_bytes, filename=filename)
    status = _poll_status(image_id)
    result_bytes = _download_result(image_id)
    out_b64 = base64.b64encode(result_bytes).decode("utf-8")

    return {
        "status": "COMPLETED",
        "image_id": image_id,
        "image_b64": out_b64,
        "meta": {
            "bytes_in": len(img_bytes),
            "bytes_out": len(result_bytes)
        }
    }

# Register with RunPod runner
runpod.serverless.start({"handler": handler})
