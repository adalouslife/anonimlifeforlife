import os
import time
import json
import runpod
from vps_client import VpsClient, VpsClientError

# ---- Configuration via ENV ----
VPS_BASE_URL = os.getenv("VPS_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
VPS_START_PATH = os.getenv("VPS_START_PATH", "/api/anonymize")
VPS_STATUS_PATH = os.getenv("VPS_STATUS_PATH", "/api/anonymize/{job_id}")

REQ_TIMEOUT = int(os.getenv("VPS_REQUEST_TIMEOUT_SECONDS", "30"))
POLL_INTERVAL = float(os.getenv("VPS_POLL_INTERVAL_SECONDS", "2"))
POLL_TIMEOUT = int(os.getenv("VPS_POLL_TIMEOUT_SECONDS", "600"))

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

client = VpsClient(
    base_url=VPS_BASE_URL,
    start_path=VPS_START_PATH,
    status_path_template=VPS_STATUS_PATH,
    request_timeout=REQ_TIMEOUT,
)

def _fail(msg: str):
    return {"status": "failed", "error": msg}

def _ok(url: str, meta: dict | None = None):
    out = {"status": "completed", "output_url": url}
    if meta:
        out["meta"] = meta
    return out

def handler(event):
    """
    Expected input:
    {
      "image_url": "https://example.com/photo.jpg",
      "mode": "low|mid|high|... (optional, passthrough)",
      "options": {...} (optional, passthrough),
      "ping": true (optional health check)
    }
    """
    try:
        data = event.get("input", {}) if isinstance(event, dict) else {}
        if data.get("ping"):
            return {"status": "ok", "message": "pong"}

        image_url = data.get("image_url")
        if not image_url:
            return _fail("Missing required 'image_url'.")

        mode = data.get("mode")
        options = data.get("options", {})

        # Hub tests can run without touching the VPS
        if DRY_RUN:
            return _ok(image_url, meta={"dry_run": True})

        # Kick off anonymization on VPS
        start_resp = client.start_job(image_url=image_url, mode=mode, options=options)

        # 1) If VPS returns output immediately (sync), pass it through
        if isinstance(start_resp, dict) and start_resp.get("output_url"):
            return _ok(start_resp["output_url"], meta={"sync": True})

        # 2) Otherwise expect a job_id and poll
        job_id = (start_resp or {}).get("job_id")
        if not job_id:
            # Try to read status if the VPS already built one
            # or return a helpful error
            return _fail("VPS did not return 'job_id' or 'output_url'.")

        t0 = time.time()
        while True:
            status = client.get_status(job_id)
            state = (status or {}).get("status", "").lower()

            if state in ("completed", "succeeded", "success"):
                out_url = status.get("output_url") or status.get("result_url") or status.get("url")
                if not out_url:
                    return _fail("VPS job completed but no 'output_url' in response.")
                return _ok(out_url, meta={"job_id": job_id})

            if state in ("failed", "error"):
                return _fail(f"VPS job failed for job_id={job_id}: {json.dumps(status)}")

            if time.time() - t0 > POLL_TIMEOUT:
                return _fail(f"Timed out waiting for VPS job_id={job_id} after {POLL_TIMEOUT}s.")

            time.sleep(POLL_INTERVAL)

    except VpsClientError as e:
        return _fail(f"VPS error: {e}")
    except Exception as e:
        return _fail(f"Unhandled error: {e}")

# Start RunPod serverless worker
runpod.serverless.start({"handler": handler})
