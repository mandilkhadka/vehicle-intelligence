"""
Processing API endpoint
Main endpoint for video processing pipeline with proper error handling
"""

import os
import logging
import asyncio
import time
import threading
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from src.services.frame_extractor import FrameExtractor
from src.services.frame_organizer import EXTERIOR_VIEWS, REVIEW_REQUIRED_VIEWS, VehicleFrameOrganizer
from src.services.vehicle_identifier import VehicleIdentifier
from src.services.dashboard_detector import DashboardDetector
from src.services.odometer_reader import OdometerReader
from src.services.damage_detector import DamageDetector
from src.services.exhaust_classifier import ExhaustClassifier
from src.services.modification_detector import ModificationDetector
from src.services.inspection_analysis import InspectionAnalysisPipeline
from src.services.report_generator import ReportGenerator
from src.services.gemini_analyzer import GeminiAnalyzer
from src.services.model_registry import ModelRegistry
from src.config.constants import FRAME_EXTRACTION
from src.utils.image_quality import enhance_image_for_analysis, read_image_with_orientation, write_jpeg
from src.utils.path_validator import path_validator

router = APIRouter()
logger = logging.getLogger(__name__)
SAFE_INSPECTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def get_backend_root() -> str:
    """Get the backend root directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")


def get_uploads_root(backend_root: Optional[str] = None) -> str:
    """Get the shared uploads directory used for videos and generated frames."""
    configured = os.getenv("UPLOADS_ROOT", "").strip()
    if configured:
        return os.path.abspath(configured)
    root = backend_root or get_backend_root()
    return os.path.abspath(os.path.join(root, "backend", "uploads"))


def convert_to_relative_path(abs_path: str, backend_root: str) -> str:
    """Convert absolute path to relative path for serving."""
    uploads_root = Path(get_uploads_root(backend_root)).resolve()
    resolved = Path(abs_path).resolve()
    try:
        rel_path = resolved.relative_to(uploads_root)
    except ValueError as exc:
        raise ValueError("Refusing to expose path outside uploads root") from exc
    return rel_path.as_posix()


def upload_path(relative_path: str, backend_root: str) -> str:
    """Convert an uploads-relative path into an absolute path."""
    uploads_root = Path(get_uploads_root(backend_root)).resolve()
    candidate = Path(relative_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (uploads_root / candidate).resolve()
    try:
        resolved.relative_to(uploads_root)
    except ValueError as exc:
        raise ValueError("Refusing to access path outside uploads root") from exc
    return str(resolved)


def _frame_extraction_config() -> Dict[str, Any]:
    """Read frame extraction settings with environment overrides."""
    return {
        "fps": _env_float("ML_FRAME_EXTRACTION_FPS", FRAME_EXTRACTION["fps"]),
        "min_blur_threshold": _env_float(
            "ML_FRAME_BLUR_THRESHOLD",
            FRAME_EXTRACTION["min_blur_threshold"],
        ),
        "jpeg_quality": _env_int("ML_FRAME_JPEG_QUALITY", FRAME_EXTRACTION["jpeg_quality"]),
    }


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return int(default)
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return int(default)


def initialize_ml_services(model_registry: Optional[ModelRegistry] = None) -> Tuple[FrameExtractor, VehicleFrameOrganizer,
                                       VehicleIdentifier, DashboardDetector,
                                       OdometerReader, DamageDetector, ExhaustClassifier, ModificationDetector,
                                       ReportGenerator, GeminiAnalyzer]:
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

    frame_extraction_config = _frame_extraction_config()

    logger.info("Initializing FrameExtractor...")
    frame_extractor = FrameExtractor(**frame_extraction_config)
    logger.info(f"FrameExtractor config: {frame_extraction_config}")
    logger.info(f"FrameExtractor initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing VehicleFrameOrganizer...")
    frame_organizer = VehicleFrameOrganizer(
        yolo_model=yolo_model,
        clip_model=clip_model,
        clip_processor=clip_processor,
    )
    logger.info(f"VehicleFrameOrganizer initialized ({time.time() - init_start_time:.2f}s)")

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

    logger.info("Initializing ModificationDetector...")
    modification_detector = ModificationDetector(
        clip_model=clip_model,
        clip_processor=clip_processor,
    )
    logger.info(f"ModificationDetector initialized ({time.time() - init_start_time:.2f}s)")

    logger.info("Initializing GeminiAnalyzer...")
    gemini_analyzer = GeminiAnalyzer()
    logger.info(f"GeminiAnalyzer initialized ({time.time() - init_start_time:.2f}s)")

    total_init_time = time.time() - init_start_time
    logger.info(f"All ML services initialized successfully in {total_init_time:.2f} seconds")

    return (frame_extractor, frame_organizer, vehicle_identifier, dashboard_detector,
            odometer_reader, damage_detector, exhaust_classifier, modification_detector, report_generator,
            gemini_analyzer)


async def extract_video_frames(frame_extractor: FrameExtractor, video_path: str,
                                inspection_id: str, backend_root: str) -> List[str]:
    """Extract frames from video and return relative paths."""
    frames_dir = os.path.join(get_uploads_root(backend_root), "frames", inspection_id)
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
    odometer_image_candidates = _uploaded_odometer_image_candidates(odometer_image_path)
    try:
        odometer_data = await asyncio.wait_for(
            odometer_reader.read(odometer_image_candidates),
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


def _uploaded_odometer_image_candidates(odometer_image_path: str) -> List[str]:
    """Prefer an enhanced readable copy while preserving the uploaded original."""
    candidates = [odometer_image_path]
    try:
        image = read_image_with_orientation(odometer_image_path)
        if image is None:
            return candidates

        source = Path(odometer_image_path)
        enhanced_path = source.with_name(f"{source.stem}_enhanced.jpg")
        enhanced = enhance_image_for_analysis(
            image,
            min_width=1200,
            min_height=900,
            denoise=True,
        )
        if write_jpeg(enhanced_path, enhanced, 98):
            return [str(enhanced_path), odometer_image_path]
    except Exception as e:
        logger.warning("Failed to enhance uploaded odometer image %s: %s", odometer_image_path, e)
    return candidates


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
    vehicle_identity_override: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional trusted VIN/registration/manual identity fields for exact year/trim verification",
    )

    @field_validator("inspection_id")
    @classmethod
    def validate_inspection_id(cls, value: str) -> str:
        if not SAFE_INSPECTION_ID_RE.fullmatch(value):
            raise ValueError("inspection_id must be a safe identifier")
        return value


class ProcessResponse(BaseModel):
    """Response model for video processing"""
    inspection_id: str
    frames: List[str]
    frame_analysis: Dict[str, Any]
    vehicle_info: Dict[str, Any]
    odometer: Dict[str, Any]
    damage: Dict[str, Any]
    exhaust: Dict[str, Any]
    report: Dict[str, Any]
    gemini_analysis: Dict[str, Any]
    inspection_analysis: Dict[str, Any]
    reference_image: Dict[str, Any]


class RetryVlmRequest(BaseModel):
    """Request model for rerunning only the VLM pass from organized frames."""
    inspection_id: str = Field(..., description="Unique inspection identifier")
    frame_analysis: Dict[str, Any] = Field(..., description="Saved frame analysis with organized frame paths")
    vehicle_info: Dict[str, Any] = Field(default_factory=dict, description="Existing vehicle info to merge VLM identity into")
    report: Dict[str, Any] = Field(default_factory=dict, description="Existing report to update with VLM analysis")

    @field_validator("inspection_id")
    @classmethod
    def validate_inspection_id(cls, value: str) -> str:
        if not SAFE_INSPECTION_ID_RE.fullmatch(value):
            raise ValueError("inspection_id must be a safe identifier")
        return value


class RetryVlmResponse(BaseModel):
    """Response model for rerun VLM analysis."""
    inspection_id: str
    gemini_analysis: Dict[str, Any]
    inspection_analysis: Dict[str, Any]
    vehicle_info: Dict[str, Any]
    report: Dict[str, Any]


@router.post("/retry-vlm", response_model=RetryVlmResponse, status_code=status.HTTP_200_OK)
async def retry_vlm_analysis(request: RetryVlmRequest, http_request: Request):
    """Rerun the VLM analysis step using already organized representative frames."""
    backend_root = get_backend_root()
    try:
        frame_analysis_abs = _absolutize_frame_analysis(request.frame_analysis, backend_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    organized_frames_absolute = _frames_from_frame_analysis(frame_analysis_abs, fallback=[])
    if not organized_frames_absolute:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No organized representative frames found for VLM retry",
        )

    ml_services = getattr(http_request.app.state, 'ml_services', None)
    if ml_services is not None:
        gemini_analyzer = ml_services[-1]
    else:
        model_registry = getattr(http_request.app.state, 'model_registry', None)
        *_, gemini_analyzer = initialize_ml_services(model_registry)

    logger.info(
        "Retrying VLM analysis for inspection %s with %d organized frames",
        request.inspection_id,
        len(organized_frames_absolute),
    )
    gemini_data = await gemini_analyzer.analyze(organized_frames_absolute, frame_analysis_abs)
    _relativize_gemini_analysis_paths(gemini_data, backend_root)

    vehicle_info = _merge_vehicle_info(dict(request.vehicle_info or {}), gemini_data)
    frame_analysis_rel = _relativize_frame_analysis(frame_analysis_abs, backend_root)
    inspection_analysis = await InspectionAnalysisPipeline().analyze(
        frame_analysis=frame_analysis_rel,
        vehicle_info=vehicle_info,
        damage={},
        exhaust={},
        vlm_result=gemini_data,
    )
    report = dict(request.report or {})
    report["gemini_analysis"] = gemini_data
    report["inspection_analysis"] = inspection_analysis
    report["visual_analysis"] = {
        "available": bool(gemini_data.get("available")),
        "reason": gemini_data.get("reason"),
        "provider": gemini_data.get("provider"),
    }
    report["vehicle_details"] = {
        **(report.get("vehicle_details") if isinstance(report.get("vehicle_details"), dict) else {}),
        **vehicle_info,
    }
    report.pop("pipeline_audit", None)

    return RetryVlmResponse(
        inspection_id=request.inspection_id,
        gemini_analysis=gemini_data,
        inspection_analysis=inspection_analysis,
        vehicle_info=vehicle_info,
        report=report,
    )


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
            if len(ml_services) == 10:
                (frame_extractor, frame_organizer, vehicle_identifier, dashboard_detector,
                 odometer_reader, damage_detector, exhaust_classifier, modification_detector, report_generator,
                 gemini_analyzer) = ml_services
            else:
                (frame_extractor, frame_organizer, vehicle_identifier, dashboard_detector,
                 odometer_reader, damage_detector, exhaust_classifier, report_generator,
                 gemini_analyzer) = ml_services
                modification_detector = None
            logger.debug("Using cached ML services from app.state")
        else:
            # Fallback: initialize per-request (should not happen in normal operation)
            logger.warning("ML services not found in app.state, initializing per-request")
            model_registry = getattr(http_request.app.state, 'model_registry', None)
            try:
                (frame_extractor, frame_organizer, vehicle_identifier, dashboard_detector,
                 odometer_reader, damage_detector, exhaust_classifier, modification_detector, report_generator,
                 gemini_analyzer) = initialize_ml_services(model_registry)
            except Exception as e:
                logger.error(f"Failed to initialize ML services: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize ML services: {str(e)}"
                )

        backend_root = get_backend_root()

        # Step 1: Extract frames (must complete before parallel processing)
        logger.info(f"Step 1/4: Extracting frames from video: {request.video_path}")
        _log_video_size(request.video_path)
        frames = await extract_video_frames(frame_extractor, request.video_path,
                                             request.inspection_id, backend_root)

        # Prepare absolute paths for processing
        frames_absolute = [upload_path(f, backend_root) for f in frames]

        # Organize frames before downstream OCR/VLM work so the rest of the
        # pipeline receives clean representative angle/dashboard shots.
        logger.info("Step 2/4: Organizing vehicle angle and dashboard frames...")
        frame_analysis_abs = await frame_organizer.organize(frames_absolute, request.inspection_id)
        frame_analysis = _relativize_frame_analysis(frame_analysis_abs, backend_root)
        organized_frames_absolute = _frames_from_frame_analysis(frame_analysis_abs, fallback=frames_absolute)
        surface_frames_absolute = _surface_frames_from_frame_analysis(frame_analysis_abs, fallback=frames_absolute)
        logger.info(
            "Frame organization complete. coverage=%s representative_frames=%d dashboard_candidates=%d",
            frame_analysis.get("coverage", {}).get("ratio"),
            len(frame_analysis.get("representative_frames") or []),
            len(frame_analysis.get("dashboard_candidates") or []),
        )

        # Step 3: Run independent ML tasks in PARALLEL using asyncio.gather
        # This is a key performance optimization - these tasks have no dependencies on each other
        logger.info("Step 3/4: Running parallel ML processing (vehicle ID, odometer, damage, exhaust)...")
        parallel_start = time.time()

        # Define async wrapper functions for better error handling and logging
        async def identify_vehicle():
            logger.info("  [Parallel] Starting vehicle identification...")
            result = await vehicle_identifier.identify(organized_frames_absolute)
            logger.info(f"  [Parallel] Vehicle identified: {result.get('type', 'unknown')} - "
                       f"{result.get('brand', 'unknown')} {result.get('model', 'unknown')}")
            return result

        async def process_odometer():
            logger.info("  [Parallel] Starting odometer reading...")
            result = await _process_odometer(request, odometer_reader, dashboard_detector,
                                             frames, backend_root, frame_analysis_abs)
            logger.info(f"  [Parallel] Odometer reading completed: {result.get('value', 'N/A')}")
            return result

        async def detect_damage():
            logger.info("  [Parallel] Starting damage detection...")
            result = await damage_detector.detect(surface_frames_absolute, request.inspection_id)
            _attach_damage_angle_metadata(result, frame_analysis_abs)
            for loc in result.get("locations", []) or []:
                if loc.get("frame"):
                    loc["frame"] = convert_to_relative_path(loc["frame"], backend_root)
            logger.info(f"  [Parallel] Damage detection completed. Severity: {result.get('severity', 'unknown')}")
            return result

        async def classify_exhaust():
            logger.info("  [Parallel] Starting exhaust classification...")
            result = await exhaust_classifier.classify(surface_frames_absolute, request.inspection_id)
            if result.get("exhaust_image_path"):
                if os.path.isabs(str(result["exhaust_image_path"])):
                    result["exhaust_image_path"] = convert_to_relative_path(
                        result["exhaust_image_path"], backend_root)
            logger.info(f"  [Parallel] Exhaust classification completed. Type: {result.get('type', 'unknown')}")
            return result

        async def analyze_with_gemini():
            logger.info("  [Parallel] Starting Gemini multimodal frame analysis...")
            result = await gemini_analyzer.analyze(organized_frames_absolute, frame_analysis_abs)
            if result.get("available"):
                vehicle = result.get("vehicle") or {}
                logger.info(
                    f"  [Parallel] Gemini analysis complete. "
                    f"Vehicle={vehicle.get('brand')} {vehicle.get('model')} ({vehicle.get('year')}) — "
                    f"per_frame={len(result.get('per_frame') or [])}"
                )
            else:
                logger.warning(f"  [Parallel] Gemini analysis unavailable: {result.get('reason')}")
            _relativize_gemini_analysis_paths(result, backend_root)
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
        _merge_visual_damage_categories(damage_data, gemini_data)

        # Merge Gemini's fine-grained vehicle ID into vehicle_info when available.
        # Gemini can name a specific model and year; CLIP zero-shot cannot.
        vehicle_info = _merge_vehicle_info(vehicle_info, gemini_data)
        vehicle_info = _merge_vehicle_identity_override(vehicle_info, request.vehicle_identity_override)

        reference_image = (gemini_data.get("reference_image") or {}) if gemini_data else {}

        logger.info("Step 3a/4: Validating and routing inspection images into canonical sections...")
        inspection_analysis = await InspectionAnalysisPipeline().analyze(
            frame_analysis=frame_analysis,
            vehicle_info=vehicle_info,
            damage=damage_data,
            exhaust=exhaust_data,
            vlm_result=gemini_data,
        )
        logger.info(
            "Inspection analysis complete. sections=%s rejected=%d conflicts=%d",
            len(inspection_analysis.get("consistency", {}).get("present_sections") or []),
            len(inspection_analysis.get("rejected_images") or []),
            len(inspection_analysis.get("consistency", {}).get("conflicts_resolved") or []),
        )

        logger.info("Step 3b/4: Running local multi-part modification analysis...")
        if modification_detector is not None:
            modification_data = await modification_detector.detect(
                surface_frames_absolute,
                frame_analysis_abs,
                exhaust_data,
            )
        else:
            modification_data = {
                "available": False,
                "reason": "ModificationDetector service unavailable",
                "items": [],
            }
        modification_data = _relativize_modification_analysis_paths(modification_data, backend_root)

        # Step 4: Generate report (depends on all previous results, including Gemini)
        logger.info("Step 4/4: Generating inspection report...")
        report = await report_generator.generate({
            "vehicle_info": vehicle_info,
            "odometer": odometer_data,
            "damage": damage_data,
            "exhaust": exhaust_data,
            "modification": modification_data,
            "gemini_analysis": gemini_data,
            "inspection_analysis": inspection_analysis,
            "frame_analysis": frame_analysis,
        })

        # Pack Gemini context into the persisted report so the frontend can show it.
        if isinstance(report, dict):
            report["gemini_analysis"] = gemini_data
            report["reference_image"] = reference_image
            report["frame_analysis"] = frame_analysis
            report["inspection_analysis"] = inspection_analysis
            report["local_modification_analysis"] = modification_data
            report["pipeline_audit"] = _build_process_pipeline_audit(
                frame_analysis=frame_analysis,
                vehicle_info=vehicle_info,
                odometer=odometer_data,
                damage=damage_data,
                exhaust=exhaust_data,
                report=report,
                gemini_analysis=gemini_data,
                inspection_analysis=inspection_analysis,
            )

        processing_time = time.time() - start_time
        logger.info(f"Video processing completed for inspection {request.inspection_id} "
                   f"in {processing_time:.2f} seconds")

        return ProcessResponse(
            inspection_id=request.inspection_id,
            frames=frames,
            frame_analysis=frame_analysis,
            vehicle_info=vehicle_info,
            odometer=odometer_data,
            damage=damage_data,
            exhaust=exhaust_data,
            report=report,
            gemini_analysis=gemini_data,
            inspection_analysis=inspection_analysis,
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
                            backend_root: str,
                            frame_analysis_abs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Process odometer reading from image or video frames."""
    if request.odometer_image_path and os.path.exists(request.odometer_image_path):
        return await read_odometer_from_image(odometer_reader, request.odometer_image_path, backend_root)

    dashboard_paths = _dashboard_paths_from_frame_analysis(frame_analysis_abs)
    if dashboard_paths:
        logger.info("Using %d organized dashboard candidates for odometer OCR", len(dashboard_paths))
        odometer_data = await odometer_reader.read(dashboard_paths)
        _attach_odometer_frame_metadata(odometer_data, frame_analysis_abs)
        if odometer_data.get("speedometer_image_path"):
            odometer_data["speedometer_image_path"] = convert_to_relative_path(
                odometer_data["speedometer_image_path"], backend_root)
        for path_key in (
            "source_frame_path",
            "inspection_frame_path",
            "organized_frame_path",
            "preview_frame_path",
            "crop_path",
            "readout_crop_path",
        ):
            if odometer_data.get(path_key):
                odometer_data[path_key] = convert_to_relative_path(odometer_data[path_key], backend_root)
        return odometer_data

    frames_absolute = [upload_path(f, backend_root) for f in frames]
    return await read_odometer_from_frames(dashboard_detector, odometer_reader, frames_absolute, backend_root)


