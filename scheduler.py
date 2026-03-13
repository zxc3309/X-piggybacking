"""
APScheduler configuration for daily X scraping tasks.

This module manages scheduled execution of:
- X scraper workflow (daily at configured time)
"""

import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class XScraperScheduler:
    """
    Manages scheduled execution of X scraping tasks.

    Features:
        - Runs scraper daily at configured time (default: 08:00 Taiwan time)
        - Uses BackgroundScheduler to run alongside web server
        - Supports Asia/Taipei timezone for scheduling

    Example:
        scheduler = XScraperScheduler()
        scheduler.add_daily_scrape_job()
        scheduler.start()
    """

    def __init__(self, background_mode: bool = True):
        """
        Initialize the scheduler.

        Args:
            background_mode: If True, uses BackgroundScheduler (non-blocking).
                           Suitable for running alongside a web server.
        """
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Taipei'))
        self.taipei_tz = pytz.timezone('Asia/Taipei')

        # Get schedule from environment or use defaults
        self.schedule_hour = int(os.getenv("COLLECTION_SCHEDULE_HOUR", "8"))
        self.schedule_minute = int(os.getenv("COLLECTION_SCHEDULE_MINUTE", "0"))

        logger.info(
            f"Scheduler initialized with scrape schedule: "
            f"{self.schedule_hour:02d}:{self.schedule_minute:02d} Asia/Taipei"
        )

    def add_daily_scrape_job(self):
        """
        Add the daily scrape job to the scheduler.

        The job runs at the configured time (default: 08:00 Taiwan time)
        and executes the full scrape and filter workflow.
        """
        self.scheduler.add_job(
            func=self._execute_scrape_job,
            trigger=CronTrigger(
                hour=self.schedule_hour,
                minute=self.schedule_minute,
                timezone=self.taipei_tz
            ),
            id='daily_x_scrape',
            name='Daily X Profile Scraper',
            replace_existing=True
        )

        logger.info(
            f"Daily scrape job scheduled at "
            f"{self.schedule_hour:02d}:{self.schedule_minute:02d} Asia/Taipei"
        )

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started successfully")

            # Log next run time
            jobs = self.scheduler.get_jobs()
            if jobs:
                next_run = jobs[0].next_run_time
                logger.info(f"Next scrape scheduled for: {next_run}")
        else:
            logger.warning("Scheduler already running")

    def shutdown(self):
        """Gracefully shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down successfully")

    def get_status(self) -> dict:
        """
        Get current scheduler status.

        Returns:
            Dictionary with scheduler information including:
            - running: Whether scheduler is active
            - next_run: Next scheduled run time
            - scheduled_time: Configured daily run time
        """
        status = {
            "running": self.scheduler.running,
            "scheduled_time": f"{self.schedule_hour:02d}:{self.schedule_minute:02d} daily (Asia/Taipei)",
            "next_run": None
        }

        if self.scheduler.running:
            jobs = self.scheduler.get_jobs()
            if jobs:
                next_run = jobs[0].next_run_time
                if next_run:
                    status["next_run"] = next_run.isoformat()

        return status

    def _execute_scrape_job(self):
        """
        Execute the scrape and filter workflow.

        This is the actual job function that runs on schedule.
        It imports and calls the main workflow function.
        """
        logger.info("=" * 80)
        logger.info("Starting scheduled X scrape job")
        logger.info(f"Execution time: {datetime.now(self.taipei_tz).isoformat()}")
        logger.info("=" * 80)

        try:
            # Import here to avoid circular dependencies
            from x_auto.workflow.scrape_filter import run_scrape_and_filter

            # Execute the workflow
            filtered_posts = run_scrape_and_filter()

            logger.info(f"Scrape job completed successfully")
            logger.info(f"Total filtered posts: {len(filtered_posts)}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Scrape job failed with error: {e}", exc_info=True)
            logger.info("=" * 80)
            raise

def execute_scrape_job_sync():
    """
    Synchronous wrapper for manual execution.

    This function can be called directly to trigger a scrape
    without waiting for the scheduled time.
    """
    logger.info("Manual scrape triggered")

    try:
        from x_auto.workflow.scrape_filter import run_scrape_and_filter
        filtered_posts = run_scrape_and_filter()
        logger.info(f"Manual scrape completed. Filtered posts: {len(filtered_posts)}")
        return filtered_posts
    except Exception as e:
        logger.error(f"Manual scrape failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="X Scraper Scheduler")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Execute the scrape job immediately instead of waiting for schedule"
    )
    args = parser.parse_args()

    if args.run_now:
        print("Running scrape job immediately...")
        execute_scrape_job_sync()
    else:
        # Start the scheduler normally
        print("Starting scheduler in background mode...")
        scheduler = XScraperScheduler()
        scheduler.add_daily_scrape_job()
        scheduler.start()

        # Keep the process running
        import time
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.shutdown()
