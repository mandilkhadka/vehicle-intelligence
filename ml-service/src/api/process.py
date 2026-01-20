"""
Processing API endpoint
Main endpoint for video processing pipeline with proper error handling
"""

import os
import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.services.frame_extractor import FrameExtractor
from src.services.vehicle_identifier import VehicleIdentifier
from src.services.dashboard_detector import DashboardDetector
from src.services.odometer_reader import OdometerReader
from src.services.damage_detector import DamageDetector
from src.services.exhaust_classifier import ExhaustClassifier
from src.services.report_generator import ReportGenerator

router = APIRouter()
logger = logging.getLogger(__name__)


class ProcessRequest(BaseModel):
    """Request model for video processing with validation"""
    video_path: str = Field(..., description="Path to the video file")
    inspection_id: str = Field(..., description="Unique inspection identifier")
    odometer_image_path: Optional[str] = Field(None, description="Optional path to odometer image")

    @field_validator("video_path")
    @classmethod
    def validate_video_path(cls, v: str) -> str:
        """Validate that video file exists"""
        if not os.path.exists(v):
            raise ValueError(f"Video file not found: {v}")
        if not os.path.isfile(v):
            raise ValueError(f"Video path is not a file: {v}")
        # Check file extension
        valid_extensions = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
        if Path(v).suffix.lower() not in valid_extensions:
            raise ValueError(f"Invalid video format. Supported: {valid_extensions}")
        return v

    @field_validator("inspection_id")
    @classmethod
    def validate_inspection_id(cls, v: str) -> str:
        """Validate inspection ID format"""
        if not v or len(v) < 10:
            raise ValueError("Inspection ID must be at least 10 characters")
        return v

    @field_validator("odometer_image_path")
    @classmethod
    def validate_odometer_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate odometer image path if provided"""
        if v is None:
            return v
        if not os.path.exists(v):
            raise ValueError(f"Odometer image file not found: {v}")
        if not os.path.isfile(v):
            raise ValueError(f"Odometer image path is not a file: {v}")
        valid_extensions = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
        if Path(v).suffix.lower() not in valid_extensions:
            raise ValueError(f"Invalid image format. Supported: {valid_extensions}")
        return v


class ProcessResponse(BaseModel):
    """Response model for video processing"""
    inspection_id: str
    frames: List[str]
    vehicle_info: Dict[str, Any]
    odometer: Dict[str, Any]
    damage: Dict[str, Any]
    exhaust: Dict[str, Any]
    report: Dict[str, Any]


@router.post("/process", response_model=ProcessResponse, status_code=status.HTTP_200_OK)
async def process_video(request: ProcessRequest):
    """
    Process a video and extract vehicle inspection data
    This is the main processing endpoint that orchestrates all ML services
    
    Args:
        request: ProcessRequest containing video path, inspection ID, and optional odometer image
        
    Returns:
        ProcessResponse with all extracted inspection data
        
    Raises:
        HTTPException: If processing fails at any stage
    """
    import time
    start_time = time.time()
    
    logger.info(
        f"Starting video processing for inspection {request.inspection_id}, "
        f"video: {request.video_path}"
    )
    
    try:
        # Initialize services
        frame_extractor = FrameExtractor()
        vehicle_identifier = VehicleIdentifier()
        dashboard_detector = DashboardDetector()
        odometer_reader = OdometerReader()
        damage_detector = DamageDetector()
        exhaust_classifier = ExhaustClassifier()
        report_generator = ReportGenerator()

        # Step 1: Extract frames from video (1 frame per second)
        logger.info(f"Step 1/6: Extracting frames from video: {request.video_path}")
        # Determine output directory (relative to backend root)
        import os
        backend_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
        frames_dir = os.path.join(backend_root, "backend", "uploads", "frames", request.inspection_id)
        os.makedirs(frames_dir, exist_ok=True)
        
        frames = await frame_extractor.extract_frames(
            request.video_path, 
            output_dir=frames_dir
        )
        
        # Convert absolute paths to relative paths for serving
        frames_relative = []
        for frame_path in frames:
            # Make path relative to backend/uploads
            rel_path = os.path.relpath(frame_path, os.path.join(backend_root, "backend", "uploads"))
            frames_relative.append(rel_path.replace("\\", "/"))  # Normalize path separators
        frames = frames_relative

        if not frames:
            logger.error("Failed to extract frames from video")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract frames from video"
            )
        
        logger.info(f"Extracted {len(frames)} frames from video")

        # Step 2: Identify vehicle (type, brand, model)
        logger.info("Step 2/6: Identifying vehicle...")
        vehicle_info = await vehicle_identifier.identify(frames)
        logger.info(f"Vehicle identified: {vehicle_info.get('type', 'unknown')} - {vehicle_info.get('brand', 'unknown')} {vehicle_info.get('model', 'unknown')}")

        # Step 3: Detect dashboard and read odometer
        logger.info("Step 3/6: Detecting dashboard and reading odometer...")
        
        # If odometer image was provided, use it directly
        if request.odometer_image_path and os.path.exists(request.odometer_image_path):
            logger.info(f"Using provided odometer image: {request.odometer_image_path}")
            # Use the uploaded odometer image directly
            odometer_data = await odometer_reader.read([request.odometer_image_path])
            
            # Convert odometer image path to relative
            if odometer_data.get("speedometer_image_path"):
                abs_path = odometer_data["speedometer_image_path"]
                rel_path = os.path.relpath(abs_path, os.path.join(backend_root, "backend", "uploads"))
                odometer_data["speedometer_image_path"] = rel_path.replace("\\", "/")
            else:
                # Use the provided image path
                rel_path = os.path.relpath(request.odometer_image_path, os.path.join(backend_root, "backend", "uploads"))
                odometer_data["speedometer_image_path"] = rel_path.replace("\\", "/")
        else:
            # Convert frame paths back to absolute for dashboard detection
            frames_absolute = [os.path.join(backend_root, "backend", "uploads", f) for f in frames]
            dashboard_frames = await dashboard_detector.detect(frames_absolute)
            odometer_data = await odometer_reader.read(dashboard_frames)
            
            # Convert dashboard frame paths to relative
            if odometer_data.get("speedometer_image_path"):
                abs_path = odometer_data["speedometer_image_path"]
                rel_path = os.path.relpath(abs_path, os.path.join(backend_root, "backend", "uploads"))
                odometer_data["speedometer_image_path"] = rel_path.replace("\\", "/")

        # Step 4: Detect vehicle damage
        logger.info("Step 4/6: Detecting vehicle damage...")
        # Convert frame paths back to absolute for damage detection
        frames_absolute = [os.path.join(backend_root, "backend", "uploads", f) for f in frames]
        damage_data = await damage_detector.detect(frames_absolute, request.inspection_id)
        logger.info(f"Damage detection completed. Severity: {damage_data.get('severity', 'unknown')}")

        # Step 5: Classify exhaust
        logger.info("Step 5/6: Classifying exhaust...")
        # Convert frame paths back to absolute for exhaust classification
        frames_absolute = [os.path.join(backend_root, "backend", "uploads", f) for f in frames]
        exhaust_data = await exhaust_classifier.classify(frames_absolute, request.inspection_id)
        
        # Convert exhaust image path to relative if present
        if exhaust_data.get("exhaust_image_path"):
            abs_path = exhaust_data["exhaust_image_path"]
            rel_path = os.path.relpath(abs_path, os.path.join(backend_root, "backend", "uploads"))
            exhaust_data["exhaust_image_path"] = rel_path.replace("\\", "/")
        
        logger.info(f"Exhaust classification completed. Type: {exhaust_data.get('type', 'unknown')}")

        # Step 6: Generate inspection report
        logger.info("Step 6/6: Generating inspection report...")
        report = await report_generator.generate({
            "vehicle_info": vehicle_info,
            "odometer": odometer_data,
            "damage": damage_data,
            "exhaust": exhaust_data,
        })

        processing_time = time.time() - start_time
        logger.info(
            f"Video processing completed successfully for inspection {request.inspection_id} "
            f"in {processing_time:.2f} seconds"
        )

        # Return complete results
        return ProcessResponse(
            inspection_id=request.inspection_id,
            frames=frames,
            vehicle_info=vehicle_info,
            odometer=odometer_data,
            damage=damage_data,
            exhaust=exhaust_data,
            report=report,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Handle validation errors
        logger.error(f"Validation error during processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}"
        )
    except FileNotFoundError as e:
        # Handle file not found errors
        logger.error(f"File not found error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {str(e)}"
        )
    except Exception as e:
        # Handle all other errors
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process video: {str(e)}" if os.getenv("NODE_ENV") != "production" else "Failed to process video"
        )
