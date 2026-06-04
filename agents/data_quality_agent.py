# agents/data_quality_agent.py
# Deterministic data quality gate for Loopa core data, VendorScope, and
# NicheRadar. This agent runs before downstream enrichment, matching, or sales
# workflows rely on the generated records.

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    AccountLead,
    DataQualityFinding,
    DataQualityRun,
    NicheMarket,
    NicheRadarScore,
    PainPoint,
    Vendor,
    VendorIntelligenceProfile,
    VendorPainPointMap,
)


VALID_TARGETS = {"account_leads", "all", "core", "niche_radar", "vendor_scope"}
SEVERITY_WEIGHT = {"critical": 10, "warning": 2, "info": 0}
DISCOVERY_PENDING = "Discovery Pending"
CONTACT_IDENTIFIED = "Contact Identified"
OUTREACH_READY_STATUSES = {"Hot", "On-fire", "Outreach Ready"}


@dataclass
class Finding:
    target: str
    severity: str
    check_name: str
    entity_type: str
    entity_id: Optional[int]
    message: str
    field_name: str = ""
    observed_value: str = ""


def text_present(value) -> bool:
    return bool(str(value or "").strip())


def normalize_domain(url: str) -> str:
    if not url:
        return ""
    value = url.strip().lower()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0].split("?")[0].strip()
    return value[4:] if value.startswith("www.") else value


def add_finding(
    findings: list[Finding],
    target: str,
    severity: str,
    check_name: str,
    entity_type: str,
    entity_id: Optional[int],
    message: str,
    field_name: str = "",
    observed_value=None,
) -> None:
    findings.append(Finding(
        target=target,
        severity=severity,
        check_name=check_name,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        observed_value="" if observed_value is None else str(observed_value),
        message=message,
    ))


def in_range(value, minimum: float, maximum: float) -> bool:
    if value is None:
        return True
    return minimum <= float(value) <= maximum


def expected_supply_gate(score: NicheRadarScore) -> str:
    tier1_supply = (
        (score.marketplace_vendor_count_serving_niche or 0) >= 5
        and (score.top_pain_point_coverage_pct or 0) >= 80
        and (score.avg_match_score_for_niche or 0) >= 45
    )
    review_supply = (
        (score.marketplace_vendor_count_serving_niche or 0) >= 2
        and (score.top_pain_point_coverage_pct or 0) >= 60
    )
    if tier1_supply:
        return "tier1_ready"
    if review_supply:
        return "review_ready"
    return "fail"


def expected_refined_tier(score: NicheRadarScore) -> tuple[str, int]:
    nps_va = score.nps_va or 0
    reachability = score.reachability_score or 0
    gate = expected_supply_gate(score)
    tier1_supply = gate == "tier1_ready"
    review_supply = gate in {"tier1_ready", "review_ready"}

    if nps_va >= 75 and reachability >= 60 and tier1_supply:
        return "Tier 1 - Hunt now", 1
    if nps_va >= 55 and review_supply:
        return "Tier 2 - Build pipeline", 2
    if nps_va >= 35 or not review_supply:
        return "Tier 3 - Watchlist", 3
    return "Tier 4 - Defer", 4


def expected_priority_watchlist(score: NicheRadarScore) -> str:
    nps_va = score.nps_va or 0
    reachability = score.reachability_score or 0
    gate = expected_supply_gate(score)
    if gate == "tier1_ready" and reachability >= 60 and 65 <= nps_va < 75:
        return "Tier 1 Candidate"
    if gate == "review_ready" and reachability >= 60 and 65 <= nps_va < 75:
        return "Tier 2 - Priority Watchlist"
    return ""


def vendor_review_missing_fields(vendor: Vendor, profile: VendorIntelligenceProfile) -> list[str]:
    checks = [
        ("product category", text_present(vendor.cyber_category)),
        ("target segment", text_present(vendor.target_market)),
        ("pricing signal", text_present(vendor.pricing_model)),
        ("compliance coverage", text_present(vendor.compliance_certifications)),
        ("website/source anchor", bool(normalize_domain(vendor.company_website))),
        ("match variables", (profile.total_match_count or 0) > 0),
    ]
    return [name for name, passed in checks if not passed]


