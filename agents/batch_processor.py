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
from database.db_manager import (
    finish_intelligence_run,
    get_database_stats,
    get_niche_markets_for_batch,
    record_run_item_failure,
    record_run_item_skipped,
    record_run_item_start,
    record_run_item_success,
    save_niche_market,
    start_intelligence_run,
)


SEED_IDENTITY_FIELDS = [
    "industry",
    "sub_industry",
    "sub_sub_industry",
    "sub_sub_sub_industry",
    "sub_sub_sub_sub_industry",
    "niche_name",
    "naics_code",
    "geography",
    "ownership_sector",
    "sector_code",
    "sub_industry_code",
    "sub_sub_industry_code",
    "sub_sub_sub_industry_code",
    "sub_sub_sub_sub_industry_code",
    "primary_buyer_role",
    "likely_compliance_regimes",
    "conditional_compliance_regimes",
    "compliance_tag_confidence",
    "compliance_tag_basis",
    "recommended_cyber_themes",
    "regulatory_or_compliance_drivers",
]


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

def _configured_ai_label() -> str:
    """Returns provider:model label for run metadata."""
    provider = os.getenv("AI_PROVIDER", "groq").strip().lower()
    if provider == "openai":
        model = os.getenv("OPENAI_MODEL", "unset")
    elif provider == "gemini":
        model = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    elif provider == "vertex":
        model = os.getenv("VERTEX_MODEL") or os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    else:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return f"{provider}:{model}"