def _dashboard_paths_from_frame_analysis(frame_analysis_abs: Optional[Dict[str, Any]]) -> List[str]:
    """Return organized dashboard/odometer candidates in priority order."""
    if not frame_analysis_abs:
        return []

    paths: List[str] = []
    for candidate in frame_analysis_abs.get("dashboard_candidates") or []:
        path = (
            candidate.get("readout_crop_path")
            or candidate.get("crop_path")
            or candidate.get("organized_path")
            or candidate.get("frame")
        )
        if path and os.path.exists(path) and path not in paths:
            paths.append(path)

    angle_shots = frame_analysis_abs.get("angle_shots") or {}
    for key in ("odometer", "dashboard", "interior"):
        candidate = angle_shots.get(key) or {}
        path = candidate.get("inspection_path") or candidate.get("organized_path") or candidate.get("frame")
        if path and os.path.exists(path) and path not in paths:
            paths.append(path)

    return paths[:8]


def _attach_odometer_frame_metadata(
    odometer_data: Dict[str, Any],
    frame_analysis_abs: Optional[Dict[str, Any]],
) -> None:
    """Attach organizer/source metadata for the dashboard frame OCR selected."""
    if not odometer_data or not frame_analysis_abs:
        return

    metadata_by_path = _dashboard_metadata_by_path(frame_analysis_abs)
    selected_path = odometer_data.get("speedometer_image_path")
    metadata = metadata_by_path.get(selected_path) if selected_path else None
    if metadata is None and metadata_by_path:
        metadata = next(iter(metadata_by_path.values()))
    if not metadata:
        return

    for key, value in metadata.items():
        if value is not None and odometer_data.get(key) is None:
            odometer_data[key] = value