def check_core_data(session) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    checked_rows = (
        session.query(NicheMarket).count()
        + session.query(PainPoint).count()
        + session.query(Vendor).count()
        + session.query(VendorPainPointMap).count()
    )

    for niche in session.query(NicheMarket).all():
        for field_name in ("industry", "niche_name", "geography"):
            if not text_present(getattr(niche, field_name)):
                add_finding(
                    findings,
                    "core",
                    "critical",
                    "required_niche_identity",
                    "niche_market",
                    niche.id,
                    f"Missing required niche identity field: {field_name}.",
                    field_name,
                )
        for field_name in ("demand_score", "outbound_score", "priority_score"):
            value = getattr(niche, field_name)
            if not in_range(value, 0, 100):
                add_finding(
                    findings,
                    "core",
                    "critical",
                    "score_range_0_100",
                    "niche_market",
                    niche.id,
                    f"{field_name} must be between 0 and 100.",
                    field_name,
                    value,
                )
        for field_name in (
            "attack_records",
            "digitalization_level",
            "reachability",
            "buyer_role_clarity",
            "procurement_friction",
            "time_to_value",
            "budget_proxy",
            "offer_fit",
        ):
            value = getattr(niche, field_name)
            if not in_range(value, 0, 10):
                add_finding(
                    findings,
                    "core",
                    "warning",
                    "score_range_0_10",
                    "niche_market",
                    niche.id,
                    f"{field_name} should be between 0 and 10.",
                    field_name,
                    value,
                )

    duplicates = (
        session.query(NicheMarket.niche_name, NicheMarket.geography, func.count(NicheMarket.id))
        .group_by(NicheMarket.niche_name, NicheMarket.geography)
        .having(func.count(NicheMarket.id) > 1)
        .all()
    )
    for name, geography, count in duplicates:
        add_finding(
            findings,
            "core",
            "critical",
            "duplicate_niche_identity",
            "niche_market",
            None,
            f"Duplicate niche identity found for {name} / {geography}: {count} rows.",
            "niche_name,geography",
            f"{name}/{geography}",
        )

    for pain_point in session.query(PainPoint).all():
        if pain_point.niche_market_id is None:
            add_finding(
                findings,
                "core",
                "critical",
                "pain_point_parent_required",
                "pain_point",
                pain_point.id,
                "Pain point is missing niche_market_id.",
                "niche_market_id",
            )
        if pain_point.pain_point_rank is not None and pain_point.pain_point_rank < 1:
            add_finding(
                findings,
                "core",
                "warning",
                "pain_point_rank_range",
                "pain_point",
                pain_point.id,
                "Pain point rank should be positive.",
                "pain_point_rank",
                pain_point.pain_point_rank,
            )
        if not in_range(pain_point.severity_score, 0, 10):
            add_finding(
                findings,
                "core",
                "warning",
                "pain_point_severity_range",
                "pain_point",
                pain_point.id,
                "Pain point severity should be between 0 and 10.",
                "severity_score",
                pain_point.severity_score,
            )

    valid_vendor_ids = {row.id for row in session.query(Vendor.id).all()}
    valid_pain_point_ids = {row.id for row in session.query(PainPoint.id).all()}
    for match in session.query(VendorPainPointMap).all():
        if match.vendor_id not in valid_vendor_ids or match.pain_point_id not in valid_pain_point_ids:
            add_finding(
                findings,
                "core",
                "critical",
                "vendor_match_foreign_key",
                "vendor_pain_point_map",
                match.id,
                "Vendor-pain-point match references a missing vendor or pain point.",
            )
        if not in_range(match.match_score, 0, 1):
            add_finding(
                findings,
                "core",
                "critical",
                "vendor_match_score_range",
                "vendor_pain_point_map",
                match.id,
                "Vendor match score must be between 0 and 1.",
                "match_score",
                match.match_score,
            )

    return findings, checked_rows


