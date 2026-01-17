"""
Frame extraction service
Extracts frames from video using OpenCV
"""

import cv2
import os
from typing import List
import asyncio
from pathlib import Path


class FrameExtractor:
    """Extracts frames from video files"""

    def __init__(self, fps: int = 1):
        """
        Initialize frame extractor
        Args:
            fps: Frames per second to extract (default: 1 frame per second)
        """
        self.fps = fps

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

    def _extract_frames_sync(
        self, video_path: str, output_dir: str
    ) -> List[str]:
        """
        Synchronous frame extraction
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
        duration = total_frames / video_fps if video_fps > 0 else 0

        # Calculate frame interval
        # Extract 1 frame per second
        frame_interval = int(video_fps) if video_fps > 0 else 30

        frame_paths = []
        frame_count = 0
        saved_count = 0

        print(f"Video FPS: {video_fps}, Total frames: {total_frames}")

        # Extract frames
        while True:
            ret, frame = cap.read()

            if not ret:
                break

            # Save frame at specified interval
            if frame_count % frame_interval == 0:
                frame_filename = f"frame_{saved_count:04d}.jpg"
                frame_path = os.path.join(output_dir, frame_filename)

                # Save frame as JPEG
                cv2.imwrite(frame_path, frame)
                # Store path relative to backend uploads directory
                # Backend serves from uploads/, so we need frames/ subdirectory
                frame_paths.append(frame_path)
                saved_count += 1

            frame_count += 1

        # Release video capture
        cap.release()

        print(f"Extracted {len(frame_paths)} frames from video")

        return frame_paths
