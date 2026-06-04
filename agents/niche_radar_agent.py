# agents/niche_radar_agent.py
# NicheRadar Phase 0: re-score existing Loopa niche markets and compute the
# vendor-supply gate from current vendor matches. This does not perform account
# discovery or outreach automation.

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    NicheMarket,
    NicheRadarScore,
    NicheRadarScoreHistory,
    NicheRadarVariable,
    PainPoint,
    VendorPainPointMap,
)
from agents.data_quality_agent import run_data_quality


TOTAL_NICHE_VARIABLES = 58


@dataclass(frozen=True)
class NicheVariableDef:
    name: str
    category: str
    tier: str
    refresh: str


NICHE_VARIABLE_CATALOG = [
    NicheVariableDef("naics_code", "Niche Identification & Taxonomy", "A", "Annual"),
    NicheVariableDef("niche_market", "Niche Identification & Taxonomy", "A", "Annual"),
    NicheVariableDef("industry_path", "Niche Identification & Taxonomy", "A", "Annual"),
    NicheVariableDef("geography", "Niche Identification & Taxonomy", "A", "Annual"),
    NicheVariableDef("niche_active_business_count", "Niche Identification & Taxonomy", "A", "Annual"),
    NicheVariableDef("breach_frequency_24mo", "Industry Vulnerability", "B", "Monthly"),
    NicheVariableDef("breach_avg_cost_usd", "Industry Vulnerability", "B", "Annual"),
    NicheVariableDef("dbir_top_pattern", "Industry Vulnerability", "B", "Annual"),
    NicheVariableDef("regulatory_pressure_score", "Industry Vulnerability", "B", "Quarterly"),
    NicheVariableDef("regulatory_deadline_within_12mo", "Industry Vulnerability", "B", "Monthly"),
    NicheVariableDef("cyber_insurance_pressure", "Industry Vulnerability", "B", "Annual"),
    NicheVariableDef("peer_breach_proximity_score", "Industry Vulnerability", "B", "Weekly"),
    NicheVariableDef("pain_point_severity_avg", "Industry Vulnerability", "B", "Quarterly"),
    NicheVariableDef("median_revenue_band", "ICP Payability", "B", "Annual"),
    NicheVariableDef("median_headcount_band", "ICP Payability", "B", "Annual"),
    NicheVariableDef("it_budget_pct_of_revenue", "ICP Payability", "B", "Annual"),
    NicheVariableDef("cyber_spend_share_of_it", "ICP Payability", "B", "Annual"),
    NicheVariableDef("inhouse_security_team_likelihood", "ICP Payability", "B", "Annual"),
    NicheVariableDef("decision_maker_concentration", "ICP Payability", "B", "Annual"),
    NicheVariableDef("avg_sales_cycle_days_estimate", "ICP Payability", "B", "Quarterly"),
    NicheVariableDef("propensity_to_buy_via_marketplace", "ICP Payability", "B", "Quarterly"),
    NicheVariableDef("trigger_event_density_90d", "ICP Payability", "B", "Weekly"),
    NicheVariableDef("primary_buyer_role", "Persona ICP", "B", "Quarterly"),
    NicheVariableDef("economic_buyer_title", "Persona ICP", "B", "Annual"),
    NicheVariableDef("champion_role", "Persona ICP", "B", "Annual"),
    NicheVariableDef("gatekeeper_role", "Persona ICP", "B", "Annual"),
    NicheVariableDef("linkedin_searchability_score", "Persona ICP", "B", "Quarterly"),
    NicheVariableDef("email_verifiability_rate", "Persona ICP", "B", "Quarterly"),
    NicheVariableDef("phone_reachability_score", "Persona ICP", "B", "Annual"),
    NicheVariableDef("linkedin_member_count_in_niche", "Reachability & Channel Fit", "B", "Quarterly"),
    NicheVariableDef("industry_association_density", "Reachability & Channel Fit", "B", "Annual"),
    NicheVariableDef("searches_per_month_intent_keywords", "Reachability & Channel Fit", "B", "Quarterly"),
    NicheVariableDef("community_presence", "Reachability & Channel Fit", "B", "Quarterly"),
    NicheVariableDef("event_density_12mo", "Reachability & Channel Fit", "B", "Quarterly"),
    NicheVariableDef("partner_overlap_score", "Reachability & Channel Fit", "B", "Annual"),
    NicheVariableDef("marketplace_vendor_count_serving_niche", "Vendor Supply Fit", "A", "Weekly"),
    NicheVariableDef("top_pain_point_coverage_pct", "Vendor Supply Fit", "A", "Weekly"),
    NicheVariableDef("avg_match_score_for_niche", "Vendor Supply Fit", "B", "Weekly"),
    NicheVariableDef("company_legal_name", "Account-Level Variables", "A", "Quarterly"),
    NicheVariableDef("dba_names", "Account-Level Variables", "B", "Quarterly"),
    NicheVariableDef("state", "Account-Level Variables", "A", "Quarterly"),
    NicheVariableDef("headquarters_address", "Account-Level Variables", "B", "Annual"),
    NicheVariableDef("employee_count_estimated", "Account-Level Variables", "B", "Quarterly"),
    NicheVariableDef("revenue_estimated_usd", "Account-Level Variables", "B", "Annual"),
    NicheVariableDef("years_in_business", "Account-Level Variables", "B", "Annual"),
    NicheVariableDef("compliance_obligations_present", "Account-Level Variables", "B", "Annual"),
    NicheVariableDef("recent_breach_or_incident", "Account-Level Variables", "B", "Weekly"),
    NicheVariableDef("recent_funding_or_expansion", "Account-Level Variables", "B", "Weekly"),
    NicheVariableDef("hiring_security_or_compliance", "Account-Level Variables", "B", "Weekly"),
    NicheVariableDef("tech_stack_signals", "Account-Level Variables", "B", "Quarterly"),
    NicheVariableDef("inferred_security_maturity", "Account-Level Variables", "B", "Quarterly"),
    NicheVariableDef("decision_maker_identified", "Account-Level Variables", "A", "Quarterly"),
    NicheVariableDef("email_verified", "Account-Level Variables", "A", "Per outreach"),
    NicheVariableDef("linkedin_url", "Account-Level Variables", "B", "Per outreach"),
    NicheVariableDef("phone_direct_dial", "Account-Level Variables", "B", "Quarterly"),
    NicheVariableDef("last_engagement", "Account-Level Variables", "A", "Continuous"),
    NicheVariableDef("existing_partner_relationship", "Account-Level Variables", "A", "Continuous"),
    NicheVariableDef("state_specific_regulatory_flags", "Account-Level Variables", "B", "Quarterly"),
]

