# agents/niche_market_agent.py
# Research agent for niche market intelligence.
# Implements Hamid's two-layer scoring model:
#   Layer 1 — Demand Score (0-100)
#   Layer 2 — Outbound Feasibility Score (0-100)
#   Final    — Priority Score = Demand x Outbound / 100

import os
import json
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PROJECT_ROOT


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def get_groq_client():
    """Creates a Groq client lazily so scoring tests do not require AI deps."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY in environment.")

    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'groq'. Install requirements with: pip install -r requirements.txt"
        ) from exc

    return Groq(api_key=api_key)


# ------------------------------------------------------------
# Scoring Configuration
# All weights follow Hamid's Prioritization Playbook exactly.
# Adjust weights here without touching any business logic.
# ------------------------------------------------------------

# Layer 1 — Demand Score weights
DEMAND_WEIGHTS = {
    "attack_records"            : +0.25,
    "digitalization_level"      : +0.20,
    "sme_revenue_contribution"  : +0.15,
    "cagr"                      : +0.15,
    "cybersecurity_readiness"   : -0.20,    # negative: low readiness = higher demand
    "industry_size"             : +0.10,
    "smb_percentage"            : +0.10,
    "estimated_annual_loss"     : +0.10,
}

# Layer 2 — Outbound Feasibility Score weights
OUTBOUND_WEIGHTS = {
    "reachability"              : +0.35,
    "buyer_role_clarity"        : +0.20,
    "procurement_friction"      : -0.25,    # negative: more friction = worse
    "time_to_value"             : +0.10,
    "vendor_sprawl"             : +0.05,
    "offer_fit"                 : +0.05,
}

# Tier thresholds (0-100 scale per Hamid's playbook)
TIER_THRESHOLDS = {
    "tier1": 70,
    "tier2": 50,
}


# ------------------------------------------------------------
# Min-Max Normalization
# Normalizes values across all niches for fair comparison.
# Uses fixed reference ranges based on expected data bounds.
# ------------------------------------------------------------

DEMAND_RANGES = {
    "attack_records"            : (1, 10),
    "digitalization_level"      : (1, 10),
    "sme_revenue_contribution"  : (0, 100),
    "cagr"                      : (0, 20),
    "cybersecurity_readiness"   : (1, 10),
    "industry_size"             : (0, 2000),
    "smb_percentage"            : (0, 100),
    "estimated_annual_loss"     : (0, 100),
}

OUTBOUND_RANGES = {
    "reachability"              : (1, 10),
    "buyer_role_clarity"        : (1, 10),
    "procurement_friction"      : (1, 10),
    "time_to_value"             : (1, 10),
    "vendor_sprawl"             : (1, 10),
    "offer_fit"                 : (1, 10),
}

REQUIRED_TOP_LEVEL_FIELDS = [
    "industry",
    "sub_industry",
    "sub_sub_industry",
    "niche_name",
    "geography",
    "naics_code",
    "avg_employee_count_min",
    "avg_employee_count_max",
    "attack_records",
    "digitalization_level",
    "sme_revenue_contribution",
    "cagr",
    "cybersecurity_readiness",
    "industry_size",
    "smb_percentage",
    "estimated_annual_loss",
    "regulatory_complexity",
    "common_cyber_risks",
    "reachability",
    "buyer_role_clarity",
    "procurement_friction",
    "time_to_value",
    "vendor_sprawl",
    "budget_proxy",
    "offer_fit",
    "compliance_audit_drivers",
    "compliance_audit_notes",
    "icp_headcount_min",
    "icp_headcount_max",
    "icp_description",
    "assumptions_notes",
    "top_pain_points",
]

SCALE_1_TO_10_FIELDS = [
    "attack_records",
    "digitalization_level",
    "cybersecurity_readiness",
    "regulatory_complexity",
    "reachability",
    "buyer_role_clarity",
    "procurement_friction",
    "time_to_value",
    "vendor_sprawl",
    "budget_proxy",
    "offer_fit",
]

PERCENTAGE_FIELDS = [
    "sme_revenue_contribution",
    "cagr",
    "smb_percentage",
]

PAIN_POINT_REQUIRED_FIELDS = [
    "rank",
    "pain_point",
    "description",
    "cyber_category",
    "cyber_subcategory",
    "severity_score",
    "growth_rate",
]


class ResearchValidationError(ValueError):
    """Raised when AI research output is invalid or incomplete."""


def normalize(value: float, min_val: float, max_val: float) -> float:
    """
    Applies min-max normalization to a single value.
    Returns a float between 0.0 and 1.0.
    """
    if max_val == min_val:
        return 0.0
    return min(max((value - min_val) / (max_val - min_val), 0.0), 1.0)


def _coerce_number(value, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchValidationError(f"{field_name} must be numeric") from exc


def strip_json_response(raw: str) -> str:
    """Extracts raw JSON from plain or fenced model output."""
    text = (raw or "").strip()

    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ResearchValidationError("AI response did not contain a JSON object")

    return text[start:end + 1]


def validate_research_output(data: dict) -> dict:
    """Validates and normalizes the AI research JSON contract."""
    if not isinstance(data, dict):
        raise ResearchValidationError("AI response must be a JSON object")

    missing = [
        field for field in REQUIRED_TOP_LEVEL_FIELDS
        if field not in data
    ]
    if missing:
        raise ResearchValidationError(f"Missing required fields: {', '.join(missing)}")

    for field in SCALE_1_TO_10_FIELDS:
        value = _coerce_number(data.get(field), field)
        if value < 1 or value > 10:
            raise ResearchValidationError(f"{field} must be between 1 and 10")
        data[field] = int(value) if value.is_integer() else value

    for field in PERCENTAGE_FIELDS:
        value = _coerce_number(data.get(field), field)
        if value < 0 or value > 100:
            raise ResearchValidationError(f"{field} must be between 0 and 100")
        data[field] = value

    for field in ["industry_size", "estimated_annual_loss"]:
        value = _coerce_number(data.get(field), field)
        if value < 0:
            raise ResearchValidationError(f"{field} must be non-negative")
        data[field] = value

    if data.get("compliance_audit_drivers") not in {"Yes", "No"}:
        raise ResearchValidationError('compliance_audit_drivers must be exactly "Yes" or "No"')

    pain_points = data.get("top_pain_points")
    if not isinstance(pain_points, list) or len(pain_points) < 3:
        raise ResearchValidationError("top_pain_points must include at least 3 items")

    for index, pain_point in enumerate(pain_points, start=1):
        if not isinstance(pain_point, dict):
            raise ResearchValidationError(f"top_pain_points[{index}] must be an object")

        missing_pain_fields = [
            field for field in PAIN_POINT_REQUIRED_FIELDS
            if field not in pain_point
        ]
        if missing_pain_fields:
            raise ResearchValidationError(
                f"top_pain_points[{index}] missing: {', '.join(missing_pain_fields)}"
            )

        severity = _coerce_number(pain_point.get("severity_score"), f"top_pain_points[{index}].severity_score")
        if severity < 1 or severity > 10:
            raise ResearchValidationError(f"top_pain_points[{index}].severity_score must be between 1 and 10")
        pain_point["severity_score"] = int(severity) if severity.is_integer() else severity

        growth_rate = _coerce_number(pain_point.get("growth_rate"), f"top_pain_points[{index}].growth_rate")
        pain_point["growth_rate"] = growth_rate

    return data


# ------------------------------------------------------------
# Scoring Functions
# ------------------------------------------------------------

def calculate_demand_score(data: dict) -> float:
    """
    Calculates the Demand Score (0-100) using Layer 1 weights.
    Reflects how urgent and large the cybersecurity opportunity is.

    Args:
        data: Research data dictionary from the AI agent.

    Returns:
        Demand score as a float between 0 and 100.
    """
    score = 0.0

    for variable, weight in DEMAND_WEIGHTS.items():
        raw_value           = data.get(variable, 0) or 0
        min_val, max_val    = DEMAND_RANGES[variable]
        normalized          = normalize(raw_value, min_val, max_val)
        contribution        = (1 - normalized) if weight < 0 else normalized
        score               += abs(weight) * contribution

    return round(score * 100, 2)


def calculate_outbound_score(data: dict) -> float:
    """
    Calculates the Outbound Feasibility Score (0-100) using Layer 2 weights.
    Reflects how easy it is to reach and convert buyers via cold outreach.

    Args:
        data: Research data dictionary from the AI agent.

    Returns:
        Outbound score as a float between 0 and 100.
    """
    score = 0.0

    for variable, weight in OUTBOUND_WEIGHTS.items():
        raw_value           = data.get(variable, 0) or 0
        min_val, max_val    = OUTBOUND_RANGES[variable]
        normalized          = normalize(raw_value, min_val, max_val)
        contribution        = (1 - normalized) if weight < 0 else normalized
        score               += abs(weight) * contribution

    return round(score * 100, 2)


def calculate_priority_score(demand: float, outbound: float) -> float:
    """
    Combines Demand and Outbound scores into the Final Priority Score.
    Formula: Priority Score = Demand Score x Outbound Score / 100

    Args:
        demand : Demand score (0-100)
        outbound: Outbound feasibility score (0-100)

    Returns:
        Final priority score as a float between 0 and 100.
    """
    return round((demand * outbound) / 100, 2)


def get_priority_tier(priority_score: float) -> int:
    """
    Assigns a priority tier based on the final priority score.

    Tier 1: Score >= 70  (top outbound targets)
    Tier 2: Score >= 50  (secondary targets)
    Tier 3: Score <  50  (monitor and revisit)

    Args:
        priority_score: Final priority score (0-100)

    Returns:
        Integer tier (1, 2, or 3).
    """
    if priority_score >= TIER_THRESHOLDS["tier1"]:
        return 1
    elif priority_score >= TIER_THRESHOLDS["tier2"]:
        return 2
    return 3


# ------------------------------------------------------------
# AI Research Function
# ------------------------------------------------------------

def research_niche_market(
    industry: str,
    sub_industry: str = None,
    sub_sub_industry: str = None,
    max_retries: int = 2,
) -> dict:
    """
    Researches a niche market using the AI model and returns
    structured data ready for scoring and database storage.
    Covers both demand variables and outbound feasibility variables.

    Args:
        industry         : Top-level industry name.
        sub_industry     : Optional sub-industry name.
        sub_sub_industry : Optional sub-sub-industry name.

    Returns:
        Dictionary containing all variables, both scores,
        priority score, tier, ICP, and top pain points.
    """
    if sub_sub_industry:
        niche_name = f"{sub_sub_industry} (within {sub_industry}, {industry})"
    elif sub_industry:
        niche_name = f"{sub_industry} (within {industry})"
    else:
        niche_name = industry

    prompt = f"""
