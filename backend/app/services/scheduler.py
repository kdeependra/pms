"""
Background Task Scheduler for Alerts.

Sets up periodic monitoring of project health and triggers alert creation.
Uses APScheduler for scheduling background jobs.

Routes:
- POST /api/v1/alerts/scheduler/start - Start scheduler
- POST /api/v1/alerts/scheduler/stop - Stop scheduler
- GET /api/v1/alerts/scheduler/status - Check scheduler status

Usage:
    from app.services.scheduler import scheduler, start_scheduler, stop_scheduler
    
    # In main.py startup
    start_scheduler()
    
    # In shutdown
    stop_scheduler()
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[BackgroundScheduler] = None
_scheduler_running = False


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Get the current scheduler instance."""
    return scheduler


def is_scheduler_running() -> bool:
    """Check if scheduler is currently running."""
    return _scheduler_running if scheduler else False


async def monitor_all_projects_job():
    """
    Background job that monitors all projects.
    
    Runs periodically to:
    1. Check sentiment from Phase 1
    2. Check communication from Phase 2
    3. Check task delays and scope
    4. Check budget and team workload
    5. Create corresponding alerts
    
    Called by APScheduler every 30 minutes by default.
    """
    try:
        from app.db import get_db
        from app.services.alert_integration_service import BackgroundAlertMonitor

        # Get database session
        db = next(get_db())

        # Run monitoring
        monitor = BackgroundAlertMonitor()
        await monitor.monitor_all_projects(db)

        logger.info(f"[{datetime.utcnow().isoformat()}] Background alert monitoring complete")

    except Exception as e:
        logger.error(f"Error in alert monitoring job: {e}", exc_info=True)


def start_scheduler(check_interval_minutes: int = 30):
    """
    Start the background scheduler.
    
    Args:
        check_interval_minutes: How often to run checks (default: 30 minutes)
    
    Returns:
        bool: True if started successfully
    """
    global scheduler, _scheduler_running

    try:
        if scheduler and scheduler.running:
            logger.warning("Scheduler is already running")
            return True

        # Create scheduler
        scheduler = BackgroundScheduler()
        
        # Add job to monitor all projects
        scheduler.add_job(
            monitor_all_projects_job,
            trigger=IntervalTrigger(minutes=check_interval_minutes),
            id='monitor_all_projects',
            name='Monitor all projects for alerts',
            replace_existing=True
        )

        # Start scheduler
        scheduler.start()
        _scheduler_running = True

        logger.info(f"Alert scheduler started. Check interval: {check_interval_minutes} minutes")
        logger.info("Background alert monitoring jobs registered")

        return True

    except Exception as e:
        logger.error(f"Failed to start alert scheduler: {e}", exc_info=True)
        _scheduler_running = False
        return False


def stop_scheduler():
    """
    Stop the background scheduler gracefully.
    
    Returns:
        bool: True if stopped successfully
    """
    global scheduler, _scheduler_running

    try:
        if not scheduler or not scheduler.running:
            logger.warning("Scheduler is not running")
            return True

        scheduler.shutdown(wait=True)
        _scheduler_running = False

        logger.info("Alert scheduler stopped")
        return True

    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)
        return False


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.
    
    Returns:
        dict with status information
    """
    try:
        if not scheduler:
            return {
                "status": "not_initialized",
                "running": False,
                "jobs": []
            }

        jobs_info = []
        if scheduler.running:
            for job in scheduler.get_jobs():
                jobs_info.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger)
                })

        return {
            "status": "running" if scheduler.running else "stopped",
            "running": scheduler.running,
            "job_count": len(jobs_info),
            "jobs": jobs_info
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# Scheduler Lifecycle Management
# ============================================================================

def initialize_scheduler():
    """
    Initialize scheduler (called on application startup).
    
    Can be integrated into FastAPI lifespan events:
    
    @app.on_event("startup")
    async def startup_event():
        initialize_scheduler()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        finalize_scheduler()
    """
    start_scheduler(check_interval_minutes=30)


def finalize_scheduler():
    """
    Finalize scheduler (called on application shutdown).
    
    Used in FastAPI shutdown event.
    """
    stop_scheduler()
