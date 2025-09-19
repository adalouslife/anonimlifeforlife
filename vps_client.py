# vps_client.py
import os
from typing import Optional, Tuple
import requests

class VPSJobError(Exception):
    pass

class VPSClient:
    """
    Minimal client for your VPS API:
      POST   /Upload                 -> { "id": "12345" }
      GET    /query?id=12345         -> { "status": "queued|processing|done|failed", "filename": "...", "message": "..." }
      STATIC /download/<filename>    -> public file
    """
    def __init__(self, base_url: str, api_key: str = "", user_agent: str = "vps-client/1.0") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key  = api_key
        self.session  = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

        # allow overriding endpoints if your VPS uses different paths
        self.path_upload = os.environ.get("VPS_PATH_UPLOAD", "/Upload")
        self.path_query  = os.environ.get("VPS_PATH_QUERY",  "/query")
        self.path_dl     = os.environ.get("VPS_PATH_DL",     "/download")

    # ---------- Public helpers ----------
    def upload(self, image_bytes: bytes, filename: str = "upload.jpg") -> str:
        url = f"{self.base_url}{self.path_upload}"
        files = {"file": (filename, image_bytes, "application/octet-stream")}
        r = self.session.post(url, files=files, timeout=120)
        r.raise_for_status()
        data = r.json()
        if "id" not in data:
            raise VPSJobError(f"Unexpected /Upload response: {data}")
        return str(data["id"])

    def query(self, job_id: str) -> Tuple[str, Optional[str], Optional[str]]:
        url = f"{self.base_url}{self.path_query}"
        r = self.session.get(url, params={"id": job_id}, timeout=30)
        r.raise_for_status()
        data = r.json()
        status   = str(data.get("status", ""))
        filename = data.get("filename")
        message  = data.get("message")
        return status, filename, message

    def download_url(self, filename: str) -> str:
        # Public HTTPS URL Caddy serves
        return f"{self.base_url}{self.path_dl}/{filename}"
