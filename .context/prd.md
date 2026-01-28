# PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Product Name:** Vehicle Intelligence Platform (VIP) – MVP  
**Version:** 1.0  
**Last Updated:** January 2026

---

## 1. MVP OBJECTIVE

Build a minimum viable product that extracts core vehicle information from a 360-degree walk-around video. The goal of the MVP is to prove that AI can reliably convert unstructured vehicle video into structured inspection data.

The MVP prioritizes accuracy, explainability, and speed over feature completeness.

---

## 2. MVP SCOPE

### 2.1 IN SCOPE

- 360-degree vehicle video upload (MP4 format)
- Frame extraction from uploaded video at fixed intervals
- Vehicle type detection (car, bike, motorcycle, truck, SUV)
- Vehicle brand and model identification
- Odometer (kilometers run) detection via OCR
- Speedometer/dashboard image extraction
- Basic vehicle condition detection (scratches, dents, rust)
- Damage severity classification (low, medium, high)
- Exhaust detection and classification (stock vs modified)
- Structured inspection output (JSON and UI display)
- Inspection history and job status tracking
- Asynchronous job processing with progress updates

### 2.2 OUT OF SCOPE (POST-MVP)

- VIN number detection
- Audio-based exhaust analysis
- Emission compliance checks
- Real-time processing
- Mobile application
- Legal or regulatory certification
- Multi-user authentication and authorization
- Payment processing
- Custom model training interface

---

## 3. TARGET USERS (MVP)

- Vehicle inspectors
- Used car dealerships
- Internal AI validation and testing users

---

## 4. CORE USER FLOW (MVP)

1. User navigates to upload page
2. User uploads a 360-degree vehicle video (MP4)
3. System creates a job and returns job ID
4. System processes video asynchronously:
   - Extracts frames from video
   - Identifies vehicle type, brand, and model
   - Detects dashboard and reads odometer
   - Detects vehicle damage (scratches, dents, rust)
   - Classifies exhaust system
   - Generates inspection report
5. User views job status and progress
6. User views inspection results dashboard with all extracted information

---

## 5. MVP USER STORIES

- **US-1:** As a user, I want to upload a 360-degree vehicle video so I can inspect a vehicle without manually taking photos.
- **US-2:** As a user, I want to see the processing status and progress so I know when my inspection is complete.
- **US-3:** As a user, I want to see images extracted from the video so I can verify what the AI analyzed.
- **US-4:** As a user, I want the system to identify the vehicle type, brand, and model with confidence scores.
- **US-5:** As a user, I want the system to detect and display the odometer reading from the dashboard.
- **US-6:** As a user, I want to know if the vehicle has visible damage such as scratches, dents, or rust with severity levels.
- **US-7:** As a user, I want to know if the exhaust appears to be stock or modified.
- **US-8:** As a user, I want a comprehensive inspection report with recommendations.
- **US-9:** As a user, I want to view my inspection history so I can access past inspections.

---

## 6. FUNCTIONAL REQUIREMENTS (MVP)

### 6.1 VIDEO UPLOAD AND FRAME EXTRACTION

- **MVP-FR-1:** The system shall allow users to upload a 360-degree vehicle video in MP4 format via web interface.
- **MVP-FR-2:** The system shall validate uploaded file format and size before processing.
- **MVP-FR-3:** The system shall extract frames from the video at fixed intervals (e.g., one frame per second).
- **MVP-FR-4:** The system shall store extracted frames for later reference.
- **MVP-FR-5:** The system shall display extracted frames in an image gallery in the results view.

### 6.2 JOB MANAGEMENT

- **MVP-FR-6:** The system shall create a job record upon video upload.
- **MVP-FR-7:** The system shall track job status (pending, processing, completed, failed).
- **MVP-FR-8:** The system shall provide job progress updates (0-100%).
- **MVP-FR-9:** The system shall allow users to query job status via API.
- **MVP-FR-10:** The system shall handle job failures gracefully with error messages.

### 6.3 VEHICLE IDENTIFICATION

- **MVP-FR-11:** The system shall detect vehicle type (car, bike, motorcycle, truck, SUV).
- **MVP-FR-12:** The system shall identify the vehicle brand.
- **MVP-FR-13:** The system shall identify the vehicle model.
- **MVP-FR-14:** The system shall display confidence scores for vehicle identification.
- **MVP-FR-15:** The system shall optionally detect vehicle color.

