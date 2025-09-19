import base64
import os
import re
import time
from typing import Optional

import requests
import runpod

# -------------------------
# Config
# -------------------------
VPS_BASE = os.environ.get("VPS_BASE", "").rstrip("/")
VPS_TOKEN = os.environ.get("VPS_TOKEN", "")
HTTP_TIMEOUT_S = int(os.environ.get("HTTP_TIMEOUT_S", "300"))  # total budget
POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", "1.2"))
UPLOAD_TIMEOUT = int(os.environ.get("UPLOAD_TIMEOUT", "60"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "60"))
QUERY_TIMEOUT = int(os.environ.get("QUERY_TIMEOUT", "15"))
RUNPOD_TEST = os.environ.get("RUNPOD_TEST", "") == "1"

# Simple 1x1 PNG (black) for RUNPOD_TEST sanity
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAn8B9m3zUSwAAAAASUVORK5CYII="
)

UA_HEADERS = {
    # Many CDNs block default python UA; use a harmless browser UA
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

session = requests.Session()


def _require_env():
    if RUNPOD_TEST:
        return
    if not VPS_BASE:
        raise RuntimeError("VPS_BASE is not set.")
    if not VPS_TOKEN:
        raise RuntimeError("VPS_TOKEN is not set.")


def _ext_from_content_type(ct: str) -> str:
    if not ct:
        return ".bin"
    ct = ct.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(ct, ".bin")


def fetch_bytes_from_url(url: str, per_request_timeout: int = 30) -> bytes:
    # HEAD optional; some CDNs forbid it—go straight to GET with a sane UA
    resp = session.get(url, headers=UA_HEADERS, timeout=per_request_timeout, stream=True)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP error: {resp.status_code} for url: {url}")
    # respect reasonable max size? (optional)
    content = resp.content
    if not content:
        raise RuntimeError("Downloaded empty body.")
    return content


def upload_bytes(img_bytes: bytes, filename: str = "image.jpg") -> str:
    headers = {"X-Auth-Token": VPS_TOKEN}
    files = {"file": (filename, img_bytes, "application/octet-stream")}
    r = session.post(
        f"{VPS_BASE}/Upload",
        headers=headers,
        files=files,
        timeout=UPLOAD_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Upload failed: {r.status_code} {r.text}")
    image_id = r.text.strip()
    if not re.fullmatch(r"[0-9a-f]{32}", image_id):
        raise RuntimeError(f"Unexpected Upload response: {image_id}")
    return image_id


def poll_ready(image_id: str, deadline_ts: float) -> str:
    headers = {"X-Auth-Token": VPS_TOKEN}
    url = f"{VPS_BASE}/query/{image_id}"
    while time.time() < deadline_ts:
        r = session.get(url, headers=headers, timeout=QUERY_TIMEOUT)
        if r.status_code == 404:
            time.sleep(POLL_INTERVAL_S)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Query failed: {r.status_code} {r.text}")
        status = r.text.strip().upper()
        if status in ("READY", "DONE"):
            return status
        if status in ("ERROR", "FAILED"):
            raise RuntimeError("Processing failed upstream.")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError("Timed out waiting for READY.")


def download_result(image_id: str) -> bytes:
    headers = {"X-Auth-Token": VPS_TOKEN}
    url = f"{VPS_BASE}/download/{image_id}"
    r = session.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Download failed: {r.status_code} {r.text}")
    return r.content


def to_b64(data: bytes, prefix: Optional[str] = None) -> str:
    b64 = base64.b64encode(data).decode("utf-8")
    if prefix:
        return f"{prefix},{b64}"
    return b64


def _tiny_ok():
    # For RUNPOD_TEST=1 fast “Testing” phase
    return {"image_b64": _TINY_PNG_B64, "meta": {"test": True}}


def handler(job):
    """
    Expected inputs:
      {
        "image_url": "https://…",        # OR
        "image_b64": "data:image/png;base64,...." | "iVBORw0…",
        "timeout_s": 300                 # optional override
      }
    Output:
      { "image_b64": "<base64>", "image_id": "...", "meta": {...} }
    """
    _require_env()

    ipt = job.get("input", {}) or {}
    timeout_s = int(ipt.get("timeout_s", HTTP_TIMEOUT_S))

    if RUNPOD_TEST:
        return _tiny_ok()

    img_bytes = None
    filename = "image.jpg"

    if "image_url" in ipt and ipt["image_url"]:
        url = ipt["image_url"]
        img_bytes = fetch_bytes_from_url(url, per_request_timeout=min(60, timeout_s))
        # attempt to guess extension from HEAD or URL (best-effort)
        try:
            head = session.head(url, headers=UA_HEADERS, timeout=10, allow_redirects=True)
            ext = _ext_from_content_type(head.headers.get("content-type", ""))
        except Exception:
            # fallback to URL suffix
            m = re.search(r"\.(png|jpg|jpeg|webp|gif)(\?|$)", url, re.I)
            ext = f".{m.group(1).lower()}" if m else ".jpg"
        filename = f"image{ext}"
    elif "image_b64" in ipt and ipt["image_b64"]:
        b64 = ipt["image_b64"]
        if "," in b64:
            # strip data URI prefix if present
            b64 = b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise RuntimeError(f"Invalid base64: {e}")
        filename = "image.png"
    else:
        raise RuntimeError("Provide either 'image_url' or 'image_b64'")

    start_ts = time.time()
    deadline_ts = start_ts + timeout_s

    # 1) Upload to VPS/Fawkes
    image_id = upload_bytes(img_bytes, filename=filename)

    # 2) Poll until READY (or timeout)
    poll_ready(image_id, deadline_ts)

    # 3) Download cloaked image
    result_bytes = download_result(image_id)

    # 4) Return base64 (no data: prefix to keep payload small/clean)
    return {
        "image_b64": to_b64(result_bytes),
        "image_id": image_id,
        "meta": {
            "elapsed_s": round(time.time() - start_ts, 3),
            "vps_base": VPS_BASE,
        },
    }


# Entrypoint for RunPod
runpod.serverless.start(
    {
        "handler": handler,
        # request/response validation can be added later if you want
    }
)
