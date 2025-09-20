# vps_client.py
import os
import requests

# Read timeout from env; default to 660s (~11 minutes)
_DEFAULT_TIMEOUT = int(os.getenv("VPS_TIMEOUT_SECONDS", "660"))

class VPSClientError(Exception):
    pass

def process_via_vps(base_url: str,
                    endpoint_path: str,
                    image_url: str,
                    timeout: int = _DEFAULT_TIMEOUT):
    """
    Calls the VPS adapter endpoint synchronously:
      POST {base_url}{endpoint_path}
      JSON: {"image_url": "<url>"}

    Expects 200 JSON like: {"output_url": "..."}
    Returns that JSON as dict.
    Raises VPSClientError on HTTP errors.
    """
    url = f"{base_url.rstrip('/')}{endpoint_path}"
    resp = None
    try:
        resp = requests.post(url, json={"image_url": image_url}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        body = ""
        try:
            body = resp.text[:300] if resp is not None else ""
        except Exception:
            pass
        raise VPSClientError(f"VPS call failed: {e} :: {body}") from e

    try:
        return resp.json()
    except ValueError:
        # Fallback if VPS ever returned non-JSON
        return {"output_url": image_url}