### 6.4 ODOMETER AND SPEEDOMETER DETECTION

- **MVP-FR-16:** The system shall detect the dashboard region from extracted frames.
- **MVP-FR-17:** The system shall extract the odometer value using OCR (PaddleOCR).
- **MVP-FR-18:** The system shall validate odometer readings across multiple frames.
- **MVP-FR-19:** The system shall display the speedometer image used for odometer extraction.
- **MVP-FR-20:** The system shall provide confidence scores for odometer readings.

### 6.5 BASIC CONDITION DETECTION

- **MVP-FR-21:** The system shall detect visible scratches and count occurrences.
- **MVP-FR-22:** The system shall detect visible dents and count occurrences.
- **MVP-FR-23:** The system shall detect visible rust and count occurrences.
- **MVP-FR-24:** The system shall classify damage severity as low, medium, or high.
- **MVP-FR-25:** The system shall provide damage locations with frame references and bounding boxes.

### 6.6 EXHAUST DETECTION

- **MVP-FR-26:** The system shall detect the exhaust region in video frames.
- **MVP-FR-27:** The system shall classify the exhaust as stock or modified.
- **MVP-FR-28:** The system shall display a confidence score for exhaust classification.
- **MVP-FR-29:** The system shall optionally store exhaust image for reference.

### 6.7 INSPECTION OUTPUT

- **MVP-FR-30:** The system shall generate a structured inspection result in JSON format.
- **MVP-FR-31:** The system shall generate a human-readable inspection report using LLM.
- **MVP-FR-32:** The system shall display the inspection result in a user-friendly dashboard.
- **MVP-FR-33:** The system shall provide recommendations based on inspection findings.
- **MVP-FR-34:** The system shall allow users to view inspection history.

---

## 7. NON-FUNCTIONAL REQUIREMENTS (MVP)

### 7.1 PERFORMANCE

- End-to-end processing time per video shall be less than 3 minutes for typical videos (30-60 seconds).
- Frame extraction shall complete within 10 seconds for a 1-minute video.
- API response time for status queries shall be less than 200ms.

### 7.2 RELIABILITY

- Odometer OCR results shall be validated using multiple frames.
- All AI outputs shall include confidence scores.
- System shall handle processing failures gracefully with error reporting.
- System shall support retry mechanisms for transient failures.

### 7.3 SECURITY

- File uploads shall be handled securely with validation.
- Uploaded files shall be stored in a secure location.
- Media files shall be accessed using secure paths (no direct public access).
- System shall validate file types and sizes before processing.

### 7.4 SCALABILITY

- System architecture shall support horizontal scaling of ML service.
- Job processing shall be asynchronous and non-blocking.
- Database shall handle concurrent read/write operations efficiently.

### 7.5 USABILITY

- User interface shall be intuitive and responsive.
- Processing status shall be clearly communicated to users.
- Results shall be presented in a clear, organized manner.
- System shall provide visual feedback during processing.

---

## 8. AI AND ML COMPONENTS (MVP)

### 8.1 FRAME EXTRACTION
- **Technology:** OpenCV (Python)
- **Method:** Fixed interval extraction (1 frame per second)
- **Output:** JPEG images stored locally

### 8.2 VEHICLE IDENTIFICATION
- **Technology:** CLIP (Contrastive Language-Image Pre-training)
- **Method:** Zero-shot classification with vehicle brand/model prompts
- **Output:** Vehicle type, brand, model, confidence scores

### 8.3 DASHBOARD DETECTION
- **Technology:** YOLOv8 (object detection)
- **Method:** Pre-trained model for dashboard/instrument cluster detection
- **Output:** Bounding boxes for dashboard regions

### 8.4 ODOMETER READING
- **Technology:** PaddleOCR
- **Method:** OCR on detected dashboard regions
- **Output:** Numeric odometer value, confidence score

### 8.5 DAMAGE DETECTION
- **Technology:** YOLOv8 (object detection)
- **Method:** Pre-trained model for general object detection with heuristics for damage classification
- **Output:** Damage type, count, locations, severity classification

