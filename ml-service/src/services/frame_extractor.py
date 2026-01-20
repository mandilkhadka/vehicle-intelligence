"""
Frame extraction service
Extracts frames from video using OpenCV with quality filtering
"""

import cv2
import os
import numpy as np
from typing import List
import asyncio
from pathlib import Path


class FrameExtractor:
    """Extracts frames from video files with quality filtering"""

    def __init__(self, fps: int = 1, min_blur_threshold: float = 100.0, jpeg_quality: int = 98):
        """
        Initialize frame extractor
        Args:
            fps: Frames per second to extract (default: 1 frame per second)
            min_blur_threshold: Minimum Laplacian variance to consider frame sharp (default: 100.0)
            jpeg_quality: JPEG quality (1-100, default: 98)
        """
        self.fps = fps
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
        Enhance frame quality with sharpening and contrast adjustment
        Args:
            frame: Image frame as numpy array
        Returns:
            Enhanced frame
        """
        # Convert to LAB color space for better processing
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge channels and convert back to BGR
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        # Apply slight sharpening
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]]) / 1.0
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        
        # Blend original and sharpened (70% sharpened, 30% original)
        result = cv2.addWeighted(sharpened, 0.7, enhanced, 0.3, 0)
        
        return result

    def _is_duplicate(self, frame1: np.ndarray, frame2: np.ndarray, threshold: float = 0.95) -> bool:
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
        
        return correlation > threshold

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
        duration = total_frames / video_fps if video_fps > 0 else 0

        # Calculate frame interval
        # Extract 1 frame per second
        frame_interval = int(video_fps) if video_fps > 0 else 30

        frame_paths = []
        frame_count = 0
        saved_count = 0
        last_saved_frame = None
        skipped_blurry = 0
        skipped_duplicate = 0

        print(f"Video FPS: {video_fps}, Total frames: {total_frames}")
        print(f"Quality settings: blur_threshold={self.min_blur_threshold}, jpeg_quality={self.jpeg_quality}")

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
                cv2.imwrite(
                    frame_path, 
                    enhanced_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                )
                
                # Store path relative to backend uploads directory
                frame_paths.append(frame_path)
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

        return frame_paths
