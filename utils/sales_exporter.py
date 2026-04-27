# utils/sales_exporter.py
# Exports sales-ready CSV rows for Apollo, ZoomInfo, or manual outreach.

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import NicheMarket, PainPoint, Vendor, VendorPainPointMap


def _parts(*values) -> str:
    return " > ".join(str(value) for value in values if value)


def _outreach_angle(niche: NicheMarket, pain_point: PainPoint = None) -> str:
    role = niche.primary_buyer_role or "cybersecurity or operations leadership"
    compliance = niche.likely_compliance_regimes or niche.compliance_audit_notes
    pain = pain_point.pain_point_name if pain_point else (niche.common_cyber_risks or "cyber risk")

    if compliance and compliance != "None auto-tagged":
        return f"Lead with {compliance} pressure and {pain}; target {role}."
    return f"Lead with industry-specific {pain}; target {role}."


def build_sales_rows(limit: int = 100, min_tier: int = 2, include_weak: bool = False) -> list:
    """Builds flattened sales rows from researched niches, pain points, and vendor matches."""
    session = get_session()

    try:
        query = (
            session.query(NicheMarket)
            .filter(NicheMarket.priority_score != None)
            .filter(NicheMarket.priority_tier <= min_tier)
            .order_by(NicheMarket.priority_score.desc())
            .limit(limit)
        )

        rows = []
        for niche in query.all():
            pain_points = (
                session.query(PainPoint)
                .filter_by(niche_market_id=niche.id)
                .order_by(PainPoint.pain_point_rank)
                .all()
            )

            if not pain_points:
                rows.append(_row_for(niche, None, None, None))
                continue

            for pain_point in pain_points:
                matches = (
                    session.query(VendorPainPointMap, Vendor)
                    .join(Vendor, Vendor.id == VendorPainPointMap.vendor_id)
                    .filter(VendorPainPointMap.pain_point_id == pain_point.id)
                    .order_by(VendorPainPointMap.match_score.desc())
                    .limit(3)
                    .all()
                )

                if not include_weak:
                    matches = [
                        pair for pair in matches
                        if pair[0].confidence_label in {"strong", "medium"}
                    ]

                if not matches:
                    rows.append(_row_for(niche, pain_point, None, None))
                    continue

                for match, vendor in matches:
                    rows.append(_row_for(niche, pain_point, match, vendor))

        return rows

    finally:
        session.close()


def _row_for(niche: NicheMarket, pain_point: PainPoint, match: VendorPainPointMap, vendor: Vendor) -> dict:
    return {
        "niche_market": niche.niche_name,
        "industry_path": _parts(
            niche.industry,
            niche.sub_industry,
            niche.sub_sub_industry,
            niche.sub_sub_sub_industry,
            niche.sub_sub_sub_sub_industry,
        ),
        "naics_code": niche.naics_code,
        "geography": niche.geography,
        "priority_tier": niche.priority_tier,
        "priority_score": niche.priority_score,
        "demand_score": niche.demand_score,
        "outbound_score": niche.outbound_score,
        "primary_buyer_role": niche.primary_buyer_role,
        "likely_compliance": niche.likely_compliance_regimes or niche.compliance_audit_notes,
        "conditional_compliance": niche.conditional_compliance_regimes,
        "recommended_cyber_themes": niche.recommended_cyber_themes or niche.common_cyber_risks,
        "pain_point_rank": pain_point.pain_point_rank if pain_point else "",
        "pain_point": pain_point.pain_point_name if pain_point else "",
        "pain_point_category": pain_point.cyber_category if pain_point else "",
        "pain_point_subcategory": pain_point.cyber_subcategory if pain_point else "",
        "pain_point_severity": pain_point.severity_score if pain_point else "",
        "vendor_name": vendor.vendor_name if vendor else "",
        "vendor_category": vendor.cyber_category if vendor else "",
        "vendor_target_market": vendor.target_market if vendor else "",
        "vendor_rating": vendor.customer_rating if vendor else "",
        "match_score": match.match_score if match else "",
        "match_confidence": match.confidence_label if match else "",
        "match_type": match.match_type if match else "",
        "matched_terms": match.matched_terms if match else "",
        "outreach_angle": _outreach_angle(niche, pain_point),
        "match_notes": match.notes if match else "",
        "last_updated": niche.last_updated,
    }


def save_sales_csv(rows: list, output_path: str = None) -> str:
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)

    if not output_path:
        output_path = os.path.join(
            output_dir,
            f"sales_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )

    fieldnames = list(rows[0].keys()) if rows else [
        "niche_market",
        "industry_path",
        "priority_tier",
        "priority_score",
        "pain_point",
        "vendor_name",
        "outreach_angle",
    ]

    with open(output_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Loopa sales-ready CSV.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of niches to export")
    parser.add_argument("--min-tier", type=int, default=2, choices=[1, 2, 3], help="Lowest priority tier to include")
    parser.add_argument("--include-weak", action="store_true", help="Include weak vendor matches")
    parser.add_argument("--output", help="Output CSV path")
    args = parser.parse_args()

    sales_rows = build_sales_rows(
        limit=args.limit,
        min_tier=args.min_tier,
        include_weak=args.include_weak,
    )
    path = save_sales_csv(sales_rows, args.output)
    print(f"Sales export saved: {path}")
    print(f"Rows: {len(sales_rows)}")