### 8.6 EXHAUST CLASSIFICATION
- **Technology:** Lightweight CNN or CLIP-based classification
- **Method:** Image classification on detected exhaust regions
- **Output:** Stock/modified classification, confidence score

### 8.7 REPORT GENERATION
- **Technology:** Google Gemini API (LLM)
- **Method:** Structured prompt with inspection data to generate human-readable report
- **Output:** Comprehensive inspection report with recommendations

---

## 9. SYSTEM ARCHITECTURE (MVP)

### 9.1 FRONTEND

- **Framework:** Next.js 14 with App Router
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **State Management:** React hooks and context
- **HTTP Client:** Axios
- **Key Features:**
  - Video upload with drag-and-drop
  - Real-time job status polling
  - Inspection results dashboard
  - Inspection history view
  - Responsive design

### 9.2 BACKEND API

- **Runtime:** Node.js 18+
- **Framework:** Express.js
- **Language:** TypeScript
- **Database:** SQLite (better-sqlite3)
- **File Upload:** Multer
- **Key Features:**
  - RESTful API endpoints
  - Asynchronous job processing
  - File management
  - Database operations
  - Error handling middleware

### 9.3 ML SERVICE

- **Runtime:** Python 3.9+
- **Framework:** FastAPI
- **Key Features:**
  - Video processing pipeline
  - ML model inference
  - Frame extraction service
  - Vehicle identification service
  - Dashboard detection service
  - Odometer reading service
  - Damage detection service
  - Exhaust classification service
  - Report generation service

### 9.4 STORAGE

- **Videos:** Local filesystem storage
- **Frames:** Local filesystem storage (JPEG images)
- **Metadata:** SQLite database
- **Database Tables:**
  - `files`: Uploaded video metadata
  - `jobs`: Processing job status and progress
  - `inspections`: Complete inspection results

### 9.5 DATA FLOW

1. User uploads video → Backend API receives file
2. Backend creates file record and job record
3. Backend sends processing request to ML service
4. ML service extracts frames from video
5. ML service runs all detection/classification models
6. ML service generates inspection report
7. ML service returns results to Backend API
8. Backend API stores results in database
9. Backend API updates job status to completed
10. Frontend polls job status and displays results

---

## 10. API SPECIFICATION (MVP)

### 10.1 BACKEND API ENDPOINTS

**Base URL:** `http://localhost:3001/api`

#### Upload Endpoint
- **POST** `/upload`
  - Upload video file
  - Returns: `{ jobId, fileId, message }`

#### Job Endpoints
- **GET** `/jobs/:id`
  - Get job status and progress
  - Returns: `{ id, status, progress, error_message, inspection_id, ... }`

#### Inspection Endpoints
- **GET** `/inspections`
  - Get all inspections (history)
  - Returns: Array of inspection records
- **GET** `/inspections/:id`
  - Get inspection by ID
  - Returns: Complete inspection data with all results

### 10.2 ML SERVICE API ENDPOINTS

**Base URL:** `http://localhost:8000/api`

#### Processing Endpoint
- **POST** `/process`
  - Process video and extract inspection data
  - Request: `{ video_path, inspection_id, odometer_image_path? }`
  - Returns: `{ inspection_id, frames, vehicle_info, odometer, damage, exhaust, report }`

#### Health Check
- **GET** `/health`
  - Service health check
  - Returns: `{ status: "ok" }`

#### Test Endpoint
- **POST** `/test`
  - Test endpoint for connectivity
  - Returns: `{ status: "ok", message: "..." }`

---

## 11. DATA MODELS (MVP)

### 11.1 VehicleInfo
```typescript
{
  type: "car" | "bike" | "motorcycle" | "truck" | "suv";
  brand: string;
  model: string;
  color?: string;
  confidence: number;
}
```

### 11.2 OdometerInfo
```typescript
{
  value: number | null;
  confidence: number;
  speedometer_image_path: string | null;
}
```

### 11.3 DamageInfo
```typescript
{
  scratches: { count: number; detected: boolean; };
  dents: { count: number; detected: boolean; };
  rust: { count: number; detected: boolean; };
  severity: "low" | "medium" | "high";
  locations?: Array<{
    type: string;
    frame: string;
    snapshot?: string;
    confidence: number;
    bbox?: [number, number, number, number];
  }>;
}
```

