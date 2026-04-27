# utils/report_generator.py
# Generates the final sales intelligence report.
# Pulls everything from the database and produces
# a clean, actionable report for the sales team.
# Updated to include Demand Score and Outbound Score
# per Hamid's two-layer scoring model.

import os
import sys
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    NicheMarket, PainPoint, Vendor, VendorPainPointMap
)


# ------------------------------------------------------------
# Data Retrieval
# ------------------------------------------------------------

def get_top_niche_markets(limit: int = 20) -> list:
    """Returns top niche markets sorted by priority score."""

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
                "geography"             : n.geography,
                "naics_code"            : n.naics_code,
                "demand_score"          : n.demand_score,
                "outbound_score"        : n.outbound_score,
                "priority_score"        : n.priority_score,
                "priority_tier"         : n.priority_tier,
                "icp_headcount_min"     : n.icp_headcount_min,
                "icp_headcount_max"     : n.icp_headcount_max,
                "icp_description"       : n.icp_description,
                "common_cyber_risks"    : n.common_cyber_risks,
                "attack_records"        : n.attack_records,
                "cagr"                  : n.cagr,
                "smb_percentage"        : n.smb_percentage,
                "reachability"          : n.reachability,
                "buyer_role_clarity"    : n.buyer_role_clarity,
                "procurement_friction"  : n.procurement_friction,
                "offer_fit"             : n.offer_fit,
                "compliance_audit_drivers" : n.compliance_audit_drivers,
                "compliance_audit_notes"   : n.compliance_audit_notes,
                "assumptions_notes"     : n.assumptions_notes,
                "last_updated"          : str(n.last_updated)
            }
            for n in niches
        ]

    finally:
        session.close()


def get_pain_points_for_niche(niche_market_id: int) -> list:
    """Returns pain points for a specific niche market."""

    session = get_session()

    try:
        pain_points = session.query(PainPoint)\
            .filter_by(niche_market_id=niche_market_id)\
            .order_by(PainPoint.pain_point_rank)\
            .all()

        return [
            {
                "id"                : pp.id,
                "pain_point_name"   : pp.pain_point_name,
                "pain_point_rank"   : pp.pain_point_rank,
                "cyber_category"    : pp.cyber_category,
                "cyber_subcategory" : pp.cyber_subcategory,
                "severity_score"    : pp.severity_score,
                "growth_rate"       : pp.growth_rate,
                "description"       : pp.description
            }
            for pp in pain_points
        ]

    finally:
        session.close()


def get_vendor_matches_for_pain_point(pain_point_id: int) -> list:
    """Returns top vendor matches for a specific pain point."""

    session = get_session()

    try:
        matches = session.query(VendorPainPointMap)\
            .filter_by(pain_point_id=pain_point_id)\
            .order_by(VendorPainPointMap.match_score.desc())\
            .limit(3)\
            .all()

        results = []

        for match in matches:
            vendor = session.query(Vendor)\
                .filter_by(id=match.vendor_id)\
                .first()

            if vendor:
                results.append({
                    "vendor_name"       : vendor.vendor_name,
                    "cyber_category"    : vendor.cyber_category,
                    "target_market"     : vendor.target_market,
                    "customer_rating"   : vendor.customer_rating,
                    "match_score"       : match.match_score,
                    "confidence_label"  : match.confidence_label,
                    "match_type"        : match.match_type,
                    "matched_terms"     : match.matched_terms,
                    "is_fallback"       : bool(match.is_fallback),
                    "notes"             : match.notes
                })

        return results

    finally:
        session.close()


# ------------------------------------------------------------
# Report Builder
# ------------------------------------------------------------

