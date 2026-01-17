# Vehicle Intelligence Platform (VIP) - MVP

AI-powered vehicle inspection system that extracts structured data from 360-degree vehicle videos.

## Overview

This MVP system processes vehicle videos to extract:
- Vehicle type, brand, and model identification
- Odometer reading from dashboard
- Damage detection (scratches, dents, rust)
- Exhaust system classification (stock vs modified)
- Comprehensive inspection reports

## Architecture

The system consists of three main components:

1. **Frontend** (Next.js + TypeScript) - User interface for uploads and results
2. **Backend API** (Node.js + Express) - Handles uploads, job management, and data serving
3. **ML Service** (Python + FastAPI) - Processes videos and runs AI/ML models

## Project Structure

```
vehicle-intelligence/
├── frontend/          # Next.js frontend application
├── backend/           # Node.js backend API
├── ml-service/        # Python ML service
├── shared/            # Shared TypeScript types
└── .context/          # PRD and documentation
```

## Prerequisites

- Node.js 18+ and npm
- Python 3.9+
- SQLite (included with Node.js)

## Setup Instructions

### 1. Backend Setup

```bash
cd backend
npm install
npm run dev
```

The backend will run on `http://localhost:3001`

### 2. ML Service Setup

```bash
cd ml-service

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set Gemini API key (optional, for report generation)
export GEMINI_API_KEY=your_api_key_here

# Run the service
python src/main.py
```

The ML service will run on `http://localhost:8000`

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will run on `http://localhost:3000`

## Environment Variables

### Backend (.env)

```env
PORT=3001
ML_SERVICE_URL=http://localhost:8000
```

### ML Service (.env)

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### Frontend (.env.local)

```env
NEXT_PUBLIC_API_URL=http://localhost:3001/api
```

## Usage

1. Start all three services (backend, ML service, frontend)
2. Navigate to `http://localhost:3000`
3. Upload a 360-degree vehicle video (MP4 format)
4. Wait for processing to complete
5. View inspection results

## API Endpoints

### Backend API (`http://localhost:3001/api`)

- `POST /upload` - Upload video file
- `GET /jobs/:id` - Get job status
- `GET /inspections` - Get all inspections
- `GET /inspections/:id` - Get inspection by ID

### ML Service API (`http://localhost:8000/api`)

- `POST /process` - Process video and extract inspection data
- `GET /health` - Health check

## Technology Stack

### Frontend
- Next.js 14
- TypeScript
- Tailwind CSS
- Axios

### Backend
- Node.js
- Express
- TypeScript
- SQLite (better-sqlite3)
- Multer (file uploads)

### ML Service
- Python 3.9+
- FastAPI
- OpenCV (frame extraction)
- YOLOv8 (object detection)
- CLIP (vehicle identification)
- PaddleOCR (OCR)
- Google Gemini (report generation)

## Development Notes

- Code is written to be simple and understandable for junior engineers
- All functions include clear comments explaining their purpose
- Error handling is implemented throughout
- The system processes jobs asynchronously and supports concurrent processing

## Limitations (MVP)

- Uses general-purpose models (not custom-trained for vehicles)
- OCR accuracy depends on video quality
- Damage detection uses heuristics (not specialized models)
- Exhaust classification is simplified

## Future Enhancements

- Custom-trained models for vehicle-specific tasks
- Real-time processing
- Mobile application
- VIN number detection
- Audio-based exhaust analysis

## License

MIT