def _dashboard_metadata_by_path(frame_analysis_abs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    metadata_by_path: Dict[str, Dict[str, Any]] = {}

    def register(payload: Dict[str, Any], default_view: str) -> None:
        if not isinstance(payload, dict):
            return
        metadata = {
            "organizer_view": payload.get("view") or default_view,
            "frame_index": payload.get("frame_index"),
            "extracted_index": payload.get("extracted_index"),
            "source_frame_index": payload.get("source_frame_index"),
            "timestamp_seconds": payload.get("timestamp_seconds"),
            "organizer_score": payload.get("score"),
            "high_confidence": payload.get("high_confidence"),
            "source_frame_path": payload.get("frame"),
            "inspection_frame_path": payload.get("inspection_path"),
            "organized_frame_path": payload.get("organized_path"),
            "preview_frame_path": payload.get("preview_path"),
            "crop_path": payload.get("crop_path"),
            "readout_crop_path": payload.get("readout_crop_path"),
        }
        for path_key in ("readout_crop_path", "crop_path", "inspection_path", "organized_path", "frame"):
            path = payload.get(path_key)
            if path:
                metadata_by_path[path] = dict(metadata)

    for candidate in frame_analysis_abs.get("dashboard_candidates") or []:
        register(candidate, "dashboard_candidate")

    angle_shots = frame_analysis_abs.get("angle_shots") or {}
    for key in ("odometer", "dashboard", "interior"):
        register(angle_shots.get(key) or {}, key)

    return metadata_by_path


def _frames_from_frame_analysis(frame_analysis_abs: Dict[str, Any], fallback: List[str]) -> List[str]:
    """Return representative absolute frame paths for VLM analysis."""
    frames: List[str] = []
    for entry in frame_analysis_abs.get("representative_frames") or []:
        path = entry.get("frame")
        if path and os.path.exists(path) and path not in frames:
            frames.append(path)

    for candidate in frame_analysis_abs.get("dashboard_candidates") or []:
        path = candidate.get("inspection_path") or candidate.get("organized_path") or candidate.get("frame")
        if path and os.path.exists(path) and path not in frames:
            frames.append(path)

    return frames or fallback


def _surface_frames_from_frame_analysis(frame_analysis_abs: Dict[str, Any], fallback: List[str]) -> List[str]:
    """Return organized exterior/interior shots for surface-level CV detectors."""
    frames: List[str] = []
    angle_shots = frame_analysis_abs.get("angle_shots") or {}
    for view in (*EXTERIOR_VIEWS, "interior"):
        candidate = angle_shots.get(view) or {}
        path = candidate.get("inspection_path") or candidate.get("organized_path") or candidate.get("frame")
        if path and os.path.exists(path) and path not in frames:
            frames.append(path)

    return frames or fallback


def _relativize_frame_analysis(frame_analysis_abs: Dict[str, Any], backend_root: str) -> Dict[str, Any]:
    """Convert absolute frame paths inside frame-analysis metadata for API clients."""
    def rel(path: Optional[str]) -> Optional[str]:
        if not path:
            return path
        return convert_to_relative_path(path, backend_root)

    def rel_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(payload)
        out["frame"] = rel(out.get("frame"))
        if out.get("inspection_path"):
            out["inspection_path"] = rel(out.get("inspection_path"))
        if out.get("preview_path"):
            out["preview_path"] = rel(out.get("preview_path"))
        if out.get("organized_path"):
            out["organized_path"] = rel(out.get("organized_path"))
        if out.get("crop_path"):
            out["crop_path"] = rel(out.get("crop_path"))
        if out.get("readout_crop_path"):
            out["readout_crop_path"] = rel(out.get("readout_crop_path"))
        return out

    out = dict(frame_analysis_abs or {})
    out["angle_shots"] = {
        view: rel_payload(payload)
        for view, payload in (out.get("angle_shots") or {}).items()
        if isinstance(payload, dict)
    }
    out["dashboard_candidates"] = [
        rel_payload(payload)
        for payload in (out.get("dashboard_candidates") or [])
        if isinstance(payload, dict)
    ]
    out["representative_frames"] = [
        rel_payload(payload)
        for payload in (out.get("representative_frames") or [])
        if isinstance(payload, dict)
    ]
    return out


def _absolutize_frame_analysis(frame_analysis: Dict[str, Any], backend_root: str) -> Dict[str, Any]:
    """Convert uploads-relative frame-analysis paths back to absolute paths."""
    def abs_path(path: Optional[str]) -> Optional[str]:
        if not path:
            return path
        return upload_path(path, backend_root)

    def abs_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(payload)
        out["frame"] = abs_path(out.get("frame"))
        if out.get("inspection_path"):
            out["inspection_path"] = abs_path(out.get("inspection_path"))
        if out.get("preview_path"):
            out["preview_path"] = abs_path(out.get("preview_path"))
        if out.get("organized_path"):
            out["organized_path"] = abs_path(out.get("organized_path"))
        if out.get("crop_path"):
            out["crop_path"] = abs_path(out.get("crop_path"))
        if out.get("readout_crop_path"):
            out["readout_crop_path"] = abs_path(out.get("readout_crop_path"))
        return out

    out = dict(frame_analysis or {})
    out["angle_shots"] = {
        view: abs_payload(payload)
        for view, payload in (out.get("angle_shots") or {}).items()
        if isinstance(payload, dict)
    }
    out["dashboard_candidates"] = [
        abs_payload(payload)
        for payload in (out.get("dashboard_candidates") or [])
        if isinstance(payload, dict)
    ]
    out["representative_frames"] = [
        abs_payload(payload)
        for payload in (out.get("representative_frames") or [])
        if isinstance(payload, dict)
    ]
    return out


def _relativize_gemini_analysis_paths(gemini_data: Dict[str, Any], backend_root: str) -> None:
    """Convert absolute frame paths inside Gemini analysis for API clients."""
    if not isinstance(gemini_data, dict):
        return
    for collection_key in ("per_frame", "damage_items", "modification_items"):
        for entry in gemini_data.get(collection_key) or []:
            if isinstance(entry, dict) and entry.get("frame"):
                entry["frame"] = convert_to_relative_path(entry["frame"], backend_root)


def _relativize_modification_analysis_paths(
    modification_data: Dict[str, Any],
    backend_root: str,
) -> Dict[str, Any]:
    """Convert absolute frame paths inside local modification evidence."""
    if not isinstance(modification_data, dict):
        return {}
    out = dict(modification_data)
    items = []
    for item in out.get("items") or []:
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        if payload.get("frame") and os.path.isabs(str(payload["frame"])):
            payload["frame"] = convert_to_relative_path(str(payload["frame"]), backend_root)
        items.append(payload)
    out["items"] = items
    return out


def _attach_damage_angle_metadata(
    damage_data: Dict[str, Any],
    frame_analysis_abs: Optional[Dict[str, Any]],
) -> None:
    """Attach organizer view metadata to damage detections for 360 viewer linking."""
    if not isinstance(damage_data, dict) or not isinstance(frame_analysis_abs, dict):
        return

    metadata_by_path: Dict[str, Dict[str, Any]] = {}

    def register(payload: Dict[str, Any], view: str) -> None:
        if not isinstance(payload, dict):
            return
        metadata = {
            "angle": payload.get("view") or view,
            "linked_view": payload.get("view") or view,
            "frame_index": payload.get("frame_index"),
            "source_frame_index": payload.get("source_frame_index"),
            "timestamp_seconds": payload.get("timestamp_seconds"),
        }
        for path_key in ("inspection_path", "organized_path", "frame"):
            path = payload.get(path_key)
            if path:
                metadata_by_path[str(path)] = metadata

    for view, payload in (frame_analysis_abs.get("angle_shots") or {}).items():
        register(payload, view)

    for index, payload in enumerate(frame_analysis_abs.get("representative_frames") or []):
        register(payload, payload.get("view") or f"representative_{index}")

    for location in damage_data.get("locations") or []:
        if not isinstance(location, dict):
            continue
        frame = location.get("frame")
        metadata = metadata_by_path.get(str(frame)) if frame else None
        if metadata:
            for key, value in metadata.items():
                if value is not None and location.get(key) is None:
                    location[key] = value

        if location.get("severity") is None:
            confidence = float(location.get("confidence") or 0.0)
            location["severity"] = "high" if confidence >= 0.75 else "medium" if confidence >= 0.45 else "low"


_DAMAGE_CATEGORY_ALIASES = {
    "scratch": "scratches",
    "scratches": "scratches",
    "dent": "dents",
    "dents": "dents",
    "rust": "rust",
    "crack": "cracks",
    "cracks": "cracks",
    "paint": "paint_damage",
    "paint_damage": "paint_damage",
    "paint_chip": "paint_damage",
    "paint_chips": "paint_damage",
    "wheel_damage": "wheel_damage",
    "rim_damage": "wheel_damage",
    "wheel": "wheel_damage",
    "broken_light": "broken_lights",
    "broken_lights": "broken_lights",
    "light_damage": "broken_lights",
    "missing_part": "missing_parts",
    "missing_parts": "missing_parts",
    "missing_trim": "missing_parts",
    "panel_misalignment": "panel_misalignment",
    "misalignment": "panel_misalignment",
}

_STRUCTURED_DAMAGE_CATEGORIES = (
    "scratches",
    "dents",
    "rust",
    "cracks",
    "paint_damage",
    "wheel_damage",
    "broken_lights",
    "missing_parts",
    "panel_misalignment",
)

_DAMAGE_LOCATION_TYPES = {
    "scratches": "scratch",
    "dents": "dent",
    "rust": "rust",
    "cracks": "crack",
    "paint_damage": "paint_damage",
    "wheel_damage": "wheel_damage",
    "broken_lights": "broken_light",
    "missing_parts": "missing_part",
    "panel_misalignment": "panel_misalignment",
}

_MIN_VISUAL_DAMAGE_CONFIDENCE = 0.55


def _merge_visual_damage_categories(
    damage_data: Dict[str, Any],
    gemini_analysis: Dict[str, Any],
) -> None:
    """Ensure every requested damage category is structured and fold VLM item types into counts."""
    if not isinstance(damage_data, dict):
        return

    for category in _STRUCTURED_DAMAGE_CATEGORIES:
        existing = damage_data.get(category)
        if not isinstance(existing, dict):
            damage_data[category] = {"count": 0, "detected": False}
        else:
            count = int(existing.get("count") or 0)
            existing["count"] = count
            existing["detected"] = bool(existing.get("detected") or count > 0)

    if not isinstance(gemini_analysis, dict):
        return

    locations = damage_data.setdefault("locations", [])
    if not isinstance(locations, list):
        locations = []
        damage_data["locations"] = locations

    existing_location_keys = {
        (
            str(location.get("type") or "").strip().lower().replace("-", "_"),
            str(location.get("frame") or ""),
            str(location.get("source_frame_index") or ""),
            str(location.get("linked_view") or location.get("angle") or ""),
        )
        for location in locations
        if isinstance(location, dict)
    }

    for item in gemini_analysis.get("damage_items") or []:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or "").strip().lower().replace("-", "_")
        category = _DAMAGE_CATEGORY_ALIASES.get(raw_type)
        if not category:
            continue
        confidence = item.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        if confidence_value is not None and confidence_value < _MIN_VISUAL_DAMAGE_CONFIDENCE:
            continue
        current = damage_data.setdefault(category, {"count": 0, "detected": False})

        linked_view = item.get("organizer_view") or item.get("view")
        location_type = _DAMAGE_LOCATION_TYPES.get(category, raw_type if raw_type != "other" else category)
        location_key = (
            location_type,
            str(item.get("frame") or ""),
            str(item.get("source_frame_index") or ""),
            str(linked_view or ""),
        )
        if location_key in existing_location_keys:
            continue
        current["count"] = int(current.get("count") or 0) + 1
        current["detected"] = True
        visual_location = {
            "type": location_type,
            "severity": item.get("severity") or "low",
            "confidence": item.get("confidence"),
            "frame": item.get("frame"),
            "angle": linked_view,
            "linked_view": linked_view,
            "frame_index": item.get("organizer_frame_index") or item.get("frame_index"),
            "source_frame_index": item.get("source_frame_index"),
            "timestamp_seconds": item.get("timestamp_seconds"),
            "notes": item.get("notes"),
            "source": "vlm",
        }
        locations.append({key: value for key, value in visual_location.items() if value is not None})
        existing_location_keys.add(location_key)


