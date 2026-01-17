"""
ML Service main entry point
FastAPI application for vehicle inspection processing
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.process import router as process_router

# Create FastAPI app
app = FastAPI(
    title="Vehicle Intelligence Platform ML Service",
    description="AI/ML service for vehicle inspection processing",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(process_router, prefix="/api", tags=["processing"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "ML Service is running"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Vehicle Intelligence Platform ML Service",
        "version": "0.1.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
