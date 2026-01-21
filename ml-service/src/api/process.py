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
    
    # Log immediately when request arrives
    logger.info("=" * 80)
    logger.info(f"RECEIVED PROCESS REQUEST - Inspection ID: {request.inspection_id}")
    logger.info(f"Video path: {request.video_path}")
    logger.info(f"Odometer image path: {request.odometer_image_path or 'None'}")
    logger.info("=" * 80)
    
    # Check if mock mode is enabled
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
    if mock_mode:
        logger.info("MOCK MODE ENABLED - Returning sample data immediately")
        await asyncio.sleep(2)  # Simulate some processing time
        
        # Return mock data
        return ProcessResponse(
            inspection_id=request.inspection_id,
            frames=["frames/sample/frame_0001.jpg", "frames/sample/frame_0002.jpg"],
            vehicle_info={
                "type": "sedan",
                "brand": "Toyota",
                "model": "Camry",
                "confidence": 0.95
            },
            odometer={
                "value": 45230,
                "confidence": 0.88,
                "speedometer_image_path": "odometer_images/sample.jpg"
            },
            damage={
                "severity": "minor",
                "scratches": {"count": 2, "locations": ["front-left", "rear-right"]},
                "dents": {"count": 1, "locations": ["front-right"]},
                "rust": {"count": 0, "locations": []}
            },
            exhaust={
                "type": "single",
                "confidence": 0.92,
                "exhaust_image_path": "exhaust/sample.jpg"
            },
            report={
                "summary": "Vehicle in good condition with minor cosmetic damage",
                "recommendations": ["Repair minor scratches", "Regular maintenance recommended"]
            }
        )
    
    logger.info(
        f"Starting video processing for inspection {request.inspection_id}, "
        f"video: {request.video_path}, "
        f"odometer_image: {request.odometer_image_path or 'None'}"
    )
    
    try:
        # Verify video file exists and is readable
        if not os.path.exists(request.video_path):
            logger.error(f"Video file not found: {request.video_path}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video file not found: {request.video_path}"
            )
        
        # Verify odometer image if provided
        if request.odometer_image_path:
            if not os.path.exists(request.odometer_image_path):
                logger.warning(f"Odometer image not found: {request.odometer_image_path}, proceeding without it")
                # Don't fail, just proceed without odometer image
                request.odometer_image_path = None
        
        # Initialize services with simpler approach
        logger.info("Initializing ML services...")
        init_start_time = time.time()
        try:
            # Initialize lightweight services first
            logger.info("Initializing FrameExtractor...")
            frame_extractor = FrameExtractor()
            logger.info(f"FrameExtractor initialized ({time.time() - init_start_time:.2f}s)")
            
            logger.info("Initializing ReportGenerator...")
            report_generator = ReportGenerator()
            logger.info(f"ReportGenerator initialized ({time.time() - init_start_time:.2f}s)")
            
            logger.info("Initializing OdometerReader...")
            odometer_reader = OdometerReader()
            logger.info(f"OdometerReader initialized ({time.time() - init_start_time:.2f}s)")
            
            # Initialize heavier models - these will be loaded lazily
            logger.info("Initializing VehicleIdentifier (lazy loading)...")
            vehicle_identifier = VehicleIdentifier()
            logger.info(f"VehicleIdentifier initialized ({time.time() - init_start_time:.2f}s)")
            
            logger.info("Initializing DashboardDetector (lazy loading)...")
            dashboard_detector = DashboardDetector()
            logger.info(f"DashboardDetector initialized ({time.time() - init_start_time:.2f}s)")
            
            logger.info("Initializing DamageDetector (lazy loading)...")
            damage_detector = DamageDetector()
            logger.info(f"DamageDetector initialized ({time.time() - init_start_time:.2f}s)")
            
            logger.info("Initializing ExhaustClassifier (lazy loading)...")
            exhaust_classifier = ExhaustClassifier()
            logger.info(f"ExhaustClassifier initialized ({time.time() - init_start_time:.2f}s)")
            
            total_init_time = time.time() - init_start_time
            logger.info(f"All ML services initialized successfully in {total_init_time:.2f} seconds")
        except Exception as e:
            logger.error(f"Failed to initialize ML services: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize ML services: {str(e)}"
            )

        # Step 1: Extract frames from video (1 frame per second)
        logger.info(f"Step 1/6: Extracting frames from video: {request.video_path}")
        
        # Verify video file is accessible before starting extraction
        if not os.path.isfile(request.video_path):
            error_msg = f"Video file is not accessible: {request.video_path}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # Get video file size for logging
        try:
            video_size = os.path.getsize(request.video_path)
            logger.info(f"Video file size: {video_size / (1024*1024):.2f} MB")
        except Exception as e:
            logger.warning(f"Could not get video file size: {e}")
        
        # Determine output directory (relative to backend root)
        import os
        backend_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
        frames_dir = os.path.join(backend_root, "backend", "uploads", "frames", request.inspection_id)
        os.makedirs(frames_dir, exist_ok=True)
        logger.info(f"Frames will be saved to: {frames_dir}")
        
        logger.info("Starting frame extraction (this may take a while for long videos)...")
        extraction_start = time.time()
        try:
            frames = await asyncio.wait_for(
                frame_extractor.extract_frames(
                    request.video_path, 
                    output_dir=frames_dir
                ),
                timeout=300.0  # 5 minute timeout for frame extraction
            )
            extraction_duration = time.time() - extraction_start
            logger.info(f"Frame extraction completed in {extraction_duration:.2f} seconds")
        except asyncio.TimeoutError:
            logger.error(f"Frame extraction timed out after 5 minutes for video: {request.video_path}")
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
            try:
                # Use the uploaded odometer image directly
                odometer_data = await asyncio.wait_for(
                    odometer_reader.read([request.odometer_image_path]),
                    timeout=60.0  # 1 minute timeout for OCR
                )
            except asyncio.TimeoutError:
                logger.warning("Odometer reading timed out, using default values")
                odometer_data = {
                    "value": None,
                    "confidence": 0.0,
                    "speedometer_image_path": request.odometer_image_path
                }
            except Exception as e:
                logger.error(f"Odometer reading failed: {str(e)}", exc_info=True)
                odometer_data = {
                    "value": None,
                    "confidence": 0.0,
                    "speedometer_image_path": request.odometer_image_path
                }
            
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