def _build_process_pipeline_audit(
    *,
    frame_analysis: Dict[str, Any],
    vehicle_info: Dict[str, Any],
    odometer: Dict[str, Any],
    damage: Dict[str, Any],
    exhaust: Dict[str, Any],
    report: Dict[str, Any],
    gemini_analysis: Dict[str, Any],
    inspection_analysis: Optional[Dict[str, Any]] = None,
    min_coverage: float = 0.75,
    min_temporal_coverage: float = 0.90,
    min_high_confidence_coverage: float = 0.50,
    min_selected_quality: float = 0.40,
    min_dashboard_candidates: int = 1,
    min_odometer_confidence: float = 0.50,
    min_vehicle_confidence: float = 0.70,
    min_modification_part_categories: int = 3,
) -> Dict[str, Any]:
    """Build a compact per-process audit for surfacing incomplete evidence."""
    coverage = frame_analysis.get("coverage") or {}
    temporal_evidence = _process_temporal_coverage_evidence(
        frame_analysis,
        min_temporal_coverage,
    )
    named_view_evidence = _process_named_view_evidence(frame_analysis)
    selected_quality_evidence = _process_selected_frame_quality_evidence(
        frame_analysis,
        min_selected_quality,
    )
    visual_analysis = _process_visual_analysis_status(report, gemini_analysis)
    condition = _process_condition(report, gemini_analysis)
    damage_evidence = _process_damage_category_evidence(damage, gemini_analysis)
    section_routing_evidence = _process_section_routing_evidence(inspection_analysis or {})
    modification_items = _process_modification_items(report, gemini_analysis, exhaust)
    modification_evidence = _process_modification_evidence(
        modification_items,
        min_modification_part_categories,
    )
    checks = [
        _audit_check(
            "frame_extraction",
            int(frame_analysis.get("frames_total") or frame_analysis.get("frames_analyzed") or 0) > 0,
            "Extract frames from the uploaded walkaround video.",
            {"frames_total": frame_analysis.get("frames_total"), "frames_analyzed": frame_analysis.get("frames_analyzed")},
        ),
        _audit_check(
            "full_video_temporal_coverage",
            bool(temporal_evidence["passed"]),
            "Sample frames across the full uploaded walkaround video duration.",
            temporal_evidence,
        ),
        _audit_check(
            "vehicle_angle_coverage",
            float(coverage.get("ratio") or 0.0) >= min_coverage,
            "Extract representative front/rear/side/quarter/dashboard angle shots.",
            {
                "coverage_ratio": coverage.get("ratio"),
                "missing_views": coverage.get("missing_views"),
                "threshold": min_coverage,
            },
        ),
        _audit_check(
            "named_view_coverage",
            bool(named_view_evidence["has_required_named_views"]),
            "Extract each named walkaround view: front, rear, sides, quarters, interior, and dashboard.",
            named_view_evidence,
        ),
        _audit_check(
            "high_confidence_angle_coverage",
            float(coverage.get("high_confidence_ratio") or 0.0) >= min_high_confidence_coverage,
            "Selected angles should have enough high-confidence model/quality evidence.",
            {
                "high_confidence_coverage_ratio": coverage.get("high_confidence_ratio"),
                "threshold": min_high_confidence_coverage,
            },
        ),
        _audit_check(
            "selected_frame_quality",
            bool(selected_quality_evidence["passed"]),
            "Selected angle/dashboard shots must have usable image paths and quality scores.",
            selected_quality_evidence,
        ),
        _audit_check(
            "dashboard_odometer_candidates",
            len(frame_analysis.get("dashboard_candidates") or []) >= min_dashboard_candidates,
            "Detect dashboard/odometer frames for OCR and VLM.",
            {
                "dashboard_candidates": len(frame_analysis.get("dashboard_candidates") or []),
                "threshold": min_dashboard_candidates,
            },
        ),
        _audit_check(
            "odometer_verified",
            odometer.get("value") is not None
            and float(odometer.get("confidence") or 0.0) >= min_odometer_confidence,
            "Read the odometer accurately enough to accept without manual review.",
            {
                "value": odometer.get("value"),
                "confidence": odometer.get("confidence"),
                "threshold": min_odometer_confidence,
                "reason": odometer.get("reason") or odometer.get("notes") or odometer.get("reasoning"),
            },
        ),
        _audit_check(
            "visual_analysis_available",
            bool(visual_analysis.get("available")),
            "Send organized frames and metadata to a live LLM/VLM analysis path.",
            {
                "available": visual_analysis.get("available"),
                "reason": visual_analysis.get("reason"),
            },
        ),
        _audit_check(
            "vehicle_identity",
            all(vehicle_info.get(field) not in (None, "") for field in ("brand", "model", "year", "variant", "type"))
            and (vehicle_info.get("vehicle_category") or vehicle_info.get("category")) not in (None, "")
            and float(vehicle_info.get("confidence") or 0.0) >= min_vehicle_confidence,
            "Determine maker, model, year, trim/version, and vehicle type/category.",
            {
                **{field: vehicle_info.get(field) for field in ("brand", "model", "year", "variant", "type")},
                "vehicle_category": vehicle_info.get("vehicle_category") or vehicle_info.get("category"),
                "year_range": vehicle_info.get("year_range"),
                "variant_candidates": vehicle_info.get("variant_candidates"),
                "variant_candidate": vehicle_info.get("variant_candidate"),
                "variant_confidence": vehicle_info.get("variant_confidence"),
                "identity_source": vehicle_info.get("identity_source"),
                "identity_override_fields": vehicle_info.get("identity_override_fields"),
                "vin_supplied": vehicle_info.get("vin") not in (None, ""),
                "registration_supplied": vehicle_info.get("registration") not in (None, ""),
                "identity_notes": vehicle_info.get("identity_notes"),
                "confidence": vehicle_info.get("confidence"),
                "threshold": min_vehicle_confidence,
            },
        ),
        _audit_check(
            "condition_assessment",
            condition not in (None, ""),
            "Determine exterior condition from extracted frames.",
            {"overall_condition": condition},
        ),
        _audit_check(
            "damage_detection",
            bool(damage_evidence["has_required_categories"])
            and damage_evidence.get("severity") not in (None, ""),
            "Detect scratches, dents, rust, cracks, paint damage, wheel damage, broken lights, missing parts, panel alignment, locations, and severity.",
            damage_evidence,
        ),
        _audit_check(
            "inspection_section_routing",
            bool(section_routing_evidence["has_routed_sections"]),
            "Route validated inspection images into confidence-aware vehicle sections.",
            section_routing_evidence,
        ),
        _audit_check(
            "modification_detection",
            bool(modification_evidence["passed"]),
            "Detect stock versus modified parts across multiple visible part categories.",
            modification_evidence,
        ),
        _audit_check(
            "inspection_summary",
            report.get("summary") not in (None, ""),
            "Generate an overall inspection summary.",
            {"summary_present": report.get("summary") not in (None, "")},
        ),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "status": "complete" if passed else "incomplete",
        "passed": passed,
        "source": "process_runtime",
        "thresholds": {
            "min_coverage": min_coverage,
            "min_temporal_coverage": min_temporal_coverage,
            "min_high_confidence_coverage": min_high_confidence_coverage,
            "min_selected_quality": min_selected_quality,
            "min_dashboard_candidates": min_dashboard_candidates,
            "min_odometer_confidence": min_odometer_confidence,
            "min_vehicle_confidence": min_vehicle_confidence,
            "min_modification_part_categories": min_modification_part_categories,
        },
        "checks": checks,
        "missing": [check["id"] for check in checks if not check["passed"]],
    }


