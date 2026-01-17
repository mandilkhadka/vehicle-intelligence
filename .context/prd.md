# PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Product Name:** Vehicle Intelligence Platform (VIP) – MVP

## MVP OBJECTIVE

Build a minimum viable product that extracts core vehicle information from a 360-degree walk-around video.
The goal of the MVP is to prove that AI can reliably convert unstructured vehicle video into structured inspection data.

The MVP prioritizes accuracy, explainability, and speed over feature completeness.

## MVP SCOPE

### IN SCOPE:

- 360-degree vehicle video upload
- Frame extraction from uploaded video
- Vehicle type, brand, and model detection
- Odometer (kilometers run) detection
- Speedometer image extraction
- Basic vehicle condition detection (scratches, dents, rust)
- Exhaust detection (stock vs modified)
- Structured inspection output (JSON and UI display)

### OUT OF SCOPE (POST-MVP):

- VIN number detection
- Audio-based exhaust analysis
- Emission compliance checks
- Real-time processing
- Mobile application
- Legal or regulatory certification

## TARGET USERS (MVP)

- Vehicle inspectors
- Used car dealerships
- Internal AI validation and testing users

## CORE USER FLOW (MVP)

Upload 360-degree video → Extract frames from video → Run AI analysis → Display inspection result dashboard

## MVP USER STORIES

- As a user, I want to upload a 360-degree vehicle video so I can inspect a vehicle without manually taking photos.

- As a user, I want to see images extracted from the video so I can verify what the AI analyzed.

- As a user, I want the system to identify the vehicle model and kilometers run.

- As a user, I want to know if the vehicle has visible damage such as scratches, dents, or rust.

- As a user, I want to know if the exhaust appears to be stock or modified.

- As a user, I want a clear and structured inspection result.

## FUNCTIONAL REQUIREMENTS (MVP)

### 6.1 VIDEO UPLOAD AND FRAME EXTRACTION

- **MVP-FR-1:** The system shall allow users to upload a 360-degree vehicle video in MP4 format.
- **MVP-FR-2:** The system shall extract frames from the video at fixed intervals (for example, one frame per second).
- **MVP-FR-3:** The system shall display extracted frames in an image gallery.

### 6.2 VEHICLE IDENTIFICATION

- **MVP-FR-4:** The system shall detect whether the vehicle is a car or a bike.
- **MVP-FR-5:** The system shall identify the vehicle brand and model.
- **MVP-FR-6:** The system shall display a confidence score for vehicle identification.

### 6.3 ODOMETER AND SPEEDOMETER DETECTION

- **MVP-FR-7:** The system shall detect the dashboard region from extracted frames.
- **MVP-FR-8:** The system shall extract the odometer value using OCR.
- **MVP-FR-9:** The system shall display the speedometer image used for odometer extraction.

### 6.4 BASIC CONDITION DETECTION

- **MVP-FR-10:** The system shall detect visible scratches.
- **MVP-FR-11:** The system shall detect visible dents.
- **MVP-FR-12:** The system shall detect visible rust.
- **MVP-FR-13:** The system shall classify damage severity as low or high.

### 6.5 EXHAUST DETECTION

- **MVP-FR-14:** The system shall detect the exhaust region.
- **MVP-FR-15:** The system shall classify the exhaust as stock or modified.
- **MVP-FR-16:** The system shall display a confidence score for exhaust classification.

### 6.6 INSPECTION OUTPUT

- **MVP-FR-17:** The system shall generate a structured inspection result in JSON format.
- **MVP-FR-18:** The system shall display the inspection result in the user interface.

## NON-FUNCTIONAL REQUIREMENTS (MVP)

### PERFORMANCE:

End-to-end processing time per video shall be less than 3 minutes.

### RELIABILITY:

- Odometer OCR results shall be validated using multiple frames.
- All AI outputs shall include confidence scores.

### SECURITY:

- File uploads shall be handled securely.
- Media files shall be accessed using temporary signed URLs.

## AI AND ML COMPONENTS (MVP)

- **FRAME EXTRACTION:** OpenCV (free)
- **OBJECT DETECTION:** YOLOv8 (open-source)
- **MODEL IDENTIFICATION:** CLIP or ViT (local inference)
- **OCR:** PaddleOCR / Tesseract (free)
- **DAMAGE DETECTION:** YOLO pretrained model
- **EXHAUST CLASSIFICATION:** Lightweight CNN (local)
- **REASONING & REPORT:** Gemini LLM (free tier)

## MODEL CONTEXT PROTOCOL (MCP) – MVP

### CONTEXT OBJECT:

VehicleInspectionContext includes:

- videoUrl
- extractedFrames
- vehicleInfo
- odometer
- exhaustInfo
- damageSummary

### TOOL EXECUTION FLOW:

1. Extract frames from video
2. Identify vehicle
3. Read odometer value
4. Detect vehicle damage
5. Detect exhaust and modifications
6. Generate inspection output

## SYSTEM ARCHITECTURE (MVP)

### FRONTEND:

- Next.js + TypeScript (free)
- Tailwind CSS

### BACKEND:

- Python + Node.js (free)
- API layer for uploads and analysis
- Python-based machine learning service
- Asynchronous job processing

### STORAGE:

- Local filesystem / free object storage
- Object storage for videos and extracted frames
- Relational database for inspection metadata

## MVP RISKS AND MITIGATION

- **RISK:** Poor video quality  
  **MITIGATION:** Use confidence scoring and flag low-quality results

- **RISK:** OCR misreads odometer values  
  **MITIGATION:** Use multi-frame averaging and validation

- **RISK:** Incorrect vehicle model identification  
  **MITIGATION:** Apply confidence thresholds and allow manual review

## MVP SUCCESS CRITERIA

- Vehicle model is correctly identified in most common cases
- Odometer reading matches visible dashboard reading
- Obvious damage is detected reliably
- End-to-end inspection flow works without manual intervention
