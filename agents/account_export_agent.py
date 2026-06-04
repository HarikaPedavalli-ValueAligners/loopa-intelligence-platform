# agents/account_export_agent.py
# Phase 1 pilot for NicheRadar account-level exports. This creates a
# source-ready account discovery queue for high-priority niches without
# fabricating company or contact records before external sources are connected.

import argparse
import csv
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.data_quality_agent import run_data_quality
from database.db_manager import get_session
from database.schema import AccountLead, NicheMarket, NicheRadarScore


DEFAULT_STATES = ["CA", "TX", "NY"]
DISCOVERY_STATUS = "Discovery Pending"


def cta_url(account_canonical_id: str, niche: NicheMarket, track: str) -> str:
    niche_slug = str(niche.niche_name or niche.id).lower().replace(" ", "-")
    return (
        "https://valuealigners.com/start"
        f"?utm_source=outbound&utm_medium=account_discovery"
        f"&utm_campaign={niche_slug}"
        f"&utm_content={track.lower().replace(' ', '_')}"
        f"&aid={account_canonical_id}"
    )


def recommended_track(score: NicheRadarScore) -> str:
    if score.priority_watchlist_status == "Tier 1 Candidate":
        return "Tier 1 Candidate Discovery"
    if score.priority_watchlist_status == "Tier 2 - Priority Watchlist":
        return "Priority Watchlist Discovery"
    return "NicheRadar Discovery"


def candidate_query(session):
    return (
        session.query(NicheRadarScore, NicheMarket)
        .join(NicheMarket, NicheMarket.id == NicheRadarScore.niche_market_id)
        .filter(NicheRadarScore.priority_watchlist_status.in_([
            "Tier 1 Candidate",
            "Tier 2 - Priority Watchlist",
        ]))
        .order_by(
            NicheRadarScore.priority_watchlist_status.asc(),
            NicheRadarScore.nps_va.desc(),
        )
    )


def seed_account_discovery_pilot(
    niche_limit: int = 3,
    states: Optional[list[str]] = None,
) -> dict:
    """Creates source-ready discovery rows for selected niche-state pairs."""
    states = states or DEFAULT_STATES
    session = get_session()
    try:
        candidates = candidate_query(session).limit(niche_limit).all()
        created = 0
        updated = 0

        for score, niche in candidates:
            track = recommended_track(score)
            for state in states:
                canonical_id = f"discovery::{niche.id}::{state.lower()}"
                lead = session.query(AccountLead).filter_by(
                    account_canonical_id=canonical_id,
                ).first()
                if lead:
                    updated += 1
                else:
                    lead = AccountLead(account_canonical_id=canonical_id)
                    session.add(lead)
                    created += 1

                lead.niche_market_id = niche.id
                lead.company_legal_name = ""
                lead.state = state
                lead.lead_score = score.nps_va
                lead.lead_status = DISCOVERY_STATUS
                lead.recommended_track = track
                lead.next_action = (
                    "Collect source-verified companies for this niche/state from "
                    "approved sources before outreach."
                )
                lead.cta_url = cta_url(canonical_id, niche, track)
                lead.source_summary = (
                    "NicheRadar Phase 1 discovery queue seed; not a discovered "
                    "company record yet."
                )
                lead.last_updated = datetime.now()

        session.commit()
        return {
            "candidate_niches": len(candidates),
            "states": len(states),
            "created": created,
            "updated": updated,
            "account_leads": session.query(AccountLead).count(),
        }
    finally:
        session.close()


