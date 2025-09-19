import base64, os, time, requests, runpod
from typing import Any, Dict, Optional, Tuple
from vps_client import VPSClient, VPSJobError

VPS_BASE_URL = os.environ.get("VPS_BASE_URL", "https://anon.example.com")
VPS_API_KEY  = os.environ.get("VPS_API_KEY", "")
POLL_INTERVAL_SEC = float(os.environ.get("POLL_INTERVAL_SEC", "1.5"))
POLL_TIMEOUT_SEC  = float(os.environ.get("POLL_TIMEOUT_SEC", "300"))

vps = VPSClient(VPS_BASE_URL, VPS_API_KEY, user_agent="runpod-bridge/1.0")

def _download_url_to_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def _decode_base64_image(b64: str) -> bytes:
    return base64.b64decode(b64, validate=True)

def _extract_input(event: Dict[str, Any]) -> Tuple[bytes, Optional[str]]:
    inp = event.get("input") or {}
    url = inp.get("image_url")
    b64 = inp.get("image_b64")
    if url:
        return _download_url_to_bytes(url), os.path.basename(url.split("?")[0]) or None
    if b64:
        return _decode_base64_image(b64), None
    raise ValueError("Provide 'image_url' or 'image_b64' in input.")

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        image_bytes, maybe_name = _extract_input(event)
        upload_id = vps.upload(image_bytes, filename=maybe_name or "upload.jpg")

        deadline = time.time() + POLL_TIMEOUT_SEC
        last_status = None
        while time.time() < deadline:
            status, filename, message = vps.query(upload_id)
            if status == "done" and filename:
                return {
                    "status": "succeeded",
                    "id": upload_id,
                    "output_url": vps.download_url(filename),
                }
            if status in {"failed", "error"}:
                raise VPSJobError(message or "VPS reported failure")
            last_status = status
            time.sleep(POLL_INTERVAL_SEC)

        raise TimeoutError(f"Timed out (last_status={last_status})")

    except VPSJobError as e:
        return {"status": "failed", "error": str(e)}
    except requests.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

runpod.serverless.start({"handler": handler})
