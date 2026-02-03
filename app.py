"""
FastAPI web server for X-piggybacking scraper with scheduled execution.

This module provides:
- Health check endpoint for Railway monitoring
- Manual trigger endpoint for on-demand scraping
- Automatic daily scraping via APScheduler
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from scheduler import XScraperScheduler, execute_scrape_job_sync
from x_auto.review.app import app as review_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize and start the scheduler
    - Shutdown: Gracefully stop the scheduler
    """
    global scheduler

    # Startup: Initialize scheduler
    logger.info("=" * 80)
    logger.info("Starting X-Piggybacking Scraper Service")
    logger.info("=" * 80)

    scheduler = XScraperScheduler(background_mode=True)
    scheduler.add_daily_scrape_job()
    scheduler.add_reply_sender_job()  # Check approved replies every 5 min
    scheduler.start()

    status = scheduler.get_status()
    logger.info(f"Scheduler status: {status}")
    logger.info("Service startup complete")
    logger.info("=" * 80)

    yield

    # Shutdown: Stop scheduler
    logger.info("Shutting down scheduler...")
    if scheduler:
        scheduler.shutdown()
    logger.info("Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="X-Piggybacking Scraper",
    description="Automated X (Twitter) profile scraper with LLM filtering",
    version="1.0.0",
    lifespan=lifespan
)


# Mount the review dashboard under /dashboard
app.mount("/dashboard", review_app)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "X-Piggybacking Scraper",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "trigger": "/trigger (POST)",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Railway monitoring.

    Returns:
        Service status including scheduler information.
    """
    if not scheduler:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": "Scheduler not initialized"
            }
        )

    status = scheduler.get_status()

    return {
        "status": "healthy",
        "service": "X-Piggybacking Scraper",
        "scheduler_running": status["running"],
        "scheduled_time": status["scheduled_time"],
        "next_scrape": status.get("next_run"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "local")
    }


@app.post("/trigger")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """
    Manually trigger a scrape job.

    This endpoint allows on-demand execution of the scraping workflow
    without waiting for the scheduled time.

    Returns:
        Status message indicating the job has been triggered.
    """
    logger.info("Manual trigger endpoint called")

    try:
        # Run the scrape job in the background
        background_tasks.add_task(execute_scrape_job_sync)

        return {
            "status": "triggered",
            "message": "Scrape job started in background",
            "note": "Check logs for execution progress"
        }

    except Exception as e:
        logger.error(f"Failed to trigger scrape: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger scrape job: {str(e)}"
        )


@app.get("/status")
async def get_status():
    """
    Get detailed scheduler status.

    Returns:
        Detailed information about the scheduler and upcoming jobs.
    """
    if not scheduler:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialized"
        )

    status = scheduler.get_status()

    return {
        "scheduler": status,
        "configuration": {
            "max_profile_urls": os.getenv("MAX_PROFILE_URLS", "0"),
            "post_results_limit": os.getenv("POST_RESULTS_LIMIT", "20"),
            "lookback_days": os.getenv("LOOKBACK_DAYS", "1"),
            "enable_x_posting": os.getenv("ENABLE_X_POSTING", "false")
        }
    }


if __name__ == "__main__":
    # Get port from environment (Railway sets this automatically)
    port = int(os.getenv("PORT", 8080))

    logger.info(f"Starting server on port {port}")

    # Run the FastAPI app with uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
