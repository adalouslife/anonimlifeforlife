import os
import requests
from typing import Any, Dict, Optional

class VpsClientError(Exception):
    pass

class VpsClient:
    def __init__(
        self,
        base_url: str,
        start_path: str = "/api/anonymize",
        status_path_template: str = "/api/anonymize/{job_id}",
        request_timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.start_path = start_path
        self.status_path_template = status_path_template
        self.timeout = request_timeout

        # Optional: if your VPS later adds simple auth, you can pass it here.
        self.api_key = os.getenv("VPS_API_KEY", "").strip()
        self.api_header_name = os.getenv("VPS_API_HEADER", "X-API-Key")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers[self.api_header_name] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def start_job(self, image_url: str, mode: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"image_url": image_url}
        if mode:
            payload["mode"] = mode
        if options:
            payload["options"] = options

        url = self._url(self.start_path)
        try:
            r = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json() if r.content else {}
        except requests.RequestException as e:
            raise VpsClientError(f"POST {url} failed: {e}") from e

    def get_status(self, job_id: str) -> Dict[str, Any]:
        path = self.status_path_template.replace("{job_id}", job_id)
        url = self._url(path)
        try:
            r = requests.get(url, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json() if r.content else {}
        except requests.RequestException as e:
            raise VpsClientError(f"GET {url} failed: {e}") from e
