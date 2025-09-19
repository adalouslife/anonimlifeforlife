import os
import time
import runpod
import requests
from urllib.parse import urlparse

# --- Minimal env ---
VPS_BASE_URL = os.getenv("VPS_BASE_URL", "").rstrip("/")  # e.g. https://anon.donkeybee.com
PUBLIC_PATH_PREFIX = os.getenv("PUBLIC_PATH_PREFIX", "/files").rstrip("/") or "/files"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))

if not VPS_BASE_URL:
    raise RuntimeError("VPS_BASE_URL is required (e.g. https://anon.donkeybee.com)")

def _is_http_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def _submit_job(image_url: str, **extra):
    # Adjust the endpoint path if your Candy routes are different.
    # Assumes your VPS exposes a job-creating endpoint.
    payload = {"image_url": image_url}
    payload.update({k: v for k, v in extra.items() if v is not None})
    r = requests.post(f"{VPS_BASE_URL}/api/fawkes/jobs", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def _poll_job(job_id: str, timeout_sec: int = REQUEST_TIMEOUT):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = requests.get(f"{VPS_BASE_URL}/api/fawkes/jobs/{job_id}", timeout=20)
        r.raise_for_status()
        data = r.json()
        status = (data.get("status") or "").lower()
        if status in ("completed", "failed", "error", "timeout"):
            return data
        time.sleep(1.8)
    return {"status": "timeout", "job_id": job_id}

def _to_public_url(vps_result: dict) -> str | None:
    """
    Normalize typical fields into a public URL:
    - absolute http(s) -> return as-is
    - '/files/abc.jpg' or 'files/abc.jpg' -> https://anon.donkeybee.com/files/abc.jpg
    - '/var/.../files/abc.jpg' -> map using PUBLIC_PATH_PREFIX -> https://anon.donkeybee.com/files/abc.jpg
    """
    candidates = [
        vps_result.get("output_url"),
        vps_result.get("url"),
        vps_result.get("result_url"),
        vps_result.get("output_path"),
        vps_result.get("path"),
        vps_result.get("result_path"),
        vps_result.get("file"),
        vps_result.get("filename"),
    ]

    files = vps_result.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                candidates.extend([
                    item.get("output_url"),
                    item.get("url"),
                    item.get("output_path"),
                    item.get("path"),
                ])
            elif isinstance(item, str):
                candidates.append(item)

    for raw in candidates:
        if not raw or not isinstance(raw, str):
            continue

        # already a public URL
        if _is_http_url(raw):
            return raw

        # relative web path e.g. "/files/x.jpg" or "files/x.jpg"
        if raw.startswith("/"):
            # starts with "/files..." -> join with base
            if raw.startswith(PUBLIC_PATH_PREFIX + "/"):
                return f"{VPS_BASE_URL}{raw}"
            # if it's some absolute FS path but contains ".../files/..."
            marker = PUBLIC_PATH_PREFIX if PUBLIC_PATH_PREFIX.startswith("/") else f"/{PUBLIC_PATH_PREFIX}"
            if marker in raw:
                # strip prefix before marker, produce "/files/..."
                tail = raw.split(marker, 1)[1].lstrip("/")
                return f"{VPS_BASE_URL}{marker}/{tail}"

        # bare "files/x.jpg"
        if raw.startswith("files/") or raw.startswith(PUBLIC_PATH_PREFIX.lstrip("/") + "/"):
            return f"{VPS_BASE_URL}/{raw}"

    return None

def handler(event):
    """
    Input:
      { "input": { "image_url": "https://..." , ...optional knobs... } }
    Output on success:
      { "status": "completed", "job_id": "...", "output_url": "https://anon.donkeybee.com/files/..." }
    """
    try:
        inp = (event or {}).get("input") or {}
        image_url = inp.get("image_url")
        if not image_url:
            return {"error": "image_url is required"}

        # Pass-thru optional flags if your VPS understands them (safe to omit)
        submit_extras = {
            "cloak_mode": inp.get("cloak_mode"),
            "strong": inp.get("strong"),
            "user_id": inp.get("user_id"),
            "request_id": event.get("id"),
        }

        job = _submit_job(image_url, **submit_extras)
        job_id = job.get("job_id") or job.get("id")
        if not job_id:
            return {"status": "failed", "error": "VPS did not return job_id", "details": job}

        result = _poll_job(job_id, REQUEST_TIMEOUT)
        status = (result.get("status") or "").lower()

        if status == "completed":
            url = _to_public_url(result)
            if not url:
                return {
                    "status": "failed",
                    "job_id": job_id,
                    "error": "VPS completed but did not include a public URL or mappable path",
                    "details": {k: result.get(k) for k in ("output_url","output_path","path","files")}
                }
            return {"status": "completed", "job_id": job_id, "output_url": url}

        return {"status": status or "failed", "job_id": job_id, "error": result.get("error"), "details": result}

    except requests.HTTPError as e:
        body = None
        code = None
        try:
            body, code = e.response.text, e.response.status_code
        except Exception:
            pass
        return {"status": "failed", "error": "HTTP error talking to VPS", "status_code": code, "body": body}

    except Exception as e:
        return {"status": "failed", "error": str(e)}

runpod.serverless.start({"handler": handler})

# rp_handler.py  — minimal shim so Runpod auto-discovers the worker
from handler import handler as _handler
import runpod

runpod.serverless.start({"handler": _handler})
