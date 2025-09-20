import requests


def process_via_vps(base_url: str, endpoint_path: str, image_url: str, timeout: int = 20) -> dict:
    """
    POSTs { image_url } to your VPS, expecting { output_url } back.
    Raises on HTTP errors; returns dict on success.
    """
    url = base_url.rstrip("/") + "/" + endpoint_path.lstrip("/")
    r = requests.post(url, json={"image_url": image_url}, timeout=timeout)
    r.raise_for_status()
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(data, dict):
        data = {"output_url": image_url}
    return data