def build_report(limit: int = 20) -> dict:
    """
    Builds the full sales intelligence report.
    Combines niche markets, pain points, and vendor matches.
    Includes both Demand and Outbound scores per Hamid's model.

    Args:
        limit: Number of top niche markets to include.

    Returns:
        Complete report dictionary.
    """

    report = {
        "title"         : "Loopa Intelligence — Sales Report",
        "generated_at"  : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_niches"  : limit,
        "scoring_model" : {
            "demand_weights"    : "Attack Records(0.25) + Digitalization(0.20) + SME Revenue(0.15) + CAGR(0.15) - Cyber Readiness(0.20) + Industry Size(0.10) + SMB %(0.10) + Annual Loss(0.10)",
            "outbound_weights"  : "Reachability(0.35) + Buyer Clarity(0.20) - Procurement Friction(0.25) + Time to Value(0.10) + Vendor Sprawl(0.05) + Offer Fit(0.05)",
            "final_formula"     : "Priority Score = Demand Score x Outbound Score / 100",
            "tier_1"            : "Priority Score >= 70",
            "tier_2"            : "Priority Score 50-69.99",
            "tier_3"            : "Priority Score < 50"
        },
        "niches"        : []
    }

    niches = get_top_niche_markets(limit)

    for niche in niches:

        pain_points = get_pain_points_for_niche(niche["id"])

        for pp in pain_points:
            pp["vendor_matches"] = get_vendor_matches_for_pain_point(pp["id"])

        niche_entry = {
            "rank"                  : niches.index(niche) + 1,
            "industry"              : niche["industry"],
            "sub_industry"          : niche["sub_industry"],
            "sub_sub_industry"      : niche["sub_sub_industry"],
            "niche_name"            : niche["niche_name"],
            "geography"             : niche["geography"],
            "naics_code"            : niche["naics_code"],
            "scores"                : {
                "demand_score"      : niche["demand_score"],
                "outbound_score"    : niche["outbound_score"],
                "priority_score"    : niche["priority_score"],
                "priority_tier"     : niche["priority_tier"],
            },
            "key_metrics"           : {
                "attack_records"    : niche["attack_records"],
                "cagr"              : niche["cagr"],
                "smb_percentage"    : niche["smb_percentage"],
                "reachability"      : niche["reachability"],
                "buyer_role_clarity": niche["buyer_role_clarity"],
                "procurement_friction" : niche["procurement_friction"],
                "offer_fit"         : niche["offer_fit"],
            },
            "compliance"            : {
                "audit_required"    : niche["compliance_audit_drivers"],
                "notes"             : niche["compliance_audit_notes"],
            },
            "ideal_customer_profile" : {
                "headcount_min"     : niche["icp_headcount_min"],
                "headcount_max"     : niche["icp_headcount_max"],
                "description"       : niche["icp_description"],
            },
            "common_cyber_risks"    : niche["common_cyber_risks"],
            "pain_points"           : pain_points,
            "assumptions"           : niche["assumptions_notes"],
            "last_updated"          : niche["last_updated"]
        }

        report["niches"].append(niche_entry)

    return report


# ------------------------------------------------------------
# Display Report
# ------------------------------------------------------------

def display_report(report: dict) -> None:
    """Prints the sales report in a clean readable format."""

    print("\n" + "=" * 70)
    print(f"  {report['title']}")
    print(f"  Generated : {report['generated_at']}")
    print("=" * 70)

    for niche in report["niches"]:

        parts = [p for p in [
            niche["industry"],
            niche["sub_industry"],
            niche["sub_sub_industry"]
        ] if p]

        scores = niche["scores"]

        print(f"\n{'─' * 70}")
        print(
            f"  #{niche['rank']}  "
            f"[Tier {scores['priority_tier']}]  |  "
            f"{' > '.join(parts)}"
        )
        print(
            f"  Priority : {scores['priority_score']}  |  "
            f"Demand : {scores['demand_score']}  |  "
            f"Outbound : {scores['outbound_score']}"
        )
        print(f"{'─' * 70}")

        # Key metrics
        metrics = niche["key_metrics"]
        print(f"\n  Key Metrics:")
        print(f"    Attack Records       : {metrics['attack_records']} / 10")
        print(f"    CAGR                 : {metrics['cagr']}%")
        print(f"    SMB Percentage       : {metrics['smb_percentage']}%")
        print(f"    Reachability         : {metrics['reachability']} / 10")
        print(f"    Buyer Role Clarity   : {metrics['buyer_role_clarity']} / 10")
        print(f"    Procurement Friction : {metrics['procurement_friction']} / 10")
        print(f"    Offer Fit            : {metrics['offer_fit']} / 10")

        # Compliance
        compliance = niche["compliance"]
        print(f"\n  Compliance Audits : {compliance['audit_required']} — {compliance['notes']}")

        # ICP
        icp = niche["ideal_customer_profile"]
        print(f"\n  Ideal Customer Profile:")
        print(f"    Headcount  : {icp['headcount_min']} - {icp['headcount_max']} employees")
        print(f"    {icp['description']}")

        # Common risks
        print(f"\n  Common Cyber Risks : {niche['common_cyber_risks']}")

        # Pain points and vendor matches
        print(f"\n  Pain Points & Recommended Vendors:")

        for pp in niche["pain_points"]:
            print(f"\n    #{pp['pain_point_rank']} {pp['pain_point_name']}")
            print(f"       Category : {pp['cyber_category']} > {pp['cyber_subcategory']}")
            print(f"       Severity : {pp['severity_score']} / 10  |  "
                  f"Growth: {pp['growth_rate']}% annually")

            if pp["vendor_matches"]:
                print(f"       Top Vendors:")
                for v in pp["vendor_matches"]:
                    print(
                        f"         - {v['vendor_name']}  "
                        f"(Match: {v['match_score']}  |  "
                        f"Confidence: {v.get('confidence_label')}  |  "
                        f"Rating: {v['customer_rating']})"
                    )
                    print(f"           {v['notes']}")
            else:
                print(f"       Top Vendors: No matches found yet")

        # Assumptions
        if niche.get("assumptions"):
            print(f"\n  Assumptions : {niche['assumptions']}")

    print("\n" + "=" * 70)


# ------------------------------------------------------------
# Save Report
# ------------------------------------------------------------

def save_report(report: dict) -> str:
    """Saves the report as a JSON file with timestamp."""

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data"
    )

    filename    = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath    = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    return filepath


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":

    print("Generating Loopa Intelligence Sales Report...")

    report   = build_report(limit=20)
    display_report(report)

    filepath = save_report(report)
    print(f"\nReport saved: {filepath}")
