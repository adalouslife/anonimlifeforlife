import os
import time
import requests
import runpod


# ---------- ENV ----------
AUTH_TOKEN         = os.getenv("AUTH_TOKEN", "")
VPS_BASE_URL       = os.getenv("VPS_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
VPS_ENDPOINT_PATH  = os.getenv("VPS_ENDPOINT_PATH", "/api/fawkes/cloak")
VPS_TIMEOUT_SECONDS= int(os.getenv("VPS_TIMEOUT_SECONDS", "900"))     # POST cloak timeout
POLL_INTERVAL_SEC  = int(os.getenv("VPS_POLL_INTERVAL", "5"))         # interval between HEAD checks
MAX_WAIT_SEC       = int(os.getenv("VPS_MAX_WAIT", "900"))            # total wait for result

# If you’re using a proxy, set standard envs HTTP_PROXY / HTTPS_PROXY at the endpoint level.
# (We intentionally do NOT override requests' proxies here to avoid the rp_ping NoneType bug.)


def _headers_with_auth():
    h = {}
    if AUTH_TOKEN:
        h["X-Auth-Token"] = AUTH_TOKEN
    return h


def _cloak(image_url: str) -> str:
    """Call VPS adapter to start/perform Fawkes and return output_url from VPS."""
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
    """Poll the download URL until it returns HTTP 200."""
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
    - If input has { "ping": "..." } -> return { "ok": true } (for tests).
    - If input has { "image_url": "..." } -> run real flow (VPS cloak + poll) and
      only return COMPLETED when the file is actually ready.
    """
    i = (event or {}).get("input", {}) or {}

    # Minimal test path (so RunPod 'Testing' phase passes quickly)
    if "ping" in i:
        return {"ok": True}

    image_url = i.get("image_url")
    if not image_url:
        return {"status": "failed", "error": "missing 'image_url' in input"}

    try:
        output_url = _cloak(image_url)
    except Exception as e:
        return {"status": "failed", "error": f"cloak call failed: {e}"}

    # Poll until the file is truly downloadable (prevents 'COMPLETED' with empty result)
    ready = _wait_until_ready(output_url)
    if not ready:
        return {"status": "failed", "error": "timeout waiting for output", "output_url": output_url}

    return {"status": "completed", "output_url": output_url}


# Start the RunPod serverless loop
runpod.serverless.start({"handler": handler})
