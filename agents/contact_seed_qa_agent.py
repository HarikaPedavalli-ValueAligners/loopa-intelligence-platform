# agents/contact_seed_qa_agent.py
# Builds deterministic QA outputs for ZoomInfo contact seed files before
# contacts are promoted into outreach-ready account leads.

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.account_source_importer import clean, coerce_int, normalize_state


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

HIGH_SENIORITY_TERMS = [
    "ceo",
    "chief",
    "founder",
    "owner",
    "president",
    "cro",
    "coo",
    "cfo",
    "cto",
    "ciso",
]
MID_SENIORITY_TERMS = ["vp", "vice president", "virtual cio", "fractional cio", "vcio", "director"]
REGULATED_INDUSTRY_TERMS = [
    "healthcare",
    "medical",
    "dental",
    "dso",
    "senior living",
    "manufacturing",
    "finance",
    "financial",
    "legal",
    "government",
    "regulated",
]
COMPLIANCE_TERMS = [
    "hipaa",
    "cmmc",
    "nist",
    "soc",
    "soc 2",
    "pci",
    "finra",
    "gdpr",
    "sox",
    "nerc",
]
SERVICE_TERMS = [
    "managed it",
    "cybersecurity",
    "compliance",
    "risk",
    "vulnerability",
    "it consulting",
    "security",
    "vciso",
]


def normalized(value: str) -> str:
    return clean(value).lower()


def has_any(value: str, terms: list[str]) -> bool:
    text = normalized(value)
    return any(term in text for term in terms)


def parse_money(value: str) -> Optional[float]:
    text = clean(value).replace(",", "").replace("$", "").upper()
    if not text:
        return None
    multiplier = 1.0
    if text.endswith("B") or "B" in text:
        multiplier = 1_000_000_000.0
    elif text.endswith("M") or "M" in text:
        multiplier = 1_000_000.0
    elif text.endswith("K") or "K" in text:
        multiplier = 1_000.0
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    return numbers[0] * multiplier


def seniority_score(title: str) -> int:
    text = normalized(title)
    if has_any(text, HIGH_SENIORITY_TERMS):
        return 30
    if has_any(text, MID_SENIORITY_TERMS):
        return 24
    if "manager" in text or "lead" in text:
        return 16
    return 10 if text else 0


def employee_band_score(employee_count: Optional[int]) -> int:
    if employee_count is None:
        return 8
    if 20 <= employee_count <= 500:
        return 20
    if 10 <= employee_count < 20 or 500 < employee_count <= 750:
        return 12
    return 4


def industry_score(target_industries: str) -> int:
    return 20 if has_any(target_industries, REGULATED_INDUSTRY_TERMS) else 8


def compliance_score(compliance_tags: str, services: str) -> int:
    text = f"{compliance_tags}; {services}"
    return 20 if has_any(text, COMPLIANCE_TERMS) else 8


def service_score(services: str) -> int:
    return 10 if has_any(services, SERVICE_TERMS) else 4


def fit_tier(score: int) -> str:
    if score >= 90:
        return "A - Strong ICP Fit"
    if score >= 75:
        return "B - Good ICP Fit"
    if score >= 60:
        return "C - Review Fit"
    return "D - Low Fit"


def contact_channel_status(row: dict) -> tuple[str, str]:
    channels = {
        "email": clean(row.get("Email")),
        "phone": clean(row.get("Phone")),
        "linkedin_url": clean(row.get("LinkedIn URL")),
    }
    missing = [name for name, value in channels.items() if not value]
    if len(missing) == 3:
        return "Needs Contact Channel", "email; phone; linkedin_url"
    return "Outreach Ready", "; ".join(missing)


def score_row(row: dict) -> dict:
    employee_count = coerce_int(row.get("Employee Count"))
    seniority = seniority_score(row.get("Title", ""))
    employee_score = employee_band_score(employee_count)
    industry = industry_score(row.get("Target Industries", ""))
    compliance = compliance_score(row.get("Compliance Tags", ""), row.get("Services", ""))
    service = service_score(row.get("Services", ""))
    total = seniority + employee_score + industry + compliance + service
    readiness, missing_channels = contact_channel_status(row)
    state = normalize_state(row.get("HQ", ""))

    return {
        "company": clean(row.get("Company")),
        "website": clean(row.get("Website")),
        "state": state,
        "hq": clean(row.get("HQ")),
        "employee_count": employee_count or "",
        "revenue": clean(row.get("Revenue")),
        "revenue_estimated_usd": parse_money(row.get("Revenue", "")) or "",
        "contact_full_name": clean(row.get("Full Name")),
        "title": clean(row.get("Title")),
        "icp_fit_score": total,
        "icp_fit_tier": fit_tier(total),
        "seniority_score": seniority,
        "employee_band_score": employee_score,
        "regulated_industry_score": industry,
        "compliance_score": compliance,
        "service_alignment_score": service,
        "outreach_readiness_status": readiness,
        "missing_channels": missing_channels,
        "target_industries": clean(row.get("Target Industries")),
        "services": clean(row.get("Services")),
        "compliance_tags": clean(row.get("Compliance Tags")),
        "source": clean(row.get("Source")),
    }


