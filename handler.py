import runpod
import requests
import base64
import os
from fawkes import Fawkes   # adjust if your fawkes import path differs

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def handler(job):
    job_input = job.get("input", {})
    image_url = job_input.get("image_url")
    image_b64 = job_input.get("imageBase64")

    if not image_url and not image_b64:
        return {"error": "Provide either 'image_url' or 'imageBase64'."}

    try:
        # --- Get image bytes ---
        if image_url:
            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()
            image_bytes = resp.content
        else:
            image_bytes = base64.b64decode(image_b64)

        # --- Save input ---
        in_path = os.path.join(UPLOAD_DIR, f"{job['id']}_in.png")
        with open(in_path, "wb") as f:
            f.write(image_bytes)

        # --- Run anonymizer ---
        out_path = os.path.join(UPLOAD_DIR, f"{job['id']}_out.png")
        fawkes = Fawkes(feature_extractor=None)  # adapt init if needed
        fawkes.run(in_path, out_path)            # adapt to your API

        # --- Return result URL ---
        return {
            "status": "DONE",
            "input_size": len(image_bytes),
            "result_url": f"https://anon.donkeybee.com/download/{job['id']}_out.png"
        }

    except Exception as e:
        return {"error": str(e)}

runpod.serverless.start({"handler": handler})
