# agents/vendor_scope_agent.py
# VendorScope Phase 0: seed and score vendor intelligence records from the
# existing Loopa vendor catalog. This deliberately uses only already-owned
# data; external enrichment connectors are a later phase.

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    Vendor,
    VendorAlert,
    VendorIntelligenceProfile,
    VendorIntelligenceVariable,
    VendorPainPointMap,
    VendorScoreHistory,
)
from agents.data_quality_agent import run_data_quality


TOTAL_VENDOR_VARIABLES = 80


@dataclass(frozen=True)
class VendorVariableDef:
    name: str
    category: str
    tier: str
    refresh: str


VENDOR_VARIABLE_CATALOG = [
    VendorVariableDef("legal_entity_verified", "Identity & Legitimacy", "A", "Quarterly"),
    VendorVariableDef("domain_age_years", "Identity & Legitimacy", "A", "Monthly"),
    VendorVariableDef("business_email_only", "Identity & Legitimacy", "A", "On change"),
    VendorVariableDef("accountable_business_contact", "Identity & Legitimacy", "A", "Quarterly"),
    VendorVariableDef("years_in_market", "Identity & Legitimacy", "B", "Quarterly"),
    VendorVariableDef("headquarters_country", "Identity & Legitimacy", "A", "Quarterly"),
    VendorVariableDef("ownership_disclosure", "Identity & Legitimacy", "A", "Annual"),
    VendorVariableDef("years_product_in_market", "Tenure, Stability & Reputation", "B", "Quarterly"),
    VendorVariableDef("funding_stage", "Tenure, Stability & Reputation", "B", "Quarterly"),
    VendorVariableDef("last_funding_or_revenue_signal_months", "Tenure, Stability & Reputation", "B", "Monthly"),
    VendorVariableDef("employee_count", "Tenure, Stability & Reputation", "B", "Monthly"),
    VendorVariableDef("employee_count_trend_12mo", "Tenure, Stability & Reputation", "B", "Monthly"),
    VendorVariableDef("media_reputation_score", "Tenure, Stability & Reputation", "B", "Weekly"),
    VendorVariableDef("breach_or_incident_history", "Tenure, Stability & Reputation", "A", "Weekly"),
    VendorVariableDef("cve_disclosures_24mo", "Tenure, Stability & Reputation", "B", "Weekly"),
    VendorVariableDef("litigation_or_regulatory_actions", "Tenure, Stability & Reputation", "A", "Monthly"),
    VendorVariableDef("g2_rating", "Customer Sentiment & Validation", "B", "Weekly"),
    VendorVariableDef("g2_review_count", "Customer Sentiment & Validation", "B", "Weekly"),
    VendorVariableDef("gartner_peer_insights_rating", "Customer Sentiment & Validation", "B", "Monthly"),
    VendorVariableDef("trustradius_rating", "Customer Sentiment & Validation", "B", "Monthly"),
    VendorVariableDef("aggregate_review_sentiment", "Customer Sentiment & Validation", "B", "Weekly"),
    VendorVariableDef("nps_self_reported", "Customer Sentiment & Validation", "B", "Annual"),
    VendorVariableDef("case_studies_named", "Customer Sentiment & Validation", "B", "Quarterly"),
    VendorVariableDef("customer_count_band", "Customer Sentiment & Validation", "B", "Annual"),
    VendorVariableDef("logo_overlap_with_VA_ICP", "Customer Sentiment & Validation", "B", "Quarterly"),
    VendorVariableDef("verified_customer_references", "Customer Sentiment & Validation", "B", "Annual"),
    VendorVariableDef("vendor_category", "Offering Fit", "B", "On change"),
    VendorVariableDef("capability_tags", "Offering Fit", "B", "On change"),
    VendorVariableDef("addressed_pain_points", "Offering Fit", "B", "Quarterly"),
    VendorVariableDef("naics_industries_served", "Offering Fit", "B", "Annual"),
    VendorVariableDef("vendor_target_market", "Offering Fit", "B", "Annual"),
    VendorVariableDef("icp_min_employees", "Offering Fit", "B", "Annual"),
    VendorVariableDef("icp_max_employees", "Offering Fit", "B", "Annual"),
    VendorVariableDef("geographies_can_sell", "Offering Fit", "B", "Annual"),
    VendorVariableDef("geographies_can_deliver_support", "Offering Fit", "B", "Annual"),
    VendorVariableDef("languages_supported", "Offering Fit", "B", "Annual"),
    VendorVariableDef("deployment_models", "Deployment & Technical Fit", "B", "On change"),
    VendorVariableDef("time_to_value_days", "Deployment & Technical Fit", "B", "Annual"),
    VendorVariableDef("supported_os_endpoints", "Deployment & Technical Fit", "B", "Annual"),
    VendorVariableDef("integrations_native", "Deployment & Technical Fit", "B", "Quarterly"),
    VendorVariableDef("firewall_or_network_prereqs", "Deployment & Technical Fit", "B", "Annual"),
    VendorVariableDef("data_residency_options", "Deployment & Technical Fit", "B", "Annual"),
    VendorVariableDef("certifications_held", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("compliance_frameworks_supported_for_clients", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("incident_notification_window_hours", "Compliance & Trust Posture", "A", "Annual"),
    VendorVariableDef("data_handling_categories", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("encryption_at_rest_in_transit", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("sub_processors_disclosed", "Compliance & Trust Posture", "B", "Quarterly"),
    VendorVariableDef("pen_test_cadence", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("sdlc_practices", "Compliance & Trust Posture", "B", "Annual"),
    VendorVariableDef("commercial_model", "Commercial Fit", "B", "Annual"),
    VendorVariableDef("entry_price_band", "Commercial Fit", "B", "Annual"),
    VendorVariableDef("min_commitment_term_months", "Commercial Fit", "B", "Annual"),
    VendorVariableDef("marketplace_pricing_alignment", "Commercial Fit", "A", "Annual"),
    VendorVariableDef("lead_threshold_acceptance", "Commercial Fit", "B", "Annual"),
    VendorVariableDef("trial_or_pilot_available", "Commercial Fit", "B", "Annual"),
    VendorVariableDef("lead_response_sla_hours", "Lead Handling & Operational Readiness", "A", "Quarterly"),
    VendorVariableDef("lead_disqualifiers_structured", "Lead Handling & Operational Readiness", "B", "Quarterly"),
    VendorVariableDef("lead_volume_capacity_per_month", "Lead Handling & Operational Readiness", "B", "Quarterly"),
    VendorVariableDef("support_severity_definitions_match_VA", "Lead Handling & Operational Readiness", "B", "Annual"),
    VendorVariableDef("support_sla_sev1_hours", "Lead Handling & Operational Readiness", "A", "Annual"),
    VendorVariableDef("named_oncall_accountability", "Lead Handling & Operational Readiness", "B", "Annual"),
    VendorVariableDef("support_channels", "Lead Handling & Operational Readiness", "B", "Annual"),
    VendorVariableDef("release_cadence", "Lead Handling & Operational Readiness", "B", "Annual"),
    VendorVariableDef("material_change_notification_days", "Lead Handling & Operational Readiness", "B", "Annual"),
    VendorVariableDef("accepts_on_platform_comms_policy", "Communications Governance", "A", "Annual"),
    VendorVariableDef("off_channel_exception_policy_understood", "Communications Governance", "B", "Annual"),
    VendorVariableDef("uses_ai_in_product", "AI & Innovation Signal", "C", "Annual"),
    VendorVariableDef("ai_model_provenance", "AI & Innovation Signal", "C", "Annual"),
    VendorVariableDef("ai_safety_controls", "AI & Innovation Signal", "C", "Annual"),
    VendorVariableDef("industry_awards_24mo", "Trust Signals & Premium Differentiators", "C", "Quarterly"),
    VendorVariableDef("analyst_coverage", "Trust Signals & Premium Differentiators", "C", "Quarterly"),
    VendorVariableDef("partner_ecosystem_size", "Trust Signals & Premium Differentiators", "C", "Quarterly"),
    VendorVariableDef("community_presence", "Trust Signals & Premium Differentiators", "C", "Monthly"),
    VendorVariableDef("vendor_response_time_to_VA_team_days", "Trust Signals & Premium Differentiators", "C", "Continuous"),
    VendorVariableDef("va_lead_acceptance_rate", "Operational History on Value Aligners", "B", "Continuous"),
    VendorVariableDef("va_lead_to_meeting_rate", "Operational History on Value Aligners", "B", "Continuous"),
    VendorVariableDef("va_close_rate", "Operational History on Value Aligners", "B", "Continuous"),
    VendorVariableDef("va_csat_post_deal", "Operational History on Value Aligners", "B", "Per deal"),
    VendorVariableDef("va_disputes_or_escalations_count_12mo", "Operational History on Value Aligners", "A", "Continuous"),
]

VARIABLE_BY_NAME = {item.name: item for item in VENDOR_VARIABLE_CATALOG}
TIER_A_GATES = {item.name for item in VENDOR_VARIABLE_CATALOG if item.tier == "A"}

REVIEW_READY_FIELD_CHECKS = [
    ("product category", lambda vendor, values, match_summary: text_present(vendor.cyber_category)),
    ("target segment", lambda vendor, values, match_summary: text_present(vendor.target_market)),
    ("pricing signal", lambda vendor, values, match_summary: text_present(vendor.pricing_model)),
    ("compliance coverage", lambda vendor, values, match_summary: text_present(vendor.compliance_certifications)),
    ("website/source anchor", lambda vendor, values, match_summary: bool(normalize_domain(vendor.company_website))),
    ("match variables", lambda vendor, values, match_summary: (match_summary.get("total_match_count") or 0) > 0),
]


def normalize_domain(url: str) -> str:
    """Extracts a stable domain from a vendor website field."""
    if not url:
        return ""
    value = url.strip()
    if not value:
        return ""
    parsed = urlparse(value if re.match(r"^[a-z]+://", value, re.I) else f"https://{value}")
    domain = (parsed.netloc or parsed.path).lower().strip()
    return domain[4:] if domain.startswith("www.") else domain


def canonical_vendor_id(vendor: Vendor) -> str:
    domain = normalize_domain(vendor.company_website)
    if domain:
        return domain
    return re.sub(r"[^a-z0-9]+", "-", vendor.vendor_name.lower()).strip("-")


def parse_employee_count(company_size: str) -> Optional[int]:
    """Best-effort extraction from catalog strings such as '11-50'."""
    if not company_size:
        return None
    numbers = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", company_size)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return int(sum(numbers[:2]) / 2)


def years_in_market(vendor: Vendor, now: Optional[datetime] = None) -> Optional[int]:
    if not vendor.year_founded:
        return None
    now = now or datetime.now()
    if vendor.year_founded > now.year or vendor.year_founded < 1800:
        return None
    return now.year - vendor.year_founded


def text_present(value) -> bool:
    return bool(str(value or "").strip())


def bool_variable(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def variable_values_for_vendor(vendor: Vendor, match_summary: dict) -> dict:
    """Maps current catalog fields into the PRD variable catalog."""
    domain = normalize_domain(vendor.company_website)
    employee_count = parse_employee_count(vendor.company_size)
    market_years = years_in_market(vendor)

    return {
        "domain_age_years": None,
        "years_in_market": market_years,
        "headquarters_country": vendor.headquarters,
        "employee_count": employee_count,
        "aggregate_review_sentiment": None,
        "customer_count_band": vendor.active_users,
        "vendor_category": vendor.cyber_category,
        "capability_tags": ", ".join(
            part for part in [
                vendor.cyber_category,
                vendor.cyber_subcategory,
                vendor.threat_types_addressed,
            ]
            if text_present(part)
        ),
        "addressed_pain_points": str(match_summary.get("total_match_count") or ""),
        "vendor_target_market": vendor.target_market,
        "deployment_models": vendor.deployment_models,
        "integrations_native": vendor.integration_capabilities,
        "certifications_held": vendor.compliance_certifications,
        "commercial_model": vendor.pricing_model,
        "trial_or_pilot_available": bool_variable(vendor.free_trial),
        "support_channels": None,
        "community_presence": domain,
    }


def populated_variable_count(values: dict) -> int:
    return sum(1 for value in values.values() if text_present(value))


def missing_review_ready_fields(vendor: Vendor, values: dict, match_summary: dict) -> list[str]:
    return [
        field_name
        for field_name, check in REVIEW_READY_FIELD_CHECKS
        if not check(vendor, values, match_summary)
    ]


def score_vendor(vendor: Vendor, values: dict, match_summary: dict) -> dict:
    """Deterministic Phase 0 scoring using only current catalog evidence."""
    trust = 0.0
    fit = 0.0
    operational = 0.0

    if normalize_domain(vendor.company_website):
        trust += 15
    if years_in_market(vendor) is not None:
        trust += min(years_in_market(vendor) or 0, 10) * 2
    if text_present(vendor.headquarters):
        trust += 10
    if text_present(vendor.compliance_certifications):
        trust += 20
    if vendor.customer_rating:
        trust += min(max(vendor.customer_rating, 0), 5) * 7

    if text_present(vendor.cyber_category):
        fit += 18
    if text_present(vendor.cyber_subcategory):
        fit += 12
    if text_present(vendor.threat_types_addressed):
        fit += 18
    if text_present(vendor.product_description):
        fit += 10
    if text_present(vendor.target_market):
        fit += 12
    if text_present(vendor.deployment_models):
        fit += 8
    if text_present(vendor.integration_capabilities):
        fit += 6

    avg_match = match_summary.get("avg_match_score") or 0
    total_matches = match_summary.get("total_match_count") or 0
    strong_matches = match_summary.get("strong_match_count") or 0
    medium_matches = match_summary.get("medium_match_count") or 0
    fit += min(avg_match * 20, 20)
    fit += min(total_matches * 0.4, 8)
    fit += min(strong_matches * 1.0, 8)
    fit += min(medium_matches * 0.5, 5)

    if vendor.free_trial is True:
        operational += 20
    if text_present(vendor.status):
        operational += 15
    if text_present(vendor.supported_platforms):
        operational += 15
    if text_present(vendor.api_available):
        operational += 10

    trust = round(min(trust, 100), 2)
    fit = round(min(fit, 100), 2)
    operational = round(min(operational, 100), 2)
    vqs = round((trust * 0.5) + (fit * 0.5), 2)

    tier_b_populated = populated_variable_count(values)
    coverage_pct = round((tier_b_populated / TOTAL_VENDOR_VARIABLES) * 100, 2)
    missing_gates = sorted(name for name in TIER_A_GATES if not text_present(values.get(name)))

    if not missing_gates:
        gate_status = "passed"
    elif normalize_domain(vendor.company_website) and text_present(vendor.vendor_name):
        gate_status = "needs_review"
    else:
        gate_status = "blocked"

    if gate_status == "passed" and tier_b_populated >= 64:
        confidence = "high"
    elif gate_status in {"passed", "needs_review"} and tier_b_populated >= 40:
        confidence = "medium"
    else:
        confidence = "low"

    review_missing = missing_review_ready_fields(vendor, values, match_summary)

    if not review_missing and gate_status == "passed" and trust >= 60 and fit >= 40:
        readiness = "Marketplace Ready"
    elif not review_missing:
        readiness = "Review Ready"
    else:
        readiness = "Submission Incomplete"

    return {
        "trust_score": trust,
        "fit_score": fit,
        "operational_score": operational,
        "vendor_quality_score": vqs,
        "match_confidence": confidence,
        "tier_a_gate_status": gate_status,
        "tier_a_missing": ", ".join(missing_gates),
        "tier_b_populated_count": tier_b_populated,
        "variable_coverage_pct": coverage_pct,
        "readiness_status": readiness,
        "review_ready_missing": ", ".join(review_missing),
    }


def match_summary_for_vendor(session, vendor_id: int) -> dict:
    total = session.query(VendorPainPointMap).filter_by(vendor_id=vendor_id).count()
    strong = session.query(VendorPainPointMap).filter_by(
        vendor_id=vendor_id,
        confidence_label="strong",
    ).count()
    medium = session.query(VendorPainPointMap).filter_by(
        vendor_id=vendor_id,
        confidence_label="medium",
    ).count()
    avg = session.query(func.avg(VendorPainPointMap.match_score)).filter_by(
        vendor_id=vendor_id,
    ).scalar()
    return {
        "total_match_count": total,
        "strong_match_count": strong,
        "medium_match_count": medium,
        "avg_match_score": round(float(avg or 0), 3),
    }


def upsert_variable(session, profile: VendorIntelligenceProfile, name: str, value) -> None:
    definition = VARIABLE_BY_NAME[name]
    existing = session.query(VendorIntelligenceVariable).filter_by(
        profile_id=profile.id,
        variable_name=name,
    ).first()
    variable = existing or VendorIntelligenceVariable(
        profile_id=profile.id,
        variable_name=name,
    )

    new_value = "" if value is None else str(value)
    if existing and variable.value_text != new_value:
        variable.prior_value = variable.value_text

    variable.variable_category = definition.category
    variable.tier = definition.tier
    variable.value_text = new_value
    variable.value_number = float(value) if isinstance(value, (int, float)) else None
    variable.value_bool = value if isinstance(value, bool) else None
    variable.source_type = "existing_vendor_catalog"
    variable.confidence = "catalog" if text_present(value) else "missing"
    variable.refresh_cadence = definition.refresh
    variable.collected_at = datetime.now()

    if not existing:
        session.add(variable)


def upsert_vendor_profile(session, vendor: Vendor) -> VendorIntelligenceProfile:
    profile = session.query(VendorIntelligenceProfile).filter_by(vendor_id=vendor.id).first()
    if not profile:
        profile = VendorIntelligenceProfile(
            vendor_id=vendor.id,
            vendor_canonical_id=canonical_vendor_id(vendor),
            canonical_name=vendor.vendor_name,
        )
        session.add(profile)
        session.flush()

    match_summary = match_summary_for_vendor(session, vendor.id)
    values = variable_values_for_vendor(vendor, match_summary)
    scores = score_vendor(vendor, values, match_summary)

    profile.vendor_canonical_id = canonical_vendor_id(vendor)
    profile.canonical_name = vendor.vendor_name
    profile.primary_domain = normalize_domain(vendor.company_website)
    profile.record_status = "enriched" if populated_variable_count(values) else "discovered"
    profile.readiness_status = scores["readiness_status"]
    profile.trust_score = scores["trust_score"]
    profile.fit_score = scores["fit_score"]
    profile.operational_score = scores["operational_score"]
    profile.vendor_quality_score = scores["vendor_quality_score"]
    profile.match_confidence = scores["match_confidence"]
    profile.tier_a_gate_status = scores["tier_a_gate_status"]
    profile.tier_a_missing = scores["tier_a_missing"]
    profile.tier_b_populated_count = scores["tier_b_populated_count"]
    profile.total_variable_count = TOTAL_VENDOR_VARIABLES
    profile.variable_coverage_pct = scores["variable_coverage_pct"]
    profile.avg_match_score = match_summary["avg_match_score"]
    profile.strong_match_count = match_summary["strong_match_count"]
    profile.medium_match_count = match_summary["medium_match_count"]
    profile.total_match_count = match_summary["total_match_count"]
    profile.source_summary = "Seeded from existing Loopa vendor catalog and vendor_pain_point_map."
    profile.last_enriched_at = datetime.now()
    profile.last_scored_at = datetime.now()

    for name, value in values.items():
        upsert_variable(session, profile, name, value)

    session.add(VendorScoreHistory(
        profile_id=profile.id,
        trust_score=profile.trust_score,
        fit_score=profile.fit_score,
        operational_score=profile.operational_score,
        vendor_quality_score=profile.vendor_quality_score,
        match_confidence=profile.match_confidence,
        score_reason="Phase 0 deterministic score from existing catalog fields.",
    ))

    session.query(VendorAlert).filter_by(
        profile_id=profile.id,
        alert_type="tier_a_gates_missing",
        status="open",
    ).delete()
    if scores["tier_a_gate_status"] != "passed":
        session.add(VendorAlert(
            profile_id=profile.id,
            alert_type="tier_a_gates_missing",
            severity="review",
            message=f"Missing or unverified Tier-A gates: {scores['tier_a_missing']}",
        ))

    session.query(VendorAlert).filter_by(
        profile_id=profile.id,
        alert_type="review_ready_core_missing",
        status="open",
    ).delete()
    if scores["readiness_status"] == "Submission Incomplete" and scores["review_ready_missing"]:
        session.add(VendorAlert(
            profile_id=profile.id,
            alert_type="review_ready_core_missing",
            severity="review",
            message=f"Missing Review Ready core fields: {scores['review_ready_missing']}",
        ))

    return profile


def run_vendor_scope_seed(limit: Optional[int] = None) -> dict:
    """Seeds VendorScope profiles from all current vendors."""
    session = get_session()
    try:
        query = session.query(Vendor).filter(Vendor.vendor_name != None).order_by(Vendor.id)
        if limit:
            query = query.limit(limit)
        vendors = query.all()

        processed = 0
        for vendor in vendors:
            upsert_vendor_profile(session, vendor)
            processed += 1
            if processed % 250 == 0:
                session.commit()
        session.commit()

        return {
            "processed": processed,
            "profiles": session.query(VendorIntelligenceProfile).count(),
            "variables": session.query(VendorIntelligenceVariable).count(),
            "alerts": session.query(VendorAlert).count(),
        }
    finally:
        session.close()


def build_vendor_intelligence_rows() -> list:
    session = get_session()
    try:
        rows = []
        profiles = (
            session.query(VendorIntelligenceProfile, Vendor)
            .join(Vendor, Vendor.id == VendorIntelligenceProfile.vendor_id)
            .order_by(VendorIntelligenceProfile.vendor_quality_score.desc())
            .all()
        )
        for profile, vendor in profiles:
            rows.append({
                "vendor_id": vendor.id,
                "vendor_name": vendor.vendor_name,
                "vendor_canonical_id": profile.vendor_canonical_id,
                "primary_domain": profile.primary_domain,
                "record_status": profile.record_status,
                "readiness_status": profile.readiness_status,
                "tier_a_gate_status": profile.tier_a_gate_status,
                "tier_a_missing": profile.tier_a_missing,
                "trust_score": profile.trust_score,
                "fit_score": profile.fit_score,
                "operational_score": profile.operational_score,
                "vendor_quality_score": profile.vendor_quality_score,
                "match_confidence": profile.match_confidence,
                "variable_coverage_pct": profile.variable_coverage_pct,
                "tier_b_populated_count": profile.tier_b_populated_count,
                "avg_match_score": profile.avg_match_score,
                "strong_match_count": profile.strong_match_count,
                "medium_match_count": profile.medium_match_count,
                "total_match_count": profile.total_match_count,
                "vendor_category": vendor.cyber_category,
                "vendor_subcategory": vendor.cyber_subcategory,
                "target_market": vendor.target_market,
                "deployment_models": vendor.deployment_models,
                "certifications_held": vendor.compliance_certifications,
                "source_summary": profile.source_summary,
                "last_scored_at": profile.last_scored_at,
            })
        return rows
    finally:
        session.close()


def save_vendor_intelligence_csv(rows: list, output_path: Optional[str] = None) -> str:
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)
    if not output_path:
        output_path = os.path.join(
            output_dir,
            f"vendor_intelligence_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )

    fieldnames = list(rows[0].keys()) if rows else [
        "vendor_id",
        "vendor_name",
        "vendor_quality_score",
        "readiness_status",
    ]
    with open(output_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def annotate_rows_with_dq(rows: list, dq_summary: Optional[dict]) -> list:
    if not dq_summary:
        return rows
    return [
        {
            **row,
            "dq_status": dq_summary["status"],
            "dq_run_id": dq_summary["run_id"],
            "dq_quality_score": dq_summary["quality_score"],
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed and export VendorScope Phase 0 intelligence.")
    parser.add_argument("--limit", type=int, help="Limit vendors processed, useful for smoke tests")
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--skip-export", action="store_true", help="Seed only, do not create CSV export")
    parser.add_argument("--skip-dq", action="store_true", help="Skip Data Quality gate")
    args = parser.parse_args()

    summary = run_vendor_scope_seed(limit=args.limit)
    print("VendorScope seed complete")
    for key, value in summary.items():
        print(f"{key}: {value}")

    dq_summary = None
    if args.limit:
        print("Data Quality gate skipped for limited smoke run.")
    elif args.skip_dq:
        print("Data Quality gate skipped by request.")
    else:
        dq_summary = run_data_quality("vendor_scope")
        print(
            "VendorScope Data Quality: "
            f"{dq_summary['status']} "
            f"(run_id={dq_summary['run_id']}, "
            f"critical={dq_summary['critical_count']}, "
            f"warnings={dq_summary['warning_count']})"
        )
        if dq_summary["critical_count"]:
            print("VendorScope export blocked because Data Quality found critical issues.")
            return 1

    if not args.skip_export:
        rows = annotate_rows_with_dq(build_vendor_intelligence_rows(), dq_summary)
        path = save_vendor_intelligence_csv(rows, args.output)
        print(f"Vendor intelligence export saved: {path}")
        print(f"Rows: {len(rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
