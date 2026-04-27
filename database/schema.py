# database/schema.py
# Defines the database schema for the Loopa Intelligence Platform.
# All tables are defined here using SQLAlchemy ORM.
# To add a new field, add it here and re-run create_tables().

from sqlalchemy import (
    Column, String, Float, Integer,
    DateTime, Text, Boolean, create_engine,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_database_url

Base = declarative_base()


class NicheMarket(Base):
    """
    Stores all niche markets across industry hierarchy levels.
    Updated weekly by the research agent.
    Scoring follows Hamid's two-layer model:
    Demand Score + Outbound Feasibility Score = Final Priority Score
    """
    __tablename__ = "niche_markets"
    __table_args__ = (
        UniqueConstraint(
            "niche_name",
            "geography",
            name="uq_niche_name_geography",
        ),
        Index("ix_niche_priority_score", "priority_score"),
        Index("ix_niche_priority_tier", "priority_tier"),
        Index("ix_niche_naics_code", "naics_code"),
    )

    id                          = Column(Integer, primary_key=True, autoincrement=True)

    # Industry hierarchy (up to 5 levels)
    industry                    = Column(String(255), nullable=False)
    sub_industry                = Column(String(255), default="")
    sub_sub_industry            = Column(String(255), default="")
    sub_sub_sub_industry        = Column(String(255), default="")
    sub_sub_sub_sub_industry    = Column(String(255), default="")
    level                       = Column(Integer)

    # Identification and segmentation
    niche_name                  = Column(String(255))
    parent_industry             = Column(String(255))
    naics_code                  = Column(String(50))
    geography                   = Column(String(100))
    ownership_sector            = Column(String(100))
    sector_code                 = Column(String(50))
    sub_industry_code           = Column(String(50))
    sub_sub_industry_code       = Column(String(50))
    sub_sub_sub_industry_code   = Column(String(50))
    sub_sub_sub_sub_industry_code = Column(String(50))
    primary_buyer_role          = Column(String(255))
    likely_compliance_regimes   = Column(Text)
    conditional_compliance_regimes = Column(Text)
    compliance_tag_confidence   = Column(String(50))
    compliance_tag_basis        = Column(Text)
    recommended_cyber_themes    = Column(Text)
    regulatory_or_compliance_drivers = Column(Text)

    # Structural and economic variables
    avg_employee_count_min      = Column(Integer)
    avg_employee_count_max      = Column(Integer)
    smb_percentage              = Column(Float)                 # % of firms that are SMBs
    sme_revenue_contribution    = Column(Float)                 # % of industry revenue from SMBs
    industry_size               = Column(Float)                 # USD billions
    cagr                        = Column(Float)                 # annual growth %

    # Cyber risk variables (1-10 scale)
    cybersecurity_readiness     = Column(Float)                 # 1-10 (lower = more vulnerable)
    attack_records              = Column(Float)                 # 1-10
    regulatory_complexity       = Column(Float)                 # 1-10
    digitalization_level        = Column(Float)                 # 1-10
    estimated_annual_loss       = Column(Float)                 # USD billions
    common_cyber_risks          = Column(Text)

    # Outbound feasibility variables (1-10 scale)
    reachability                = Column(Float)                 # 1-10
    buyer_role_clarity          = Column(Float)                 # 1-10
    procurement_friction        = Column(Float)                 # 1-10 (negative weight)
    time_to_value               = Column(Float)                 # 1-10
    compliance_audit_drivers    = Column(String(10))            # Yes/No
    compliance_audit_notes      = Column(Text)
    vendor_sprawl               = Column(Float)                 # 1-10
    budget_proxy                = Column(Float)                 # 1-10
    offer_fit                   = Column(Float)                 # 1-10

    # Computed scores (Hamid's two-layer model)
    demand_score                = Column(Float)                 # 0-100
    outbound_score              = Column(Float)                 # 0-100
    priority_score              = Column(Float)                 # 0-100 final
    priority_tier               = Column(Integer)               # 1, 2, or 3

    # Ideal Customer Profile
    icp_headcount_min           = Column(Integer)
    icp_headcount_max           = Column(Integer)
    icp_description             = Column(Text)

    # Assumptions and notes
    assumptions_notes           = Column(Text)
    source_notes                = Column(Text)
    source_status               = Column(String(50), default="seed")

    # Timestamps
    last_updated                = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at                  = Column(DateTime, default=func.now())

    pain_points                 = relationship(
        "PainPoint",
        back_populates="niche_market",
        cascade="all, delete-orphan",
    )
    run_items                   = relationship("RunItem", back_populates="niche_market")


class PainPoint(Base):
    """
    Stores cybersecurity pain points per niche market.
    Ranked by severity. Updated weekly.
    """
    __tablename__ = "pain_points"
    __table_args__ = (
        UniqueConstraint("niche_market_id", "pain_point_rank", name="uq_pain_point_rank_per_niche"),
        Index("ix_pain_point_niche_market_id", "niche_market_id"),
        Index("ix_pain_point_category", "cyber_category", "cyber_subcategory"),
    )

    id                  = Column(Integer, primary_key=True, autoincrement=True)

    # Reference to parent niche market
    niche_market_id     = Column(Integer, ForeignKey("niche_markets.id", ondelete="CASCADE"), nullable=False)
    industry            = Column(String(255))
    sub_industry        = Column(String(255))

    # Pain point details
    pain_point_name     = Column(String(255))
    pain_point_rank     = Column(Integer)
    description         = Column(Text)

    # Cybersecurity taxonomy mapping
    cyber_category      = Column(String(255))
    cyber_subcategory   = Column(String(255))

    # Scoring
    severity_score      = Column(Float)
    growth_rate         = Column(Float)

    # Timestamps
    last_updated        = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at          = Column(DateTime, default=func.now())

    niche_market        = relationship("NicheMarket", back_populates="pain_points")
    vendor_matches      = relationship(
        "VendorPainPointMap",
        back_populates="pain_point",
        cascade="all, delete-orphan",
    )


class Vendor(Base):
    """
    Stores vendor information from the Loopa marketplace.
    Maps vendors to cybersecurity categories and pain points.
    """
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("vendor_name", name="uq_vendor_name"),
        Index("ix_vendor_category", "cyber_category", "cyber_subcategory"),
    )

    id                          = Column(Integer, primary_key=True, autoincrement=True)

    # Company information
    vendor_name                 = Column(String(255), nullable=False)
    company_website             = Column(String(255))
    company_size                = Column(String(100))
    year_founded                = Column(Integer)
    headquarters                = Column(String(255))
    status                      = Column(String(100))

    # Cybersecurity classification
    cyber_category              = Column(String(255))
    cyber_subcategory           = Column(String(255))
    threat_types_addressed      = Column(Text)

    # Product details
    product_name                = Column(String(255))
    product_description         = Column(Text)
    target_market               = Column(String(255))
    pricing_model               = Column(String(100))
    supported_platforms         = Column(String(255))
    deployment_models           = Column(String(255))

    # Technical specifications
    integration_capabilities    = Column(Text)
    compliance_certifications   = Column(Text)
    api_available               = Column(Boolean)
    free_trial                  = Column(Boolean)

    # Performance metrics
    customer_rating             = Column(Float)
    active_users                = Column(String(100))
    customer_retention_rate     = Column(String(100))

    # Clustering output
    cluster_id                  = Column(Integer)

    # Timestamps
    last_updated                = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at                  = Column(DateTime, default=func.now())

    pain_point_matches          = relationship(
        "VendorPainPointMap",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )


