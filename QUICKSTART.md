# Quick Start Guide

Follow these steps to get the Vehicle Intelligence Platform running locally.

## Prerequisites Check

Make sure you have:
- Node.js 18+ installed (`node --version`)
- Python 3.9+ installed (`python --version`)
- npm installed (`npm --version`)

## Step-by-Step Setup

### 1. Install Backend Dependencies

```bash
cd backend
npm install
```

### 2. Install ML Service Dependencies

```bash
cd ../ml-service

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt
```

**Note:** First installation may take 10-15 minutes as it downloads ML models.

### 3. Install Frontend Dependencies

```bash
cd ../frontend
npm install
```

### 4. Configure Environment Variables (Optional)

**Backend** (`backend/.env`):
```env
PORT=3001
ML_SERVICE_URL=http://localhost:8000
```

**ML Service** (`ml-service/.env`):
```env
GEMINI_API_KEY=your_key_here
```
*Note: Gemini API key is optional. Without it, the system will generate mock reports.*

**Frontend** (`frontend/.env.local`):
```env
NEXT_PUBLIC_API_URL=http://localhost:3001/api
```

### 5. Start All Services

You need to run three services simultaneously. Open three terminal windows:

**Terminal 1 - Backend:**
```bash
cd backend
npm run dev
```
Backend runs on `http://localhost:3001`

**Terminal 2 - ML Service:**
```bash
cd ml-service
source venv/bin/activate  # On Windows: venv\Scripts\activate
python src/main.py
```
ML Service runs on `http://localhost:8000`

**Terminal 3 - Frontend:**
```bash
cd frontend
npm run dev
```
Frontend runs on `http://localhost:3000`

### 6. Test the System

1. Open browser to `http://localhost:3000`
2. Click "Start Inspection" or navigate to `/upload`
3. Upload a vehicle video (MP4 format, max 500MB)
4. Wait for processing (typically 1-3 minutes)
5. View inspection results

## Troubleshooting

### Backend won't start
- Check if port 3001 is available
- Make sure SQLite database can be created (check file permissions)

### ML Service won't start
- Ensure virtual environment is activated
- Check Python version (3.9+ required)
- Verify all dependencies installed: `pip list`

### Frontend won't start
- Check if port 3000 is available
- Verify Node.js version: `node --version` (should be 18+)

### Processing fails
- Check ML service is running and accessible
- Verify video file format (MP4 recommended)
- Check backend logs for error messages

### Images not displaying
- Ensure backend is serving static files from `uploads/` directory
- Check file paths in browser console

## Next Steps

- Read the main [README.md](README.md) for detailed documentation
- Check individual component READMEs for specific details
- Review the PRD in `.context/prd.md` for requirements

## Development Tips

- Backend uses SQLite - database file is `backend/vehicle_intelligence.db`
- Uploaded videos are stored in `backend/uploads/videos/`
- Extracted frames are stored in `backend/uploads/frames/`
- ML models are downloaded on first use (stored in system cache)
