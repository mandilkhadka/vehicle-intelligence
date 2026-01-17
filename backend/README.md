# Backend API Server

Node.js Express server for Vehicle Intelligence Platform.

## Setup

```bash
npm install
npm run dev
```

## Environment Variables

Create a `.env` file:

```env
PORT=3001
ML_SERVICE_URL=http://localhost:8000
```

## API Endpoints

- `POST /api/upload` - Upload video file
- `GET /api/jobs/:id` - Get job status
- `GET /api/inspections` - Get all inspections
- `GET /api/inspections/:id` - Get inspection by ID
- `GET /health` - Health check

## Database

Uses SQLite database (`vehicle_intelligence.db`) for storing:
- File metadata
- Job status
- Inspection results

## File Storage

Uploaded videos are stored in `uploads/videos/`
Extracted frames are stored in `uploads/frames/`