VARIABLE_BY_NAME = {item.name: item for item in NICHE_VARIABLE_CATALOG}


def clamp_score(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return round(max(0.0, min(float(value), 100.0)), 2)


def scale_1_to_10(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return clamp_score(float(value) * 10)


def text_present(value) -> bool:
    return bool(str(value or "").strip())


def industry_path(niche: NicheMarket) -> str:
    return " > ".join(
        part for part in [
            niche.industry,
            niche.sub_industry,
            niche.sub_sub_industry,
            niche.sub_sub_sub_industry,
            niche.sub_sub_sub_sub_industry,
        ]
        if text_present(part)
    )


def compliance_pressure(niche: NicheMarket) -> float:
    text = " ".join([
        niche.likely_compliance_regimes or "",
        niche.conditional_compliance_regimes or "",
        niche.regulatory_or_compliance_drivers or "",
        niche.compliance_audit_notes or "",
    ]).lower()
    if not text.strip() or "none auto-tagged" in text:
        return 20.0
    frameworks = ["hipaa", "pci", "cmmc", "soc2", "glba", "ferpa", "gdpr", "privacy", "audit"]
    hits = sum(1 for framework in frameworks if framework in text)
    return clamp_score(35 + hits * 10)


def avg_pain_point_severity(pain_points: list[PainPoint]) -> float:
    values = [pp.severity_score for pp in pain_points if pp.severity_score is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def vendor_supply_summary(session, pain_points: list[PainPoint]) -> dict:
    if not pain_points:
        return {
            "vendor_count": 0,
            "coverage_pct": 0.0,
            "covered_count": 0,
            "top_count": 0,
            "avg_match_score": 0.0,
            "strong_count": 0,
            "medium_count": 0,
            "total_count": 0,
        }

    top_points = pain_points[:5]
    pain_point_ids = [pp.id for pp in top_points]
    matches = (
        session.query(VendorPainPointMap)
        .filter(VendorPainPointMap.pain_point_id.in_(pain_point_ids))
        .filter(VendorPainPointMap.confidence_label.in_(["strong", "medium"]))
        .all()
    )

    covered_ids = {match.pain_point_id for match in matches}
    vendor_ids = {match.vendor_id for match in matches}
    scores = [match.match_score for match in matches if match.match_score is not None]
    avg_match = round((sum(scores) / len(scores)) * 100, 2) if scores else 0.0
    strong = sum(1 for match in matches if match.confidence_label == "strong")
    medium = sum(1 for match in matches if match.confidence_label == "medium")

    return {
        "vendor_count": len(vendor_ids),
        "coverage_pct": round((len(covered_ids) / len(top_points)) * 100, 2),
        "covered_count": len(covered_ids),
        "top_count": len(top_points),
        "avg_match_score": avg_match,
        "strong_count": strong,
        "medium_count": medium,
        "total_count": len(matches),
    }


def score_niche(niche: NicheMarket, pain_points: list[PainPoint], supply: dict) -> dict:
    severity_avg = avg_pain_point_severity(pain_points)
    regulatory_pressure = compliance_pressure(niche)

    vulnerability = clamp_score(
        (clamp_score(niche.demand_score) * 0.45)
        + (scale_1_to_10(severity_avg) * 0.25)
        + (regulatory_pressure * 0.15)
        + (scale_1_to_10(niche.attack_records) * 0.10)
        + (scale_1_to_10(niche.digitalization_level) * 0.05)
    )

    procurement_inverse = 100 - scale_1_to_10(niche.procurement_friction)
    payability = clamp_score(
        (clamp_score(niche.outbound_score) * 0.30)
        + (scale_1_to_10(niche.buyer_role_clarity) * 0.20)
        + (scale_1_to_10(niche.budget_proxy) * 0.20)
        + (scale_1_to_10(niche.offer_fit) * 0.15)
        + (procurement_inverse * 0.15)
    )

    reachability = clamp_score(
        (clamp_score(niche.outbound_score) * 0.45)
        + (scale_1_to_10(niche.reachability) * 0.30)
        + (scale_1_to_10(niche.time_to_value) * 0.15)
        + (scale_1_to_10(niche.buyer_role_clarity) * 0.10)
    )

    nps_va = clamp_score(
        (vulnerability * 0.45)
        + (payability * 0.35)
        + (reachability * 0.20)
    )

    tier1_supply = (
        supply["vendor_count"] >= 5
        and supply["coverage_pct"] >= 80
        and supply["avg_match_score"] >= 45
    )
    review_supply = (
        supply["vendor_count"] >= 2
        and supply["coverage_pct"] >= 60
    )

    if tier1_supply:
        gate_status = "tier1_ready"
        gap_reason = ""
    elif review_supply:
        gate_status = "review_ready"
        gap_reason = "Vendor supply passes review threshold but not Tier 1 threshold."
    else:
        gate_status = "fail"
        gap_reason = (
            f"Needs at least 2 vendors and 60% pain-point coverage; "
            f"current vendors={supply['vendor_count']}, coverage={supply['coverage_pct']}%."
        )

    if nps_va >= 75 and reachability >= 60 and tier1_supply:
        refined_tier = "Tier 1 - Hunt now"
        refined_tier_rank = 1
    elif nps_va >= 55 and review_supply:
        refined_tier = "Tier 2 - Build pipeline"
        refined_tier_rank = 2
    elif nps_va >= 35 or not review_supply:
        refined_tier = "Tier 3 - Watchlist"
        refined_tier_rank = 3
    else:
        refined_tier = "Tier 4 - Defer"
        refined_tier_rank = 4

    if tier1_supply and reachability >= 60 and 65 <= nps_va < 75:
        priority_watchlist_status = "Tier 1 Candidate"
    elif review_supply and reachability >= 60 and 65 <= nps_va < 75:
        priority_watchlist_status = "Tier 2 - Priority Watchlist"
    else:
        priority_watchlist_status = ""

    return {
        "vulnerability_score": vulnerability,
        "payability_score": payability,
        "reachability_score": reachability,
        "nps_va": nps_va,
        "refined_tier": refined_tier,
        "refined_tier_rank": refined_tier_rank,
        "priority_watchlist_status": priority_watchlist_status,
        "vendor_supply_gate_status": gate_status,
        "vendor_supply_gap_reason": gap_reason,
        "pain_point_severity_avg": severity_avg,
        "regulatory_pressure_score": regulatory_pressure,
    }


def variable_values_for_niche(niche: NicheMarket, pain_points: list[PainPoint], supply: dict, scores: dict) -> dict:
    return {
        "naics_code": niche.naics_code,
        "niche_market": niche.niche_name,
        "industry_path": industry_path(niche),
        "geography": niche.geography,
        "niche_active_business_count": None,
        "breach_frequency_24mo": niche.attack_records,
        "breach_avg_cost_usd": niche.estimated_annual_loss,
        "dbir_top_pattern": niche.common_cyber_risks,
        "regulatory_pressure_score": scores["regulatory_pressure_score"],
        "regulatory_deadline_within_12mo": None,
        "cyber_insurance_pressure": None,
        "peer_breach_proximity_score": None,
        "pain_point_severity_avg": scores["pain_point_severity_avg"],
        "median_revenue_band": None,
        "median_headcount_band": f"{niche.avg_employee_count_min or ''}-{niche.avg_employee_count_max or ''}".strip("-"),
        "it_budget_pct_of_revenue": None,
        "cyber_spend_share_of_it": None,
        "inhouse_security_team_likelihood": None,
        "decision_maker_concentration": niche.buyer_role_clarity,
        "avg_sales_cycle_days_estimate": None,
        "propensity_to_buy_via_marketplace": niche.offer_fit,
        "trigger_event_density_90d": None,
        "primary_buyer_role": niche.primary_buyer_role,
        "economic_buyer_title": niche.primary_buyer_role.split(";")[0].strip() if niche.primary_buyer_role else None,
        "champion_role": None,
        "gatekeeper_role": None,
        "linkedin_searchability_score": niche.reachability,
        "email_verifiability_rate": None,
        "phone_reachability_score": None,
        "linkedin_member_count_in_niche": None,
        "industry_association_density": None,
        "searches_per_month_intent_keywords": None,
        "community_presence": None,
        "event_density_12mo": None,
        "partner_overlap_score": None,
        "marketplace_vendor_count_serving_niche": supply["vendor_count"],
        "top_pain_point_coverage_pct": supply["coverage_pct"],
        "avg_match_score_for_niche": supply["avg_match_score"],
    }


def upsert_variable(session, radar_score: NicheRadarScore, name: str, value) -> None:
    definition = VARIABLE_BY_NAME[name]
    existing = session.query(NicheRadarVariable).filter_by(
        score_id=radar_score.id,
        variable_name=name,
    ).first()
    variable = existing or NicheRadarVariable(
        score_id=radar_score.id,
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
    variable.source_type = "existing_loopa_research"
    variable.confidence = "catalog" if text_present(value) else "missing"
    variable.refresh_cadence = definition.refresh
    variable.collected_at = datetime.now()

    if not existing:
        session.add(variable)


def upsert_niche_radar_score(session, niche: NicheMarket) -> NicheRadarScore:
    pain_points = (
        session.query(PainPoint)
        .filter_by(niche_market_id=niche.id)
        .order_by(PainPoint.pain_point_rank)
        .all()
    )
    supply = vendor_supply_summary(session, pain_points)
    scores = score_niche(niche, pain_points, supply)

    radar_score = session.query(NicheRadarScore).filter_by(niche_market_id=niche.id).first()
    if not radar_score:
        radar_score = NicheRadarScore(niche_market_id=niche.id)
        session.add(radar_score)
        session.flush()

    radar_score.vulnerability_score = scores["vulnerability_score"]
    radar_score.payability_score = scores["payability_score"]
    radar_score.reachability_score = scores["reachability_score"]
    radar_score.nps_va = scores["nps_va"]
    radar_score.refined_tier = scores["refined_tier"]
    radar_score.refined_tier_rank = scores["refined_tier_rank"]
    radar_score.priority_watchlist_status = scores["priority_watchlist_status"]
    radar_score.marketplace_vendor_count_serving_niche = supply["vendor_count"]
    radar_score.top_pain_point_coverage_pct = supply["coverage_pct"]
    radar_score.avg_match_score_for_niche = supply["avg_match_score"]
    radar_score.vendor_supply_gate_status = scores["vendor_supply_gate_status"]
    radar_score.vendor_supply_gap_reason = scores["vendor_supply_gap_reason"]
    radar_score.top_pain_point_count = supply["top_count"]
    radar_score.covered_top_pain_point_count = supply["covered_count"]
    radar_score.strong_match_count = supply["strong_count"]
    radar_score.medium_match_count = supply["medium_count"]
    radar_score.total_match_count = supply["total_count"]
    radar_score.score_basis = "Phase 0 deterministic score from existing Loopa niche research and vendor matches."
    radar_score.source_summary = "Existing niche_markets, pain_points, and vendor_pain_point_map tables."
    radar_score.last_scored_at = datetime.now()

    values = variable_values_for_niche(niche, pain_points, supply, scores)
    for name, value in values.items():
        upsert_variable(session, radar_score, name, value)

    session.add(NicheRadarScoreHistory(
        score_id=radar_score.id,
        vulnerability_score=radar_score.vulnerability_score,
        payability_score=radar_score.payability_score,
        reachability_score=radar_score.reachability_score,
        nps_va=radar_score.nps_va,
        refined_tier=radar_score.refined_tier,
        priority_watchlist_status=radar_score.priority_watchlist_status,
        vendor_supply_gate_status=radar_score.vendor_supply_gate_status,
        score_reason=radar_score.score_basis,
    ))

    return radar_score


def run_niche_radar_seed(limit: Optional[int] = None) -> dict:
    session = get_session()
    try:
        query = (
            session.query(NicheMarket)
            .filter(NicheMarket.priority_score != None)
            .order_by(NicheMarket.id)
        )
        if limit:
            query = query.limit(limit)

        processed = 0
        for niche in query.all():
            upsert_niche_radar_score(session, niche)
            processed += 1
            if processed % 250 == 0:
                session.commit()
        session.commit()

        return {
            "processed": processed,
            "scores": session.query(NicheRadarScore).count(),
            "variables": session.query(NicheRadarVariable).count(),
        }
    finally:
        session.close()


def build_niche_radar_rows() -> list:
    session = get_session()
    try:
        rows = []
        results = (
            session.query(NicheRadarScore, NicheMarket)
            .join(NicheMarket, NicheMarket.id == NicheRadarScore.niche_market_id)
            .order_by(NicheRadarScore.refined_tier_rank, NicheRadarScore.nps_va.desc())
            .all()
        )
        for score, niche in results:
            rows.append({
                "niche_market_id": niche.id,
                "niche_market": niche.niche_name,
                "industry_path": industry_path(niche),
                "naics_code": niche.naics_code,
                "geography": niche.geography,
                "original_priority_tier": niche.priority_tier,
                "original_priority_score": niche.priority_score,
                "refined_tier": score.refined_tier,
                "priority_watchlist_status": score.priority_watchlist_status,
                "nps_va": score.nps_va,
                "vulnerability_score": score.vulnerability_score,
                "payability_score": score.payability_score,
                "reachability_score": score.reachability_score,
                "vendor_supply_gate_status": score.vendor_supply_gate_status,
                "marketplace_vendor_count_serving_niche": score.marketplace_vendor_count_serving_niche,
                "top_pain_point_coverage_pct": score.top_pain_point_coverage_pct,
                "avg_match_score_for_niche": score.avg_match_score_for_niche,
                "covered_top_pain_point_count": score.covered_top_pain_point_count,
                "top_pain_point_count": score.top_pain_point_count,
                "strong_match_count": score.strong_match_count,
                "medium_match_count": score.medium_match_count,
                "total_match_count": score.total_match_count,
                "vendor_supply_gap_reason": score.vendor_supply_gap_reason,
                "primary_buyer_role": niche.primary_buyer_role,
                "likely_compliance": niche.likely_compliance_regimes or niche.compliance_audit_notes,
                "recommended_cyber_themes": niche.recommended_cyber_themes or niche.common_cyber_risks,
                "score_basis": score.score_basis,
                "last_scored_at": score.last_scored_at,
            })
        return rows
    finally:
        session.close()


def save_niche_radar_csv(rows: list, output_path: Optional[str] = None) -> str:
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)
    if not output_path:
        output_path = os.path.join(
            output_dir,
            f"niche_radar_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )

    fieldnames = list(rows[0].keys()) if rows else [
        "niche_market",
        "refined_tier",
        "priority_watchlist_status",
        "nps_va",
        "vendor_supply_gate_status",
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
    parser = argparse.ArgumentParser(description="Seed and export NicheRadar Phase 0 scores.")
    parser.add_argument("--limit", type=int, help="Limit niches processed, useful for smoke tests")
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--skip-export", action="store_true", help="Seed only, do not create CSV export")
    parser.add_argument("--skip-dq", action="store_true", help="Skip Data Quality gate")
    args = parser.parse_args()

    summary = run_niche_radar_seed(limit=args.limit)
    print("NicheRadar seed complete")
    for key, value in summary.items():
        print(f"{key}: {value}")

    dq_summary = None
    if args.limit:
        print("Data Quality gate skipped for limited smoke run.")
    elif args.skip_dq:
        print("Data Quality gate skipped by request.")
    else:
        dq_summary = run_data_quality("niche_radar")
        print(
            "NicheRadar Data Quality: "
            f"{dq_summary['status']} "
            f"(run_id={dq_summary['run_id']}, "
            f"critical={dq_summary['critical_count']}, "
            f"warnings={dq_summary['warning_count']})"
        )
        if dq_summary["critical_count"]:
            print("NicheRadar export blocked because Data Quality found critical issues.")
            return 1

    if not args.skip_export:
        rows = annotate_rows_with_dq(build_niche_radar_rows(), dq_summary)
        path = save_niche_radar_csv(rows, args.output)
        print(f"NicheRadar export saved: {path}")
        print(f"Rows: {len(rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
