# logic.py
from PIL import Image, ImageFilter
from pathlib import Path

def anonymize(input_path: str, output_path: str) -> str:
    """
    Minimal, fast anonymization:
      1) Pixelate down then up
      2) Light Gaussian blur
    Replace with your stronger cloaking if desired; keep the function signature.
    """
    src = Image.open(input_path).convert("RGB")

    # --- Pixelation ---
    # downscale aggressively then upscale using NEAREST to create blocky pixels
    w, h = src.size
    factor = 12 if max(w, h) >= 1600 else 8
    small = src.resize((max(1, w // factor), max(1, h // factor)), Image.BILINEAR)
    pix = small.resize((w, h), Image.NEAREST)

    # --- Subtle blur to soften edges ---
    out = pix.filter(ImageFilter.GaussianBlur(radius=1.2))

    # Save (PNG to avoid JPEG artifacts if you prefer)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, format="PNG", compress_level=6)

    return output_path