def build_account_export_rows(lead_status: Optional[str] = None) -> list[dict]:
    session = get_session()
    try:
        rows = []
        query = (
            session.query(AccountLead, NicheMarket, NicheRadarScore)
            .outerjoin(NicheMarket, NicheMarket.id == AccountLead.niche_market_id)
            .outerjoin(NicheRadarScore, NicheRadarScore.niche_market_id == NicheMarket.id)
        )
        if lead_status:
            query = query.filter(AccountLead.lead_status == lead_status)
        results = query.order_by(AccountLead.lead_score.desc(), AccountLead.state).all()
        for lead, niche, score in results:
            rows.append({
                "account_canonical_id": lead.account_canonical_id,
                "is_discovery_placeholder": lead.lead_status == DISCOVERY_STATUS,
                "company_legal_name": lead.company_legal_name,
                "dba_names": lead.dba_names,
                "state": lead.state,
                "headquarters_address": lead.headquarters_address,
                "employee_count_estimated": lead.employee_count_estimated,
                "revenue_estimated_usd": lead.revenue_estimated_usd,
                "years_in_business": lead.years_in_business,
                "decision_maker_name": lead.decision_maker_name,
                "decision_maker_title": lead.decision_maker_title,
                "email": lead.email,
                "linkedin_url": lead.linkedin_url,
                "phone": lead.phone,
                "recent_trigger_type": lead.recent_trigger_type,
                "recent_trigger_date": lead.recent_trigger_date,
                "recent_trigger_summary": lead.recent_trigger_summary,
                "lead_score": lead.lead_score,
                "lead_status": lead.lead_status,
                "recommended_track": lead.recommended_track,
                "assigned_owner": lead.assigned_owner,
                "next_action": lead.next_action,
                "next_action_due": lead.next_action_due,
                "cta_url": lead.cta_url,
                "last_engagement_at": lead.last_engagement_at,
                "niche_market_id": niche.id if niche else "",
                "niche_market": niche.niche_name if niche else "",
                "naics_code": niche.naics_code if niche else "",
                "priority_watchlist_status": score.priority_watchlist_status if score else "",
                "nps_va": score.nps_va if score else "",
                "vendor_supply_gate_status": score.vendor_supply_gate_status if score else "",
                "source_summary": lead.source_summary,
                "last_updated": lead.last_updated,
            })
        return rows
    finally:
        session.close()


def annotate_rows_with_dq(rows: list[dict], dq_summary: Optional[dict]) -> list[dict]:
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


def save_account_export_csv(rows: list[dict], output_path: Optional[str] = None) -> str:
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)
    if not output_path:
        output_path = os.path.join(
            output_dir,
            f"account_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )

    fieldnames = list(rows[0].keys()) if rows else [
        "account_canonical_id",
        "is_discovery_placeholder",
        "company_legal_name",
        "state",
        "lead_score",
        "lead_status",
        "recommended_track",
        "niche_market",
        "nps_va",
    ]
    with open(output_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed and export NicheRadar account discovery pilot rows.")
    parser.add_argument("--niche-limit", type=int, default=3, help="Number of watchlist niches to seed")
    parser.add_argument("--states", default=",".join(DEFAULT_STATES), help="Comma-separated state list")
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--lead-status", help="Only export account rows with this lead status")
    parser.add_argument("--skip-seed", action="store_true", help="Export existing account rows only")
    parser.add_argument("--skip-export", action="store_true", help="Seed only, do not create CSV export")
    parser.add_argument("--skip-dq", action="store_true", help="Skip account Data Quality gate")
    args = parser.parse_args()

    states = [state.strip().upper() for state in args.states.split(",") if state.strip()]
    if not args.skip_seed:
        summary = seed_account_discovery_pilot(args.niche_limit, states)
        print("Account discovery pilot seed complete")
        for key, value in summary.items():
            print(f"{key}: {value}")

    dq_summary = None
    if args.skip_dq:
        print("Account Data Quality gate skipped by request.")
    else:
        dq_summary = run_data_quality("account_leads")
        print(
            "Account Data Quality: "
            f"{dq_summary['status']} "
            f"(run_id={dq_summary['run_id']}, "
            f"critical={dq_summary['critical_count']}, "
            f"warnings={dq_summary['warning_count']})"
        )
        if dq_summary["critical_count"]:
            print("Account export blocked because Data Quality found critical issues.")
            return 1

    if not args.skip_export:
        rows = annotate_rows_with_dq(build_account_export_rows(args.lead_status), dq_summary)
        path = save_account_export_csv(rows, args.output)
        print(f"Account export saved: {path}")
        print(f"Rows: {len(rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