def check_niche_radar(session) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    scores = session.query(NicheRadarScore).all()
    checked_rows = len(scores)
    expected_score_count = session.query(NicheMarket).filter(NicheMarket.priority_score != None).count()
    if len(scores) != expected_score_count:
        add_finding(
            findings,
            "niche_radar",
            "critical",
            "score_coverage",
            "niche_radar_score",
            None,
            f"NicheRadar has {len(scores)} scores but {expected_score_count} researched niches.",
            "score_count",
            len(scores),
        )

    for score in scores:
        for field_name in ("vulnerability_score", "payability_score", "reachability_score", "nps_va"):
            value = getattr(score, field_name)
            if not in_range(value, 0, 100):
                add_finding(
                    findings,
                    "niche_radar",
                    "critical",
                    "score_range_0_100",
                    "niche_radar_score",
                    score.id,
                    f"{field_name} must be between 0 and 100.",
                    field_name,
                    value,
                )

        gate = expected_supply_gate(score)
        if score.vendor_supply_gate_status != gate:
            add_finding(
                findings,
                "niche_radar",
                "critical",
                "vendor_supply_gate_consistency",
                "niche_radar_score",
                score.id,
                f"Expected vendor supply gate {gate}, found {score.vendor_supply_gate_status}.",
                "vendor_supply_gate_status",
                score.vendor_supply_gate_status,
            )

        tier, rank = expected_refined_tier(score)
        if score.refined_tier != tier or score.refined_tier_rank != rank:
            add_finding(
                findings,
                "niche_radar",
                "critical",
                "tier_rule_consistency",
                "niche_radar_score",
                score.id,
                f"Expected {tier} / rank {rank}, found {score.refined_tier} / {score.refined_tier_rank}.",
                "refined_tier",
                score.refined_tier,
            )

        watchlist = expected_priority_watchlist(score)
        if (score.priority_watchlist_status or "") != watchlist:
            add_finding(
                findings,
                "niche_radar",
                "warning",
                "priority_watchlist_consistency",
                "niche_radar_score",
                score.id,
                f"Expected priority watchlist status {watchlist!r}, found {(score.priority_watchlist_status or '')!r}.",
                "priority_watchlist_status",
                score.priority_watchlist_status,
            )

        if not score.variables:
            add_finding(
                findings,
                "niche_radar",
                "critical",
                "niche_radar_variables_present",
                "niche_radar_score",
                score.id,
                "NicheRadar score has no provenance variable rows.",
            )

    return findings, checked_rows


def check_vendor_scope(session) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    profiles = session.query(VendorIntelligenceProfile).all()
    checked_rows = len(profiles)
    vendor_count = session.query(Vendor).count()
    if len(profiles) != vendor_count:
        add_finding(
            findings,
            "vendor_scope",
            "critical",
            "profile_coverage",
            "vendor_intelligence_profile",
            None,
            f"VendorScope has {len(profiles)} profiles but {vendor_count} vendors.",
            "profile_count",
            len(profiles),
        )

    for profile in profiles:
        vendor = profile.vendor
        if not vendor:
            add_finding(
                findings,
                "vendor_scope",
                "critical",
                "profile_vendor_required",
                "vendor_intelligence_profile",
                profile.id,
                "Vendor intelligence profile is missing its parent vendor.",
                "vendor_id",
                profile.vendor_id,
            )
            continue

        for field_name in ("trust_score", "fit_score", "operational_score", "vendor_quality_score"):
            value = getattr(profile, field_name)
            if not in_range(value, 0, 100):
                add_finding(
                    findings,
                    "vendor_scope",
                    "critical",
                    "vendor_score_range_0_100",
                    "vendor_intelligence_profile",
                    profile.id,
                    f"{field_name} must be between 0 and 100.",
                    field_name,
                    value,
                )

        missing = vendor_review_missing_fields(vendor, profile)
        if profile.readiness_status in {"Review Ready", "Marketplace Ready"} and missing:
            add_finding(
                findings,
                "vendor_scope",
                "critical",
                "review_ready_core_fields",
                "vendor_intelligence_profile",
                profile.id,
                f"Vendor marked {profile.readiness_status} but is missing core fields: {', '.join(missing)}.",
                "readiness_status",
                profile.readiness_status,
            )

        if profile.readiness_status == "Submission Incomplete" and not missing:
            add_finding(
                findings,
                "vendor_scope",
                "info",
                "submission_incomplete_review",
                "vendor_intelligence_profile",
                profile.id,
                "Vendor has core fields but remains Submission Incomplete; review scoring gates.",
                "readiness_status",
                profile.readiness_status,
            )

        if not profile.variables:
            add_finding(
                findings,
                "vendor_scope",
                "critical",
                "vendor_variables_present",
                "vendor_intelligence_profile",
                profile.id,
                "Vendor intelligence profile has no provenance variable rows.",
            )

    return findings, checked_rows


