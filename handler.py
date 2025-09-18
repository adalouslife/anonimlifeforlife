import os, io, base64, time, typing, requests
import runpod

# ---------- CONFIG (from RunPod Endpoint Env Vars) ----------
VPS_BASE   = os.getenv("VPS_BASE")                 # e.g. https://b554b03f8e10.ngrok-free.app
AUTH_TOKEN = os.getenv("AUTH_TOKEN")               # e.g. dev-local-secret-change-me

# timeouts (seconds)
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "10"))
READ_TIMEOUT    = float(os.getenv("READ_TIMEOUT", "120"))
REQ_TIMEOUT     = (CONNECT_TIMEOUT, READ_TIMEOUT)

# polling config
POLL_INTERVAL_S  = float(os.getenv("POLL_INTERVAL_S", "0.7"))
POLL_MAX_SECONDS = float(os.getenv("POLL_MAX_SECONDS", "60"))

# hard caps to avoid abuse
MAX_IMAGE_B64_BYTES = int(os.getenv("MAX_IMAGE_B64_BYTES", str(15 * 1024 * 1024)))  # 15MB base64-encoded
OUTPUT_AS_DATA_URI  = os.getenv("OUTPUT_AS_DATA_URI", "false").lower() == "true"    # return data URI if you want

# ------------------------------------------------------------

def _fail(message: str, http_status: int = 500):
    return {"status": "FAILED", "error": message, "http_status": http_status}

def _require_env():
    if not VPS_BASE or not AUTH_TOKEN:
        raise RuntimeError("Missing VPS_BASE or AUTH_TOKEN in environment.")

def _decode_input_b64(img_b64: str) -> bytes:
    # Accept raw base64 or data URI
    if img_b64.startswith("data:"):
        try:
            img_b64 = img_b64.split(",", 1)[1]
        except Exception:
            raise ValueError("Malformed data URI.")
    # size guard
    if len(img_b64) > MAX_IMAGE_B64_BYTES:
        raise ValueError("Input base64 payload too large.")
    try:
        return base64.b64decode(img_b64, validate=True)
    except Exception:
        raise ValueError("Invalid base64 image data.")

def _download_url(url: str) -> bytes:
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.content

def _upload_bytes_to_vps(session: requests.Session, img_bytes: bytes) -> str:
    files = {"file": ("image.jpg", img_bytes, "image/jpeg")}
    headers = {"X-Auth-Token": AUTH_TOKEN}
    r = session.post(f"{VPS_BASE}/Upload", files=files, headers=headers, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.text.strip()  # image_id

def _poll_done(session: requests.Session, image_id: str) -> bool:
    headers = {"X-Auth-Token": AUTH_TOKEN}
    deadline = time.time() + POLL_MAX_SECONDS
    while time.time() < deadline:
        r = session.get(f"{VPS_BASE}/query/{image_id}", headers=headers, timeout=REQ_TIMEOUT)
        # Your FastAPI returns {"done": true/false, "id": "..."} — treat non-200 as retryable
        if r.status_code == 200:
            js = r.json()
            if js.get("done") is True:
                return True
        time.sleep(POLL_INTERVAL_S)
    return False

def _download_result(session: requests.Session, image_id: str) -> bytes:
    headers = {"X-Auth-Token": AUTH_TOKEN}
    r = session.get(f"{VPS_BASE}/download/{image_id}", headers=headers, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.content

def handler(job: dict):
    """
    INPUT (from your platform):
      {
        "image_b64": "<base64 or data URI>",     # preferred
        # OR
        "image_url": "https://..."
      }

    OUTPUT:
      {
        "status": "COMPLETED",
        "output": { "image_b64": "<base64>", "mime": "image/png" }
      }
      or { "status":"FAILED", "error":"...", "http_status":502 }
    """
    try:
        _require_env()
    except Exception as e:
        return _fail(str(e), 500)

    data = (job or {}).get("input") or {}
    img_bytes: typing.Optional[bytes] = None

    try:
        if "image_b64" in data and data["image_b64"]:
            img_bytes = _decode_input_b64(data["image_b64"])
        elif "image_url" in data and data["image_url"]:
            img_bytes = _download_url(data["image_url"])
        else:
            return _fail("Provide 'image_b64' (preferred) or 'image_url' in input.", 400)
    except ValueError as ve:
        return _fail(f"Bad image input: {ve}", 400)
    except requests.RequestException as re:
        return _fail(f"Failed to fetch image_url: {re}", 502)

    try:
        with requests.Session() as s:
            s.headers.update({"User-Agent": "runpod-fawkes-proxy/1.0"})

            # 1) Upload to your local Fawkes (through ngrok)
            image_id = _upload_bytes_to_vps(s, img_bytes)

            # 2) Poll until done
            if not _poll_done(s, image_id):
                return _fail("Upstream processing timed out.", 504)

            # 3) Download processed image
            out_bytes = _download_result(s, image_id)

        out_b64 = base64.b64encode(out_bytes).decode("utf-8")
        mime = "image/png"  # your API returns PNG; change if needed

        if OUTPUT_AS_DATA_URI:
            out_b64 = f"data:{mime};base64,{out_b64}"

        return {"status": "COMPLETED", "output": {"image_b64": out_b64, "mime": mime}}

    except requests.HTTPError as he:
        # Map common upstream errors cleanly
        status = he.response.status_code if he.response is not None else 502
        body = he.response.text if he.response is not None else str(he)
        return _fail(f"Upstream HTTP error {status}: {body}", status if 400 <= status < 600 else 502)
    except requests.Timeout:
        return _fail("Upstream timeout contacting VPS_BASE.", 504)
    except requests.RequestException as re:
        return _fail(f"Network error contacting VPS_BASE: {re}", 502)
    except Exception as e:
        return _fail(f"Unhandled error: {repr(e)}", 500)

# Keep the worker alive for RunPod serverless
runpod.serverless.start({"handler": handler})
