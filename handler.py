# handler.py
from __future__ import annotations
import base64, time, requests
import runpod

# Defaults (overridable per request)
DEFAULT_VPS_BASE   = "http://127.0.0.1:8000"
DEFAULT_VPS_TOKEN  = "dev-local-secret-change-me"
DEFAULT_TIMEOUT_S  = 300.0     # total processing timeout
DEFAULT_POLL_EVERY = 2.0
DEFAULT_REQ_CONNECT = 20.0     # connect timeout
DEFAULT_REQ_READ    = 240.0    # read timeout

def _upload_bytes(vps_base: str, vps_token: str, img_bytes: bytes,
                  req_connect: float, req_read: float) -> str:
    files = {"file": ("upload.jpg", img_bytes, "application/octet-stream")}
    headers = {"X-Auth-Token": vps_token}
    r = requests.post(f"{vps_base.rstrip('/')}/Upload",
                      files=files, headers=headers,
                      timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.text.strip()

def _poll_ready(vps_base: str, vps_token: str, image_id: str,
                req_connect: float, req_read: float) -> bool:
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(f"{vps_base.rstrip('/')}/query/{image_id}",
                     headers=headers, timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.text.strip().upper() == "READY"

def _download_image(vps_base: str, vps_token: str, image_id: str,
                    req_connect: float, req_read: float) -> bytes:
    headers = {"X-Auth-Token": vps_token}
    r = requests.get(f"{vps_base.rstrip('/')}/download/{image_id}",
                     headers=headers, timeout=(req_connect, req_read))
    r.raise_for_status()
    return r.content

def handler(job: dict) -> dict:
    """
    Input:
    {
      "input": {
        "image_url": "https://...",            // OR
        "image_b64": "<base64>",

        // optional overrides:
        "vps_base": "https://YOUR-NGROK.ngrok-free.app",
        "vps_token": "dev-local-secret-change-me",
        "timeout_s": 300,
        "poll_every": 2.0,
        "request_timeout_connect": 20,
        "request_timeout_read": 240
      }
    }
    """
    data = (job or {}).get("input") or {}
    vps_base  = data.get("vps_base", DEFAULT_VPS_BASE)
    vps_token = data.get("vps_token", DEFAULT_VPS_TOKEN)

    timeout_s   = float(data.get("timeout_s", DEFAULT_TIMEOUT_S))
    poll_every  = float(data.get("poll_every", DEFAULT_POLL_EVERY))
    req_connect = float(data.get("request_timeout_connect", DEFAULT_REQ_CONNECT))
    req_read    = float(data.get("request_timeout_read", DEFAULT_REQ_READ))

    # Load image
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
        return {"error": "Provide image_url or image_b64 in input"}

    # Upload
    try:
        image_id = _upload_bytes(vps_base, vps_token, img_bytes, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Upload timed out: {e}"}
    except Exception as e:
        return {"error": f"Upload failed: {e}"}

    # Poll
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if _poll_ready(vps_base, vps_token, image_id, req_connect, req_read):
                break
        except Exception:
            pass
        time.sleep(poll_every)
    else:
        return {"error": "Processing timeout", "image_id": image_id, "timeout_s": timeout_s}

    # Download
    try:
        out_bytes = _download_image(vps_base, vps_token, image_id, req_connect, req_read)
    except requests.Timeout as e:
        return {"error": f"Download timed out: {e}", "image_id": image_id}
    except Exception as e:
        return {"error": f"Download failed: {e}", "image_id": image_id}

    return {
        "image_id": image_id,
        "cloaked_b64": base64.b64encode(out_bytes).decode("utf-8"),
        "note": "Base64-encoded image (likely JPEG/PNG)."
    }

runpod.serverless.start({"handler": handler})