You are a senior cybersecurity market analyst specializing in SMB outreach strategy.
Research the following niche market for cybersecurity targeting and outbound sales purposes:

NICHE MARKET: {niche_name}

Return ONLY a valid JSON object with ALL fields below.
No markdown. No explanation. No code blocks. Raw JSON only.

{{
    "industry"                      : "{industry}",
    "sub_industry"                  : "{sub_industry or ''}",
    "sub_sub_industry"              : "{sub_sub_industry or ''}",
    "niche_name"                    : "<short descriptive name>",
    "geography"                     : "US",
    "naics_code"                    : "<best fit NAICS code if known>",

    "avg_employee_count_min"        : <typical minimum headcount>,
    "avg_employee_count_max"        : <typical maximum headcount>,

    "attack_records"                : <integer 1-10>,
    "digitalization_level"          : <integer 1-10>,
    "sme_revenue_contribution"      : <percentage 0-100>,
    "cagr"                          : <annual growth rate as percentage>,
    "cybersecurity_readiness"       : <integer 1-10>,
    "industry_size"                 : <market size in USD billions>,
    "smb_percentage"                : <percentage 0-100>,
    "estimated_annual_loss"         : <estimated annual cyber loss in USD billions>,
    "regulatory_complexity"         : <integer 1-10>,
    "common_cyber_risks"            : "<top 3 threats separated by commas>",

    "reachability"                  : <integer 1-10>,
    "buyer_role_clarity"            : <integer 1-10>,
    "procurement_friction"          : <integer 1-10>,
    "time_to_value"                 : <integer 1-10>,
    "vendor_sprawl"                 : <integer 1-10>,
    "budget_proxy"                  : <integer 1-10>,
    "offer_fit"                     : <integer 1-10>,
    "compliance_audit_drivers"      : "<Yes or No>",
    "compliance_audit_notes"        : "<e.g. HIPAA audits, PCI DSS, cyber insurance renewals>",

    "icp_headcount_min"             : <minimum employee count for ideal customer>,
    "icp_headcount_max"             : <maximum employee count for ideal customer>,
    "icp_description"               : "<2-3 sentence ideal customer profile>",

    "assumptions_notes"             : "<any assumptions made in this research>",

    "top_pain_points": [
        {{
            "rank"              : 1,
            "pain_point"        : "<name>",
            "description"       : "<description>",
            "cyber_category"    : "<category>",
            "cyber_subcategory" : "<subcategory>",
            "severity_score"    : <1-10>,
            "growth_rate"       : <annual growth %>
        }},
        {{
            "rank"              : 2,
            "pain_point"        : "<name>",
            "description"       : "<description>",
            "cyber_category"    : "<category>",
            "cyber_subcategory" : "<subcategory>",
            "severity_score"    : <1-10>,
            "growth_rate"       : <annual growth %>
        }},
        {{
            "rank"              : 3,
            "pain_point"        : "<name>",
            "description"       : "<description>",
            "cyber_category"    : "<category>",
            "cyber_subcategory" : "<subcategory>",
            "severity_score"    : <1-10>,
            "growth_rate"       : <annual growth %>
        }}
    ]
}}

