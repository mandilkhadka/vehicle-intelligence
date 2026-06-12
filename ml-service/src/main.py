"""
ML Service main entry point
Production-ready FastAPI application for vehicle inspection processing
"""

import os
import sys
import signal
import logging
from secrets import compare_digest
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

# Add parent directory (ml-service) to path to allow imports
# When running from ml-service directory: python src/main.py
# When running from project root: python ml-service/src/main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Load environment variables before importing service modules that may read env.
from src.config.env import load_ml_environment

load_ml_environment()

from src.api.process import router as process_router, initialize_ml_services
from src.api.preflight import router as preflight_router
from src.services.model_registry import get_model_registry
from src.services.pipeline_readiness import build_pipeline_readiness

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Environment configuration
NODE_ENV = os.getenv("NODE_ENV", "development")
PORT = int(os.getenv("PORT", "8000"))
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001"
).split(",")
ML_SERVICE_API_KEY = os.getenv("ML_SERVICE_API_KEY", "").strip()
PROTECTED_API_PATHS = {"/api/process", "/api/retry-vlm"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("Starting ML Service...")
    logger.info(f"Environment: {NODE_ENV}")
    logger.info(f"Port: {PORT}")
    if NODE_ENV == "production" and len(ML_SERVICE_API_KEY) < 32:
        raise RuntimeError("ML_SERVICE_API_KEY must be set to at least 32 characters in production")

    # Initialize ML models at startup (singleton pattern)
    logger.info("Initializing ML models at startup...")
    try:
        model_registry = get_model_registry()
        model_registry.initialize_all_models()
        app.state.model_registry = model_registry
        logger.info("ML models initialized and stored in app.state")

        # Cache ML service instances to avoid re-initialization per request
        ml_services = initialize_ml_services(model_registry)
        app.state.ml_services = ml_services
        logger.info("ML services initialized and cached in app.state")
    except Exception as e:
        logger.error(f"Failed to initialize ML models: {e}", exc_info=True)
        raise RuntimeError(f"ML Service startup failed: {e}") from e

    yield
    # Shutdown
    logger.info("Shutting down ML Service...")


# Create FastAPI app
app = FastAPI(
    title="Vehicle Intelligence Platform ML Service",
    description="AI/ML service for vehicle inspection processing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if NODE_ENV != "production" else None,
    redoc_url="/redoc" if NODE_ENV != "production" else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in CORS_ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_internal_api_key(request: Request, call_next):
    """Require a shared internal token for backend-to-ML processing calls."""
    if request.url.path in PROTECTED_API_PATHS and ML_SERVICE_API_KEY:
        supplied = request.headers.get("X-Internal-API-Key", "")
        if not compare_digest(supplied, ML_SERVICE_API_KEY):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid internal API key",
                    }
                },
            )
    return await call_next(request)


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred" if NODE_ENV == "production" else str(exc),
            }
        },
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Include routers
app.include_router(process_router, prefix="/api", tags=["processing"])
app.include_router(preflight_router, prefix="/api", tags=["preflight"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ml-service",
        "version": "1.0.0",
        "environment": NODE_ENV,
    }


@app.get("/ready")
async def readiness_check(
    live_gemini: bool = False,
    live_openai: bool = False,
    live_ollama: bool = False,
):
    """Readiness check endpoint for video-understanding dependencies."""
    return build_pipeline_readiness(
        model_registry=getattr(app.state, "model_registry", None),
        require_loaded_models=True,
        live_gemini=live_gemini,
        live_openai=live_openai,
        live_ollama=live_ollama,
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Vehicle Intelligence Platform ML Service",
        "version": "1.0.0",
        "docs": "/docs" if NODE_ENV != "production" else None,
    }


# Graceful shutdown handler
def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal, shutting down gracefully...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
    )
