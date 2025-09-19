# handler.py
import base64
import io
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from PIL import Image
import runpod

from logic import anonymize

# --- Config via env ---
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/uploads"))
OUTPUT_BASE_URL = os.getenv("OUTPUT_BASE_URL", "https://anon.donkeybee.com").rstrip("/")
OUTPUT_PUBLIC_PREFIX = "/" + os.getenv("OUTPUT_PUBLIC_PREFIX", "/download").strip("/")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _save_from_url(url: str, dst_path: Path) -> Path:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    # Trust content-type lightly; open with PIL to normalize & validate.
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    img.save(dst_path, format="PNG", compress_level=6)
    return dst_path


def _save_from_base64(b64_str: str, dst_path: Path) -> Path:
    # accept both data URLs and raw base64
    if b64_str.startswith("data:"):
        b64_str = b64_str.split(",", 1)[1]
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.save(dst_path, format="PNG", compress_level=6)
    return dst_path


def _build_public_url(filename: str) -> str:
    # final URL: {OUTPUT_BASE_URL}{OUTPUT_PUBLIC_PREFIX}/{filename}
    return f"{OUTPUT_BASE_URL}{OUTPUT_PUBLIC_PREFIX}/{filename}"


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected input:
    {
      "input": {
        "image_url": "https://...",
        // or
        "image_base64": "data:image/png;base64,...",
        "jobId": "optional-passthrough",
        "filename": "optional-base-name.png"
      }
    }
    """
    try:
        data = (event or {}).get("input") or {}
        image_url: Optional[str] = data.get("image_url")
        image_base64: Optional[str] = data.get("image_base64")
        job_id: Optional[str] = data.get("jobId")
        requested_name: Optional[str] = data.get("filename")

        if not image_url and not image_base64:
            return {
                "status": "FAILED",
                "error": "Provide either 'image_url' or 'image_base64' in input."
            }

        # Generate stable filename
        stem = (Path(requested_name).stem if requested_name else str(uuid.uuid4()))
        in_name = f"{stem}_in.png"
        out_name = f"{stem}_out.png"
        in_path = OUTPUT_DIR / in_name
        out_path = OUTPUT_DIR / out_name

        # Save input to disk
        if image_url:
            _save_from_url(image_url, in_path)
        else:
            _save_from_base64(image_base64, in_path)

        # Run anonymization pipeline
        anonymize(str(in_path), str(out_path))

        # Build public URL for the output
        output_url = _build_public_url(out_name)

        return {
            "status": "DONE",
            "output_url": output_url,
            "jobId": job_id,
            "input_saved": _build_public_url(in_name)  # handy for debugging (keep/remove as you like)
        }

    except requests.RequestException as rexc:
        return {"status": "FAILED", "error": f"Download error: {str(rexc)}"}
    except Exception as exc:
        return {"status": "FAILED", "error": f"Unhandled error: {str(exc)}"}


# Required entrypoint for Runpod Serverless
runpod.serverless.start({"handler": handler})
