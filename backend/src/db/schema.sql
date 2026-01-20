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
    -- vehicle_type: 'car', 'bike'
    vehicle_brand TEXT,
    vehicle_model TEXT,
    vehicle_confidence REAL,
    
    -- Odometer information
    odometer_value INTEGER,
    odometer_confidence REAL,
    speedometer_image_path TEXT,
    
    -- Damage detection
    damage_summary TEXT,
    -- JSON string with damage details
    scratches_detected INTEGER DEFAULT 0,
    dents_detected INTEGER DEFAULT 0,
    rust_detected INTEGER DEFAULT 0,
    damage_severity TEXT,
    -- damage_severity: 'low', 'high'
    
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