def _audit_check(check_id: str, passed: bool, requirement: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": check_id,
        "requirement": requirement,
        "passed": bool(passed),
        "evidence": evidence,
    }


def _process_visual_analysis_status(report: Dict[str, Any], gemini_analysis: Dict[str, Any]) -> Dict[str, Any]:
    visual_analysis = report.get("visual_analysis") if isinstance(report.get("visual_analysis"), dict) else {}
    if "available" in visual_analysis:
        return visual_analysis
    if isinstance(gemini_analysis, dict) and "available" in gemini_analysis:
        return gemini_analysis
    return {"available": False, "reason": "no visual analysis evidence supplied"}


def _process_temporal_coverage_evidence(
    frame_analysis: Dict[str, Any],
    min_temporal_coverage: float,
) -> Dict[str, Any]:
    metadata = (
        frame_analysis.get("extraction_metadata")
        if isinstance(frame_analysis.get("extraction_metadata"), dict)
        else {}
    )
    first_timestamp = metadata.get("first_timestamp_seconds")
    last_timestamp = metadata.get("last_timestamp_seconds")
    ratio = metadata.get("temporal_coverage_ratio")

    return {
        "frames_extracted": metadata.get("frames_extracted"),
        "video_duration_seconds": metadata.get("video_duration_seconds"),
        "first_timestamp_seconds": first_timestamp,
        "last_timestamp_seconds": last_timestamp,
        "temporal_coverage_ratio": ratio,
        "threshold": min_temporal_coverage,
        "passed": metadata.get("frames_extracted") not in (None, 0)
        and first_timestamp is not None
        and float(first_timestamp) <= 2.0
        and ratio is not None
        and float(ratio) >= min_temporal_coverage,
    }


