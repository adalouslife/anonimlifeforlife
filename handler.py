# handler.py
from __future__ import annotations

import base64
import time
import requests
import runpod


# ---------- Defaults (can be overridden per request) ----------
DEFAULT_VPS_BASE   = "http://127.0.0.1:8000"          # will be overridden by input.vps_base
DEFAULT_VPS_TOKEN  = "dev-local-secret-change-me"     # will be overridden by input.vps_token
DEFAULT_TIMEOUT_S  = 300.0                            # total processing timeout window
DEFAULT_POLL_EVERY = 2.0                              # seconds between /query polls
DEFAULT_REQ_CONNECT = 20.0                            # requests connect timeout
DEFAULT_REQ_READ    = 240.0                           # requests read timeout
# --------------------------------------------------------------


def _upload_bytes(vps_base: str, vps_token: str, img_bytes: bytes,
                  req_connect: float, req_read: float) -> str:
    """POST /Upload -> returns image_id (plain text)."""
    url = f"{vps_base.rstrip('/')}/Upload"
    headers = {"X-Auth-Token": vps_token}
    files = {"file": ("upload.jpg", img_bytes, "application/octet-stream")}
    r = requests.post(url, headers=headers, files=files,
                      timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.text.strip()


def _poll_ready(vps_base: str, vps_token: str, image_id: str,
                req_connect: float, req_read: float) -> bool:
    """GET /query/{id} -> 'READY' when done."""
    url = f"{vps_base.rstrip('/')}/query/{image_id}"
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(url, headers=headers, timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.text.strip().upper() == "READY"


def _download_image(vps_base: str, vps_token: str, image_id: str,
                    req_connect: float, req_read: float) -> bytes:
    """GET /download/{id} -> image bytes."""
    url = f"{vps_base.rstrip('/')}/download/{image_id}"
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(url, headers=headers, timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.content


def handler(job: dict) -> dict:
    """
    Input shape examples
    --------------------
    Minimal (URL):
      { "input": { "image_url": "https://..." } }

    With overrides:
      {
        "input": {
          "image_url": "https://...",
          "vps_base": "https://YOUR.ngrok-free.app",
          "vps_token": "dev-local-secret-change-me",
          "timeout_s": 300,
          "poll_every": 2.0,
          "request_timeout_connect": 20,
          "request_timeout_read": 240
        }
      }

    Base64 mode:
      {
        "input": {
          "image_b64": "<base64-encoded-image>",
          "vps_base": "...",
          "vps_token": "..."
        }
      }

    Fast hub test (no network):
      { "input": { "ping": true, "echo": "hub-test" } }
    """
    data = (job or {}).get("input") or {}

    # ---------- FAST TEST PATH for Runpod Hub ----------
    # If tests.json sends {"ping": true}, we immediately return.
    if data.get("ping") is True:
        return {"ok": True, "mode": "ping", "echo": data.get("echo")}
    # ---------------------------------------------------

    # Read overrides (or fall back to defaults)
    vps_base   = data.get("vps_base", DEFAULT_VPS_BASE)
    vps_token  = data.get("vps_token", DEFAULT_VPS_TOKEN)
    timeout_s  = float(data.get("timeout_s", DEFAULT_TIMEOUT_S))
    poll_every = float(data.get("poll_every", DEFAULT_POLL_EVERY))
    req_connect = float(data.get("request_timeout_connect", DEFAULT_REQ_CONNECT))
    req_read    = float(data.get("request_timeout_read", DEFAULT_REQ_READ))

    # ---- Load input image (URL or base64) ----
    if "image_b64" in data:
        try:
            img_bytes = base64.b64decode(data["image_b64"], validate=True)
        except Exception as e:
            return {"error": f"Invalid base64: {e}"}
    elif "image_url" in data:
        try:
            r = requests.get(data["image_url"], timeout=(req_connect, req_read))
            r.raise_for_status()
            img_bytes = r.content
        except Exception as e:
            return {"error": f"Failed to fetch image_url: {e}"}
    else:
        return {"error": "Provide image_url or image_b64 in input."}

    # ---- Upload to your Fawkes API ----
    try:
        image_id = _upload_bytes(vps_base, vps_token, img_bytes, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Upload timed out: {e}"}
    except Exception as e:
        return {"error": f"Upload failed: {e}"}

    # ---- Poll until READY or timeout ----
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if _poll_ready(vps_base, vps_token, image_id, req_connect, req_read):
                break
        except Exception:
            # transient errors while the job is processing; keep polling
            pass
        time.sleep(poll_every)
    else:
        return {"error": "Processing timeout", "image_id": image_id, "timeout_s": timeout_s}

    # ---- Download result ----
    try:
        out_bytes = _download_image(vps_base, vps_token, image_id, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Download timed out: {e}", "image_id": image_id}
    except Exception as e:
        return {"error": f"Download failed: {e}", "image_id": image_id}

    # Return base64 so caller can save it
    return {
        "image_id": image_id,
        "cloaked_b64": base64.b64encode(out_bytes).decode("utf-8"),
        "note": "Base64-encoded image (JPEG/PNG)."
    }


# Start the Runpod serverless handler
runpod.serverless.start({"handler": handler})