def _is_rate_limit_error(error: Exception) -> bool:
    """Returns True when an exception looks like a provider quota/rate limit."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in [
            "rate limit",
            "rate_limit",
            "error code: 429",
            "'code': 'rate_limit_exceeded'",
            '"code": "rate_limit_exceeded"',
        ]
    )


def _market_components(market) -> dict:
    """Normalizes tuple or DB market input into one dictionary."""
    if isinstance(market, dict):
        return market

    return {
        "industry": market[0],
        "sub_industry": market[1] if len(market) > 1 else None,
        "sub_sub_industry": market[2] if len(market) > 2 else None,
    }


def _market_display_name(market: dict) -> str:
    """Builds a readable market name without losing deep hierarchy context."""
    if market.get("niche_name"):
        return market["niche_name"]

    parts = [
        market.get("industry"),
        market.get("sub_industry"),
        market.get("sub_sub_industry"),
        market.get("sub_sub_sub_industry"),
        market.get("sub_sub_sub_sub_industry"),
    ]
    return " > ".join(str(part) for part in parts if part)


def _apply_seed_identity(data: dict, market: dict) -> dict:
    """
    Preserves the imported niche identity while keeping AI enrichment values.
    This prevents broad model-generated labels from creating duplicate rows.
    """
    if not market.get("id"):
        return data

    for field in SEED_IDENTITY_FIELDS:
        value = market.get(field)
        if value not in (None, ""):
            data[field] = value

    data["geography"] = data.get("geography") or "US"
    data["source_status"] = "researched"
    return data

def process_batch(
    niche_markets: list = None,
    delay_seconds: int = 3,
    save_to_db: bool = True,
    verbose: bool = False,
    limit: int = None,
    resume: bool = False,
    only_failed: bool = False,
    use_database: bool = True,
    ai_retries: int = 2,
    stop_on_rate_limit: bool = True,
) -> dict:
    """
    Researches and saves a list of niche markets.

    Args:
        niche_markets : List of (industry, sub_industry, sub_sub_industry) tuples.
        delay_seconds : Seconds to wait between API calls.
        save_to_db    : Whether to save results to the database.
        verbose       : Whether to print full output per niche.
        limit         : Optional max number of niches to process.
        resume        : Process only niches without a successful latest run.
        only_failed   : Process only niches whose latest run item failed.
        use_database  : Read niches from the database when no explicit list is passed.
        ai_retries    : Number of AI output validation retries per niche.
        stop_on_rate_limit: Stop the batch when provider quota is exhausted.

    Returns:
        Dictionary with summary of results.
    """

    if niche_markets is not None:
        markets = niche_markets
        source = "explicit"
    elif use_database:
        markets = get_niche_markets_for_batch(
            limit=limit,
            only_failed=only_failed,
            resume=resume,
        )
        source = "database"
        if not markets:
            markets = NICHE_MARKETS_TO_RESEARCH[:limit] if limit else NICHE_MARKETS_TO_RESEARCH
            source = "fallback_seed_list"
    else:
        markets = NICHE_MARKETS_TO_RESEARCH[:limit] if limit else NICHE_MARKETS_TO_RESEARCH
        source = "seed_list"

    if limit and niche_markets is not None:
        markets = markets[:limit]

    total   = len(markets)
    run_id  = None

    if save_to_db:
        run_id = start_intelligence_run(
            total_items=total,
            run_type="batch",
            source=source,
            ai_model=_configured_ai_label(),
            metadata={
                "resume": resume,
                "only_failed": only_failed,
                "limit": limit,
                "ai_retries": ai_retries,
                "stop_on_rate_limit": stop_on_rate_limit,
            },
        )

    results = {
        "total"      : total,
        "success"    : 0,
        "failed"     : 0,
        "errors"     : [],
        "processed"  : [],
        "skipped"    : 0,
        "started_at" : datetime.now().isoformat(),
        "source"     : source,
        "run_id"     : run_id,
        "stopped_early": False,
        "stop_reason": None,
    }

    print(f"\nLoopa Intelligence - Batch Processor")
    print(f"Started    : {results['started_at']}")
    print(f"Total Jobs : {total}")
    print("-" * 60)

    for index, market in enumerate(markets, start=1):

        market_data      = _market_components(market)
        industry         = market_data.get("industry")
        sub_industry     = market_data.get("sub_industry")
        sub_sub_industry = market_data.get("sub_sub_industry")
        niche_market_id  = market_data.get("id")
        niche_name       = _market_display_name(market_data)

        print(f"\n[{index}/{total}] {niche_name}")

        try:
            if run_id and niche_market_id:
                record_run_item_start(run_id, niche_market_id)

            data = research_niche_market(
                industry         = industry,
                sub_industry     = sub_industry,
                sub_sub_industry = sub_sub_industry,
                niche_name       = market_data.get("niche_name"),
                market_context   = market_data,
                max_retries      = ai_retries,
            )
            data = _apply_seed_identity(data, market_data)

            if verbose:
                display_results(data)

            if save_to_db:
                niche_id = save_niche_market(data)
                if run_id:
                    record_run_item_success(run_id, niche_market_id or niche_id, data)
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
            if run_id and niche_market_id:
                record_run_item_failure(run_id, niche_market_id, str(e))
            results["errors"].append({
                "niche" : niche_name,
                "error" : str(e)
            })
            if stop_on_rate_limit and _is_rate_limit_error(e):
                results["stopped_early"] = True
                results["stop_reason"] = "rate_limit"
                skipped_markets = markets[index:]
                results["skipped"] += len(skipped_markets)
                if run_id:
                    for skipped_market in skipped_markets:
                        skipped_data = _market_components(skipped_market)
                        skipped_id = skipped_data.get("id")
                        if skipped_id:
                            record_run_item_skipped(
                                run_id,
                                skipped_id,
                                "Skipped because the AI provider rate limit stopped the batch.",
                            )
                print("  Stopping batch early because the AI provider rate limit was reached.")
                break

        if index < total:
            time.sleep(delay_seconds)

    results["completed_at"] = datetime.now().isoformat()

    if run_id:
        finish_intelligence_run(
            run_id,
            error_summary=json.dumps(results["errors"][:20]) if results["errors"] else None,
        )

    return results


def display_batch_summary(results: dict) -> None:
    """Prints a clean summary of the batch run."""

    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Total    : {results['total']}")
    print(f"Success  : {results['success']}")
    print(f"Failed   : {results['failed']}")
    print(f"Skipped  : {results.get('skipped', 0)}")
    print(f"Source   : {results.get('source')}")
    if results.get("run_id"):
        print(f"Run ID   : {results['run_id']}")
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

    if results.get("stopped_early"):
        print(f"\nStopped early: {results.get('stop_reason')}")

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
    import argparse

    parser = argparse.ArgumentParser(description="Run Loopa niche market batch processing.")
    parser.add_argument("--limit", type=int, help="Maximum number of niches to process")
    parser.add_argument("--delay", type=int, default=3, help="Seconds to wait between AI calls")
    parser.add_argument("--resume", action="store_true", help="Process niches without a successful latest run")
    parser.add_argument("--only-failed", action="store_true", help="Process only niches whose latest run failed")
    parser.add_argument("--seed-list", action="store_true", help="Use the built-in 20-market seed list instead of DB rows")
    parser.add_argument("--no-save", action="store_true", help="Run without saving to database")
    parser.add_argument("--verbose", action="store_true", help="Print each full niche report")
    parser.add_argument("--ai-retries", type=int, default=2, help="AI output validation retries per niche")
    parser.add_argument("--continue-on-rate-limit", action="store_true", help="Keep processing after provider rate-limit errors")
    args = parser.parse_args()

    results = process_batch(
        delay_seconds = args.delay,
        save_to_db    = not args.no_save,
        verbose       = args.verbose,
        limit         = args.limit,
        resume        = args.resume,
        only_failed   = args.only_failed,
        use_database  = not args.seed_list,
        ai_retries    = args.ai_retries,
        stop_on_rate_limit = not args.continue_on_rate_limit,
    )

    display_batch_summary(results)
    save_batch_report(results)

    print()
    get_database_stats()
