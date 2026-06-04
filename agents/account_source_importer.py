# agents/account_source_importer.py
# Imports source-verified account CSVs into account_leads. This is the first
# connector shape for Apollo, ZoomInfo, D&B, state registry, or generic CSV
# exports before direct API connectors are approved.

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.account_export_agent import cta_url
from agents.data_quality_agent import run_data_quality
from database.db_manager import get_session
from database.schema import AccountLead, NicheMarket, NicheRadarScore


TEMPLATE_FIELDS = [
    "niche_market_id",
    "niche_market",
    "company_legal_name",
    "dba_names",
    "state",
    "headquarters_address",
    "employee_count_estimated",
    "revenue_estimated_usd",
    "years_in_business",
    "decision_maker_name",
    "decision_maker_title",
    "email",
    "linkedin_url",
    "phone",
    "recent_trigger_type",
    "recent_trigger_date",
    "recent_trigger_summary",
    "lead_score",
    "lead_status",
    "recommended_track",
    "assigned_owner",
    "next_action",
    "next_action_due",
    "source_url",
]

ACCOUNT_TARGET_STATUS = "Account Target"
CONTACT_IDENTIFIED_STATUS = "Contact Identified"
OUTREACH_READY_STATUS = "Outreach Ready"
AUTO_CONTACT_STATUS = "__auto_contact_status__"

US_STATE_ABBREVIATIONS = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}

FIELD_ALIASES = {
    "company_legal_name": ["company_legal_name", "company", "company_name", "organization", "account_name", "name"],
    "dba_names": ["dba_names", "dba", "doing_business_as"],
    "state": ["state", "region", "hq", "hq_state", "headquarters_state", "company_state"],
    "headquarters_address": ["headquarters_address", "address", "hq_address", "street_address"],
    "employee_count_estimated": ["employee_count_estimated", "employees", "employee_count", "company_size"],
    "revenue_estimated_usd": [
        "revenue_estimated_usd",
        "revenue",
        "annual_revenue",
        "revenue_range_in_usd",
        "revenue_in_000s_usd",
    ],
    "years_in_business": ["years_in_business", "company_age", "years_active"],
    "decision_maker_name": ["decision_maker_name", "contact_name", "person_name", "full_name", "contact_full_name"],
    "decision_maker_title": ["decision_maker_title", "title", "job_title", "contact_title"],
    "email": ["email", "work_email", "business_email"],
    "linkedin_url": ["linkedin_url", "linkedin", "person_linkedin", "contact_linkedin_url"],
    "phone": ["phone", "direct_phone", "direct_dial", "company_phone", "company_hq_phone", "phone_number"],
    "recent_trigger_type": ["recent_trigger_type", "trigger_type"],
    "recent_trigger_date": ["recent_trigger_date", "trigger_date"],
    "recent_trigger_summary": ["recent_trigger_summary", "trigger_summary", "trigger"],
    "lead_score": ["lead_score", "score", "account_score"],
    "lead_status": ["lead_status", "status"],
    "recommended_track": ["recommended_track", "track"],
    "assigned_owner": ["assigned_owner", "owner"],
    "next_action": ["next_action", "action"],
    "next_action_due": ["next_action_due", "due_date"],
    "niche_market_id": ["niche_market_id", "niche_id"],
    "niche_market": ["niche_market", "niche"],
    "source_url": ["source_url", "profile_url", "company_website", "company_domain", "website", "domain", "source"],
}


def clean(value) -> str:
    return str(value or "").strip()


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def coerce_int(value) -> Optional[int]:
    value = clean(value).replace(",", "").replace("$", "")
    if not value:
        return None
    range_value = parse_number_range(value)
    if range_value is not None:
        return int(range_value)
    try:
        return int(float(value))
    except ValueError:
        return None


def coerce_float(value) -> Optional[float]:
    value = clean(value)
    if not value:
        return None
    range_value = parse_money_range(value) or parse_number_range(value)
    if range_value is not None:
        return float(range_value)
    value = value.replace(",", "").replace("$", "")
    try:
        return float(value)
    except ValueError:
        return None