STRICT RULES:
- All 1-10 scale fields must be integers between 1 and 10
- All percentage fields must be between 0 and 100
- compliance_audit_drivers must be exactly "Yes" or "No"
- Base all values on real cybersecurity research and market data
- Return raw JSON only — no markdown, no extra text
"""

    client = get_groq_client()
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    last_error = None

    for attempt in range(max_retries + 1):
        response = client.chat.completions.create(
            model       = model,
            messages    = [{"role": "user", "content": prompt}],
            temperature = 0.3,
        )

        raw = response.choices[0].message.content.strip()

        try:
            data = json.loads(strip_json_response(raw))
            data = validate_research_output(data)
            break
        except (json.JSONDecodeError, ResearchValidationError) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise ResearchValidationError(
                    f"AI research output failed validation after {max_retries + 1} attempts: {exc}"
                ) from exc
    else:
        raise ResearchValidationError(str(last_error))

    data["industry"] = industry
    data["sub_industry"] = sub_industry or ""
    data["sub_sub_industry"] = sub_sub_industry or ""
    data["ai_model"] = model

    # Calculate two-layer scores
    data["demand_score"]    = calculate_demand_score(data)
    data["outbound_score"]  = calculate_outbound_score(data)
    data["priority_score"]  = calculate_priority_score(
        data["demand_score"],
        data["outbound_score"]
    )
    data["priority_tier"]   = get_priority_tier(data["priority_score"])

    return data


# ------------------------------------------------------------
# Display
# ------------------------------------------------------------

def display_results(data: dict) -> None:
    """Prints research results in a readable format."""

    print("\n" + "=" * 60)
    print("NICHE MARKET INTELLIGENCE REPORT")
    print("=" * 60)

    print(f"\nNiche          : {data.get('niche_name', '')}")
    print(f"Industry       : {data['industry']}")
    if data.get("sub_industry"):
        print(f"Sub-Industry   : {data['sub_industry']}")
    if data.get("sub_sub_industry"):
        print(f"Sub-Sub        : {data['sub_sub_industry']}")
    print(f"Geography      : {data.get('geography', 'US')}")
    print(f"NAICS Code     : {data.get('naics_code', 'N/A')}")

    print(f"\nDemand Score   : {data['demand_score']} / 100")
    print(f"Outbound Score : {data['outbound_score']} / 100")
    print(f"Priority Score : {data['priority_score']} / 100")
    print(f"Priority Tier  : {data['priority_tier']}")

    print("\nDemand Variables:")
    print(f"  Attack Records         : {data.get('attack_records')} / 10")
    print(f"  Digitalization         : {data.get('digitalization_level')} / 10")
    print(f"  Cyber Readiness        : {data.get('cybersecurity_readiness')} / 10")
    print(f"  Regulatory Complexity  : {data.get('regulatory_complexity')} / 10")
    print(f"  SME Revenue            : {data.get('sme_revenue_contribution')}%")
    print(f"  CAGR                   : {data.get('cagr')}%")
    print(f"  Industry Size          : ${data.get('industry_size')}B")
    print(f"  SMB Percentage         : {data.get('smb_percentage')}%")
    print(f"  Est. Annual Loss       : ${data.get('estimated_annual_loss')}B")

    print("\nOutbound Variables:")
    print(f"  Reachability           : {data.get('reachability')} / 10")
    print(f"  Buyer Role Clarity     : {data.get('buyer_role_clarity')} / 10")
    print(f"  Procurement Friction   : {data.get('procurement_friction')} / 10")
    print(f"  Time to Value          : {data.get('time_to_value')} / 10")
    print(f"  Vendor Sprawl          : {data.get('vendor_sprawl')} / 10")
    print(f"  Budget Proxy           : {data.get('budget_proxy')} / 10")
    print(f"  Offer Fit              : {data.get('offer_fit')} / 10")
    print(f"  Compliance Audits      : {data.get('compliance_audit_drivers')} — {data.get('compliance_audit_notes')}")

    print(f"\nCommon Cyber Risks : {data.get('common_cyber_risks')}")

    print(f"\nIdeal Customer Profile:")
    print(f"  Headcount  : {data.get('icp_headcount_min')} - {data.get('icp_headcount_max')} employees")
    print(f"  {data.get('icp_description')}")

    if data.get("assumptions_notes"):
        print(f"\nAssumptions : {data.get('assumptions_notes')}")

    print("\nTop Pain Points:")
    for pp in data.get("top_pain_points", []):
        print(f"\n  #{pp['rank']} {pp['pain_point']}")
        print(f"     Category  : {pp['cyber_category']} > {pp['cyber_subcategory']}")
        print(f"     Severity  : {pp['severity_score']} / 10")
        print(f"     Growth    : {pp['growth_rate']}% annually")
        print(f"     Details   : {pp['description']}")

    print("\n" + "=" * 60)


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":
    from database.db_manager import save_niche_market, get_database_stats

    result = research_niche_market(
        industry         = "Healthcare",
        sub_industry     = "Hospitals",
        sub_sub_industry = "Hospital Supply Chain"
    )

    display_results(result)

    with open("data/sample_result.json", "w") as f:
        json.dump(result, f, indent=2)

    niche_id = save_niche_market(result)
    print(f"\nSaved to database. Record ID: {niche_id}")

    get_database_stats()
