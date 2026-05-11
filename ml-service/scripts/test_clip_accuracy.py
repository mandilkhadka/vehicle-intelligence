"""
Local sanity check for the improved CLIP vehicle identification.

Runs FrameExtractor + (optionally) the OLD baseline VehicleIdentifier and
the NEW improved one on a real video, and prints both results so you can
eyeball the accuracy bump.

Usage:
    python scripts/test_clip_accuracy.py /path/to/video.mov
    python scripts/test_clip_accuracy.py /path/to/video.mov --baseline   # also run the old logic
"""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# Make `src` importable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR.parent))  # so `src.services.*` imports resolve

from src.services.frame_extractor import FrameExtractor  # noqa: E402
from src.services.model_registry import ModelRegistry  # noqa: E402
from src.services.vehicle_identifier import VehicleIdentifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_clip_accuracy")


async def run(video_path: str, run_baseline: bool) -> None:
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    print("=" * 70)
    print(f"Test video: {video_path}")
    print("=" * 70)

    # 1) Initialize ModelRegistry (loads YOLO + CLIP + brand embeddings).
    t0 = time.time()
    registry = ModelRegistry()
    registry.initialize_all_models()
    print(f"\n[setup] ModelRegistry ready in {time.time() - t0:.2f}s")

    # 2) Extract frames into a temp dir.
    with tempfile.TemporaryDirectory(prefix="clip_test_frames_") as tmpdir:
        extractor = FrameExtractor()
        t0 = time.time()
        frame_paths = await extractor.extract_frames(video_path, tmpdir)
        print(f"[extract] {len(frame_paths)} frames in {time.time() - t0:.2f}s")
        if not frame_paths:
            print("No frames extracted — aborting.")
            return

        # 3) NEW improved identifier
        new_identifier = VehicleIdentifier(
            yolo_model=registry.get_yolo_model(),
            clip_model=registry.get_clip_model(),
            clip_processor=registry.get_clip_processor(),
            brand_text_embeddings=registry.get_brand_text_embeddings(),
            brand_names=registry.get_brand_names(),
        )
        t0 = time.time()
        new_result = await new_identifier.identify(frame_paths)
        new_elapsed = time.time() - t0
        print("\n--- IMPROVED CLIP IDENTIFIER ---")
        for k, v in new_result.items():
            print(f"  {k:11s}: {v}")
        print(f"  elapsed   : {new_elapsed:.2f}s")

        # 4) OPTIONAL baseline — replicate original behavior (no crop, first 3 frames,
        #    single-template prompts, softmax-average, no confidence floor).
        if run_baseline:
            print("\n--- BASELINE (original logic, for comparison) ---")
            baseline_result = await _run_baseline(
                frame_paths,
                clip_model=registry.get_clip_model(),
                clip_processor=registry.get_clip_processor(),
                brand_names=registry.get_brand_names(),
            )
            for k, v in baseline_result.items():
                print(f"  {k:11s}: {v}")


async def _run_baseline(frame_paths, clip_model, clip_processor, brand_names):
    """Reproduce the previous identification logic for an A/B comparison."""
    import torch
    from PIL import Image

    images = [Image.open(p) for p in frame_paths[:3]]
    brand_texts = [f"a {b} vehicle" for b in brand_names]
    inputs = clip_processor(text=brand_texts, images=images, return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = clip_model(**inputs)
    logits_per_image = outputs.logits_per_image
    probs = logits_per_image.softmax(dim=1)
    avg_probs = probs.mean(dim=0)
    best_idx = int(avg_probs.argmax().item())
    return {
        "brand": brand_names[best_idx],
        "confidence": float(avg_probs[best_idx].item()),
        "frames_used": len(images),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to a video file")
    parser.add_argument("--baseline", action="store_true", help="Also run the previous baseline logic")
    args = parser.parse_args()
    asyncio.run(run(args.video, run_baseline=args.baseline))


if __name__ == "__main__":
    main()