def normalize_state(value: str) -> str:
    state = clean(value).upper()
    if not state:
        return ""
    if "," in state:
        state = state.split(",")[-1].strip()
    if len(state) == 2:
        return state
    return US_STATE_ABBREVIATIONS.get(state, state)


def parse_number_range(value: str) -> Optional[float]:
    text = clean(value).replace(",", "")
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return sum(numbers[:2]) / 2


def parse_money_range(value: str) -> Optional[float]:
    text = clean(value).replace(",", "").upper()
    multiplier = 1.0
    if "B" in text:
        multiplier = 1_000_000_000.0
    elif "M" in text:
        multiplier = 1_000_000.0
    elif "K" in text:
        multiplier = 1_000.0
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0] * multiplier
    return (sum(numbers[:2]) / 2) * multiplier


def canonical_company_key(company_name: str, state: str, niche_id: Optional[int]) -> str:
    company_slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    state_slug = state.lower() or "unknown"
    niche_slug = str(niche_id or "unknown")
    return f"account::{state_slug}::{niche_slug}::{company_slug}"


def canonical_contact_key(
    company_name: str,
    state: str,
    niche_id: Optional[int],
    contact_name: str,
) -> str:
    company_slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    contact_slug = re.sub(r"[^a-z0-9]+", "-", contact_name.lower()).strip("-") or "unknown-contact"
    state_slug = state.lower() or "unknown"
    niche_slug = str(niche_id or "unknown")
    return f"contact::{state_slug}::{niche_slug}::{company_slug}::{contact_slug}"


def zoominfo_company_id(row: dict) -> str:
    normalized = {normalized_key(key): value for key, value in row.items()}
    value = clean(normalized.get("zoominfo_company_id"))
    if not value:
        return ""
    value = re.sub(r"\.0$", "", value)
    return re.sub(r"[^0-9A-Za-z_-]+", "", value)


