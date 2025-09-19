import requests


def process_via_vps(base_url: str, endpoint_path: str, image_url: str, timeout: int = 120) -> dict:
    """
    Minimal, robust forwarder to your VPS.
    Expects the VPS endpoint to accept: POST JSON {"image_url": "..."}
    and to return a JSON with {"output_url": "..."} on success.
    """
    url = f"{base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"
    try:
        resp = requests.post(url, json={"image_url": image_url}, timeout=timeout)
        resp.raise_for_status()
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    except Exception as e:
        # Don't crash the worker; fall back gracefully in handler.py
        return {"status": "failed", "error": str(e)}
