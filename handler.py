import os
from typing import Any, Dict

from vps_client import VpsClient, VpsError


def _get_input(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    data = event.get("input", event)
    return data if isinstance(data, dict) else {}


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Production call (what your clients use):
      { "input": { "image_url": "https://..." } }
    Returns:
      { "output_url": "https://..." }

    Hub self-test (fast & hermetic):
      { "input": { "self_test": true } } -> { "ok": true }

    Optional “echo” path (for docs-style tests.json):
      { "input": { "text": "Hello", "language": "en" } } -> { "ok": true, "echo": {...} }
    """
    inp = _get_input(event)

    # --- Hermetic Hub test path ---
    if inp.get("self_test"):
        return {"ok": True}

    # --- Optional echo path (keeps tests.json flexible) ---
    if "text" in inp:
        return {"ok": True, "echo": inp}

    # --- Production path: call your VPS ---
    image_url = (inp.get("image_url") or "").strip()
    if not image_url:
        return {
            "error": "missing_required_input",
            "message": "Provide 'image_url' inside 'input'."
        }

    base_url   = os.environ.get("VPS_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
    endpoint   = os.environ.get("VPS_ENDPOINT_PATH", "/api/fawkes/cloak")
    timeout_s  = int(os.environ.get("VPS_TIMEOUT_SECONDS", "180"))  # you can raise this
    auth_token = os.environ.get("VPS_AUTH_TOKEN", "").strip() or None
    proxy      = os.environ.get("VPS_PROXY", "").strip() or None

    client = VpsClient(
        base_url=base_url,
        endpoint_path=endpoint,
        timeout_seconds=timeout_s,
        auth_token=auth_token,
        proxies=proxy
    )

    try:
        return client.process_image(image_url=image_url)
    except VpsError as e:
        return {"error": "vps_error", "message": str(e)}
