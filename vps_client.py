# vps_client.py
import os
import requests

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
VPS_BASE_URL = os.getenv("VPS_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
VPS_ENDPOINT_PATH = os.getenv("VPS_ENDPOINT_PATH", "/api/fawkes/cloak")
VPS_TIMEOUT_SECONDS = int(os.getenv("VPS_TIMEOUT_SECONDS", "900"))

def _headers_with_auth():
    return {"X-Auth-Token": AUTH_TOKEN} if AUTH_TOKEN else {}

def cloak(image_url: str, timeout: int = VPS_TIMEOUT_SECONDS) -> dict:
    url = f"{VPS_BASE_URL}{VPS_ENDPOINT_PATH}"
    r = requests.post(
        url,
        json={"image_url": image_url},
        headers=_headers_with_auth(),
        timeout=timeout
    )
    r.raise_for_status()
    return r.json()
