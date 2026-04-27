# scheduler.py
# Weekly scheduler for the Loopa Intelligence Platform.
# Runs the batch processor automatically every Monday at 9:00 AM.
# Can also be triggered manually at any time.

import os
import sys
import schedule
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.batch_processor import process_batch, display_batch_summary, save_batch_report
from database.db_manager import get_database_stats


def run_weekly_update():
    """
    Runs the full intelligence update cycle.
    Called automatically every Monday at 9:00 AM
    or manually when needed.
    """

    print("\n" + "=" * 60)
    print("LOOPA INTELLIGENCE - WEEKLY UPDATE STARTED")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        results = process_batch(
            delay_seconds = 3,
            save_to_db    = True,
            verbose       = False
        )

        display_batch_summary(results)
        save_batch_report(results)

        print()
        get_database_stats()

        print("\nWeekly update completed successfully.")
        print(f"Next run: Monday at 09:00 AM")

    except Exception as e:
        print(f"\nWeekly update failed: {str(e)}")
        raise e


def start_scheduler():
    """
    Starts the scheduler.
    Registers the weekly job and keeps the process running.
    """

    print("Loopa Intelligence Scheduler started.")
    print("Scheduled: Every Monday at 09:00 AM")
    print("Press Ctrl+C to stop.\n")

    schedule.every().monday.at("09:00").do(run_weekly_update)

    while True:
        schedule.run_pending()
        time.sleep(60)


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(description="Loopa Intelligence Scheduler")
    parser.add_argument(
        "--run-now",
        action  = "store_true",
        help    = "Run the update immediately instead of waiting for schedule"
    )
    args = parser.parse_args()

    if args.run_now:
        run_weekly_update()
    else:
        start_scheduler()