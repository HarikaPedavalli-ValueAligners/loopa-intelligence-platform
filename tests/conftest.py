# tests/conftest.py
# Shared fixtures for the SaaS wrapper tests.
#
# Everything runs against TEMPORARY SQLite databases seeded in-process. No real
# secrets, no real .env, and the production loopa_intelligence.db is never read
# or written. Two databases are involved:
#   - a temp "catalog" DB holding the existing intelligence schema + seed rows
#   - a temp "saas" control-plane DB holding tenants/keys/grants

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Make the repo root importable (tests/ -> repo root).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.schema import (  # noqa: E402
    Base, NicheMarket, PainPoint, Vendor, VendorPainPointMap,
)
from saas.tenancy import make_saas_engine, make_session_factory  # noqa: E402


# ---------------------------------------------------------------------------
# Catalog (existing intelligence) fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def catalog_engine(tmp_path):
    """A temp SQLite engine holding the existing intelligence schema."""
    db_path = tmp_path / "catalog.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def catalog_session_factory(catalog_engine):
    return sessionmaker(bind=catalog_engine, future=True)


@pytest.fixture()
def seeded_catalog(catalog_engine, catalog_session_factory):
    """
    Seeds two niche markets, each with a pain point and a vendor match, so
    isolation tests can prove one tenant cannot see the other tenant's niche.

    Returns a dict with the ids of the seeded rows.
    """
    Session = catalog_session_factory
    s = Session()
    try:
        n1 = NicheMarket(industry="Healthcare", sub_industry="Hospitals",
                         niche_name="Hospital Supply Chain", level=2,
                         demand_score=80, outbound_score=70, priority_score=56,
                         priority_tier=2)
        n2 = NicheMarket(industry="Finance", sub_industry="Banking",
                         niche_name="Retail Banking", level=2,
                         demand_score=90, outbound_score=85, priority_score=76,
                         priority_tier=1)
        s.add_all([n1, n2])
        s.commit()

        pp1 = PainPoint(niche_market_id=n1.id, pain_point_name="Ransomware",
                        pain_point_rank=1, cyber_category="Malware",
                        severity_score=9.0, growth_rate=12.0)
        pp2 = PainPoint(niche_market_id=n2.id, pain_point_name="Account Takeover",
                        pain_point_rank=1, cyber_category="Identity",
                        severity_score=8.0, growth_rate=15.0)
        s.add_all([pp1, pp2])
        s.commit()

        v1 = Vendor(vendor_name="ShieldCo", cyber_category="Malware",
                    target_market="Healthcare", customer_rating=4.5)
        v2 = Vendor(vendor_name="IdentEx", cyber_category="Identity",
                    target_market="Finance", customer_rating=4.2)
        s.add_all([v1, v2])
        s.commit()

        m1 = VendorPainPointMap(vendor_id=v1.id, pain_point_id=pp1.id,
                                match_score=0.9, notes="strong category match")
        m2 = VendorPainPointMap(vendor_id=v2.id, pain_point_id=pp2.id,
                                match_score=0.8, notes="identity coverage")
        s.add_all([m1, m2])
        s.commit()

        return {
            "niche_a": n1.id, "niche_b": n2.id,
            "pain_a": pp1.id, "pain_b": pp2.id,
            "vendor_a": v1.id, "vendor_b": v2.id,
        }
    finally:
        s.close()


# ---------------------------------------------------------------------------
# SaaS control-plane fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def saas_session_factory(tmp_path):
    """A temp SaaS control-plane DB session factory."""
    db_path = tmp_path / "saas.db"
    engine = make_saas_engine(str(db_path))
    return make_session_factory(engine)
