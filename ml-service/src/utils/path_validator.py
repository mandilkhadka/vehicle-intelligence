"""
Path validation utility to prevent directory traversal attacks.

Defense in depth: Backend already uses absolute paths, but this
provides an extra layer of protection at the ML service boundary.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PathValidator:
    """
    Validates file paths to prevent directory traversal attacks.

    Usage:
        validator = PathValidator(["/path/to/uploads"])
        if validator.is_safe_path(user_provided_path):
            # Safe to use

        # Or raise on invalid:
        safe_path = validator.validate_or_raise(user_provided_path, "video")
    """

    def __init__(self, allowed_base_paths: list[str] | None = None):
        """
        Initialize the path validator.

        Args:
            allowed_base_paths: List of allowed base directories.
                               If None, loads from ALLOWED_UPLOAD_PATHS env var.
                               Defaults to ../backend/uploads if not configured.
        """
        if allowed_base_paths is None:
            env_paths = os.environ.get("ALLOWED_UPLOAD_PATHS", "")
            allowed_base_paths = [p.strip() for p in env_paths.split(",") if p.strip()]

            # Default to ../backend/uploads if not configured
            if not allowed_base_paths:
                project_root = Path(__file__).parent.parent.parent.parent
                allowed_base_paths = [str(project_root / "backend" / "uploads")]

        self.allowed_base_paths = []
        for p in allowed_base_paths:
            try:
                resolved = Path(p).resolve()
                self.allowed_base_paths.append(resolved)
            except (ValueError, OSError) as e:
                logger.warning(f"Invalid allowed path '{p}': {e}")

        logger.info(f"PathValidator initialized with allowed paths: {self.allowed_base_paths}")

    def is_safe_path(self, file_path: str) -> bool:
        """
        Check if path is within allowed directories.

        Args:
            file_path: The path to validate.

        Returns:
            True if the path is within an allowed directory, False otherwise.
        """
        if not file_path:
            return False

        try:
            resolved = Path(file_path).resolve()
            return any(
                self._is_subpath(resolved, base)
                for base in self.allowed_base_paths
            )
        except (ValueError, OSError):
            return False

    def _is_subpath(self, path: Path, parent: Path) -> bool:
        """
        Check if path is under parent directory.

        Args:
            path: The path to check.
            parent: The parent directory.

        Returns:
            True if path is a subpath of parent.
        """
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def validate_or_raise(self, file_path: str, context: str = "file") -> Path:
        """
        Validate path and raise if unsafe.

        Args:
            file_path: The path to validate.
            context: Description for error message (e.g., "video", "image").

        Returns:
            The resolved Path if valid.

        Raises:
            ValueError: If path is not within allowed directories.
        """
        if not self.is_safe_path(file_path):
            logger.warning(f"Path validation failed for {context}: {file_path}")
            raise ValueError(f"Invalid {context} path: access denied")
        return Path(file_path).resolve()


# Singleton instance for use across the service
path_validator = PathValidator()
