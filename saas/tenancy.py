# saas/tenancy.py
# Multi-tenant identity layer for the Loopa SaaS wrapper.
#
# Design goals:
#   1. Do NOT modify the existing intelligence schema or its data. The legacy
#      tables (niche_markets, pain_points, vendors, vendor_pain_point_map) stay
#      exactly as they are.
#   2. Add tenant identity + a per-tenant data-isolation mechanism on top, in a
#      SEPARATE set of saas_* tables, stored in their own SQLite file by default
#      so legacy runs are untouched.
#
# Isolation model
# ---------------
# The existing data is a shared catalog of market intelligence. Each tenant is
# granted access to a subset of niche markets via the `saas_tenant_niche` table
# (an allow-list of niche_market_id values per tenant). Every tenant-facing read
# is scoped through this allow-list (see repository.py), so tenant A can never
# read niche rows that were not provisioned to tenant A.
#
# A tenant may be marked `full_catalog=True`, meaning "this tenant sees the whole
# shared catalog" (still scoped by plan quotas) without enumerating every id.
# New tenants default to full_catalog=False with an empty allow-list -> they see
# nothing until explicitly provisioned. That is the safe default for isolation.

import os
import secrets
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

SaaSBase = declarative_base()


def generate_tenant_id() -> str:
    """Returns an opaque, URL-safe tenant identifier."""
    return "tnt_" + secrets.token_hex(8)


class Tenant(SaaSBase):
    """A paying (or free) customer of the Loopa SaaS."""

    __tablename__ = "saas_tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False, default="free")

    # If True, the tenant can read the entire shared catalog (still plan-capped).
    # If False, access is limited to the explicit allow-list below.
    full_catalog = Column(Boolean, nullable=False, default=False)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=func.now())
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())

    api_keys = relationship(
        "ApiKey", back_populates="tenant", cascade="all, delete-orphan"
    )
    niche_grants = relationship(
        "TenantNicheAccess", back_populates="tenant", cascade="all, delete-orphan"
    )


class ApiKey(SaaSBase):
    """
    An API key belonging to a tenant.

    Only a salted hash of the key is stored, never the plaintext. The plaintext
    is returned exactly once at mint time and cannot be recovered afterward.
    """

    __tablename__ = "saas_api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_pk = Column(Integer, ForeignKey("saas_tenants.id"), nullable=False, index=True)

    # Public, non-secret prefix used to locate the key row before hashing.
    key_prefix = Column(String(32), nullable=False, unique=True, index=True)
    # Hex-encoded HMAC-SHA256 of the secret part. Never the plaintext.
    key_hash = Column(String(128), nullable=False)

    label = Column(String(255), default="")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=func.now())
    last_used_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="api_keys")


class TenantNicheAccess(SaaSBase):
    """
    Allow-list mapping a tenant to a single niche_market_id from the shared
    catalog. The presence of a row is what grants read access; absence denies it.
    """

    __tablename__ = "saas_tenant_niche"
    __table_args__ = (
        UniqueConstraint("tenant_pk", "niche_market_id", name="uq_tenant_niche"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_pk = Column(Integer, ForeignKey("saas_tenants.id"), nullable=False, index=True)
    niche_market_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="niche_grants")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------

def default_saas_db_path() -> str:
    """
    Path to the SaaS control-plane SQLite DB. Kept SEPARATE from the legacy
    loopa_intelligence.db so the existing platform is never touched. Overridable
    via LOOPA_SAAS_DB_PATH (used by tests to point at a temp file).
    """
    override = os.environ.get("LOOPA_SAAS_DB_PATH")
    if override:
        return override
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "loopa_saas.db")


def make_saas_engine(db_path: str = None):
    """Creates a SQLAlchemy engine for the SaaS control-plane DB."""
    path = db_path or default_saas_db_path()
    return create_engine(f"sqlite:///{path}", future=True)


def init_saas_db(engine) -> None:
    """Creates the saas_* tables if they do not exist."""
    SaaSBase.metadata.create_all(engine)


def make_session_factory(engine):
    """
    Returns a sessionmaker bound to the given engine.

    expire_on_commit=False so that committed Tenant/ApiKey instances keep their
    loaded attribute values after the session is closed. The SaaS layer routinely
    creates an object, commits, closes the session, and then reads simple scalar
    attributes (tenant_id, plan, id) off the detached instance.
    """
    init_saas_db(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)
