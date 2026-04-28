# database/db_manager.py
# Handles all database read and write operations.
# All other modules interact with the database through this file only.
# Direct database access outside this file is discouraged.

import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_database_url
from database.schema import (
    Base,
    IntelligenceRun,
    NicheMarket,
    PainPoint,
    RunItem,
    Vendor,
    VendorPainPointMap,
)


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


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _niche_identity(data: dict) -> dict:
    return {
        "industry": _clean_text(data.get("industry")),
        "sub_industry": _clean_text(data.get("sub_industry")),
        "sub_sub_industry": _clean_text(data.get("sub_sub_industry")),
        "sub_sub_sub_industry": _clean_text(data.get("sub_sub_sub_industry")),
        "sub_sub_sub_sub_industry": _clean_text(data.get("sub_sub_sub_sub_industry")),
        "geography": _clean_text(data.get("geography") or "US") or "US",
    }


def _find_existing_niche(session, data: dict):
    geography = _clean_text(data.get("geography") or "US") or "US"
    niche_name = _clean_text(data.get("niche_name"))

    if niche_name:
        existing = session.query(NicheMarket).filter_by(
            niche_name=niche_name,
            geography=geography,
        ).first()
        if existing:
            return existing

    identity = _niche_identity(data)
    return session.query(NicheMarket).filter_by(**identity).first()


