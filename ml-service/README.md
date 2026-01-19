# ML Service

Python FastAPI service for vehicle inspection processing.

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY=your_api_key_here  # Optional

# Run service
python3 src/main.py
```

## Services

- **FrameExtractor** - Extracts frames from video (1 per second)
- **VehicleIdentifier** - Identifies vehicle type, brand, and model
- **DashboardDetector** - Detects dashboard region
- **OdometerReader** - Reads odometer value using OCR
- **DamageDetector** - Detects scratches, dents, and rust
- **ExhaustClassifier** - Classifies exhaust as stock or modified
- **ReportGenerator** - Generates inspection report using Gemini LLM

## API Endpoints

- `POST /api/process` - Process video
- `GET /health` - Health check

## Models

Models are downloaded automatically on first use:
- YOLOv8 (object detection)
- CLIP (vehicle identification)
- PaddleOCR (OCR)

## Notes

- First run will download ML models (may take several minutes)
- GPU acceleration is optional but recommended for faster processing
- Gemini API key is optional (will use mock reports if not provided)
