"""
Processing API endpoint
Main endpoint for video processing pipeline with proper error handling
"""

import os
import logging
import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from src.services.frame_extractor import FrameExtractor
from src.services.vehicle_identifier import VehicleIdentifier
from src.services.dashboard_detector import DashboardDetector
from src.services.odometer_reader import OdometerReader
from src.services.damage_detector import DamageDetector
from src.services.exhaust_classifier import ExhaustClassifier
from src.services.report_generator import ReportGenerator
from src.services.gemini_analyzer import GeminiAnalyzer
from src.services.model_registry import ModelRegistry
from src.utils.path_validator import path_validator

router = APIRouter()
logger = logging.getLogger(__name__)


def get_backend_root() -> str:
    """Get the backend root directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")


def convert_to_relative_path(abs_path: str, backend_root: str) -> str:
    """Convert absolute path to relative path for serving."""
    rel_path = os.path.relpath(abs_path, os.path.join(backend_root, "backend", "uploads"))
    return rel_path.replace("\\", "/")


def initialize_ml_services(model_registry: Optional[ModelRegistry] = None) -> Tuple[FrameExtractor, VehicleIdentifier, DashboardDetector,
                                       OdometerReader, DamageDetector, ExhaustClassifier, ReportGenerator,
                                       GeminiAnalyzer]:
    """
    Initialize all ML services and return them as a tuple.

    Args:
        model_registry: Pre-initialized ModelRegistry with loaded models.
                       If provided, services will use shared model instances.
                       If None, services will load models internally (legacy behavior).
    """
    init_start_time = time.time()

    # Get shared models from registry if available
    yolo_model = None
    clip_model = None
    clip_processor = None
    brand_text_embeddings = None
    brand_names = None

    if model_registry is not None and model_registry.is_initialized:
        logger.info("Using pre-loaded models from ModelRegistry")
        yolo_model = model_registry.get_yolo_model()
        clip_model = model_registry.get_clip_model()
        clip_processor = model_registry.get_clip_processor()
        brand_text_embeddings = model_registry.get_brand_text_embeddings()
        brand_names = model_registry.get_brand_names()
    else:
        logger.warning("ModelRegistry not available - services will load models internally")

    logger.info("Initializing FrameExtractor...")
    frame_extractor = FrameExtractor()
    logger.info(f"FrameExtractor initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing ReportGenerator...")
    report_generator = ReportGenerator()
    logger.info(f"ReportGenerator initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing OdometerReader...")
    odometer_reader = OdometerReader()
    logger.info(f"OdometerReader initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing VehicleIdentifier...")
    vehicle_identifier = VehicleIdentifier(
        yolo_model=yolo_model,
        clip_model=clip_model,
        clip_processor=clip_processor,
        brand_text_embeddings=brand_text_embeddings,
        brand_names=brand_names,
    )
    logger.info(f"VehicleIdentifier initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing DashboardDetector...")
    dashboard_detector = DashboardDetector(yolo_model=yolo_model)
    logger.info(f"DashboardDetector initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing DamageDetector...")
    damage_detector = DamageDetector(yolo_model=yolo_model)
    logger.info(f"DamageDetector initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing ExhaustClassifier...")
    exhaust_classifier = ExhaustClassifier(yolo_model=yolo_model)
    logger.info(f"ExhaustClassifier initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing GeminiAnalyzer...")
    gemini_analyzer = GeminiAnalyzer()
    logger.info(f"GeminiAnalyzer initialized ({time.time() - init_start_time:.2f}s)")

    total_init_time = time.time() - init_start_time
    logger.info(f"All ML services initialized successfully in {total_init_time:.2f} seconds")

    return (frame_extractor, vehicle_identifier, dashboard_detector,
            odometer_reader, damage_detector, exhaust_classifier, report_generator,
            gemini_analyzer)


async def extract_video_frames(frame_extractor: FrameExtractor, video_path: str,
                                inspection_id: str, backend_root: str) -> List[str]:
    """Extract frames from video and return relative paths."""
    frames_dir = os.path.join(backend_root, "backend", "uploads", "frames", inspection_id)
    os.makedirs(frames_dir, exist_ok=True)
    logger.info(f"Frames will be saved to: {frames_dir}")

    logger.info("Starting frame extraction (this may take a while for long videos)...")
    extraction_start = time.time()

    try:
        frames = await asyncio.wait_for(
            frame_extractor.extract_frames(video_path, output_dir=frames_dir),
            timeout=300.0  # 5 minute timeout
        )
        extraction_duration = time.time() - extraction_start
        logger.info(f"Frame extraction completed in {extraction_duration:.2f} seconds")
    except asyncio.TimeoutError:
        logger.error(f"Frame extraction timed out after 5 minutes for video: {video_path}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Frame extraction timed out. The video may be too long or corrupted."
        )
    except Exception as e:
        logger.error(f"Frame extraction failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract frames from video: {str(e)}"
        )

    # Convert to relative paths
    frames_relative = [convert_to_relative_path(f, backend_root) for f in frames]

    if not frames_relative:
        logger.error("Failed to extract frames from video")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to extract frames from video"
        )

    logger.info(f"Extracted {len(frames_relative)} frames from video")
    return frames_relative


async def read_odometer_from_image(odometer_reader: OdometerReader, odometer_image_path: str,
                                    backend_root: str) -> Dict[str, Any]:
    """Read odometer from provided image."""
    logger.info(f"Using provided odometer image: {odometer_image_path}")
    try:
        odometer_data = await asyncio.wait_for(
            odometer_reader.read([odometer_image_path]),
            timeout=60.0
        )
    except asyncio.TimeoutError:
        logger.warning("Odometer reading timed out, using default values")
        odometer_data = {
            "value": None,
            "confidence": 0.0,
            "speedometer_image_path": odometer_image_path
        }
    except Exception as e:
        logger.error(f"Odometer reading failed: {str(e)}", exc_info=True)
        odometer_data = {
            "value": None,
            "confidence": 0.0,
            "speedometer_image_path": odometer_image_path
        }

    # Convert path to relative
    if odometer_data.get("speedometer_image_path"):
        odometer_data["speedometer_image_path"] = convert_to_relative_path(
            odometer_data["speedometer_image_path"], backend_root)
    else:
        odometer_data["speedometer_image_path"] = convert_to_relative_path(
            odometer_image_path, backend_root)

    return odometer_data


async def read_odometer_from_frames(dashboard_detector: DashboardDetector,
                                     odometer_reader: OdometerReader,
                                     frames_absolute: List[str],
                                     backend_root: str) -> Dict[str, Any]:
    """Detect dashboard frames and read odometer."""
    dashboard_frames = await dashboard_detector.detect(frames_absolute)
    odometer_data = await odometer_reader.read(dashboard_frames)

    if odometer_data.get("speedometer_image_path"):
        odometer_data["speedometer_image_path"] = convert_to_relative_path(
            odometer_data["speedometer_image_path"], backend_root)

    return odometer_data


@router.post("/test")
async def test_endpoint():
    """Simple test endpoint to verify the service is receiving requests"""
    logger.info("TEST ENDPOINT CALLED - Service is receiving requests")
    return {
        "status": "ok",
        "message": "ML service is receiving requests",
        "timestamp": time.time()
    }


class ProcessRequest(BaseModel):
    """Request model for video processing with validation"""
    video_path: str = Field(..., description="Path to the video file")
    inspection_id: str = Field(..., description="Unique inspection identifier")
    odometer_image_path: Optional[str] = Field(None, description="Optional path to odometer image")


class ProcessResponse(BaseModel):
    """Response model for video processing"""
    inspection_id: str
    frames: List[str]
    vehicle_info: Dict[str, Any]
    odometer: Dict[str, Any]
    damage: Dict[str, Any]
    exhaust: Dict[str, Any]
    report: Dict[str, Any]
    gemini_analysis: Dict[str, Any]
    reference_image: Dict[str, Any]


@router.post("/process", response_model=ProcessResponse, status_code=status.HTTP_200_OK)
async def process_video(request: ProcessRequest, http_request: Request):
    """
    Process a video and extract vehicle inspection data.
    Orchestrates all ML services for complete vehicle inspection.

    Args:
        request: ProcessRequest containing video path, inspection ID, and optional odometer image
        http_request: FastAPI Request object to access app.state

    Returns:
        ProcessResponse with all extracted inspection data

    Raises:
        HTTPException: If processing fails at any stage
    """
    start_time = time.time()

    # Log request arrival
    logger.info("=" * 80)
    logger.info(f"RECEIVED PROCESS REQUEST - Inspection ID: {request.inspection_id}")
    logger.info(f"Video path: {request.video_path}")
    logger.info(f"Odometer image path: {request.odometer_image_path or 'None'}")
    logger.info("=" * 80)

    logger.info(f"Starting video processing for inspection {request.inspection_id}")

    try:
        # Validate input files
        _validate_input_files(request)

        # Get cached ML services from app.state (initialized at startup)
        ml_services = getattr(http_request.app.state, 'ml_services', None)
        if ml_services is not None:
            (frame_extractor, vehicle_identifier, dashboard_detector,
             odometer_reader, damage_detector, exhaust_classifier, report_generator,
             gemini_analyzer) = ml_services
            logger.debug("Using cached ML services from app.state")
        else:
            # Fallback: initialize per-request (should not happen in normal operation)
            logger.warning("ML services not found in app.state, initializing per-request")
            model_registry = getattr(http_request.app.state, 'model_registry', None)
            try:
                (frame_extractor, vehicle_identifier, dashboard_detector,
                 odometer_reader, damage_detector, exhaust_classifier, report_generator,
                 gemini_analyzer) = initialize_ml_services(model_registry)
            except Exception as e:
                logger.error(f"Failed to initialize ML services: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize ML services: {str(e)}"
                )

        backend_root = get_backend_root()

        # Step 1: Extract frames (must complete before parallel processing)
        logger.info(f"Step 1/3: Extracting frames from video: {request.video_path}")
        _log_video_size(request.video_path)
        frames = await extract_video_frames(frame_extractor, request.video_path,
                                             request.inspection_id, backend_root)

        # Prepare absolute paths for processing
        frames_absolute = [os.path.join(backend_root, "backend", "uploads", f) for f in frames]

        # Step 2: Run independent ML tasks in PARALLEL using asyncio.gather
        # This is a key performance optimization - these tasks have no dependencies on each other
        logger.info("Step 2/3: Running parallel ML processing (vehicle ID, odometer, damage, exhaust)...")
        parallel_start = time.time()

        # Define async wrapper functions for better error handling and logging
        async def identify_vehicle():
            logger.info("  [Parallel] Starting vehicle identification...")
            result = await vehicle_identifier.identify(frames)
            logger.info(f"  [Parallel] Vehicle identified: {result.get('type', 'unknown')} - "
                       f"{result.get('brand', 'unknown')} {result.get('model', 'unknown')}")
            return result

        async def process_odometer():
            logger.info("  [Parallel] Starting odometer reading...")
            result = await _process_odometer(request, odometer_reader, dashboard_detector,
                                             frames, backend_root)
            logger.info(f"  [Parallel] Odometer reading completed: {result.get('value', 'N/A')}")
            return result

        async def detect_damage():
            logger.info("  [Parallel] Starting damage detection...")
            result = await damage_detector.detect(frames_absolute, request.inspection_id)
            for loc in result.get("locations", []) or []:
                if loc.get("frame"):
                    loc["frame"] = convert_to_relative_path(loc["frame"], backend_root)
            logger.info(f"  [Parallel] Damage detection completed. Severity: {result.get('severity', 'unknown')}")
            return result

        async def classify_exhaust():
            logger.info("  [Parallel] Starting exhaust classification...")
            result = await exhaust_classifier.classify(frames_absolute, request.inspection_id)
            if result.get("exhaust_image_path"):
                result["exhaust_image_path"] = convert_to_relative_path(
                    result["exhaust_image_path"], backend_root)
            logger.info(f"  [Parallel] Exhaust classification completed. Type: {result.get('type', 'unknown')}")
            return result

        async def analyze_with_gemini():
            logger.info("  [Parallel] Starting Gemini multimodal frame analysis...")
            result = await gemini_analyzer.analyze(frames_absolute)
            if result.get("available"):
                vehicle = result.get("vehicle") or {}
                logger.info(
                    f"  [Parallel] Gemini analysis complete. "
                    f"Vehicle={vehicle.get('brand')} {vehicle.get('model')} ({vehicle.get('year')}) — "
                    f"per_frame={len(result.get('per_frame') or [])}"
                )
            else:
                logger.warning(f"  [Parallel] Gemini analysis unavailable: {result.get('reason')}")
            # Convert per-frame paths to relative paths so the frontend can render them.
            for entry in result.get("per_frame") or []:
                if entry.get("frame"):
                    entry["frame"] = convert_to_relative_path(entry["frame"], backend_root)
            return result

        # Execute all parallel ML tasks (including Gemini multimodal analysis).
        try:
            vehicle_info, odometer_data, damage_data, exhaust_data, gemini_data = await asyncio.gather(
                identify_vehicle(),
                process_odometer(),
                detect_damage(),
                classify_exhaust(),
                analyze_with_gemini(),
                return_exceptions=False  # Raise first exception immediately
            )
        except Exception as e:
            logger.error(f"Error during parallel processing: {str(e)}", exc_info=True)
            raise

        parallel_duration = time.time() - parallel_start
        logger.info(f"Parallel ML processing completed in {parallel_duration:.2f} seconds")

        # Merge Gemini's fine-grained vehicle ID into vehicle_info when available.
        # Gemini can name a specific model and year; CLIP zero-shot cannot.
        vehicle_info = _merge_vehicle_info(vehicle_info, gemini_data)

        reference_image = (gemini_data.get("reference_image") or {}) if gemini_data else {}

        # Step 3: Generate report (depends on all previous results, including Gemini)
        logger.info("Step 3/3: Generating inspection report...")
        report = await report_generator.generate({
            "vehicle_info": vehicle_info,
            "odometer": odometer_data,
            "damage": damage_data,
            "exhaust": exhaust_data,
            "gemini_analysis": gemini_data,
        })

        # Pack Gemini context into the persisted report so the frontend can show it.
        if isinstance(report, dict):
            report["gemini_analysis"] = gemini_data
            report["reference_image"] = reference_image

        processing_time = time.time() - start_time
        logger.info(f"Video processing completed for inspection {request.inspection_id} "
                   f"in {processing_time:.2f} seconds")

        return ProcessResponse(
            inspection_id=request.inspection_id,
            frames=frames,
            vehicle_info=vehicle_info,
            odometer=odometer_data,
            damage=damage_data,
            exhaust=exhaust_data,
            report=report,
            gemini_analysis=gemini_data,
            reference_image=reference_image,
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error during processing: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Validation error: {str(e)}")
    except FileNotFoundError as e:
        logger.error(f"File not found error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {str(e)}")
    except Exception as e:
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        detail = f"Failed to process video: {str(e)}" if os.getenv("NODE_ENV") != "production" else "Failed to process video"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _validate_input_files(request: ProcessRequest) -> None:
    """Validate that input files exist, are accessible, and are within allowed directories."""
    # Security: Validate paths are within allowed directories (defense in depth)
    try:
        path_validator.validate_or_raise(request.video_path, "video")
    except ValueError as e:
        logger.warning(f"Path validation failed for video: {request.video_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if request.odometer_image_path:
        try:
            path_validator.validate_or_raise(request.odometer_image_path, "odometer image")
        except ValueError as e:
            logger.warning(f"Path validation failed for odometer image: {request.odometer_image_path}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    # Check file existence
    if not os.path.exists(request.video_path):
        logger.error(f"Video file not found: {request.video_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file not found: {request.video_path}"
        )

    if not os.path.isfile(request.video_path):
        error_msg = f"Video file is not accessible: {request.video_path}"
        logger.error(error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if request.odometer_image_path and not os.path.exists(request.odometer_image_path):
        logger.warning(f"Odometer image not found: {request.odometer_image_path}, proceeding without it")
        request.odometer_image_path = None


def _log_video_size(video_path: str) -> None:
    """Log video file size for debugging."""
    try:
        video_size = os.path.getsize(video_path)
        logger.info(f"Video file size: {video_size / (1024*1024):.2f} MB")
    except Exception as e:
        logger.warning(f"Could not get video file size: {e}")


async def _process_odometer(request: ProcessRequest, odometer_reader: OdometerReader,
                            dashboard_detector: DashboardDetector, frames: List[str],
                            backend_root: str) -> Dict[str, Any]:
    """Process odometer reading from image or video frames."""
    if request.odometer_image_path and os.path.exists(request.odometer_image_path):
        return await read_odometer_from_image(odometer_reader, request.odometer_image_path, backend_root)
    else:
        frames_absolute = [os.path.join(backend_root, "backend", "uploads", f) for f in frames]
        return await read_odometer_from_frames(dashboard_detector, odometer_reader, frames_absolute, backend_root)


def _merge_vehicle_info(base_info: Dict[str, Any], gemini_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Override CLIP/YOLO results with Gemini's identification when available.
    Gemini reads badges + body shape and is far better at naming a specific model
    and year. We keep the original confidence as a fallback signal.
    """
    if not gemini_data or not gemini_data.get("available"):
        return base_info

    g_vehicle = gemini_data.get("vehicle") or {}
    merged = dict(base_info or {})

    # Prefer Gemini for these fields whenever it returned a non-empty value.
    for key in ("type", "brand", "model", "color"):
        g_val = g_vehicle.get(key)
        if g_val and str(g_val).strip().lower() not in ("", "unknown", "null", "none"):
            merged[key] = g_val

    # New fields Gemini provides that CLIP cannot.
    if g_vehicle.get("year"):
        merged["year"] = g_vehicle.get("year")
    if g_vehicle.get("variant"):
        merged["variant"] = g_vehicle.get("variant")

    # Take the higher of the two confidences so a confident Gemini lifts the score.
    g_conf = g_vehicle.get("confidence")
    try:
        g_conf_f = float(g_conf) if g_conf is not None else 0.0
    except (TypeError, ValueError):
        g_conf_f = 0.0
    base_conf = float(merged.get("confidence") or 0.0)
    merged["confidence"] = max(base_conf, g_conf_f)

    return merged
