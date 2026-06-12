-- Database schema for Vehicle Intelligence Platform
-- SQLite database to store inspection metadata

-- Table to store uploaded video files
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table to store processing jobs
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    -- status: 'pending', 'processing', 'completed', 'failed'
    progress INTEGER DEFAULT 0,
    -- progress: 0-100 percentage
    error_message TEXT,
    inspection_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id)
);

-- Table to store inspection results
CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    
    -- Vehicle identification
    vehicle_type TEXT,
    -- vehicle_type: VehicleType in shared/types.ts ('car', 'bike', 'motorcycle', 'truck', 'suv')
    vehicle_brand TEXT,
    vehicle_model TEXT,
    vehicle_year TEXT,
    vehicle_variant TEXT,
    vehicle_confidence REAL,
    vehicle_info TEXT,
    
    -- Odometer information
    odometer_value INTEGER,
    odometer_confidence REAL,
    speedometer_image_path TEXT,
    odometer_info TEXT,
    
    -- Damage detection
    damage_summary TEXT,
    -- JSON string with damage details
    scratches_detected INTEGER DEFAULT 0,
    dents_detected INTEGER DEFAULT 0,
    rust_detected INTEGER DEFAULT 0,
    cracks_detected INTEGER DEFAULT 0,
    paint_damage_detected INTEGER DEFAULT 0,
    damage_severity TEXT,
    -- damage_severity: DamageSeverity in shared/types.ts ('low', 'medium', 'high')
    
    -- Exhaust information
    exhaust_type TEXT,
    -- exhaust_type: 'stock', 'modified'
    exhaust_confidence REAL,
    exhaust_image_path TEXT,
    
    -- Complete inspection report (JSON)
    inspection_report TEXT,
    
    -- Frame information (JSON array of frame paths)
    extracted_frames TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_file_id ON jobs(file_id);
CREATE INDEX IF NOT EXISTS idx_inspections_job_id ON inspections(job_id);
CREATE INDEX IF NOT EXISTS idx_inspections_file_id ON inspections(file_id);

-- HITL feedback on detected damage. Stored separately from the
-- damage_summary JSON so it survives pipeline schema changes.
-- Keyed by (inspection_id, location_index) instead of an internal damage
-- UUID, because location_index is stable across re-renders.
CREATE TABLE IF NOT EXISTS damage_feedback (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    location_index INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    -- verdict: 'confirmed' | 'wrong_type' | 'false_positive' | 'missed_severity'
    corrected_type TEXT,
    corrected_severity TEXT,
    note TEXT,
    reviewer TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id)
);

-- Damage the model didn't catch. Reviewer draws a bbox over any frame
-- in the gallery and tags it with the correct type/severity.
CREATE TABLE IF NOT EXISTS damage_missing_reports (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    frame_path TEXT,
    bbox TEXT,
    -- bbox: JSON array [x1, y1, x2, y2] in frame coordinates
    type TEXT,
    severity TEXT,
    part TEXT,
    note TEXT,
    reviewer TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inspection_id) REFERENCES inspections(id)
);

CREATE INDEX IF NOT EXISTS idx_damage_feedback_inspection
    ON damage_feedback(inspection_id);
CREATE INDEX IF NOT EXISTS idx_damage_feedback_created_at
    ON damage_feedback(created_at);
-- One verdict per (inspection_id, location_index) — the documented feedback
-- key. Re-reviews upsert in place (see createDamageFeedback). Existing DBs
-- with duplicates are deduped by the init.ts migration before this index is
-- (re)attempted there.
CREATE UNIQUE INDEX IF NOT EXISTS idx_damage_feedback_key
    ON damage_feedback(inspection_id, location_index);
CREATE INDEX IF NOT EXISTS idx_damage_missing_inspection
    ON damage_missing_reports(inspection_id);
CREATE INDEX IF NOT EXISTS idx_damage_missing_created_at
    ON damage_missing_reports(created_at);
