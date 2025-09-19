import os, requests
from typing import Optional, Tuple

class VPSJobError(Exception): pass

class VPSClient:
    def __init__(self, base_url: str, api_key: str = "", user_agent: str = "vps-client/1.0"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self.path_upload = os.environ.get("VPS_PATH_UPLOAD", "/Upload")
        self.path_query  = os.environ.get("VPS_PATH_QUERY",  "/query")
        self.path_dl     = os.environ.get("VPS_PATH_DL",     "/download")

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
        return str(data.get("status", "")), data.get("filename"), data.get("message")

    def download_url(self, filename: str) -> str:
        return f"{self.base_url}{self.path_dl}/{filename}"
