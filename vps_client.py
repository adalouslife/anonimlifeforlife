"""
Minimal stub for your real VPS pipeline.
Implement `process_image_bytes` to send the image to your VPS (Fawkes/Candy flow)
and return a *URL* to the processed result (Runpod’s test only validates that it’s a URL).
"""

import os
import aiohttp
import asyncio
from typing import Optional

VPS_ENDPOINT = os.getenv("VPS_ENDPOINT", "").strip()
# Example: "https://anon.donkeybee.com/api/process"

async def _post_bytes(session: aiohttp.ClientSession, url: str, data: bytes) -> Optional[str]:
    # Your real endpoint contract probably needs multipart/form-data; adjust as needed.
    form = aiohttp.FormData()
    form.add_field("file", data, filename="input.jpg", content_type="image/jpeg")
    async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
        resp.raise_for_status()
        js = await resp.json()
        # Expect your service to return {"output_url": "..."} or similar
        return js.get("output_url") or js.get("url")

def process_image_bytes(data: bytes) -> Optional[str]:
    if not VPS_ENDPOINT:
        return None
    async def _run():
        async with aiohttp.ClientSession() as session:
            return await _post_bytes(session, VPS_ENDPOINT, data)
    return asyncio.run(_run())