def detect_field(row: dict, field_name: str):
    normalized = {normalized_key(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field_name]:
        key = normalized_key(alias)
        if key in normalized and clean(normalized[key]):
            return normalized[key]
    return ""


def detect_contact_name(row: dict) -> str:
    full_name = clean(detect_field(row, "decision_maker_name"))
    if full_name:
        return full_name
    normalized = {normalized_key(key): value for key, value in row.items()}
    first_name = clean(normalized.get("first_name"))
    last_name = clean(normalized.get("last_name"))
    return " ".join(part for part in [first_name, last_name] if part)


def resolve_niche(session, row: dict, default_niche_id: Optional[int] = None):
    niche_id = coerce_int(detect_field(row, "niche_market_id")) or default_niche_id
    if niche_id:
        niche = session.query(NicheMarket).filter_by(id=niche_id).first()
        if niche:
            return niche

    niche_name = clean(detect_field(row, "niche_market"))
    if niche_name:
        return session.query(NicheMarket).filter_by(niche_name=niche_name).first()
    return None


def default_lead_status(score: Optional[float]) -> str:
    if score is None:
        return "Cold"
    if score >= 85:
        return "On-fire"
    if score >= 70:
        return "Hot"
    if score >= 50:
        return "Warm"
    return "Cold"


def default_track(niche_score: Optional[NicheRadarScore]) -> str:
    if not niche_score:
        return "Account Discovery"
    if niche_score.priority_watchlist_status == "Tier 1 Candidate":
        return "Tier 1 Candidate Account Enrichment"
    if niche_score.priority_watchlist_status == "Tier 2 - Priority Watchlist":
        return "Priority Watchlist Account Enrichment"
    return "NicheRadar Account Enrichment"


def parse_csv_date(value):
    value = clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def upsert_account_from_row(
    session,
    row: dict,
    source_type: str,
    default_niche_id: Optional[int] = None,
    default_lead_status_value: Optional[str] = None,
) -> str:
    niche = resolve_niche(session, row, default_niche_id)
    niche_score = None
    if niche:
        niche_score = session.query(NicheRadarScore).filter_by(niche_market_id=niche.id).first()

    company_name = clean(detect_field(row, "company_legal_name"))
    state = normalize_state(detect_field(row, "state"))
    decision_maker_name = detect_contact_name(row)
    if not company_name:
        raise ValueError("Missing company_legal_name/company field")
    if not state:
        raise ValueError(f"Missing state for {company_name}")

    lead_score = coerce_float(detect_field(row, "lead_score"))
    if lead_score is None and niche_score:
        lead_score = niche_score.nps_va

    zoominfo_id = zoominfo_company_id(row)
    import_as_contact = default_lead_status_value in {CONTACT_IDENTIFIED_STATUS, AUTO_CONTACT_STATUS}
    canonical_id = (
        clean(row.get("account_canonical_id"))
        or (f"zoominfo_company::{zoominfo_id}" if zoominfo_id else "")
        or (
            canonical_contact_key(
                company_name,
                state,
                niche.id if niche else default_niche_id,
                decision_maker_name,
            )
            if import_as_contact
            else ""
        )
        or canonical_company_key(
            company_name,
            state,
            niche.id if niche else default_niche_id,
        )
    )
    lead = session.query(AccountLead).filter_by(account_canonical_id=canonical_id).first()
    action = "updated" if lead else "created"
    if not lead:
        lead = AccountLead(account_canonical_id=canonical_id)
        session.add(lead)

    lead.niche_market_id = niche.id if niche else default_niche_id
    lead.company_legal_name = company_name
    lead.dba_names = clean(detect_field(row, "dba_names")) or None
    lead.state = state
    lead.headquarters_address = clean(detect_field(row, "headquarters_address")) or None
    lead.employee_count_estimated = coerce_int(detect_field(row, "employee_count_estimated"))
    lead.revenue_estimated_usd = coerce_float(detect_field(row, "revenue_estimated_usd"))
    lead.years_in_business = coerce_int(detect_field(row, "years_in_business"))
    lead.decision_maker_name = decision_maker_name or None
    lead.decision_maker_title = clean(detect_field(row, "decision_maker_title")) or None
    email = clean(detect_field(row, "email"))
    linkedin_url = clean(detect_field(row, "linkedin_url"))
    phone = clean(detect_field(row, "phone"))
    lead.email = email or None
    lead.linkedin_url = linkedin_url or None
    lead.phone = phone or None
    lead.recent_trigger_type = clean(detect_field(row, "recent_trigger_type")) or None
    lead.recent_trigger_date = parse_csv_date(detect_field(row, "recent_trigger_date"))
    lead.recent_trigger_summary = clean(detect_field(row, "recent_trigger_summary")) or None
    lead.lead_score = lead_score
    row_status = clean(detect_field(row, "lead_status"))
    if row_status:
        lead.lead_status = row_status
    elif default_lead_status_value == AUTO_CONTACT_STATUS:
        lead.lead_status = OUTREACH_READY_STATUS if (email or linkedin_url or phone) else CONTACT_IDENTIFIED_STATUS
    else:
        lead.lead_status = default_lead_status_value or default_lead_status(lead_score)
    lead.recommended_track = (
        clean(detect_field(row, "recommended_track"))
        or ("ZoomInfo Company Target" if lead.lead_status == ACCOUNT_TARGET_STATUS else "")
        or ("ZoomInfo Contact Seed" if lead.lead_status == CONTACT_IDENTIFIED_STATUS else "")
        or ("ZoomInfo Outreach Ready" if lead.lead_status == OUTREACH_READY_STATUS else "")
        or default_track(niche_score)
    )
    lead.assigned_owner = clean(detect_field(row, "assigned_owner")) or None
    lead.next_action = clean(detect_field(row, "next_action")) or "Review account enrichment quality before outreach."
    lead.next_action_due = parse_csv_date(detect_field(row, "next_action_due"))
    lead.cta_url = cta_url(canonical_id, niche, lead.recommended_track) if niche else None
    lead.source_summary = f"Imported from {source_type} CSV"
    source_url = clean(detect_field(row, "source_url"))
    if source_url:
        lead.source_summary = f"{lead.source_summary}: {source_url}"
    optional_context = optional_source_context(row)
    if optional_context:
        lead.source_summary = f"{lead.source_summary}; {optional_context}"
    lead.last_updated = datetime.now()
    return action


def optional_source_context(row: dict) -> str:
    parts = []
    normalized = {normalized_key(key): value for key, value in row.items()}
    for field_name in [
        "industry",
        "id",
        "priority",
        "tier",
        "category",
        "city",
        "country",
        "company_website",
        "linkedin_company_profile_url",
        "company_linkedin_url",
        "zoominfo_company_profile_url",
        "primary_industry",
        "primary_sub_industry",
        "all_industries",
        "all_sub_industries",
        "naics_code",
        "sic_code",
        "company_description",
        "technologies_used",
        "target_industries",
        "services",
        "compliance_tags",
        "data_freshness",
        "email_confidence",
        "verified_email",
        "verified_phone",
        "email_subject",
        "email_body",
        "linkedin_message",
        "segment",
        "icp_track",
    ]:
        value = clean(normalized.get(field_name))
        if value:
            parts.append(f"{field_name}={value}")
    return "; ".join(parts)


def import_account_csv(
    path: str,
    source_type: str = "generic_csv",
    default_niche_id: Optional[int] = None,
    default_lead_status_value: Optional[str] = None,
) -> dict:
    session = get_session()
    created = 0
    updated = 0
    skipped = 0
    errors = []
    try:
        with open(path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for index, row in enumerate(reader, start=2):
                try:
                    action = upsert_account_from_row(
                        session,
                        row,
                        source_type,
                        default_niche_id,
                        default_lead_status_value,
                    )
                    if action == "created":
                        created += 1
                    else:
                        updated += 1
                except ValueError as exc:
                    skipped += 1
                    errors.append(f"row {index}: {exc}")
        session.commit()
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "account_leads": session.query(AccountLead).count(),
        }
    finally:
        session.close()


def write_template(path: str) -> str:
    with open(path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Import account source CSVs into account_leads.")
    parser.add_argument("--input", help="Input CSV path")
    parser.add_argument("--source-type", default="generic_csv", help="Source label, e.g. apollo, zoominfo, state_registry")
    parser.add_argument("--default-niche-id", type=int, help="Niche ID to apply when rows do not include one")
    parser.add_argument("--default-lead-status", help="Default lead status when rows do not include one")
    parser.add_argument("--company-target-mode", action="store_true", help="Import rows as company-level Account Target records")
    parser.add_argument("--contact-seed-mode", action="store_true", help="Import rows as contact-level Contact Identified records")
    parser.add_argument("--contact-enrichment-mode", action="store_true", help="Import contacts and auto-promote rows with email, phone, or LinkedIn to Outreach Ready")
    parser.add_argument("--write-template", help="Write an empty import template CSV")
    parser.add_argument("--skip-dq", action="store_true", help="Skip account Data Quality gate")
    args = parser.parse_args()

    if args.write_template:
        path = write_template(args.write_template)
        print(f"Account import template saved: {path}")
        return 0

    if not args.input:
        parser.error("--input is required unless --write-template is used")

    default_status = args.default_lead_status
    if args.company_target_mode:
        default_status = ACCOUNT_TARGET_STATUS
    if args.contact_seed_mode:
        default_status = CONTACT_IDENTIFIED_STATUS
    if args.contact_enrichment_mode:
        default_status = AUTO_CONTACT_STATUS
    summary = import_account_csv(args.input, args.source_type, args.default_niche_id, default_status)
    print("Account source import complete")
    for key, value in summary.items():
        if key == "errors":
            continue
        print(f"{key}: {value}")
    for error in summary["errors"][:10]:
        print(f"error: {error}")

    if not args.skip_dq:
        dq_summary = run_data_quality("account_leads")
        print(
            "Account Data Quality: "
            f"{dq_summary['status']} "
            f"(run_id={dq_summary['run_id']}, "
            f"critical={dq_summary['critical_count']}, "
            f"warnings={dq_summary['warning_count']})"
        )
        if dq_summary["critical_count"]:
            print("Account import requires review because Data Quality found critical issues.")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
