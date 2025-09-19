import os
import json
import time
import logging
import runpod
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")
TIMEOUT_S = int(os.getenv("REQUEST_TIMEOUT_S", "60"))

def handle_job(job):
    """
    Input shape (examples):
      { "image_url": "https://..." }   # what tests send
      or
      { "prompt": "...", "mode": "ping" }
    Output shape (always):
      { "status": "completed"|"failed", "output_url": "...", "output": {...}, "logs": [...] }
    """
    logs = []
    try:
        inp = job.get("input", {}) if isinstance(job, dict) else {}
        mode = (inp.get("mode") or "").lower()

        if mode == "ping":
            return {"status": "completed", "output": {"pong": True}, "logs": logs}

        image_url = inp.get("image_url")
        if DRY_RUN:
            # Don’t call external systems in Hub tests; just echo input
            logs.append("DRY_RUN=true: skipping external calls.")
            if image_url:
                return {
                    "status": "completed",
                    "output_url": image_url,
                    "output": {"echo": True, "image_url": image_url},
                    "logs": logs
                }
            else:
                return {
                    "status": "completed",
                    "output": {"echo": True, "received": inp},
                    "logs": logs
                }

        # --- Real path (not used by Hub tests) ---
        if image_url:
            r = requests.get(image_url, timeout=15)
            r.raise_for_status()
            # ... do your processing, upload somewhere, produce output_url ...
            # placeholder:
            processed_url = image_url
            return {
                "status": "completed",
                "output_url": processed_url,
                "output": {"note": "processed"},
                "logs": logs
            }
        else:
            # If no image, just return an echo payload
            return {
                "status": "completed",
                "output": {"echo": True, "received": inp},
                "logs": logs
            }

    except Exception as e:
        logs.append(f"error: {repr(e)}")
        return {"status": "failed", "error": str(e), "logs": logs}

if __name__ == "__main__":
    logging.info("---- Starting RunPod serverless worker ----")
    logging.info(f"DRY_RUN={DRY_RUN}")
    logging.info(f"RUNPOD_SERVERLESS={os.getenv('RUNPOD_SERVERLESS')}")
    logging.info(f"RUNPOD_WORKER_ID={os.getenv('RUNPOD_WORKER_ID')}")
    runpod.serverless.start({"handler": handle_job})
