import os
import time
from typing import Optional

import requests

VPS_BASE = os.environ.get("VPS_BASE", "https://anon.donkeybee.com")
# cloak endpoint is intentionally unauthenticated in your VPS adapter
CLOAK_URL = f"{VPS_BASE}/api/fawkes/cloak"

# Be generous: Fawkes takes ~2–3 min typically; allow up to 12 min to be safe.
DEFAULT_TOTAL_TIMEOUT_SEC = int(os.environ.get("VPS_TOTAL_TIMEOUT_SEC", "720"))

# a browser-y UA to avoid 403s from some CDNs
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/122.0.0.0 Safari/537.36")

class VPSClientError(Exception):
    pass

def cloak_sync(image_url: Optional[str] = None,
               image_b64: Optional[str] = None,
               total_timeout_sec: int = DEFAULT_TOTAL_TIMEOUT_SEC) -> str:
    """
    Calls your VPS /api/fawkes/cloak synchronously.
    Returns the output_url (download URL) only after VPS finished Fawkes.
    Raises VPSClientError on any failure.
    """
    if not image_url and not image_b64:
        raise VPSClientError("Provide image_url or image_b64.")

    payload = {}
    if image_url:
        payload["image_url"] = image_url
    if image_b64:
        payload["image_b64"] = image_b64

    # Use a single POST; let the VPS block until ready and return output_url.
    # requests timeout applies per I/O operation; we use a big overall window.
    deadline = time.time() + total_timeout_sec
    last_err = None

    while time.time() < deadline:
        try:
            # connect timeout 30s, read timeout close to remaining budget
            rt = max(30, int(deadline - time.time()))
            resp = requests.post(
                CLOAK_URL,
                json=payload,
                headers={"User-Agent": _UA, "Content-Type": "application/json"},
                timeout=(30, rt)  # (connect, read)
            )
            if resp.status_code != 200:
                raise VPSClientError(f"CLOAK {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            output_url = data.get("output_url")
            if not output_url:
                raise VPSClientError(f"CLOAK returned 200 without output_url: {data}")
            return output_url
        except requests.Timeout as e:
            last_err = e
            # try once more until deadline
        except Exception as e:
            # Non-timeout error: don’t loop forever, but give one brief retry in case of transient
            last_err = e
            time.sleep(2)
            break

    raise VPSClientError(f"Timed out or failed contacting VPS cloak: {last_err}")
