import os
# --- Hardening for runpod 1.7.0 ping bug; harmless on newer versions ---
os.environ.setdefault("HTTP_PROXY", "")
os.environ.setdefault("HTTPS_PROXY", "")
os.environ.setdefault("NO_PROXY", "*")

import runpod  # must import after the env guards
from vps_client import cloak_sync, VPSClientError

# Optional: let you override timeout from RunPod env
TOTAL_TIMEOUT = int(os.environ.get("VPS_TOTAL_TIMEOUT_SEC", "720"))  # 12 min

# ---- RunPod Handler ----
def handler(event):
    """
    Expected input:
      { "image_url": "https://..." }  OR  { "image_b64": "..." }
    Returns ONLY when the VPS returns a real output_url (ready result).
    """
    inp = event.get("input") or {}
    image_url = inp.get("image_url")
    image_b64 = inp.get("image_b64")

    if not image_url and not image_b64:
        return {"status": "failed", "error": "Provide image_url or image_b64."}

    try:
        output_url = cloak_sync(image_url=image_url,
                                image_b64=image_b64,
                                total_timeout_sec=TOTAL_TIMEOUT)
        # Signal success ONLY when we have a real URL
        return {"status": "completed", "output_url": output_url}
    except VPSClientError as e:
        return {"status": "failed", "error": str(e)}
    except Exception as e:
        return {"status": "failed", "error": f"unexpected: {e}"}

runpod.serverless.start({"handler": handler})
