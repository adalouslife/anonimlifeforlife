# handler.py
from __future__ import annotations
import base64
import io
import time
import requests
import runpod

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Fallback defaults (still configurable via request input)
DEFAULT_VPS_BASE   = "http://127.0.0.1:8000"
DEFAULT_VPS_TOKEN  = "dev-local-secret-change-me"
DEFAULT_TIMEOUT_S  = 300.0   # total processing timeout
DEFAULT_POLL_EVERY = 2.0
DEFAULT_REQ_CONNECT = 20.0   # connect timeout
DEFAULT_REQ_READ    = 240.0  # read timeout (was 60)
MAX_UPLOAD_BYTES_BEFORE_COMPRESS = 2_000_000  # 2 MB
MAX_SIDE_PX = 1280
JPEG_QUALITY = 85

def _shrink_if_large(img_bytes: bytes) -> bytes:
    """If image is large, try to downscale+re-encode to speed up upload.
       If Pillow missing or anything fails, return original bytes."""
    if not PIL_AVAILABLE:
        return img_bytes
    if len(img_bytes) <= MAX_UPLOAD_BYTES_BEFORE_COMPRESS:
        return img_bytes
    try:
        with Image.open(io.BytesIO(img_bytes)) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, MAX_SIDE_PX / float(max(w, h)))
            if scale < 1.0:
                new_size = (int(w * scale), int(h * scale))
                im = im.resize(new_size, Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except Exception:
        return img_bytes

def _upload_bytes(vps_base: str, vps_token: str, img_bytes: bytes, req_connect: float, req_read: float) -> str:
    files = {"file": ("upload.jpg", img_bytes, "image/jpeg")}
    headers = {"X-Auth-Token": vps_token}
    r = requests.post(
        f"{vps_base}/Upload",
        files=files,
        headers=headers,
        timeout=(req_connect, req_read),
    )
    r.raise_for_status()
    return r.text.strip()

def _poll_ready(vps_base: str, vps_token: str, image_id: str, req_connect: float, req_read: float) -> bool:
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(
        f"{vps_base}/query/{image_id}",
        headers=headers,
        timeout=(req_connect, req_read),
    )
    r.raise_for_status()
    return r.text.strip().upper() == "READY"

def _download_image(vps_base: str, vps_token: str, image_id: str, req_connect: float, req_read: float) -> bytes:
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(
        f"{vps_base}/download/{image_id}",
        headers=headers,
        timeout=(req_connect, req_read),
    )
    r.raise_for_status()
    return r.content

def handler(job):
    """
    Request shape:
    {
      "input": {
        "image_url": "https://...",
        // or
        "image_b64": "<base64>",

        // overrides (optional)
        "vps_base": "https://xxxx.ngrok-free.app",
        "vps_token": "dev-local-secret-change-me",
        "timeout_s": 300,
        "poll_every": 2.0,
        "request_timeout_connect": 20,
        "request_timeout_read": 240
      }
    }
    """
    data = job.get("input") or {}
    vps_base  = data.get("vps_base", DEFAULT_VPS_BASE).rstrip("/")
    vps_token = data.get("vps_token", DEFAULT_VPS_TOKEN)

    timeout_s   = float(data.get("timeout_s", DEFAULT_TIMEOUT_S))
    poll_every  = float(data.get("poll_every", DEFAULT_POLL_EVERY))
    req_connect = float(data.get("request_timeout_connect", DEFAULT_REQ_CONNECT))
    req_read    = float(data.get("request_timeout_read", DEFAULT_REQ_READ))

    # Get image bytes
    if "image_b64" in data:
        try:
            img_bytes = base64.b64decode(data["image_b64"], validate=True)
        except Exception as e:
            return {"error": f"Invalid base64: {e}"}
    elif "image_url" in data:
        try:
            resp = requests.get(data["image_url"], timeout=(req_connect, req_read))
            resp.raise_for_status()
            img_bytes = resp.content
        except Exception as e:
            return {"error": f"Failed to fetch image_url: {e}"}
    else:
        return {"error": "Provide image_url or image_b64 in input"}

    # Possibly shrink (to speed up upload via ngrok free)
    img_bytes = _shrink_if_large(img_bytes)

    # Upload to VPS
    try:
        image_id = _upload_bytes(vps_base, vps_token, img_bytes, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Upload timed out: {e}", "hint": "Increase request_timeout_read or use smaller image"}
    except Exception as e:
        return {"error": f"Upload failed: {e}"}

    # Poll until READY
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if _poll_ready(vps_base, vps_token, image_id, req_connect, req_read):
                break
        except Exception:
            # transient issues, keep polling
            pass
        time.sleep(poll_every)
    else:
        return {"error": "Processing timeout", "image_id": image_id, "timeout_s": timeout_s}

    # Download result
    try:
        result_bytes = _download_image(vps_base, vps_token, image_id, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Download timed out: {e}", "image_id": image_id}
    except Exception as e:
        return {"error": f"Download failed: {e}", "image_id": image_id}

    result_b64 = base64.b64encode(result_bytes).decode("utf-8")
    return {
        "image_id": image_id,
        "cloaked_b64": result_b64,
        "note": "Result is base64-encoded image (JPEG)."
    }

runpod.serverless.start({"handler": handler})