### 11.4 ExhaustInfo
```typescript
{
  type: "stock" | "modified";
  confidence: number;
}
```

### 11.5 InspectionReport
```typescript
{
  summary: string;
  vehicle_details: {
    type: string;
    brand: string;
    model: string;
    condition: string;
  };
  odometer_reading: {
    value: number | null;
    status: string;
  };
  damage_assessment: {
    overall_severity: "low" | "medium" | "high";
    details: string;
  };
  exhaust_status: {
    type: "stock" | "modified";
    notes: string;
  };
  recommendations: string[];
}
```

### 11.6 InspectionData (Complete)
```typescript
{
  id: string;
  job_id: string;
  file_id: string;
  vehicle_info?: VehicleInfo;
  odometer?: OdometerInfo;
  damage?: DamageInfo;
  exhaust?: ExhaustInfo;
  inspection_report?: InspectionReport;
  extracted_frames?: string[];
  created_at: string;
  updated_at: string;
}
```

---

## 12. MVP RISKS AND MITIGATION

### 12.1 TECHNICAL RISKS

- **RISK:** Poor video quality affecting detection accuracy  
  **MITIGATION:** Use confidence scoring and flag low-quality results. Provide clear upload guidelines.

- **RISK:** OCR misreads odometer values  
  **MITIGATION:** Use multi-frame averaging and validation. Display confidence scores prominently.

- **RISK:** Incorrect vehicle model identification  
  **MITIGATION:** Apply confidence thresholds and allow manual review. Support common vehicle models first.

- **RISK:** ML service processing failures  
  **MITIGATION:** Implement proper error handling, retry mechanisms, and graceful degradation.

- **RISK:** Large video files causing memory issues  
  **MITIGATION:** Implement file size limits, streaming processing, and efficient frame extraction.

### 12.2 BUSINESS RISKS

- **RISK:** Limited accuracy with general-purpose models  
  **MITIGATION:** Set clear expectations in MVP. Plan for custom model training in post-MVP.

- **RISK:** User adoption challenges  
  **MITIGATION:** Focus on user experience, clear documentation, and responsive support.

---

## 13. MVP SUCCESS CRITERIA

### 13.1 FUNCTIONAL SUCCESS

- ✅ Vehicle type is correctly identified in 80%+ of cases
- ✅ Vehicle brand/model is correctly identified in 70%+ of common cases
- ✅ Odometer reading matches visible dashboard reading in 75%+ of cases
- ✅ Obvious damage (scratches, dents, rust) is detected reliably (70%+ recall)
- ✅ Exhaust classification accuracy of 75%+ for clear cases
- ✅ End-to-end inspection flow works without manual intervention

### 13.2 PERFORMANCE SUCCESS

- ✅ Processing completes within 3 minutes for typical videos
- ✅ System handles concurrent uploads without degradation
- ✅ API response times meet specified targets

### 13.3 USER EXPERIENCE SUCCESS

- ✅ Users can successfully upload and process videos
- ✅ Results are presented clearly and understandably
- ✅ System provides helpful error messages when issues occur

---

## 14. DEPLOYMENT AND INFRASTRUCTURE

### 14.1 DEVELOPMENT SETUP

- All services can run locally with Docker Compose
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:3001`
- ML Service: `http://localhost:8000`

### 14.2 ENVIRONMENT VARIABLES

**Backend:**
- `PORT`: API server port (default: 3001)
- `ML_SERVICE_URL`: ML service endpoint URL

**ML Service:**
- `GEMINI_API_KEY`: Google Gemini API key for report generation
- `MOCK_MODE`: Enable mock mode for testing (optional)

**Frontend:**
- `NEXT_PUBLIC_API_URL`: Backend API URL

### 14.3 DOCKER DEPLOYMENT

- Docker Compose configuration for all services
- Separate Dockerfiles for frontend, backend, and ML service
- Production-ready docker-compose configuration available

---

## 15. FUTURE ENHANCEMENTS (POST-MVP)

- Custom-trained models for vehicle-specific tasks
- VIN number detection and validation
- Audio-based exhaust analysis
- Real-time processing capabilities
- Mobile application (iOS/Android)
- Multi-user authentication and authorization
- Advanced analytics and reporting
- Integration with vehicle databases
- Batch processing for multiple videos
- Export functionality (PDF, CSV)