def check_account_leads(session) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    leads = session.query(AccountLead).all()
    checked_rows = len(leads)
    valid_niche_ids = {row.id for row in session.query(NicheMarket.id).all()}
    seen_ids = set()

    for lead in leads:
        if not text_present(lead.account_canonical_id):
            add_finding(
                findings,
                "account_leads",
                "critical",
                "account_canonical_id_required",
                "account_lead",
                lead.id,
                "Account lead is missing account_canonical_id.",
                "account_canonical_id",
            )
        elif lead.account_canonical_id in seen_ids:
            add_finding(
                findings,
                "account_leads",
                "critical",
                "duplicate_account_canonical_id",
                "account_lead",
                lead.id,
                "Duplicate account_canonical_id found.",
                "account_canonical_id",
                lead.account_canonical_id,
            )
        seen_ids.add(lead.account_canonical_id)

        if lead.niche_market_id and lead.niche_market_id not in valid_niche_ids:
            add_finding(
                findings,
                "account_leads",
                "critical",
                "account_niche_fk",
                "account_lead",
                lead.id,
                "Account lead references a missing niche market.",
                "niche_market_id",
                lead.niche_market_id,
            )

        if not text_present(lead.state):
            add_finding(
                findings,
                "account_leads",
                "warning",
                "account_state_required",
                "account_lead",
                lead.id,
                "Account lead should include a state for per-state discovery/routing.",
                "state",
            )

        if not in_range(lead.lead_score, 0, 100):
            add_finding(
                findings,
                "account_leads",
                "critical",
                "lead_score_range_0_100",
                "account_lead",
                lead.id,
                "Lead score must be between 0 and 100.",
                "lead_score",
                lead.lead_score,
            )

        if lead.lead_status == DISCOVERY_PENDING:
            if text_present(lead.company_legal_name):
                add_finding(
                    findings,
                    "account_leads",
                    "warning",
                    "discovery_pending_company_name",
                    "account_lead",
                    lead.id,
                    "Discovery Pending rows should not look like verified company records.",
                    "company_legal_name",
                    lead.company_legal_name,
                )
            continue

        if not text_present(lead.company_legal_name):
            add_finding(
                findings,
                "account_leads",
                "critical",
                "company_legal_name_required",
                "account_lead",
                lead.id,
                "Non-placeholder account lead is missing company_legal_name.",
                "company_legal_name",
            )

        if lead.lead_status == CONTACT_IDENTIFIED and not (
            text_present(lead.email) or text_present(lead.linkedin_url) or text_present(lead.phone)
        ):
            add_finding(
                findings,
                "account_leads",
                "warning",
                "contact_identified_channel_missing",
                "account_lead",
                lead.id,
                "Contact Identified row needs email, LinkedIn, or phone before it can become outreach-ready.",
            )

        if lead.lead_status in OUTREACH_READY_STATUSES:
            if not text_present(lead.decision_maker_title):
                add_finding(
                    findings,
                    "account_leads",
                    "critical",
                    "hot_lead_persona_required",
                    "account_lead",
                    lead.id,
                    "Hot/On-fire lead is missing decision_maker_title.",
                    "decision_maker_title",
                )
            if not (text_present(lead.email) or text_present(lead.linkedin_url) or text_present(lead.phone)):
                add_finding(
                    findings,
                    "account_leads",
                    "critical",
                    "hot_lead_contact_required",
                    "account_lead",
                    lead.id,
                    "Hot/On-fire lead needs at least one verified contact channel.",
                )

    return findings, checked_rows


