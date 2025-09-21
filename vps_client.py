import os
from typing import Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class VpsError(Exception):
    pass


class VpsClient:
    """
    POST   { "image_url": "..." }
    EXPECT { "output_url": "..." }
    """

    def __init__(
        self,
        base_url: str,
        endpoint_path: str,
        timeout_seconds: int = 180,
        auth_token: Optional[str] = None,
        proxies: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        self.timeout = timeout_seconds

        self.session = requests.Session()
        self.headers = {
            "User-Agent": "RunPod-Worker/1.0",
            "Content-Type": "application/json",
        }
        if auth_token:
            # If Caddy/app expects a header, edit the key if needed
            self.headers["X-Auth-Token"] = auth_token

        # Only set proxies if provided; avoid the old NoneType.setdefault issue
        if proxies:
            self.session.proxies = {"http": proxies, "https": proxies}

        # Remove inherited proxy env to avoid surprises
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.8, min=1, max=4),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    )
    def _post(self, url: str, json_body: Dict) -> Dict:
        resp = self.session.post(url, json=json_body, headers=self.headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise VpsError(f"VPS HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except Exception as e:
            raise VpsError(f"VPS invalid JSON: {e}") from e

    def process_image(self, image_url: str) -> Dict:
        url = f"{self.base_url}{self.path}"
        payload = {"image_url": image_url}
        data = self._post(url, payload)
        output_url = (data or {}).get("output_url")
        if not output_url:
            raise VpsError(f"No 'output_url' in VPS response: {str(data)[:300]}")
        return {"output_url": output_url}
