# handler.py
import base64
import os
import time
from typing import Dict, Any, Optional

import requests
import runpod

# -------- Config (env) --------
DEFAULT_VPS_BASE = os.getenv("VPS_BASE", "https://anon.donkeybee.com")
DEFAULT_VPS_TOKEN = os.getenv("VPS_TOKEN", "dev-local-secret-change-me")

# Network tuning
CONNECT_TIMEOUT = 10        # seconds to connect
READ_TIMEOUT = 180          # seconds to read (VPS may take time to cloak)
TOTAL_POLL_SECONDS = 600    # max overall poll time (10 minutes)
POLL_INTERVAL = 1.2         # seconds between polls
RETRY_COUNT = 3
RETRY_BACKOFF = 1.5         # multiplier


def _request_with_retries(method: str, url: str, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            return requests.request(
                method,
                url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                **kwargs
            )
        except Exception as e:
            last_exc = e
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF ** attempt)
    raise last_exc


def _download_bytes_from_url(url: str) -> bytes:
    r = _request_with_retries("GET", url, stream=True)
    r.raise_for_status()
    return r.content


def _upload_to_vps(img_bytes: bytes, vps_base: str, vps_token: str) -> str:
    files = {"file": ("image", img_bytes, "application/octet-stream")}
    headers = {"X-Auth-Token": vps_token}
    r = _request_with_retries("POST", f"{vps_base}/Upload", files=files, headers=headers)
    # The API returns raw 32-char id as text/plain
    r.raise_for_status()
    image_id = r.text.strip()
    if len(image_id) != 32 or not all(c in "0123456789abcdef" for c in image_id.lower()):
        raise RuntimeError(f"Unexpected IMAGE_ID format: {image_id!r}")
    return image_id


def _poll_ready(vps_base: str, vps_token: str, image_id: str) -> None:
    headers = {"X-Auth-Token": vps_token}
    deadline = time.time() + TOTAL_POLL_SECONDS
    while True:
        r = _request_with_retries("GET", f"{vps_base}/query/{image_id}", headers=headers)
        r.raise_for_status()
        status = r.text.strip().upper()  # READY, PENDING, PROCESSING, etc.
        if status == "READY":
            return
        if time.time() > deadline:
            raise TimeoutError(f"Polling exceeded {TOTAL_POLL_SECONDS}s; last status={status}")
        time.sleep(POLL_INTERVAL)


def _download_result(vps_base: str, vps_token: str, image_id: str) -> bytes:
    headers = {"X-Auth-Token": vps_token}
    r = _request_with_retries("GET", f"{vps_base}/download/{image_id}", headers=headers, stream=True)
    r.raise_for_status()
    return r.content


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input JSON supports:
      {
        "image_url": "...",           # OR
        "image_b64": "...",
        "vps_base": "https://anon.donkeybee.com",   # optional override
        "vps_token": "dev-local-secret-change-me"   # optional override
      }

    Output JSON:
      {
        "status": "COMPLETED" | "FAILED",
        "image_b64": "<base64 string>"   # on success
      }
    """
    try:
        inp = event.get("input") or {}
        vps_base = (inp.get("vps_base") or DEFAULT_VPS_BASE).rstrip("/")
        vps_token = inp.get("vps_token") or DEFAULT_VPS_TOKEN

        # 1) get bytes
        if "image_b64" in inp and inp["image_b64"]:
            try:
                # accept data URLs or plain base64
                b64 = inp["image_b64"]
                if b64.startswith("data:"):
                    b64 = b64.split(",", 1)[1]
                img_bytes = base64.b64decode(b64)
            except Exception as e:
                return {"status": "FAILED", "error": f"Invalid image_b64: {e}"}
        elif "image_url" in inp and inp["image_url"]:
            try:
                img_bytes = _download_bytes_from_url(inp["image_url"])
            except Exception as e:
                return {"status": "FAILED", "error": f"HTTP error: {e}"}
        else:
            return {"status": "FAILED", "error": "Provide 'image_url' or 'image_b64'."}

        # 2) upload -> get IMAGE_ID
        try:
            image_id = _upload_to_vps(img_bytes, vps_base, vps_token)
        except Exception as e:
            return {"status": "FAILED", "error": f"Upload failed: {e}"}

        # 3) poll until READY
        try:
            _poll_ready(vps_base, vps_token, image_id)
        except Exception as e:
            return {"status": "FAILED", "error": f"Polling failed: {e}", "image_id": image_id}

        # 4) download result
        try:
            result_bytes = _download_result(vps_base, vps_token, image_id)
        except Exception as e:
            return {"status": "FAILED", "error": f"Download failed: {e}", "image_id": image_id}

        # 5) return base64
        out_b64 = base64.b64encode(result_bytes).decode("utf-8")
        return {"status": "COMPLETED", "image_b64": out_b64, "image_id": image_id}

    except Exception as e:
        return {"status": "FAILED", "error": f"Unhandled: {e}"}


runpod.serverless.start({"handler": handler})
