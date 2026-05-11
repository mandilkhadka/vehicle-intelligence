"""
Pytest configuration and shared fixtures for ML Service tests.

This file provides common fixtures and configuration used across all test modules.
Generated: 2026-01-27
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator, Dict, Any

import pytest

# Add src directory to Python path for imports
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


# ===========================================================================
# Environment Configuration
# ===========================================================================

@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """
    Configure environment variables for testing.

    Sets up test-specific configuration to isolate tests from production.
    """
    # Set test environment
    os.environ.setdefault("NODE_ENV", "test")
    os.environ.setdefault("LOG_LEVEL", "WARNING")

    # Disable rate limiting for tests
    os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

    # Use mock mode if GEMINI_API_KEY not set
    if not os.environ.get("GEMINI_API_KEY"):
        os.environ.setdefault("MOCK_MODE", "true")

    yield

    # Cleanup (optional)


# ===========================================================================
# Test Directories
# ===========================================================================

@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """
    Return path to test data directory.

    Creates the directory if it doesn't exist.
    """
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture(scope="function")
def temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for each test.

    Automatically cleaned up after test completion.
    """
    with tempfile.TemporaryDirectory(prefix="vip_ml_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="session")
def session_temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory shared across session.

    Cleaned up after all tests complete.
    """
    with tempfile.TemporaryDirectory(prefix="vip_ml_session_") as tmpdir:
        yield Path(tmpdir)


# ===========================================================================
# FastAPI Test Client
# ===========================================================================

@pytest.fixture(scope="module")
def app():
    """
    Create FastAPI application instance for testing.

    Returns the configured app without running the server.
    """
    # Import here to avoid import errors if FastAPI not installed
    try:
        from main import app as fastapi_app
        return fastapi_app
    except ImportError:
        pytest.skip("FastAPI application not available")


@pytest.fixture(scope="module")
def client(app):
    """
    Create TestClient for synchronous API tests.
    """
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except ImportError:
        pytest.skip("FastAPI TestClient not available")


@pytest.fixture
async def async_client(app):
    """
    Create AsyncClient for asynchronous API tests.
    """
    try:
        from httpx import AsyncClient
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    except ImportError:
        pytest.skip("httpx AsyncClient not available")


# ===========================================================================
# Mock Data Fixtures
# ===========================================================================

@pytest.fixture
def mock_vehicle_info() -> Dict[str, Any]:
    """Return mock vehicle identification data."""
    return {
        "type": "car",
        "brand": "Toyota",
        "model": "Camry",
        "color": "Silver",
        "confidence": 0.92
    }


@pytest.fixture
def mock_odometer_info() -> Dict[str, Any]:
    """Return mock odometer reading data."""
    return {
        "value": 45000,
        "confidence": 0.85,
        "speedometer_image_path": "uploads/frames/speedometer.jpg"
    }


@pytest.fixture
def mock_damage_info() -> Dict[str, Any]:
    """Return mock damage detection data."""
    return {
        "scratches": {"count": 2, "detected": True},
        "dents": {"count": 1, "detected": True},
        "rust": {"count": 0, "detected": False},
        "severity": "medium",
        "locations": [
            {
                "type": "scratch",
                "frame": "frame_001.jpg",
                "confidence": 0.78,
                "bbox": [100, 200, 50, 30]
            },
            {
                "type": "scratch",
                "frame": "frame_002.jpg",
                "confidence": 0.72,
                "bbox": [150, 180, 40, 25]
            },
            {
                "type": "dent",
                "frame": "frame_003.jpg",
                "confidence": 0.65,
                "bbox": [200, 150, 60, 60]
            }
        ]
    }


@pytest.fixture
def mock_exhaust_info() -> Dict[str, Any]:
    """Return mock exhaust classification data."""
    return {
        "type": "stock",
        "confidence": 0.95,
        "exhaust_image_path": "uploads/frames/exhaust.jpg"
    }


@pytest.fixture
def mock_inspection_report() -> Dict[str, Any]:
    """Return mock inspection report data."""
    return {
        "summary": "Vehicle is in good overall condition with minor cosmetic damage.",
        "vehicle_details": {
            "type": "car",
            "brand": "Toyota",
            "model": "Camry",
            "condition": "Good"
        },
        "odometer_reading": {
            "value": 45000,
            "status": "Within expected range"
        },
        "damage_assessment": {
            "overall_severity": "medium",
            "details": "Minor scratches on driver side, small dent on rear bumper."
        },
        "exhaust_status": {
            "type": "stock",
            "notes": "Original manufacturer exhaust system."
        },
        "recommendations": [
            "Consider touch-up paint for scratches",
            "Monitor rear bumper dent for rust",
            "Schedule regular maintenance"
        ]
    }


@pytest.fixture
def mock_complete_inspection(
    mock_vehicle_info,
    mock_odometer_info,
    mock_damage_info,
    mock_exhaust_info,
    mock_inspection_report
) -> Dict[str, Any]:
    """Return complete mock inspection data."""
    import uuid
    return {
        "inspection_id": str(uuid.uuid4()),
        "frames": ["frame_001.jpg", "frame_002.jpg", "frame_003.jpg"],
        "vehicle_info": mock_vehicle_info,
        "odometer": mock_odometer_info,
        "damage": mock_damage_info,
        "exhaust": mock_exhaust_info,
        "report": mock_inspection_report
    }


# ===========================================================================
# File Fixtures
# ===========================================================================

@pytest.fixture
def mock_video_file(temp_dir: Path) -> Path:
    """
    Create a mock video file for testing.

    Note: This creates a fake file, not a real video.
    For real video testing, use fixtures from test_data_dir.
    """
    video_path = temp_dir / "test_video.mp4"
    video_path.write_bytes(b"mock video content" * 1000)
    return video_path


@pytest.fixture
def mock_image_file(temp_dir: Path) -> Path:
    """
    Create a mock image file for testing.

    Note: This creates a fake file, not a real image.
    """
    image_path = temp_dir / "test_image.jpg"
    image_path.write_bytes(b"mock image content" * 100)
    return image_path


@pytest.fixture
def mock_frame_files(temp_dir: Path) -> list:
    """
    Create multiple mock frame files for testing.
    """
    frames = []
    for i in range(5):
        frame_path = temp_dir / f"frame_{i:04d}.jpg"
        frame_path.write_bytes(f"mock frame {i} content".encode() * 100)
        frames.append(frame_path)
    return frames


# ===========================================================================
# Markers Configuration
# ===========================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "requires_ml_models: marks tests that require ML models to be loaded"
    )
    config.addinivalue_line(
        "markers", "requires_gemini: marks tests that require Gemini API access"
    )
