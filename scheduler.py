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
from agents.vendor_matcher import run_vendor_matching
from database.db_manager import get_database_stats
from utils.monitoring import save_status
from utils.report_generator import build_report, save_report
from utils.sales_exporter import build_sales_rows, save_sales_csv


def run_weekly_update(limit: int = None, skip_batch: bool = False):
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
        results = None
        if not skip_batch:
            results = process_batch(
                delay_seconds = 3,
                save_to_db    = True,
                verbose       = False,
                limit         = limit,
                resume        = True,
            )

            display_batch_summary(results)
            save_batch_report(results)
        else:
            print("Skipping AI batch update.")

        print("\nRunning vendor matching...")
        run_vendor_matching(min_confidence="weak", include_fallback=False)

        print("\nGenerating sales intelligence report...")
        report_path = save_report(build_report(limit=20))
        print(f"Report saved: {report_path}")

        print("\nGenerating sales-ready CSV...")
        sales_path = save_sales_csv(build_sales_rows(limit=100, min_tier=2, include_weak=False))
        print(f"Sales CSV saved: {sales_path}")

        print("\nWriting monitoring status...")
        status_path = save_status()
        print(f"Monitoring status saved: {status_path}")

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
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of niche markets to update during this run"
    )
    parser.add_argument(
        "--skip-batch",
        action="store_true",
        help="Skip AI niche batch and only run matching/report/export/monitoring"
    )
    args = parser.parse_args()

    if args.run_now:
        run_weekly_update(limit=args.limit, skip_batch=args.skip_batch)
    else:
        start_scheduler()
