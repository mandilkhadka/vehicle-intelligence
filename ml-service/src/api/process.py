"""
Processing API endpoint
Main endpoint for video processing pipeline
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio

from src.services.frame_extractor import FrameExtractor
from src.services.vehicle_identifier import VehicleIdentifier
from src.services.dashboard_detector import DashboardDetector
from src.services.odometer_reader import OdometerReader
from src.services.damage_detector import DamageDetector
from src.services.exhaust_classifier import ExhaustClassifier
from src.services.report_generator import ReportGenerator

router = APIRouter()


class ProcessRequest(BaseModel):
    """Request model for video processing"""
    video_path: str
    inspection_id: str


class ProcessResponse(BaseModel):
    """Response model for video processing"""
    inspection_id: str
    frames: List[str]
    vehicle_info: Dict[str, Any]
    odometer: Dict[str, Any]
    damage: Dict[str, Any]
    exhaust: Dict[str, Any]
    report: Dict[str, Any]


@router.post("/process", response_model=ProcessResponse)
async def process_video(request: ProcessRequest):
    """
    Process a video and extract vehicle inspection data
    This is the main processing endpoint that orchestrates all ML services
    """
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
        print(f"Extracting frames from video: {request.video_path}")
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
            raise HTTPException(
                status_code=400, 
                detail="Failed to extract frames from video"
            )

        # Step 2: Identify vehicle (type, brand, model)
        print("Identifying vehicle...")
        vehicle_info = await vehicle_identifier.identify(frames)

        # Step 3: Detect dashboard and read odometer
        print("Detecting dashboard and reading odometer...")
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
        print("Detecting vehicle damage...")
        damage_data = await damage_detector.detect(frames)

        # Step 5: Classify exhaust
        print("Classifying exhaust...")
        exhaust_data = await exhaust_classifier.classify(frames)

        # Step 6: Generate inspection report
        print("Generating inspection report...")
        report = await report_generator.generate({
            "vehicle_info": vehicle_info,
            "odometer": odometer_data,
            "damage": damage_data,
            "exhaust": exhaust_data,
        })

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

    except Exception as e:
        print(f"Processing error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process video: {str(e)}"
        )