def _process_named_view_evidence(frame_analysis: Dict[str, Any]) -> Dict[str, Any]:
    required = list(EXTERIOR_VIEWS) + ["interior", "dashboard"]
    detail_views = [
        view
        for view in REVIEW_REQUIRED_VIEWS
        if view not in required
    ]
    angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
    coverage = frame_analysis.get("coverage") if isinstance(frame_analysis.get("coverage"), dict) else {}
    present = set(coverage.get("present_views") or [])
    present.update(view for view, payload in angle_shots.items() if payload)

    dashboard_present = (
        "dashboard" in present
        or "odometer" in present
        or bool(frame_analysis.get("dashboard_candidates"))
    )
    normalized_present = sorted(present | ({"dashboard"} if dashboard_present else set()))
    missing = [view for view in required if view not in normalized_present]
    missing_detail_views = [view for view in detail_views if view not in normalized_present]

    return {
        "required_named_views": required,
        "detail_views": detail_views,
        "present_named_views": normalized_present,
        "missing_named_views": missing,
        "missing_detail_views": missing_detail_views,
        "dashboard_candidates": len(frame_analysis.get("dashboard_candidates") or []),
        "has_required_named_views": len(missing) == 0,
    }


def _process_selected_frame_quality_evidence(
    frame_analysis: Dict[str, Any],
    min_selected_quality: float,
) -> Dict[str, Any]:
    angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
    dashboard_candidates = (
        frame_analysis.get("dashboard_candidates")
        if isinstance(frame_analysis.get("dashboard_candidates"), list)
        else []
    )
    selected = [
        item
        for item in list(angle_shots.values()) + dashboard_candidates
        if isinstance(item, dict)
    ]
    missing_paths = [
        item.get("view") or f"selected_{index}"
        for index, item in enumerate(selected)
        if not (item.get("organized_path") or item.get("frame"))
    ]
    missing_quality = [
        item.get("view") or f"selected_{index}"
        for index, item in enumerate(selected)
        if item.get("quality_score") is None
    ]
    low_quality = [
        {
            "view": item.get("view") or f"selected_{index}",
            "quality_score": item.get("quality_score"),
        }
        for index, item in enumerate(selected)
        if item.get("quality_score") is not None
        and float(item.get("quality_score") or 0.0) < min_selected_quality
    ]

    return {
        "selected_frames": len(selected),
        "threshold": min_selected_quality,
        "missing_paths": missing_paths,
        "missing_quality": missing_quality,
        "low_quality": low_quality,
        "min_quality": min(
            [float(item.get("quality_score")) for item in selected if item.get("quality_score") is not None],
            default=None,
        ),
        "passed": bool(selected)
        and not missing_paths
        and not missing_quality
        and not low_quality,
    }


