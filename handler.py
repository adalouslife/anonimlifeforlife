import os, time, base64, requests
import runpod

VPS_BASE   = os.environ.get("VPS_BASE", "http://127.0.0.1:8000")   # CHANGE to your VPS later
VPS_TOKEN  = os.environ.get("VPS_TOKEN", "dev-local-secret-change-me")
TIMEOUT_S  = int(os.environ.get("TIMEOUT_S", "180"))
POLL_EVERY = float(os.environ.get("POLL_EVERY", "2.0"))

def upload_bytes(img_bytes: bytes, filename: str = "input.jpg") -> str:
    files = {"file": (filename, img_bytes, "image/jpeg")}
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.post(f"{VPS_BASE}/Upload", files=files, headers=headers, timeout=60)
    r.raise_for_status()
    return r.text.strip()

def poll_ready(image_id: str) -> bool:
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.get(f"{VPS_BASE}/query/{image_id}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.text.strip().upper() == "READY"

def download(image_id: str) -> bytes:
    headers = {"X-Auth-Token": VPS_TOKEN}
    r = requests.get(f"{VPS_BASE}/download/{image_id}", headers=headers, timeout=60)
    r.raise_for_status()
    return r.content

def handler(event):
    """
    Input:
    {
      "image_base64": "<...>"    # OR
      "image_url": "https://example.com/photo.jpg"
    }
    """
    body = event.get("input", {}) or {}
    image_b64 = body.get("image_base64")
    image_url = body.get("image_url")

    if not image_b64 and not image_url:
        return {"error": "Provide image_base64 or image_url"}

    # fetch bytes
    if image_b64:
        try:
            img_bytes = base64.b64decode(image_b64)
        except Exception:
            return {"error": "Invalid base64"}
    else:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        img_bytes = resp.content

    # upload → get id
    image_id = upload_bytes(img_bytes)

    # poll until ready
    start = time.time()
    while True:
        if poll_ready(image_id):
            break
        if time.time() - start > TIMEOUT_S:
            return {"error": "Processing timeout", "image_id": image_id}
        time.sleep(POLL_EVERY)

    # download result
    out_bytes = download(image_id)
    out_b64 = base64.b64encode(out_bytes).decode("utf-8")
    return {"image_id": image_id, "image_base64": out_b64}

runpod.serverless.start({"handler": handler})