def _niche_to_dict(niche: NicheMarket) -> dict:
    return {
        "id": niche.id,
        "industry": niche.industry,
        "sub_industry": niche.sub_industry,
        "sub_sub_industry": niche.sub_sub_industry,
        "sub_sub_sub_industry": niche.sub_sub_sub_industry,
        "sub_sub_sub_sub_industry": niche.sub_sub_sub_sub_industry,
        "niche_name": niche.niche_name,
        "naics_code": niche.naics_code,
        "geography": niche.geography,
        "ownership_sector": niche.ownership_sector,
        "sector_code": niche.sector_code,
        "sub_industry_code": niche.sub_industry_code,
        "sub_sub_industry_code": niche.sub_sub_industry_code,
        "sub_sub_sub_industry_code": niche.sub_sub_sub_industry_code,
        "sub_sub_sub_sub_industry_code": niche.sub_sub_sub_sub_industry_code,
        "primary_buyer_role": niche.primary_buyer_role,
        "likely_compliance_regimes": niche.likely_compliance_regimes,
        "conditional_compliance_regimes": niche.conditional_compliance_regimes,
        "compliance_tag_confidence": niche.compliance_tag_confidence,
        "compliance_tag_basis": niche.compliance_tag_basis,
        "recommended_cyber_themes": niche.recommended_cyber_themes,
        "regulatory_or_compliance_drivers": niche.regulatory_or_compliance_drivers,
        "priority_score": niche.priority_score,
        "priority_tier": niche.priority_tier,
        "last_updated": str(niche.last_updated) if niche.last_updated else None,
    }


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
        identity = _niche_identity(data)
        existing = _find_existing_niche(session, data)

        niche = existing if existing else NicheMarket()

        # Identification and segmentation
        niche.industry                  = identity["industry"]
        niche.sub_industry              = identity["sub_industry"]
        niche.sub_sub_industry          = identity["sub_sub_industry"]
        niche.sub_sub_sub_industry      = identity["sub_sub_sub_industry"]
        niche.sub_sub_sub_sub_industry  = identity["sub_sub_sub_sub_industry"]
        niche.niche_name                = data.get("niche_name")
        niche.parent_industry           = data.get("industry")
        niche.naics_code                = data.get("naics_code")
        niche.geography                 = identity["geography"]
        niche.ownership_sector          = data.get("ownership_sector")
        niche.sector_code               = data.get("sector_code")
        niche.sub_industry_code         = data.get("sub_industry_code")
        niche.sub_sub_industry_code     = data.get("sub_sub_industry_code")
        niche.sub_sub_sub_industry_code = data.get("sub_sub_sub_industry_code")
        niche.sub_sub_sub_sub_industry_code = data.get("sub_sub_sub_sub_industry_code")
        niche.primary_buyer_role        = data.get("primary_buyer_role")
        niche.likely_compliance_regimes = data.get("likely_compliance_regimes")
        niche.conditional_compliance_regimes = data.get("conditional_compliance_regimes")
        niche.compliance_tag_confidence = data.get("compliance_tag_confidence")
        niche.compliance_tag_basis      = data.get("compliance_tag_basis")
        niche.recommended_cyber_themes  = data.get("recommended_cyber_themes")
        niche.regulatory_or_compliance_drivers = data.get("regulatory_or_compliance_drivers")
        niche.level                     = (
            5 if data.get("sub_sub_sub_sub_industry") else
            4 if data.get("sub_sub_sub_industry") else
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
        niche.source_notes              = data.get("source_notes") or data.get("assumptions_notes")
        niche.source_status             = data.get("source_status") or "researched"
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


def upsert_niche_market_seed(data: dict) -> int:
    """
    Creates or updates a niche market seed row before AI enrichment.
    Used by the 700+ niche market importer.
    """
    session = get_session()

    try:
        identity = _niche_identity(data)
        if not identity["industry"]:
            raise ValueError("industry is required")

        niche = _find_existing_niche(session, data)
        if not niche:
            niche = NicheMarket(**identity)
            session.add(niche)
        else:
            niche.industry = identity["industry"]
            niche.sub_industry = identity["sub_industry"]
            niche.sub_sub_industry = identity["sub_sub_industry"]
            niche.sub_sub_sub_industry = identity["sub_sub_sub_industry"]
            niche.sub_sub_sub_sub_industry = identity["sub_sub_sub_sub_industry"]
            niche.geography = identity["geography"]

        niche.niche_name = data.get("niche_name") or " > ".join(
            p for p in [
                identity["industry"],
                identity["sub_industry"],
                identity["sub_sub_industry"],
                identity["sub_sub_sub_industry"],
                identity["sub_sub_sub_sub_industry"],
            ] if p
        )
        niche.parent_industry = data.get("parent_industry") or identity["industry"]
        niche.naics_code = data.get("naics_code")
        niche.ownership_sector = data.get("ownership_sector")
        niche.sector_code = data.get("sector_code")
        niche.sub_industry_code = data.get("sub_industry_code")
        niche.sub_sub_industry_code = data.get("sub_sub_industry_code")
        niche.sub_sub_sub_industry_code = data.get("sub_sub_sub_industry_code")
        niche.sub_sub_sub_sub_industry_code = data.get("sub_sub_sub_sub_industry_code")
        niche.primary_buyer_role = data.get("primary_buyer_role")
        niche.likely_compliance_regimes = data.get("likely_compliance_regimes")
        niche.conditional_compliance_regimes = data.get("conditional_compliance_regimes")
        niche.compliance_tag_confidence = data.get("compliance_tag_confidence")
        niche.compliance_tag_basis = data.get("compliance_tag_basis")
        niche.recommended_cyber_themes = data.get("recommended_cyber_themes")
        niche.regulatory_or_compliance_drivers = data.get("regulatory_or_compliance_drivers")
        niche.source_notes = data.get("source_notes")
        niche.source_status = data.get("source_status") or "seed"
        niche.level = (
            5 if identity["sub_sub_sub_sub_industry"] else
            4 if identity["sub_sub_sub_industry"] else
            3 if identity["sub_sub_industry"] else
            2 if identity["sub_industry"] else 1
        )
        niche.last_updated = datetime.now()

        session.commit()
        return niche.id

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def get_niche_markets_for_batch(limit: int = None, only_failed: bool = False, resume: bool = False) -> list:
    """
    Returns niche markets to process from the database.

    only_failed: process niches whose latest run item failed.
    resume: process niches that have not had a successful run yet.
    """
    session = get_session()

    try:
        query = session.query(NicheMarket)

        if only_failed or resume:
            latest_status = (
                session.query(RunItem.status)
                .join(IntelligenceRun, IntelligenceRun.id == RunItem.run_id)
                .filter(RunItem.niche_market_id == NicheMarket.id)
                .order_by(RunItem.completed_at.desc(), RunItem.id.desc())
                .limit(1)
                .correlate(NicheMarket)
                .scalar_subquery()
            )
            if only_failed:
                query = query.filter(latest_status == "failed")
            else:
                query = query.filter((latest_status.is_(None)) | (latest_status != "success"))

        query = query.order_by(
            NicheMarket.priority_score.desc().nullslast(),
            NicheMarket.id.asc(),
        )

        if limit:
            query = query.limit(limit)

        return [_niche_to_dict(niche) for niche in query.all()]

    finally:
        session.close()


def start_intelligence_run(
    total_items: int,
    run_type: str = "batch",
    source: str = None,
    ai_model: str = None,
    metadata: dict = None,
) -> int:
    """Creates a new intelligence run record."""
    session = get_session()

    try:
        run = IntelligenceRun(
            run_type=run_type,
            status="running",
            total_items=total_items,
            source=source,
            ai_model=ai_model,
            metadata_json=json.dumps(metadata or {}),
            started_at=datetime.now(),
        )
        session.add(run)
        session.commit()
        return run.id

    finally:
        session.close()


def record_run_item_start(run_id: int, niche_market_id: int) -> int:
    """Creates or updates a run item when processing starts."""
    session = get_session()

    try:
        item = session.query(RunItem).filter_by(
            run_id=run_id,
            niche_market_id=niche_market_id,
        ).first()
        if not item:
            item = RunItem(run_id=run_id, niche_market_id=niche_market_id)
            session.add(item)

        item.status = "running"
        item.attempts = (item.attempts or 0) + 1
        item.error_message = None
        item.started_at = datetime.now()
        item.last_updated = datetime.now()
        session.commit()
        return item.id

    finally:
        session.close()


def record_run_item_success(run_id: int, niche_market_id: int, data: dict) -> None:
    """Marks one run item as successful."""
    session = get_session()

    try:
        item = session.query(RunItem).filter_by(
            run_id=run_id,
            niche_market_id=niche_market_id,
        ).first()
        if not item:
            item = RunItem(run_id=run_id, niche_market_id=niche_market_id)
            session.add(item)

        item.status = "success"
        item.error_message = None
        item.demand_score = data.get("demand_score")
        item.outbound_score = data.get("outbound_score")
        item.priority_score = data.get("priority_score")
        item.priority_tier = data.get("priority_tier")
        item.completed_at = datetime.now()
        item.last_updated = datetime.now()
        session.commit()

    finally:
        session.close()


def record_run_item_failure(run_id: int, niche_market_id: int, error_message: str) -> None:
    """Marks one run item as failed."""
    session = get_session()

    try:
        item = session.query(RunItem).filter_by(
            run_id=run_id,
            niche_market_id=niche_market_id,
        ).first()
        if not item:
            item = RunItem(run_id=run_id, niche_market_id=niche_market_id)
            session.add(item)

        item.status = "failed"
        item.error_message = str(error_message)
        item.completed_at = datetime.now()
        item.last_updated = datetime.now()
        session.commit()

    finally:
        session.close()


def finish_intelligence_run(run_id: int, status: str = None, error_summary: str = None) -> None:
    """Finalizes an intelligence run using its item counts."""
    session = get_session()

    try:
        run = session.query(IntelligenceRun).filter_by(id=run_id).first()
        if not run:
            return

        success_count = session.query(RunItem).filter_by(run_id=run_id, status="success").count()
        failure_count = session.query(RunItem).filter_by(run_id=run_id, status="failed").count()
        skipped_count = session.query(RunItem).filter_by(run_id=run_id, status="skipped").count()

        run.success_count = success_count
        run.failure_count = failure_count
        run.skipped_count = skipped_count
        run.completed_at = datetime.now()
        run.error_summary = error_summary
        run.status = status or ("completed_with_errors" if failure_count else "completed")
        session.commit()

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
            "total_runs"          : session.query(IntelligenceRun).count(),
            "latest_run_status"   : None,
        }

        latest_run = session.query(IntelligenceRun).order_by(IntelligenceRun.id.desc()).first()
        if latest_run:
            stats["latest_run_status"] = latest_run.status

        print("\nLoopa Intelligence - Database Summary")
        print("-" * 40)
        print(f"Niche Markets   : {stats['total_niche_markets']}")
        print(f"  Tier 1        : {stats['tier_1']}")
        print(f"  Tier 2        : {stats['tier_2']}")
        print(f"  Tier 3        : {stats['tier_3']}")
        print(f"Pain Points     : {stats['total_pain_points']}")
        print(f"Vendors         : {stats['total_vendors']}")
        print(f"Runs            : {stats['total_runs']}")
        if stats["latest_run_status"]:
            print(f"Latest Run      : {stats['latest_run_status']}")
        print("-" * 40)

        return stats

    finally:
        session.close()


if __name__ == "__main__":
    get_database_stats()
