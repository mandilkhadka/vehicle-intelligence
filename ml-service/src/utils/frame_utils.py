"""
Frame selection utilities shared across ML services.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


def select_frames(frame_paths: List[str], max_frames: int, caller: str = "") -> List[str]:
    """
    Select evenly-spaced frames from the input list.
    Ensures good coverage across the entire 360-degree video.

    Args:
        frame_paths: Full list of frame paths
        max_frames: Maximum number of frames to select
        caller: Optional caller name for logging

    Returns:
        List of evenly-spaced frame paths
    """
    if len(frame_paths) <= max_frames:
        return frame_paths

    step = len(frame_paths) / max_frames
    selected_indices = [int(i * step) for i in range(max_frames)]
    selected_frames = [frame_paths[i] for i in selected_indices]

    prefix = f"{caller}: " if caller else ""
    logger.info(f"{prefix}Selected {len(selected_frames)} frames from {len(frame_paths)} total (evenly spaced)")
    return selected_frames
