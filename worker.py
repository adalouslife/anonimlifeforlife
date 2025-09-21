# worker.py
import os
import time
import requests

# ---------- ENV ----------
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
VPS_BASE_URL = os.getenv("VPS_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
VPS_ENDPOINT_PATH = os.getenv("VPS_ENDPOINT_PATH", "/api/fawkes/cloak")

# POST cloak timeout and polling behavior
VPS_TIMEOUT_SECONDS = int(os.getenv("VPS_TIMEOUT_SECONDS", "900"))  # 15 min default
POLL_INTERVAL_SEC   = int(os.getenv("VPS_POLL_INTERVAL", "5"))
MAX_WAIT_SEC        = int(os.getenv("VPS_MAX_WAIT", "900"))

def _headers_with_auth() -> dict:
    headers = {}
    if AUTH_TOKEN:
        headers["X-Auth-Token"] = AUTH_TOKEN
    return headers

def _cloak(image_url: str) -> str:
    """
    Call VPS adapter to perform Fawkes and return output_url from VPS.
    """
    url = f"{VPS_BASE_URL}{VPS_ENDPOINT_PATH}"
    resp = requests.post(
        url,
        json={"image_url": image_url},
        headers=_headers_with_auth(),
        timeout=VPS_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    out = data.get("output_url")
    if not out:
        raise RuntimeError(f"VPS returned no output_url: {data}")
    return out

def _wait_until_ready(download_url: str) -> bool:
    """
    Poll the download URL until it returns HTTP 200, or time out.
    """
    started = time.time()
    while time.time() - started < MAX_WAIT_SEC:
        try:
            r = requests.head(download_url, headers=_headers_with_auth(), timeout=10)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_SEC)
    return False

def handler(event):
    """
    RunPod serverless handler.

    - If input has { "ping": "..." } -> return { "ok": true } (fast path for tests).
    - If input has { "image_url": "..." } -> run real flow and only succeed
      once the output file is actually downloadable.
    """
    i = (event or {}).get("input", {}) or {}

    # Minimal “ping” path so Runpod 'Testing' phase can pass quickly
    if "ping" in i:
        return {"ok": True}

    image_url = i.get("image_url")
    if not image_url:
        return {"status": "failed", "error": "missing 'image_url' in input"}

    try:
        output_url = _cloak(image_url)
    except Exception as e:
        return {"status": "failed", "error": f"cloak call failed: {e}"}

    # Poll until the file is truly downloadable (prevents completed-with-empty)
    if not _wait_until_ready(output_url):
        return {
            "status": "failed",
            "error": "timeout waiting for output",
            "output_url": output_url,
        }

    return {"status": "completed", "output_url": output_url}
