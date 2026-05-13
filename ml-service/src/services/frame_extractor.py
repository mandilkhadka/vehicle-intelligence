"""
Frame extraction service
Extracts frames from video using OpenCV with quality filtering
"""

import asyncio
import json
import os
from typing import Any, Dict, List

import cv2
import numpy as np

from src.utils.image_quality import enhance_image_for_analysis, write_jpeg


class FrameExtractor:
    """Extracts frames from video files with quality filtering"""

    def __init__(self, fps: int = 1, min_blur_threshold: float = 15.0, jpeg_quality: int = 98):
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
        """
        Calculate blur score using Laplacian variance
        Higher values indicate sharper images
        Args:
            frame: Image frame as numpy array
        Returns:
            Blur score (Laplacian variance)
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return laplacian_var

    def _enhance_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Enhance frame quality with contrast and detail adjustment
        Args:
            frame: Image frame as numpy array
        Returns:
            Enhanced frame
        """
        return enhance_image_for_analysis(frame, denoise=False)

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
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Open video file
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        # Get video properties
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Calculate frame interval from requested extraction FPS. A 60 FPS
        # video with fps=2 processes every 30th frame; fps=1 preserves the
        # previous default behavior.
        frame_interval = self._frame_interval(video_fps)

        frame_paths = []
        frame_metadata: List[Dict[str, Any]] = []
        frame_count = 0
        saved_count = 0
        last_saved_frame = None
        skipped_blurry = 0
        skipped_duplicate = 0

        print(f"Video FPS: {video_fps}, Total frames: {total_frames}")
        print(
            "Extraction settings: "
            f"target_fps={self.fps}, frame_interval={frame_interval}, "
            f"blur_threshold={self.min_blur_threshold}, jpeg_quality={self.jpeg_quality}"
        )

        # Extract frames with quality filtering
        while True:
            ret, frame = cap.read()

            if not ret:
                break

            # Process frame at specified interval
            if frame_count % frame_interval == 0:
                # Check blur score
                blur_score = self._calculate_blur_score(frame)
                
                if blur_score < self.min_blur_threshold:
                    skipped_blurry += 1
                    frame_count += 1
                    continue
                
                # Check for duplicates
                if last_saved_frame is not None and self._is_duplicate(frame, last_saved_frame):
                    skipped_duplicate += 1
                    frame_count += 1
                    continue
                
                # Enhance frame quality
                enhanced_frame = self._enhance_frame(frame)
                
                # Save frame as high-quality JPEG
                frame_filename = f"frame_{saved_count:04d}.jpg"
                frame_path = os.path.join(output_dir, frame_filename)
                
                # Save with high quality
                write_jpeg(frame_path, enhanced_frame, self.jpeg_quality)
                
                # Store path relative to backend uploads directory
                frame_paths.append(frame_path)
                frame_metadata.append({
                    "extracted_index": saved_count,
                    "source_frame_index": frame_count,
                    "timestamp_seconds": round(frame_count / video_fps, 3) if video_fps > 0 else None,
                    "path": frame_path,
                    "blur_score": round(float(blur_score), 3),
                })
                last_saved_frame = frame.copy()
                saved_count += 1

            frame_count += 1

        # Release video capture
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
            jpeg_quality=self.jpeg_quality,
        )
        return frame_paths

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
        jpeg_quality: int,
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
            "jpeg_quality": jpeg_quality,
            "image_enhancement": "clahe_unsharp",
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