def read_seed(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as csvfile:
        return list(csv.DictReader(csvfile))


def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_enrichment_requests(rows: list[dict]) -> list[dict]:
    requests = []
    for row in rows:
        _, missing_channels = contact_channel_status(row)
        requests.append({
            "priority": clean(row.get("Priority")),
            "company": clean(row.get("Company")),
            "website": clean(row.get("Website")),
            "hq": clean(row.get("HQ")),
            "employee_count": clean(row.get("Employee Count")),
            "revenue": clean(row.get("Revenue")),
            "contact_full_name": clean(row.get("Full Name")),
            "title": clean(row.get("Title")),
            "current_email": clean(row.get("Email")),
            "current_phone": clean(row.get("Phone")),
            "current_linkedin_url": clean(row.get("LinkedIn URL")),
            "missing_fields": missing_channels,
            "required_next_action": "Add at least one verified outreach channel: work email, phone, or LinkedIn URL.",
            "source": clean(row.get("Source")),
        })
    return requests


def build_summary(scored_rows: list[dict], enrichment_rows: list[dict]) -> dict:
    companies = {row["company"] for row in scored_rows}
    ready = sum(1 for row in scored_rows if row["outreach_readiness_status"] == "Outreach Ready")
    needs_channel = len(scored_rows) - ready
    strong_fit = sum(1 for row in scored_rows if row["icp_fit_tier"] == "A - Strong ICP Fit")
    good_fit = sum(1 for row in scored_rows if row["icp_fit_tier"] == "B - Good ICP Fit")
    return {
        "contacts": len(scored_rows),
        "companies": len(companies),
        "outreach_ready": ready,
        "needs_contact_channel": needs_channel,
        "strong_icp_fit": strong_fit,
        "good_icp_fit": good_fit,
        "enrichment_requests": len(enrichment_rows),
    }


def write_markdown_summary(path: str, summary: dict, scored_rows: list[dict], output_paths: dict) -> str:
    top_rows = scored_rows[:10]
    lines = [
        "# ZoomInfo Contact Seed QA Summary",
        "",
        "## Result",
        "",
        f"- Contacts reviewed: `{summary['contacts']}`",
        f"- Companies reviewed: `{summary['companies']}`",
        f"- Outreach-ready contacts: `{summary['outreach_ready']}`",
        f"- Contacts needing email/phone/LinkedIn: `{summary['needs_contact_channel']}`",
        f"- A-tier ICP fit contacts: `{summary['strong_icp_fit']}`",
        f"- B-tier ICP fit contacts: `{summary['good_icp_fit']}`",
        "",
        "## Outputs",
        "",
        f"- Enrichment request CSV: `{output_paths['enrichment']}`",
        f"- ICP scoring CSV: `{output_paths['scoring']}`",
        "",
        "## Top Contact Order",
        "",
        "| Rank | Company | Contact | Title | ICP Fit | Status |",
        "|---:|---|---|---|---:|---|",
    ]
    for index, row in enumerate(top_rows, start=1):
        lines.append(
            f"| {index} | {row['company']} | {row['contact_full_name']} | "
            f"{row['title']} | {row['icp_fit_score']} | {row['outreach_readiness_status']} |"
        )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "These contacts should stay in `Contact Identified` until at least one verified outreach channel is available.",
    ])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as markdown:
        markdown.write("\n".join(lines) + "\n")
    return path


def run_contact_seed_qa(
    input_path: str,
    output_date: Optional[str] = None,
    output_dir: str = OUTPUT_DIR,
) -> dict:
    output_date = output_date or datetime.now().strftime("%Y%m%d")
    rows = read_seed(input_path)
    scored_rows = [score_row(row) for row in rows]
    scored_rows.sort(key=lambda row: (-row["icp_fit_score"], row["company"], row["contact_full_name"]))
    for index, row in enumerate(scored_rows, start=1):
        row["rank"] = index

    enrichment_rows = build_enrichment_requests(rows)
    enrichment_path = os.path.join(output_dir, f"contact_enrichment_request_{output_date}.csv")
    scoring_path = os.path.join(output_dir, f"contact_icp_fit_scoring_{output_date}.csv")
    summary_path = os.path.join(
        os.path.dirname(output_dir),
        "docs",
        f"contact_seed_qa_summary_{output_date}.md",
    )

    enrichment_fields = [
        "priority",
        "company",
        "website",
        "hq",
        "employee_count",
        "revenue",
        "contact_full_name",
        "title",
        "current_email",
        "current_phone",
        "current_linkedin_url",
        "missing_fields",
        "required_next_action",
        "source",
    ]
    scoring_fields = [
        "rank",
        "company",
        "website",
        "state",
        "hq",
        "employee_count",
        "revenue",
        "revenue_estimated_usd",
        "contact_full_name",
        "title",
        "icp_fit_score",
        "icp_fit_tier",
        "seniority_score",
        "employee_band_score",
        "regulated_industry_score",
        "compliance_score",
        "service_alignment_score",
        "outreach_readiness_status",
        "missing_channels",
        "target_industries",
        "services",
        "compliance_tags",
        "source",
    ]
    write_csv(enrichment_path, enrichment_rows, enrichment_fields)
    write_csv(scoring_path, scored_rows, scoring_fields)
    summary = build_summary(scored_rows, enrichment_rows)
    write_markdown_summary(summary_path, summary, scored_rows, {
        "enrichment": enrichment_path,
        "scoring": scoring_path,
    })
    return {
        **summary,
        "enrichment_path": enrichment_path,
        "scoring_path": scoring_path,
        "summary_path": summary_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QA and enrichment outputs for a ZoomInfo contact seed CSV.")
    parser.add_argument("--input", required=True, help="ZoomInfo contact seed CSV path")
    parser.add_argument("--output-date", help="Date suffix for output files, e.g. 20260522")
    args = parser.parse_args()

    summary = run_contact_seed_qa(args.input, args.output_date)
    print("Contact seed QA complete")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
