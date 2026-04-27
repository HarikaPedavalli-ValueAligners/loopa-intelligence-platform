# agents/batch_processor.py
# Processes multiple niche markets in sequence.
# Researches, scores, and saves each one to the database.
# This is the core engine behind the weekly automated update.

import os
import sys
import time
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.niche_market_agent import research_niche_market, display_results
from database.db_manager import save_niche_market, get_top_niche_markets, get_database_stats


# ------------------------------------------------------------
# Niche Market List
# ------------------------------------------------------------

NICHE_MARKETS_TO_RESEARCH = [

    # Healthcare
    ("Healthcare", "Hospitals", "Hospital Supply Chain"),
    ("Healthcare", "Hospitals", "Emergency Services"),
    ("Healthcare", "Medical Devices", None),
    ("Healthcare", "Telemedicine", None),

    # Financial Services
    ("Financial Services", "Banking", "Retail Banking"),
    ("Financial Services", "Banking", "Investment Banking"),
    ("Financial Services", "Insurance", None),
    ("Financial Services", "Fintech", None),

    # Manufacturing
    ("Manufacturing", "Contract Manufacturing", None),
    ("Manufacturing", "Automotive", "Auto Parts Supply Chain"),

    # E-Commerce
    ("E-Commerce", "E-Commerce Platforms", None),
    ("E-Commerce", "Direct-to-Consumer Brands", None),

    # Logistics
    ("Logistics", "Supply Chain Management", None),
    ("Logistics", "Last Mile Delivery", None),

    # Energy
    ("Energy", "Oil and Gas", None),
    ("Energy", "Renewable Energy", "Solar Energy Providers"),

    # Professional Services
    ("Professional Services", "Legal Services", None),
    ("Professional Services", "Accounting Firms", None),

    # Retail
    ("Retail", "Grocery Retail", None),
    ("Retail", "Fashion Retail", None),
]


# ------------------------------------------------------------
# Batch Processing Engine
# ------------------------------------------------------------

def process_batch(
    niche_markets: list = None,
    delay_seconds: int = 3,
    save_to_db: bool = True,
    verbose: bool = False
) -> dict:
    """
    Researches and saves a list of niche markets.

    Args:
        niche_markets : List of (industry, sub_industry, sub_sub_industry) tuples.
        delay_seconds : Seconds to wait between API calls.
        save_to_db    : Whether to save results to the database.
        verbose       : Whether to print full output per niche.

    Returns:
        Dictionary with summary of results.
    """

    markets = niche_markets or NICHE_MARKETS_TO_RESEARCH
    total   = len(markets)

    results = {
        "total"      : total,
        "success"    : 0,
        "failed"     : 0,
        "errors"     : [],
        "processed"  : [],
        "started_at" : datetime.now().isoformat(),
    }

    print(f"\nLoopa Intelligence - Batch Processor")
    print(f"Started    : {results['started_at']}")
    print(f"Total Jobs : {total}")
    print("-" * 60)

    for index, market in enumerate(markets, start=1):

        industry         = market[0]
        sub_industry     = market[1] if len(market) > 1 else None
        sub_sub_industry = market[2] if len(market) > 2 else None

        parts      = [p for p in [industry, sub_industry, sub_sub_industry] if p]
        niche_name = " > ".join(parts)

        print(f"\n[{index}/{total}] {niche_name}")

        try:
            data = research_niche_market(
                industry         = industry,
                sub_industry     = sub_industry,
                sub_sub_industry = sub_sub_industry
            )

            if verbose:
                display_results(data)

            if save_to_db:
                niche_id = save_niche_market(data)
                print(
                    f"  Saved — "
                    f"Demand: {data['demand_score']} | "
                    f"Outbound: {data['outbound_score']} | "
                    f"Priority: {data['priority_score']} | "
                    f"Tier: {data['priority_tier']} | "
                    f"DB ID: {niche_id}"
                )

            results["success"] += 1
            results["processed"].append({
                "niche"          : niche_name,
                "demand_score"   : data["demand_score"],
                "outbound_score" : data["outbound_score"],
                "priority_score" : data["priority_score"],
                "priority_tier"  : data["priority_tier"],
                "top_pain_point" : data["top_pain_points"][0]["pain_point"] if data.get("top_pain_points") else "N/A"
            })

        except Exception as e:
            print(f"  Failed — {str(e)}")
            results["failed"] += 1
            results["errors"].append({
                "niche" : niche_name,
                "error" : str(e)
            })

        if index < total:
            time.sleep(delay_seconds)

    results["completed_at"] = datetime.now().isoformat()

    return results


def display_batch_summary(results: dict) -> None:
    """Prints a clean summary of the batch run."""

    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Total    : {results['total']}")
    print(f"Success  : {results['success']}")
    print(f"Failed   : {results['failed']}")
    print(f"Started  : {results['started_at']}")
    print(f"Finished : {results['completed_at']}")

    if results["processed"]:
        print("\nResults (sorted by priority score):")
        print("-" * 60)

        sorted_results = sorted(
            results["processed"],
            key     = lambda x: x["priority_score"],
            reverse = True
        )

        for i, item in enumerate(sorted_results, start=1):
            print(
                f"  {i:>2}. "
                f"[Tier {item['priority_tier']}] "
                f"Priority: {item['priority_score']}  |  "
                f"Demand: {item['demand_score']}  |  "
                f"Outbound: {item['outbound_score']}  |  "
                f"{item['niche']}"
            )
            print(f"       Top Threat: {item['top_pain_point']}")

    if results["errors"]:
        print("\nFailed:")
        for err in results["errors"]:
            print(f"  - {err['niche']}: {err['error']}")

    print("=" * 60)


def save_batch_report(results: dict) -> None:
    """Saves the batch results to a JSON report file."""

    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nReport saved: {report_path}")


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":

    results = process_batch(
        delay_seconds = 3,
        save_to_db    = True,
        verbose       = False
    )

    display_batch_summary(results)
    save_batch_report(results)

    print()
    get_database_stats()