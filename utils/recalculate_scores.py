# utils/recalculate_scores.py
# Recomputes stored niche market scores after scoring model changes.

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.niche_market_agent import (
    calculate_demand_score,
    calculate_outbound_score,
    calculate_priority_score,
    get_priority_tier,
)
from database.db_manager import get_session
from database.schema import NicheMarket


SCORING_FIELDS = [
    "attack_records",
    "digitalization_level",
    "sme_revenue_contribution",
    "cagr",
    "cybersecurity_readiness",
    "industry_size",
    "smb_percentage",
    "estimated_annual_loss",
    "reachability",
    "buyer_role_clarity",
    "procurement_friction",
    "time_to_value",
    "vendor_sprawl",
    "offer_fit",
]


def recalculate_scores() -> dict:
    """Recomputes demand, outbound, priority, and tier for all niches."""
    session = get_session()
    updated = 0
    tiers = {1: 0, 2: 0, 3: 0}

    try:
        niches = session.query(NicheMarket).all()

        for niche in niches:
            data = {field: getattr(niche, field) for field in SCORING_FIELDS}
            demand = calculate_demand_score(data)
            outbound = calculate_outbound_score(data)
            priority = calculate_priority_score(demand, outbound)
            tier = get_priority_tier(priority)

            niche.demand_score = demand
            niche.outbound_score = outbound
            niche.priority_score = priority
            niche.priority_tier = tier

            tiers[tier] += 1
            updated += 1

        session.commit()
        return {"updated": updated, "tiers": tiers}

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


if __name__ == "__main__":
    result = recalculate_scores()
    print("Recalculated niche market scores.")
    print(f"Updated: {result['updated']}")
    print(f"Tier 1: {result['tiers'][1]}")
    print(f"Tier 2: {result['tiers'][2]}")
    print(f"Tier 3: {result['tiers'][3]}")
