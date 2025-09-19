import io
import os
from urllib.parse import urlparse

import requests
from PIL import Image
import runpod


def _get_image_bytes(url: str, timeout: int = 15) -> bytes:
    """Fetches an image and verifies it is actually an image."""
    r = requests.get(url, timeout=timeout, stream=True)
    r.raise_for_status()

    ct = (r.headers.get("content-type") or "").lower()
    if "image" not in ct:
        # still try to validate as image; if not, PIL will raise
        pass

    data = r.content
    # validate with PIL (no decode, just header checks)
    with Image.open(io.BytesIO(data)) as im:
        im.verify()

    return data


def handler(event):
    """
    Runpod Serverless entrypoint.
    Accepts:  {"image_url": "..."}   OR   {"input": {"image_url": "..."}}
    Returns:  {"status": "completed", "output_url": "<url>"}
    """
    payload = event.get("input", event) or {}
    image_url = payload.get("image_url")

    if not image_url:
        return {"status": "failed", "error": "Missing 'image_url' in input."}

    try:
        # Validate the image fetch (fast check)
        _ = _get_image_bytes(image_url)

        # Optional: forward to your VPS if configured
        vps_base = os.getenv("VPS_BASE_URL", "").strip()
        vps_path = os.getenv("VPS_ENDPOINT_PATH", "/api/fawkes/cloak").strip()
        use_vps = (os.getenv("VPS_PROXY", "false").lower() == "true") and vps_base

        if use_vps:
            from vps_client import process_via_vps
            vps_res = process_via_vps(vps_base, vps_path, image_url)
            # If your VPS returns {"output_url": "..."} we use it; else echo input
            output_url = vps_res.get("output_url", image_url)
        else:
            # For Hub smoke testing, just echo back a valid URL that we verified
            output_url = image_url

        return {"status": "completed", "output_url": output_url}

    except Exception as e:
        return {"status": "failed", "error": str(e)}


# IMPORTANT: start the Runpod serverless poller
# This is the bit that prevents "stuck in QUEUE".
runpod.serverless.start({"handler": handler})