class VendorPainPointMap(Base):
    """
    Maps vendors to the pain points they solve.
    This is the bridge between Phase 2 and Phase 3.
    """
    __tablename__ = "vendor_pain_point_map"
    __table_args__ = (
        UniqueConstraint("vendor_id", "pain_point_id", name="uq_vendor_pain_point_match"),
        Index("ix_vendor_match_pain_point", "pain_point_id", "match_score"),
        Index("ix_vendor_match_vendor", "vendor_id"),
    )

    id              = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id       = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    pain_point_id   = Column(Integer, ForeignKey("pain_points.id", ondelete="CASCADE"), nullable=False)
    match_score     = Column(Float)
    confidence_label = Column(String(50))
    match_type      = Column(String(50))
    matched_terms   = Column(Text)
    is_fallback     = Column(Boolean, default=False)
    notes           = Column(Text)
    last_updated    = Column(DateTime, default=func.now(), onupdate=func.now())

    vendor          = relationship("Vendor", back_populates="pain_point_matches")
    pain_point      = relationship("PainPoint", back_populates="vendor_matches")


class IntelligenceRun(Base):
    """
    Tracks each batch run so weekly intelligence can be audited, resumed,
    and reviewed without guessing what happened.
    """
    __tablename__ = "intelligence_runs"
    __table_args__ = (
        Index("ix_intelligence_run_status", "status"),
        Index("ix_intelligence_run_started_at", "started_at"),
    )

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    run_type            = Column(String(50), default="batch")
    status              = Column(String(50), default="running")
    total_items         = Column(Integer, default=0)
    success_count       = Column(Integer, default=0)
    failure_count       = Column(Integer, default=0)
    skipped_count       = Column(Integer, default=0)
    ai_model            = Column(String(255))
    source              = Column(String(255))
    started_at          = Column(DateTime, default=func.now())
    completed_at        = Column(DateTime)
    error_summary       = Column(Text)
    metadata_json       = Column(Text)
    created_at          = Column(DateTime, default=func.now())

    items               = relationship(
        "RunItem",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class RunItem(Base):
    """Tracks the status of one niche market inside one intelligence run."""
    __tablename__ = "run_items"
    __table_args__ = (
        UniqueConstraint("run_id", "niche_market_id", name="uq_run_item_niche"),
        Index("ix_run_item_status", "status"),
        Index("ix_run_item_niche_market_id", "niche_market_id"),
    )

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    run_id              = Column(Integer, ForeignKey("intelligence_runs.id", ondelete="CASCADE"), nullable=False)
    niche_market_id     = Column(Integer, ForeignKey("niche_markets.id", ondelete="CASCADE"), nullable=False)
    status              = Column(String(50), default="pending")
    attempts            = Column(Integer, default=0)
    error_message       = Column(Text)
    demand_score        = Column(Float)
    outbound_score      = Column(Float)
    priority_score      = Column(Float)
    priority_tier       = Column(Integer)
    started_at          = Column(DateTime)
    completed_at        = Column(DateTime)
    created_at          = Column(DateTime, default=func.now())
    last_updated        = Column(DateTime, default=func.now(), onupdate=func.now())

    run                 = relationship("IntelligenceRun", back_populates="items")
    niche_market        = relationship("NicheMarket", back_populates="run_items")


def create_tables():
    """Creates all database tables if they do not already exist."""
    engine = create_engine(get_database_url())
    Base.metadata.create_all(engine)
    print("Database tables created successfully.")
    return engine


if __name__ == "__main__":
    create_tables()
