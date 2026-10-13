"""Persistent single-job-at-a-time SavedFlow worker."""

import logging
import os
import signal
import threading
import time

from app import create_app
from extensions import get_db
from services.jobs.manager import claim_next_job, run_analysis_job


def run_worker(poll_seconds=None, stop_event=None):
    app = create_app()
    stop_event = stop_event or threading.Event()
    poll_seconds = poll_seconds or int(os.environ.get("SAVEDFLOW_WORKER_POLL_SECONDS", "5"))
    if poll_seconds < 1:
        raise ValueError("SAVEDFLOW_WORKER_POLL_SECONDS must be at least 1.")

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    logger = logging.getLogger("savedflow.worker")
    with app.app_context():
        db = get_db()
        logger.info("SavedFlow worker started; polling every %s seconds.", poll_seconds)
        while not stop_event.is_set():
            job = claim_next_job(db)
            if job:
                logger.info("Claimed AI job %s for item %s", job["_id"], job["item_id"])
                run_analysis_job(db, job["_id"])
                finished = db.ai_jobs.find_one({"_id": job["_id"]})
                logger.info("AI job %s finished with status %s", job["_id"], (finished or {}).get("status", "UNKNOWN"))
                continue
            stop_event.wait(poll_seconds)
        logger.info("SavedFlow worker stopped.")


def main():
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    run_worker(stop_event=stop_event)


if __name__ == "__main__":
    main()
