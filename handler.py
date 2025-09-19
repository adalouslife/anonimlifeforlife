import base64, os, time, requests, runpod

DEFAULT_VPS_BASE  = os.getenv("VPS_BASE", "https://anon.donkeybee.com").rstrip("/")
DEFAULT_VPS_TOKEN = os.getenv("VPS_TOKEN", "dev-local-secret-change-me")

CONNECT_TIMEOUT = 10
READ_TIMEOUT    = 180
TOTAL_POLL_S    = 600
POLL_INTERVAL   = 1.2
RETRY_COUNT     = 3
BACKOFF         = 1.5

def _req(method, url, **kw):
    last = None
    for i in range(1, RETRY_COUNT+1):
        try:
            return requests.request(method, url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), **kw)
        except Exception as e:
            last = e
            if i < RETRY_COUNT:
                time.sleep(BACKOFF**i)
    raise last

def _download(url: str) -> bytes:
    r = _req("GET", url, stream=True); r.raise_for_status(); return r.content

def _upload(img: bytes, base: str, token: str) -> str:
    r = _req("POST", f"{base}/Upload", files={"file": ("image", img, "application/octet-stream")},
             headers={"X-Auth-Token": token})
    r.raise_for_status()
    image_id = r.text.strip()
    if len(image_id) != 32 or any(c not in "0123456789abcdef" for c in image_id.lower()):
        raise RuntimeError(f"Unexpected IMAGE_ID: {image_id!r}")
    return image_id

def _poll(base: str, token: str, image_id: str):
    deadline = time.time() + TOTAL_POLL_S
    headers = {"X-Auth-Token": token}
    while True:
        r = _req("GET", f"{base}/query/{image_id}", headers=headers); r.raise_for_status()
        s = r.text.strip().upper()
        if s == "READY": return
        if time.time() > deadline: raise TimeoutError(f"poll timeout; last status={s}")
        time.sleep(POLL_INTERVAL)

def _download_result(base: str, token: str, image_id: str) -> bytes:
    r = _req("GET", f"{base}/download/{image_id}", headers={"X-Auth-Token": token}, stream=True)
    r.raise_for_status(); return r.content

def handler(event):
    try:
        inp = event.get("input") or {}
        vps_base  = (inp.get("vps_base") or DEFAULT_VPS_BASE).rstrip("/")
        vps_token =  inp.get("vps_token") or DEFAULT_VPS_TOKEN

        # get input bytes
        if inp.get("image_b64"):
            b64 = inp["image_b64"]
            if b64.startswith("data:"): b64 = b64.split(",",1)[1]
            try:
                img = base64.b64decode(b64)
            except Exception as e:
                return {"status":"FAILED","error":f"Invalid image_b64: {e}"}
        elif inp.get("image_url"):
            try:
                img = _download(inp["image_url"])
            except Exception as e:
                return {"status":"FAILED","error":f"HTTP error: {e}"}
        else:
            return {"status":"FAILED","error":"Provide 'image_url' or 'image_b64'."}

        image_id = _upload(img, vps_base, vps_token)
        _poll(vps_base, vps_token, image_id)
        out = _download_result(vps_base, vps_token, image_id)
        return {"status":"COMPLETED","image_b64": base64.b64encode(out).decode(),"image_id":image_id}
    except Exception as e:
        return {"status":"FAILED","error":f"Unhandled: {e}"}

runpod.serverless.start({"handler": handler})