def summarize_findings(findings: list[Finding], checked_rows: int) -> dict:
    critical = sum(1 for finding in findings if finding.severity == "critical")
    warning = sum(1 for finding in findings if finding.severity == "warning")
    info = sum(1 for finding in findings if finding.severity == "info")
    penalty = sum(SEVERITY_WEIGHT.get(finding.severity, 0) for finding in findings)
    quality_score = round(max(0.0, 100.0 - penalty), 2)
    status = "fail" if critical else "review" if warning else "pass"
    return {
        "status": status,
        "quality_score": quality_score,
        "critical_count": critical,
        "warning_count": warning,
        "info_count": info,
        "checked_row_count": checked_rows,
    }


def save_run(session, target: str, findings: list[Finding], checked_rows: int) -> DataQualityRun:
    summary = summarize_findings(findings, checked_rows)
    run = DataQualityRun(
        target=target,
        status=summary["status"],
        quality_score=summary["quality_score"],
        critical_count=summary["critical_count"],
        warning_count=summary["warning_count"],
        info_count=summary["info_count"],
        checked_row_count=summary["checked_row_count"],
        summary_json=json.dumps(summary, sort_keys=True),
    )
    session.add(run)
    session.flush()

    for finding in findings:
        session.add(DataQualityFinding(
            run_id=run.id,
            target=finding.target,
            severity=finding.severity,
            check_name=finding.check_name,
            entity_type=finding.entity_type,
            entity_id=finding.entity_id,
            field_name=finding.field_name,
            observed_value=finding.observed_value,
            message=finding.message,
        ))
    session.commit()
    return run


def run_data_quality(target: str = "all") -> dict:
    if target not in VALID_TARGETS:
        raise ValueError(f"Unsupported target: {target}")

    session = get_session()
    try:
        checks = []
        if target in {"all", "core"}:
            checks.append(("core", check_core_data))
        if target in {"all", "vendor_scope"}:
            checks.append(("vendor_scope", check_vendor_scope))
        if target in {"all", "niche_radar"}:
            checks.append(("niche_radar", check_niche_radar))
        if target in {"all", "account_leads"}:
            checks.append(("account_leads", check_account_leads))

        all_findings: list[Finding] = []
        checked_rows = 0
        per_target = {}
        for target_name, check in checks:
            findings, rows = check(session)
            all_findings.extend(findings)
            checked_rows += rows
            per_target[target_name] = summarize_findings(findings, rows)

        run = save_run(session, target, all_findings, checked_rows)
        summary = summarize_findings(all_findings, checked_rows)
        summary.update({
            "run_id": run.id,
            "target": target,
            "per_target": per_target,
        })
        return summary
    finally:
        session.close()


def latest_findings(run_id: int) -> list[dict]:
    session = get_session()
    try:
        rows = (
            session.query(DataQualityFinding)
            .filter_by(run_id=run_id)
            .order_by(DataQualityFinding.severity, DataQualityFinding.target, DataQualityFinding.check_name)
            .all()
        )
        return [
            {
                "run_id": row.run_id,
                "target": row.target,
                "severity": row.severity,
                "check_name": row.check_name,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "field_name": row.field_name,
                "observed_value": row.observed_value,
                "message": row.message,
            }
            for row in rows
        ]
    finally:
        session.close()


def save_findings_csv(run_id: int, output_path: Optional[str] = None) -> str:
    rows = latest_findings(run_id)
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)
    if not output_path:
        output_path = os.path.join(
            output_dir,
            f"data_quality_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )

    fieldnames = [
        "run_id",
        "target",
        "severity",
        "check_name",
        "entity_type",
        "entity_id",
        "field_name",
        "observed_value",
        "message",
    ]
    with open(output_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loopa data quality gates.")
    parser.add_argument("--target", choices=sorted(VALID_TARGETS), default="all")
    parser.add_argument("--output", help="Optional CSV output path for findings")
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()

    summary = run_data_quality(args.target)
    print("Data quality run complete")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if not args.skip_export:
        path = save_findings_csv(summary["run_id"], args.output)
        print(f"Data quality findings saved: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
