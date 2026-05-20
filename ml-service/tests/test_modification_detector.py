from pathlib import Path

import torch
from PIL import Image

from src.services.modification_detector import ModificationDetector, PartPromptConfig


class FakeProcessor:
    def __call__(self, text=None, images=None, return_tensors=None, padding=None, truncation=None):
        if text is not None:
            return {"input_ids": torch.arange(len(text), dtype=torch.float32).unsqueeze(1)}
        return {"pixel_values": torch.ones((len(images), 1), dtype=torch.float32)}


class FakeClipModel:
    def get_text_features(self, **inputs):
        rows = int(inputs["input_ids"].shape[0])
        features = torch.zeros((rows, 2), dtype=torch.float32)
        for index in range(rows):
            features[index, 0 if index == 0 else 1] = 1.0
        return features

    def get_image_features(self, **inputs):
        rows = int(inputs["pixel_values"].shape[0])
        return torch.tensor([[1.0, 0.0]] * rows, dtype=torch.float32)


def test_modification_detector_returns_exhaust_item_when_clip_unavailable():
    detector = ModificationDetector()

    result = detector._detect_sync([], {}, {"type": "stock", "confidence": 0.81})

    assert result["available"] is False
    assert result["items"][0]["part"] == "exhaust"
    assert result["items"][0]["status"] == "stock"
    assert result["items"][0]["confidence"] == 0.81


def test_modification_detector_classifies_part_with_clip_prompt_evidence(tmp_path):
    frame = tmp_path / "front-left.jpg"
    Image.new("RGB", (16, 16), "white").save(frame)
    detector = ModificationDetector(clip_model=FakeClipModel(), clip_processor=FakeProcessor())
    config = PartPromptConfig(
        part="wheels",
        views=("front-left",),
        stock_prompts=("factory stock wheels",),
        modified_prompts=("aftermarket wheels",),
    )

    result = detector._classify_part(
        config,
        [str(frame)],
        {
            "angle_shots": {
                "front-left": {
                    "view": "front-left",
                    "frame": str(frame),
                    "organized_path": str(frame),
                    "frame_index": 2,
                    "source_frame_index": 20,
                    "timestamp_seconds": 4.0,
                }
            }
        },
    )

    assert result["part"] == "wheels"
    assert result["status"] == "stock"
    assert result["confidence"] > 0.9
    assert result["source"] == "local_clip"
    assert result["frame"] == str(frame)
    assert result["source_frame_index"] == 20
