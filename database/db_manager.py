# database/db_manager.py
# Handles all database read and write operations.
# All other modules interact with the database through this file only.
# Direct database access outside this file is discouraged.

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_database_url
from database.schema import Base, NicheMarket, PainPoint, Vendor, VendorPainPointMap


def get_engine():
    """
    Returns the database engine.
    Uses SQLite for development and Azure SQL when ENVIRONMENT=production.
    """
    return create_engine(get_database_url())


def get_session():
    """Opens a new database session."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def save_niche_market(data: dict) -> int:
    """
    Saves or updates a niche market and its pain points.
    If the niche market already exists it is updated in place.
    Pain points are always replaced with the latest data.

    Args:
        data: Dictionary returned by the research agent.

    Returns:
        The database ID of the saved niche market.
    """
    session = get_session()

    try:
        # Check if record already exists
        existing = session.query(NicheMarket).filter_by(
            industry         = data.get("industry"),
            sub_industry     = data.get("sub_industry", ""),
            sub_sub_industry = data.get("sub_sub_industry", "")
        ).first()

        niche = existing if existing else NicheMarket()

        # Identification and segmentation
        niche.industry                  = data.get("industry")
        niche.sub_industry              = data.get("sub_industry", "")
        niche.sub_sub_industry          = data.get("sub_sub_industry", "")
        niche.niche_name                = data.get("niche_name")
        niche.parent_industry           = data.get("industry")
        niche.naics_code                = data.get("naics_code")
        niche.geography                 = data.get("geography", "US")
        niche.level                     = (
            3 if data.get("sub_sub_industry") else
            2 if data.get("sub_industry") else 1
        )

        # Structural and economic variables
        niche.avg_employee_count_min    = data.get("avg_employee_count_min")
        niche.avg_employee_count_max    = data.get("avg_employee_count_max")
        niche.smb_percentage            = data.get("smb_percentage")
        niche.sme_revenue_contribution  = data.get("sme_revenue_contribution")
        niche.industry_size             = data.get("industry_size")
        niche.cagr                      = data.get("cagr")

        # Cyber risk variables
        niche.cybersecurity_readiness   = data.get("cybersecurity_readiness")
        niche.attack_records            = data.get("attack_records")
        niche.regulatory_complexity     = data.get("regulatory_complexity")
        niche.digitalization_level      = data.get("digitalization_level")
        niche.estimated_annual_loss     = data.get("estimated_annual_loss")
        niche.common_cyber_risks        = data.get("common_cyber_risks")

        # Outbound feasibility variables
        niche.reachability              = data.get("reachability")
        niche.buyer_role_clarity        = data.get("buyer_role_clarity")
        niche.procurement_friction      = data.get("procurement_friction")
        niche.time_to_value             = data.get("time_to_value")
        niche.compliance_audit_drivers  = data.get("compliance_audit_drivers")
        niche.compliance_audit_notes    = data.get("compliance_audit_notes")
        niche.vendor_sprawl             = data.get("vendor_sprawl")
        niche.budget_proxy              = data.get("budget_proxy")
        niche.offer_fit                 = data.get("offer_fit")

        # Computed scores
        niche.demand_score              = data.get("demand_score")
        niche.outbound_score            = data.get("outbound_score")
        niche.priority_score            = data.get("priority_score")
        niche.priority_tier             = data.get("priority_tier")

        # ICP
        niche.icp_headcount_min         = data.get("icp_headcount_min")
        niche.icp_headcount_max         = data.get("icp_headcount_max")
        niche.icp_description           = data.get("icp_description")

        # Notes
        niche.assumptions_notes         = data.get("assumptions_notes")
        niche.last_updated              = datetime.now()

        if not existing:
            session.add(niche)

        session.commit()

        # Replace pain points with latest data
        session.query(PainPoint).filter_by(niche_market_id=niche.id).delete()

        for pp in data.get("top_pain_points", []):
            pain_point = PainPoint(
                niche_market_id     = niche.id,
                industry            = data.get("industry"),
                sub_industry        = data.get("sub_industry", ""),
                pain_point_name     = pp.get("pain_point"),
                pain_point_rank     = pp.get("rank"),
                description         = pp.get("description"),
                cyber_category      = pp.get("cyber_category"),
                cyber_subcategory   = pp.get("cyber_subcategory"),
                severity_score      = pp.get("severity_score"),
                growth_rate         = pp.get("growth_rate"),
                last_updated        = datetime.now()
            )
            session.add(pain_point)

        session.commit()
        return niche.id

    except Exception as e:
        session.rollback()
        raise e

    finally:
        session.close()


def get_top_niche_markets(limit: int = 20) -> list:
    """
    Returns the top N niche markets sorted by priority score.

    Args:
        limit: Number of results to return. Default is 20.

    Returns:
        List of niche market dictionaries.
    """
    session = get_session()

    try:
        niches = session.query(NicheMarket)\
            .order_by(NicheMarket.priority_score.desc())\
            .limit(limit)\
            .all()

        return [
            {
                "id"                    : n.id,
                "industry"              : n.industry,
                "sub_industry"          : n.sub_industry,
                "sub_sub_industry"      : n.sub_sub_industry,
                "niche_name"            : n.niche_name,
                "demand_score"          : n.demand_score,
                "outbound_score"        : n.outbound_score,
                "priority_score"        : n.priority_score,
                "priority_tier"         : n.priority_tier,
                "icp_headcount_min"     : n.icp_headcount_min,
                "icp_headcount_max"     : n.icp_headcount_max,
                "common_cyber_risks"    : n.common_cyber_risks,
                "last_updated"          : str(n.last_updated)
            }
            for n in niches
        ]

    finally:
        session.close()


def get_pain_points(niche_market_id: int) -> list:
    """
    Returns all pain points for a given niche market.

    Args:
        niche_market_id: The database ID of the niche market.

    Returns:
        List of pain point dictionaries sorted by rank.
    """
    session = get_session()

    try:
        pain_points = session.query(PainPoint)\
            .filter_by(niche_market_id=niche_market_id)\
            .order_by(PainPoint.pain_point_rank)\
            .all()

        return [
            {
                "rank"          : pp.pain_point_rank,
                "pain_point"    : pp.pain_point_name,
                "category"      : pp.cyber_category,
                "subcategory"   : pp.cyber_subcategory,
                "severity"      : pp.severity_score,
                "growth_rate"   : pp.growth_rate,
                "description"   : pp.description
            }
            for pp in pain_points
        ]

    finally:
        session.close()


def get_database_stats() -> dict:
    """
    Returns a summary of current database contents.
    Useful for monitoring and progress reporting.
    """
    session = get_session()

    try:
        stats = {
            "total_niche_markets" : session.query(NicheMarket).count(),
            "tier_1"              : session.query(NicheMarket).filter_by(priority_tier=1).count(),
            "tier_2"              : session.query(NicheMarket).filter_by(priority_tier=2).count(),
            "tier_3"              : session.query(NicheMarket).filter_by(priority_tier=3).count(),
            "total_pain_points"   : session.query(PainPoint).count(),
            "total_vendors"       : session.query(Vendor).count(),
        }

        print("\nLoopa Intelligence - Database Summary")
        print("-" * 40)
        print(f"Niche Markets   : {stats['total_niche_markets']}")
        print(f"  Tier 1        : {stats['tier_1']}")
        print(f"  Tier 2        : {stats['tier_2']}")
        print(f"  Tier 3        : {stats['tier_3']}")
        print(f"Pain Points     : {stats['total_pain_points']}")
        print(f"Vendors         : {stats['total_vendors']}")
        print("-" * 40)

        return stats

    finally:
        session.close()


if __name__ == "__main__":
    get_database_stats()
