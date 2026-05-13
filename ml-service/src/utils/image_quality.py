"""Image enhancement helpers shared by frame extraction and OCR crops."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def read_image_with_orientation(path: str | Path) -> np.ndarray | None:
    """Read an image and honor camera EXIF orientation when Pillow can decode it."""
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    except Exception:
        return cv2.imread(str(path))


def enhance_image_for_analysis(
    image: np.ndarray,
    *,
    min_width: Optional[int] = None,
    min_height: Optional[int] = None,
    denoise: bool = False,
) -> np.ndarray:
    """Improve readability without heavy artificial sharpening."""
    if image is None or image.size == 0:
        return image

    enhanced = image.copy()
    h, w = enhanced.shape[:2]
    scale = 1.0
    if min_width and w > 0:
        scale = max(scale, min_width / float(w))
    if min_height and h > 0:
        scale = max(scale, min_height / float(h))
    if scale > 1.05:
        enhanced = cv2.resize(
            enhanced,
            (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )

    if denoise:
        enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 3, 3, 7, 21)

    lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    enhanced = cv2.cvtColor(
        cv2.merge([l_channel, a_channel, b_channel]),
        cv2.COLOR_LAB2BGR,
    )

    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.15)
    enhanced = cv2.addWeighted(enhanced, 1.32, blurred, -0.32, 0)
    return np.clip(enhanced, 0, 255).astype(np.uint8)


def write_jpeg(path: str | Path, image: np.ndarray, quality: int = 98) -> bool:
    """Write a JPEG with consistent high-quality encoder flags."""
    params = [cv2.IMWRITE_JPEG_QUALITY, int(np.clip(quality, 1, 100))]
    if hasattr(cv2, "IMWRITE_JPEG_OPTIMIZE"):
        params.extend([cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if hasattr(cv2, "IMWRITE_JPEG_PROGRESSIVE"):
        params.extend([cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(path), image, params))
