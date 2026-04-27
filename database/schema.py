# database/schema.py
# Defines the database schema for the Loopa Intelligence Platform.
# All tables are defined here using SQLAlchemy ORM.
# To add a new field, add it here and re-run create_tables().

from sqlalchemy import (
    Column, String, Float, Integer,
    DateTime, Text, Boolean, create_engine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

Base = declarative_base()


class NicheMarket(Base):
    """
    Stores all niche markets across industry hierarchy levels.
    Updated weekly by the research agent.
    Scoring follows Hamid's two-layer model:
    Demand Score + Outbound Feasibility Score = Final Priority Score
    """
    __tablename__ = "niche_markets"

    id                          = Column(Integer, primary_key=True, autoincrement=True)

    # Industry hierarchy (up to 5 levels)
    industry                    = Column(String(255), nullable=False)
    sub_industry                = Column(String(255), default="")
    sub_sub_industry            = Column(String(255), default="")
    level                       = Column(Integer)

    # Identification and segmentation
    niche_name                  = Column(String(255))
    parent_industry             = Column(String(255))
    naics_code                  = Column(String(50))
    geography                   = Column(String(100))

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

    # Timestamps
    last_updated                = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at                  = Column(DateTime, default=func.now())


class PainPoint(Base):
    """
    Stores cybersecurity pain points per niche market.
    Ranked by severity. Updated weekly.
    """
    __tablename__ = "pain_points"

    id                  = Column(Integer, primary_key=True, autoincrement=True)

    # Reference to parent niche market
    niche_market_id     = Column(Integer, nullable=False)
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


class Vendor(Base):
    """
    Stores vendor information from the Loopa marketplace.
    Maps vendors to cybersecurity categories and pain points.
    """
    __tablename__ = "vendors"

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


class VendorPainPointMap(Base):
    """
    Maps vendors to the pain points they solve.
    This is the bridge between Phase 2 and Phase 3.
    """
    __tablename__ = "vendor_pain_point_map"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id       = Column(Integer, nullable=False)
    pain_point_id   = Column(Integer, nullable=False)
    match_score     = Column(Float)
    notes           = Column(Text)
    last_updated    = Column(DateTime, default=func.now(), onupdate=func.now())


def create_tables():
    """Creates all database tables if they do not already exist."""
    engine = create_engine("sqlite:///loopa_intelligence.db")
    Base.metadata.create_all(engine)
    print("Database tables created successfully.")
    return engine


if __name__ == "__main__":
    create_tables()