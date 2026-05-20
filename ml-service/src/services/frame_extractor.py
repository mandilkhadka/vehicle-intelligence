"""
Frame extraction service.

Extracts source-preserved inspection frames with separate lightweight previews.
ffmpeg is preferred for direct frame extraction; OpenCV remains a fallback for
environments where ffmpeg is unavailable.
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.utils.image_quality import write_jpeg


@dataclass(frozen=True)
class FrameQualityMetrics:
    blur_score: float
    brightness: float
    contrast: float
    overexposed_ratio: float
    underexposed_ratio: float
    motion_blur_score: float
    quality_score: float
    exposure_state: str


class FrameExtractor:
    """Extracts frames from video files with quality filtering"""

    def __init__(
        self,
        fps: int = 1,
        min_blur_threshold: float = 15.0,
        jpeg_quality: int = 98,
        preview_jpeg_quality: int = 84,
        preview_max_width: int = 720,
        candidate_multiplier: int = 3,
    ):
        """
        Initialize frame extractor
        Args:
            fps: Frames per second to extract (default: 1 frame per second)
            min_blur_threshold: Minimum Laplacian variance to consider frame sharp (default: 15.0)
            jpeg_quality: JPEG quality (1-100, default: 98)
        """
        self.fps = max(float(fps), 0.1)
        self.min_blur_threshold = min_blur_threshold
        self.jpeg_quality = jpeg_quality
        self.preview_jpeg_quality = int(np.clip(preview_jpeg_quality, 1, 100))
        self.preview_max_width = max(int(preview_max_width), 240)
        self.candidate_multiplier = max(int(candidate_multiplier), 1)

    async def extract_frames(
        self, video_path: str, output_dir: str
    ) -> List[str]:
        """
        Extract frames from video
        Args:
            video_path: Path to input video file
            output_dir: Directory to save extracted frames
        Returns:
            List of frame file paths (relative to project root)
        """
        # Run in thread pool to avoid blocking
        return await asyncio.to_thread(
            self._extract_frames_sync, video_path, output_dir
        )

    def _calculate_blur_score(self, frame: np.ndarray) -> float:
        """Calculate blur score using Laplacian variance."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return laplacian_var

    def _is_duplicate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        threshold: float = 0.985,
        max_mean_difference: float = 0.018,
    ) -> bool:
        """
        Check if two frames are too similar (duplicates)
        Args:
            frame1: First frame
            frame2: Second frame
            threshold: Similarity threshold (default: 0.95)
        Returns:
            True if frames are duplicates
        """
        # Resize for faster comparison
        frame1_small = cv2.resize(frame1, (64, 64))
        frame2_small = cv2.resize(frame2, (64, 64))
        
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1_small, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2_small, cv2.COLOR_BGR2GRAY)
        
        # Calculate structural similarity
        # Using histogram correlation as a simple metric
        hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])
        
        correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        mean_difference = float(np.mean(cv2.absdiff(gray1, gray2))) / 255.0

        return correlation > threshold and mean_difference < max_mean_difference

    def _extract_frames_sync(
        self, video_path: str, output_dir: str
    ) -> List[str]:
        """
        Synchronous frame extraction with quality filtering
        """
        os.makedirs(output_dir, exist_ok=True)
        if shutil.which("ffmpeg"):
            try:
                return self._extract_frames_ffmpeg(video_path, output_dir)
            except Exception as exc:
                print(f"ffmpeg extraction failed, falling back to OpenCV: {exc}")
        return self._extract_frames_opencv(video_path, output_dir)

    def _extract_frames_ffmpeg(self, video_path: str, output_dir: str) -> List[str]:
        video_fps, total_frames, source_width, source_height = self._video_properties(video_path)
        candidate_fps = self._candidate_fps(video_fps)
        frame_interval = self._frame_interval(video_fps)

        with tempfile.TemporaryDirectory(prefix=".ffmpeg-candidates-", dir=output_dir) as temp_dir:
            candidate_pattern = str(Path(temp_dir) / "candidate_%06d.jpg")
            vf = (
                f"fps={candidate_fps},"
                "scale=iw:ih:flags=lanczos:in_range=auto:out_range=pc,"
                "format=yuvj420p"
            )
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                video_path,
                "-vf",
                vf,
                "-q:v",
                "1",
                candidate_pattern,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            candidates = sorted(Path(temp_dir).glob("candidate_*.jpg"))
            if not candidates:
                raise ValueError("ffmpeg did not produce any candidate frames")

            frame_paths, frame_metadata, skipped = self._select_and_write_frames(
                candidate_paths=[str(path) for path in candidates],
                output_dir=output_dir,
                video_path=video_path,
                video_fps=video_fps,
                total_frames=total_frames,
                frame_interval=frame_interval,
                source_width=source_width,
                source_height=source_height,
                candidate_fps=candidate_fps,
                extraction_method="ffmpeg_direct",
                preserve_candidate_file=True,
            )

        self._write_metadata(
            output_dir=output_dir,
            video_path=video_path,
            video_fps=video_fps,
            total_frames=total_frames,
            frame_interval=frame_interval,
            frame_metadata=frame_metadata,
            skipped_blurry=skipped["blurry"],
            skipped_duplicate=skipped["duplicate"],
            skipped_overexposed=skipped["overexposed"],
            skipped_underexposed=skipped["underexposed"],
            skipped_motion_blur=skipped["motion_blur"],
            jpeg_quality=self.jpeg_quality,
            preview_jpeg_quality=self.preview_jpeg_quality,
            extraction_method="ffmpeg_direct",
            source_width=source_width,
            source_height=source_height,
            candidate_fps=candidate_fps,
        )
        print(f"Extracted {len(frame_paths)} source-preserved frames from video")
        return frame_paths

    def _extract_frames_opencv(self, video_path: str, output_dir: str) -> List[str]:
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_interval = self._frame_interval(video_fps)

        frame_paths = []
        frame_metadata: List[Dict[str, Any]] = []
        frame_count = 0
        saved_count = 0
        last_saved_frame = None
        skipped_blurry = 0
        skipped_duplicate = 0
        skipped_overexposed = 0
        skipped_underexposed = 0
        skipped_motion_blur = 0

        print(f"Video FPS: {video_fps}, Total frames: {total_frames}")
        print(
            "Extraction settings: "
            f"target_fps={self.fps}, frame_interval={frame_interval}, "
            f"blur_threshold={self.min_blur_threshold}, jpeg_quality={self.jpeg_quality}"
        )

        while True:
            ret, frame = cap.read()

            if not ret:
                break

            if frame_count % frame_interval == 0:
                metrics = self._assess_frame_quality(frame)
                rejection = self._quality_rejection(metrics)
                if rejection:
                    if rejection == "blur":
                        skipped_blurry += 1
                    elif rejection == "overexposed":
                        skipped_overexposed += 1
                    elif rejection == "underexposed":
                        skipped_underexposed += 1
                    elif rejection == "motion_blur":
                        skipped_motion_blur += 1
                    frame_count += 1
                    continue

                if last_saved_frame is not None and self._is_duplicate(frame, last_saved_frame):
                    skipped_duplicate += 1
                    frame_count += 1
                    continue

                frame_filename = f"frame_{saved_count:04d}.jpg"
                frame_path = os.path.join(output_dir, frame_filename)
                write_jpeg(frame_path, frame, self.jpeg_quality)
                preview_path = self._write_preview(frame, output_dir, frame_filename)

                frame_paths.append(frame_path)
                frame_metadata.append(
                    self._metadata_payload(
                        extracted_index=saved_count,
                        source_frame_index=frame_count,
                        timestamp_seconds=round(frame_count / video_fps, 3) if video_fps > 0 else None,
                        path=frame_path,
                        preview_path=preview_path,
                        metrics=metrics,
                        frame=frame,
                    )
                )
                last_saved_frame = frame.copy()
                saved_count += 1

            frame_count += 1

        cap.release()

        print(f"Extracted {len(frame_paths)} frames from video")
        if skipped_blurry > 0:
            print(f"Skipped {skipped_blurry} blurry frames")
        if skipped_duplicate > 0:
            print(f"Skipped {skipped_duplicate} duplicate frames")

        self._write_metadata(
            output_dir=output_dir,
            video_path=video_path,
            video_fps=video_fps,
            total_frames=total_frames,
            frame_interval=frame_interval,
            frame_metadata=frame_metadata,
            skipped_blurry=skipped_blurry,
            skipped_duplicate=skipped_duplicate,
            skipped_overexposed=skipped_overexposed,
            skipped_underexposed=skipped_underexposed,
            skipped_motion_blur=skipped_motion_blur,
            jpeg_quality=self.jpeg_quality,
            preview_jpeg_quality=self.preview_jpeg_quality,
            extraction_method="opencv_fallback",
            source_width=source_width,
            source_height=source_height,
            candidate_fps=None,
        )
        return frame_paths

    def _select_and_write_frames(
        self,
        *,
        candidate_paths: List[str],
        output_dir: str,
        video_path: str,
        video_fps: float,
        total_frames: int,
        frame_interval: int,
        source_width: int,
        source_height: int,
        candidate_fps: float,
        extraction_method: str,
        preserve_candidate_file: bool,
    ) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, int]]:
        del video_path, extraction_method
        group_size = max(1, int(round(candidate_fps / self.fps)))
        frame_paths: List[str] = []
        frame_metadata: List[Dict[str, Any]] = []
        skipped = {
            "blurry": 0,
            "duplicate": 0,
            "overexposed": 0,
            "underexposed": 0,
            "motion_blur": 0,
        }
        last_saved_frame: Optional[np.ndarray] = None
        saved_count = 0

        for group_start in range(0, len(candidate_paths), group_size):
            group = candidate_paths[group_start:group_start + group_size]
            best = self._best_candidate(group)
            if best is None:
                continue
            candidate_path, frame, metrics, rejection = best
            if rejection:
                skipped[self._skip_key(rejection)] += 1
                continue
            if last_saved_frame is not None and self._is_duplicate(frame, last_saved_frame):
                skipped["duplicate"] += 1
                continue

            frame_filename = f"frame_{saved_count:04d}.jpg"
            frame_path = os.path.join(output_dir, frame_filename)
            if preserve_candidate_file:
                shutil.copy2(candidate_path, frame_path)
            else:
                write_jpeg(frame_path, frame, self.jpeg_quality)
            preview_path = self._write_preview(frame, output_dir, frame_filename)

            candidate_index = int(Path(candidate_path).stem.split("_")[-1]) - 1
            timestamp_seconds = round(candidate_index / candidate_fps, 3) if candidate_fps > 0 else None
            source_frame_index = (
                int(round(timestamp_seconds * video_fps))
                if timestamp_seconds is not None and video_fps > 0
                else group_start * frame_interval
            )

            frame_paths.append(frame_path)
            frame_metadata.append(
                self._metadata_payload(
                    extracted_index=saved_count,
                    source_frame_index=source_frame_index,
                    timestamp_seconds=timestamp_seconds,
                    path=frame_path,
                    preview_path=preview_path,
                    metrics=metrics,
                    frame=frame,
                    source_width=source_width,
                    source_height=source_height,
                )
            )
            last_saved_frame = frame.copy()
            saved_count += 1

        return frame_paths, frame_metadata, skipped

    def _best_candidate(
        self,
        candidate_paths: List[str],
    ) -> Optional[Tuple[str, np.ndarray, FrameQualityMetrics, Optional[str]]]:
        ranked: List[Tuple[str, np.ndarray, FrameQualityMetrics, Optional[str]]] = []
        for path in candidate_paths:
            frame = cv2.imread(path)
            if frame is None:
                continue
            metrics = self._assess_frame_quality(frame)
            ranked.append((path, frame, metrics, self._quality_rejection(metrics)))
        if not ranked:
            return None
        usable = [item for item in ranked if item[3] is None]
        candidates = usable or ranked
        return max(candidates, key=lambda item: item[2].quality_score)

    def _assess_frame_quality(self, frame: np.ndarray) -> FrameQualityMetrics:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        overexposed_ratio = float(np.mean(gray >= 248))
        underexposed_ratio = float(np.mean(gray <= 6))
        exposure_state = "ok"
        if overexposed_ratio > 0.42 and brightness > 210:
            exposure_state = "overexposed"
        elif underexposed_ratio > 0.42 and brightness < 45:
            exposure_state = "underexposed"

        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_energy = float(np.sqrt((sobel_x ** 2) + (sobel_y ** 2)).mean())
        motion_blur_score = float(np.clip(1.0 - (gradient_energy / 55.0), 0.0, 1.0))

        sharpness_score = min(blur / 320.0, 1.0)
        contrast_score = min(contrast / 72.0, 1.0)
        exposure_score = 1.0 - min(max(overexposed_ratio, underexposed_ratio) * 1.8, 1.0)
        motion_score = 1.0 - motion_blur_score
        quality_score = float(
            np.clip(
                (sharpness_score * 0.42)
                + (contrast_score * 0.24)
                + (exposure_score * 0.22)
                + (motion_score * 0.12),
                0.0,
                1.0,
            )
        )

        return FrameQualityMetrics(
            blur_score=blur,
            brightness=brightness,
            contrast=contrast,
            overexposed_ratio=overexposed_ratio,
            underexposed_ratio=underexposed_ratio,
            motion_blur_score=motion_blur_score,
            quality_score=quality_score,
            exposure_state=exposure_state,
        )

    def _quality_rejection(self, metrics: FrameQualityMetrics) -> Optional[str]:
        if metrics.blur_score < self.min_blur_threshold:
            return "blur"
        if metrics.exposure_state in {"overexposed", "underexposed"}:
            return metrics.exposure_state
        if metrics.motion_blur_score >= 0.96 and metrics.blur_score < self.min_blur_threshold * 2:
            return "motion_blur"
        return None

    @staticmethod
    def _skip_key(rejection: str) -> str:
        if rejection == "blur":
            return "blurry"
        return rejection

    @staticmethod
    def _write_metadata(
        output_dir: str,
        video_path: str,
        video_fps: float,
        total_frames: int,
        frame_interval: int,
        frame_metadata: List[Dict[str, Any]],
        skipped_blurry: int,
        skipped_duplicate: int,
        skipped_overexposed: int,
        skipped_underexposed: int,
        skipped_motion_blur: int,
        jpeg_quality: int,
        preview_jpeg_quality: int,
        extraction_method: str,
        source_width: int,
        source_height: int,
        candidate_fps: Optional[float],
    ) -> None:
        metadata_path = os.path.join(output_dir, "frame_metadata.json")
        payload = {
            "video_path": video_path,
            "video_fps": video_fps,
            "total_source_frames": total_frames,
            "frame_interval": frame_interval,
            "frames_extracted": len(frame_metadata),
            "skipped_blurry": skipped_blurry,
            "skipped_duplicate": skipped_duplicate,
            "skipped_overexposed": skipped_overexposed,
            "skipped_underexposed": skipped_underexposed,
            "skipped_motion_blur": skipped_motion_blur,
            "jpeg_quality": jpeg_quality,
            "preview_jpeg_quality": preview_jpeg_quality,
            "image_enhancement": "none_source_preserved",
            "extraction_method": extraction_method,
            "candidate_fps": candidate_fps,
            "source_width": source_width,
            "source_height": source_height,
            "pipelines": {
                "inspection_frames": "source-preserved high-quality JPEGs for zoom review",
                "ui_previews": "downscaled JPEG previews only for grids and thumbnails",
                "ai_derived_images": "crops/enhancements are separate and never main inspection images",
            },
            "frames": frame_metadata,
        }
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _frame_interval(self, video_fps: float) -> int:
        """
        Convert requested extraction FPS to a source-frame interval.

        Returns at least 1 so callers can request dense sampling for fast
        walkarounds without modulo-by-zero or skipped-frame surprises.
        """
        if video_fps <= 0:
            fallback_source_fps = 30.0
            return max(1, int(round(fallback_source_fps / self.fps)))
        return max(1, int(round(video_fps / self.fps)))

    def _candidate_fps(self, video_fps: float) -> float:
        requested = self.fps * self.candidate_multiplier
        if video_fps > 0:
            return round(min(max(self.fps, requested), video_fps), 3)
        return round(requested, 3)

    @staticmethod
    def _video_properties(video_path: str) -> Tuple[float, int, int, int]:
        cap = cv2.VideoCapture(video_path)
        try:
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {video_path}")
            return (
                float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
                int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
                int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            )
        finally:
            cap.release()

    def _write_preview(self, frame: np.ndarray, output_dir: str, frame_filename: str) -> Optional[str]:
        if frame is None or frame.size == 0:
            return None
        h, w = frame.shape[:2]
        preview = frame
        if w > self.preview_max_width:
            scale = self.preview_max_width / float(w)
            preview = cv2.resize(
                frame,
                (self.preview_max_width, max(1, int(round(h * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        preview_path = os.path.join(output_dir, "previews", frame_filename)
        return preview_path if write_jpeg(preview_path, preview, self.preview_jpeg_quality) else None

    @staticmethod
    def _metadata_payload(
        *,
        extracted_index: int,
        source_frame_index: int,
        timestamp_seconds: Optional[float],
        path: str,
        preview_path: Optional[str],
        metrics: FrameQualityMetrics,
        frame: np.ndarray,
        source_width: Optional[int] = None,
        source_height: Optional[int] = None,
    ) -> Dict[str, Any]:
        h, w = frame.shape[:2]
        return {
            "extracted_index": extracted_index,
            "source_frame_index": source_frame_index,
            "timestamp_seconds": timestamp_seconds,
            "path": path,
            "inspection_path": path,
            "preview_path": preview_path,
            "width": int(w),
            "height": int(h),
            "source_width": int(source_width or w),
            "source_height": int(source_height or h),
            "aspect_ratio": round(float(w) / float(h), 5) if h else None,
            "blur_score": round(float(metrics.blur_score), 3),
            "brightness": round(float(metrics.brightness), 3),
            "contrast": round(float(metrics.contrast), 3),
            "overexposed_ratio": round(float(metrics.overexposed_ratio), 5),
            "underexposed_ratio": round(float(metrics.underexposed_ratio), 5),
            "motion_blur_score": round(float(metrics.motion_blur_score), 4),
            "quality_score": round(float(metrics.quality_score), 4),
            "exposure_state": metrics.exposure_state,
        }