def _process_section_routing_evidence(inspection_analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not inspection_analysis:
        return {
            "routed_images": None,
            "present_sections": [],
            "missing_sections": [],
            "conflicts_resolved": [],
            "rejected_count": None,
            "has_routed_sections": False,
            "not_supplied": True,
        }
    sections = inspection_analysis.get("sections") if isinstance(inspection_analysis.get("sections"), dict) else {}
    consistency = (
        inspection_analysis.get("consistency")
        if isinstance(inspection_analysis.get("consistency"), dict)
        else {}
    )
    expected_sections = [
        "front",
        "front-left",
        "left",
        "rear-left",
        "rear",
        "rear-right",
        "right",
        "dashboard",
        "odometer",
        "wheels",
        "tyres",
        "exhaust",
        "damage-closeups",
    ]
    present = [
        section
        for section in expected_sections
        if isinstance(sections.get(section), list) and len(sections.get(section) or []) > 0
    ]
    routed_images = sum(len(items) for items in sections.values() if isinstance(items, list))
    return {
        "routed_images": routed_images,
        "present_sections": present,
        "missing_sections": consistency.get("missing_sections"),
        "conflicts_resolved": consistency.get("conflicts_resolved"),
        "rejected_count": consistency.get("rejected_count"),
        "has_routed_sections": routed_images > 0 and len(present) > 0,
    }


def _process_condition(report: Dict[str, Any], gemini_analysis: Dict[str, Any]) -> Any:
    vehicle_details = report.get("vehicle_details") if isinstance(report.get("vehicle_details"), dict) else {}
    for candidate in (
        gemini_analysis.get("overall_condition") if isinstance(gemini_analysis, dict) else None,
        report.get("overall_condition"),
        vehicle_details.get("condition"),
    ):
        if candidate not in (None, ""):
            return candidate
    return None


def _process_damage_category_evidence(
    damage: Dict[str, Any],
    gemini_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    required = list(_STRUCTURED_DAMAGE_CATEGORIES)
    category_counts = {
        key: (damage.get(key) or {}).get("count")
        for key in required
        if isinstance(damage.get(key), dict)
    }
    category_detected_flags = {
        key: (damage.get(key) or {}).get("detected")
        for key in required
        if isinstance(damage.get(key), dict)
    }
    location_types = [
        str(item.get("type") or "").strip().lower()
        for item in (damage.get("locations") or [])
        if isinstance(item, dict)
    ]
    visual_items = (
        gemini_analysis.get("damage_items")
        if isinstance(gemini_analysis, dict) and isinstance(gemini_analysis.get("damage_items"), list)
        else []
    )
    visual_types = [
        str(item.get("type") or "").strip().lower()
        for item in visual_items
        if isinstance(item, dict)
    ]

    return {
        "required_categories": required,
        "present_categories": sorted(category_counts.keys()),
        "missing_categories": [key for key in required if key not in category_counts],
        "has_required_categories": all(key in category_counts for key in required),
        "category_counts": category_counts,
        "category_detected_flags": category_detected_flags,
        "severity": damage.get("severity"),
        "damage_locations": len(damage.get("locations") or []),
        "location_types": sorted(set(location_types)),
        "visual_damage_items": len(visual_items),
        "visual_damage_types": sorted(set(visual_types)),
    }


def _process_modification_items(
    report: Dict[str, Any],
    gemini_analysis: Dict[str, Any],
    exhaust: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(gemini_analysis, dict) and isinstance(gemini_analysis.get("modification_items"), list):
        items.extend(item for item in gemini_analysis.get("modification_items") if isinstance(item, dict))
    modification = report.get("modification_assessment") if isinstance(report.get("modification_assessment"), dict) else {}
    if isinstance(modification.get("items"), list):
        items.extend(item for item in modification.get("items") if isinstance(item, dict))
    local_modification = (
        report.get("local_modification_analysis")
        if isinstance(report.get("local_modification_analysis"), dict)
        else {}
    )
    if isinstance(local_modification.get("items"), list):
        items.extend(item for item in local_modification.get("items") if isinstance(item, dict))
    exhaust_type = str((exhaust or {}).get("type") or "").strip().lower()
    if exhaust_type in {"stock", "modified"}:
        items.append({"part": "exhaust", "status": exhaust_type, "confidence": (exhaust or {}).get("confidence")})
    return items


def _process_modification_evidence(
    items: List[Dict[str, Any]],
    min_part_categories: int,
) -> Dict[str, Any]:
    concrete_parts = sorted({
        str(item.get("part") or "").strip().lower()
        for item in items
        if str(item.get("status") or "").strip().lower() in {"stock", "modified"}
        and str(item.get("part") or "").strip()
    })
    concrete_status_items = sum(
        1
        for item in items
        if str(item.get("status") or "").strip().lower() in {"stock", "modified"}
    )
    return {
        "modification_items": len(items),
        "concrete_status_items": concrete_status_items,
        "concrete_part_categories": concrete_parts,
        "concrete_part_category_count": len(concrete_parts),
        "threshold": min_part_categories,
        "exhaust_only": concrete_parts == ["exhaust"],
        "passed": len(concrete_parts) >= min_part_categories,
    }


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


def _merge_vehicle_identity_override(
    base_info: Dict[str, Any],
    override: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge trusted non-video identity evidence into vehicle_info.

    This is intentionally explicit: the video-only pipeline should not guess
    exact year/trim when VLM is unavailable, but VIN, registration, or manually
    confirmed metadata can provide the missing exact identity fields.
    """
    if not isinstance(override, dict) or not override:
        return base_info

    merged = dict(base_info or {})
    allowed_fields = (
        "brand",
        "model",
        "year",
        "variant",
        "type",
        "vehicle_category",
        "category",
        "color",
        "vin",
        "registration",
    )
    applied = []
    for field in allowed_fields:
        value = override.get(field)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[field] = value
        applied.append(field)

    source = str(override.get("source") or "provided_identity_evidence").strip()
    merged["identity_source"] = source
    if applied:
        merged["identity_override_fields"] = applied
        merged["identity_notes"] = (
            f"Exact identity fields merged from {source}; video-derived fields remain candidates where not overridden."
        )

    try:
        override_confidence = float(override.get("confidence"))
    except (TypeError, ValueError):
        override_confidence = 0.95 if applied else 0.0
    merged["confidence"] = max(float(merged.get("confidence") or 0.0), override_confidence)
    return merged
