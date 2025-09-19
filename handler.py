# handler.py
import base64
import io
import os
import time
from typing import Any, Dict, Optional, Tuple
import requests
import runpod

from vps_client import VPSClient, VPSJobError

# ---- Config via env ----
VPS_BASE_URL = os.environ.get("VPS_BASE_URL", "https://anon.donkeybee.com")
VPS_API_KEY  = os.environ.get("VPS_API_KEY", "")  # optional
# Query polling
POLL_INTERVAL_SEC = float(os.environ.get("POLL_INTERVAL_SEC", "1.5"))
POLL_TIMEOUT_SEC  = float(os.environ.get("POLL_TIMEOUT_SEC", "300"))

vps = VPSClient(
    base_url=VPS_BASE_URL,
    api_key=VPS_API_KEY,
    user_agent="runpod-bridge/1.0"
)

def _download_url_to_bytes(url: str) -> bytes:
    """Fetch an image from a remote URL into memory."""
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def _decode_base64_image(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=True)
    except Exception as e:
        raise ValueError(f"Invalid base64 image: {e}")

def _extract_input(event: Dict[str, Any]) -> Tuple[bytes, Optional[str]]:
    """
    Accepts one of:
      event['input']['image_url']   -> fetch
      event['input']['image_b64']   -> decode
    Returns (image_bytes, original_filename or None)
    """
    inp = event.get("input") or {}
    url = inp.get("image_url")
    b64 = inp.get("image_b64")

    if url:
        return _download_url_to_bytes(url), os.path.basename(url.split("?")[0]) or None
    if b64:
        return _decode_base64_image(b64), None

    raise ValueError("Provide 'image_url' or 'image_b64' in input.")

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runpod handler contract: return a JSON-serializable dict.
    """
    try:
        image_bytes, maybe_name = _extract_input(event)

        # 1) Upload to VPS
        upload_id = vps.upload(image_bytes, filename=maybe_name or "upload.jpg")

        # 2) Poll query until done / failed / timeout
        deadline = time.time() + POLL_TIMEOUT_SEC
        last_status = None
        while time.time() < deadline:
            status, filename, message = vps.query(upload_id)

            if status == "done" and filename:
                # 3) Build public URL for client
                output_url = vps.download_url(filename)
                return {
                    "status": "succeeded",
                    "id": upload_id,
                    "output_url": output_url,
                }

            if status in {"failed", "error"}:
                raise VPSJobError(f"VPS reported failure: {message or 'unknown error'}")

            last_status = status
            time.sleep(POLL_INTERVAL_SEC)

        # timeout
        raise TimeoutError(f"Timed out waiting for VPS job (last_status={last_status}).")

    except VPSJobError as e:
        return {"status": "failed", "error": str(e)}
    except requests.HTTPError as e:
        return {"status": "failed", "error": f"HTTP error: {e.response.status_code} {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# Runpod boot
runpod.serverless.start({"handler": handler})
