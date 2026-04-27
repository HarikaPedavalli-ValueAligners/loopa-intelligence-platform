# agents/vendor_matcher.py
# Matches vendors to pain points using keyword-based matching.
# No AI API calls — fast, free, and reliable at any scale.
# Matches based on cybersecurity category and threat type overlap.

import os
import sys
import argparse
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    PainPoint, Vendor, VendorPainPointMap
)


# ------------------------------------------------------------
# Keyword Matching Logic
# ------------------------------------------------------------

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "the", "to", "with", "within", "security",
    "cyber", "cybersecurity", "solution", "solutions", "platform", "system",
    "systems", "service", "services", "management", "protection",
}

SYNONYM_GROUPS = [
    {"iam", "identity", "access", "identity access", "identity and access", "identity access management"},
    {"mfa", "multi factor", "multifactor", "authentication", "2fa"},
    {"edr", "endpoint", "endpoint detection", "endpoint detection response"},
    {"xdr", "extended detection", "extended detection response"},
    {"siem", "security information event management", "log management"},
    {"soc", "managed detection", "mdr", "monitoring"},
    {"dlp", "data loss prevention", "data leakage", "data protection"},
    {"grc", "governance", "risk", "compliance"},
    {"vulnerability", "vulnerabilities", "vulnerability management", "exposure management"},
    {"phishing", "anti phishing", "email security", "business email compromise", "bec"},
    {"ransomware", "malware", "anti malware", "backup", "recovery"},
    {"cloud", "saas", "cloud security", "cspm", "posture"},
    {"zero trust", "ztna", "network access", "secure access"},
    {"privacy", "data privacy", "consent", "dsar"},
    {"third party", "vendor risk", "supply chain", "supplier risk"},
]

SYNONYM_LOOKUP = {
    term: group
    for group in SYNONYM_GROUPS
    for term in group
}

CONFIDENCE_THRESHOLDS = {
    "strong": 0.65,
    "medium": 0.45,
    "weak": 0.30,
}


def tokenize(text: str) -> set:
    """Normalizes text into meaningful keywords with synonym expansion."""
    clean = re.sub(r"[^a-z0-9+ ]+", " ", (text or "").lower())
    raw_tokens = [token for token in clean.split() if len(token) > 2 and token not in STOPWORDS]
    tokens = set(raw_tokens)

    for phrase, group in SYNONYM_LOOKUP.items():
        if phrase in clean:
            tokens.update(group)

    return tokens


def overlap_ratio(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), 1)


def confidence_label(score: float) -> str:
    if score >= CONFIDENCE_THRESHOLDS["strong"]:
        return "strong"
    if score >= CONFIDENCE_THRESHOLDS["medium"]:
        return "medium"
    if score >= CONFIDENCE_THRESHOLDS["weak"]:
        return "weak"
    return "below_threshold"


def calculate_match(pain_point: dict, vendor: dict) -> dict:
    """
    Calculates a structured match between a pain point and vendor.
    Returns score, confidence, type, and matched terms.
    """
    score = 0.0
    matched_terms = set()

    pp_category = tokenize(pain_point.get("cyber_category"))
    pp_subcategory = tokenize(pain_point.get("cyber_subcategory"))
    pp_threat = tokenize(f"{pain_point.get('pain_point_name')} {pain_point.get('description')}")

    v_category = tokenize(vendor.get("cyber_category"))
    v_subcategory = tokenize(vendor.get("cyber_subcategory"))
    v_capability = tokenize(
        " ".join([
            vendor.get("threat_types_addressed") or "",
            vendor.get("product_description") or "",
            vendor.get("compliance_certifications") or "",
            vendor.get("deployment_models") or "",
        ])
    )

    category_overlap = pp_category & v_category
    subcategory_overlap = pp_subcategory & v_subcategory
    threat_overlap = pp_threat & v_capability
    broad_overlap = (pp_category | pp_subcategory | pp_threat) & (v_category | v_subcategory | v_capability)

    if category_overlap:
        score += 0.35 * min(overlap_ratio(pp_category, v_category), 1.0)
        matched_terms.update(category_overlap)

    if subcategory_overlap:
        score += 0.25 * min(overlap_ratio(pp_subcategory, v_subcategory), 1.0)
        matched_terms.update(subcategory_overlap)

    if threat_overlap:
        score += 0.25 * min(overlap_ratio(pp_threat, v_capability), 1.0)
        matched_terms.update(threat_overlap)

    if broad_overlap:
        score += 0.15 * min(overlap_ratio(pp_category | pp_subcategory | pp_threat, v_category | v_subcategory | v_capability), 1.0)
        matched_terms.update(broad_overlap)

    # Boost score if vendor has a rating
    if vendor.get("customer_rating") and vendor["customer_rating"] > 4.0:
        score = min(score * 1.05, 1.0)

    score = round(score, 3)
    label = confidence_label(score)

    if category_overlap and (subcategory_overlap or threat_overlap):
        match_type = "category_and_capability"
    elif threat_overlap:
        match_type = "capability"
    elif category_overlap or subcategory_overlap:
        match_type = "taxonomy"
    else:
        match_type = "keyword"

    return {
        "score": score,
        "confidence_label": label,
        "match_type": match_type,
        "matched_terms": sorted(matched_terms),
    }


def calculate_match_score(pain_point: dict, vendor: dict) -> float:
    """Backward-compatible score-only helper."""
    return calculate_match(pain_point, vendor)["score"]


def generate_match_notes(pain_point: dict, vendor: dict, match: dict) -> str:
    """
    Generates a human-readable explanation for why a vendor
    matches a specific pain point.
    """
    v_category  = vendor.get("cyber_category") or "cybersecurity"
    v_threats   = vendor.get("threat_types_addressed") or "various threats"
    pp_name     = pain_point.get("pain_point_name") or "this threat"
    rating      = vendor.get("customer_rating")
    rating_str  = f" with a {rating} customer rating" if rating else ""
    terms = ", ".join(match.get("matched_terms") or [])
    terms_str = f" Matched terms: {terms}." if terms else ""

    return (
        f"{vendor['vendor_name']} specializes in {v_category} "
        f"addressing {v_threats}{rating_str}, "
        f"making it a {match['confidence_label']} fit for {pp_name}."
        f"{terms_str}"
    )


# ------------------------------------------------------------
# Get Data from Database
# ------------------------------------------------------------

def get_all_pain_points() -> list:
    """Returns all pain points stored in the database."""

    session = get_session()

    try:
        pain_points = session.query(PainPoint).all()

        return [
            {
                "id"                : pp.id,
                "niche_market_id"   : pp.niche_market_id,
                "industry"          : pp.industry,
                "sub_industry"      : pp.sub_industry,
                "pain_point_name"   : pp.pain_point_name,
                "pain_point_rank"   : pp.pain_point_rank,
                "cyber_category"    : pp.cyber_category,
                "cyber_subcategory" : pp.cyber_subcategory,
                "severity_score"    : pp.severity_score,
                "description"       : pp.description
            }
            for pp in pain_points
        ]

    finally:
        session.close()


def get_all_vendors() -> list:
    """Returns all vendors from the database."""

    session = get_session()

    try:
        vendors = session.query(Vendor)\
            .filter(Vendor.vendor_name != None)\
            .all()

        return [
            {
                "id"                        : v.id,
                "vendor_name"               : v.vendor_name,
                "cyber_category"            : v.cyber_category,
                "cyber_subcategory"         : v.cyber_subcategory,
                "threat_types_addressed"    : v.threat_types_addressed,
                "target_market"             : v.target_market,
                "customer_rating"           : v.customer_rating,
                "compliance_certifications" : v.compliance_certifications,
                "deployment_models"         : v.deployment_models,
                "product_description"       : v.product_description,
            }
            for v in vendors
        ]

    finally:
        session.close()


# ------------------------------------------------------------
# Save Matches to Database
# ------------------------------------------------------------

def save_matches(pain_point_id: int, matches: list) -> None:
    """Saves vendor-pain point matches to the database."""

    session = get_session()

    try:
        session.query(VendorPainPointMap).filter_by(
            pain_point_id = pain_point_id
        ).delete()

        for match in matches:
            mapping = VendorPainPointMap(
                vendor_id     = match["vendor_id"],
                pain_point_id = pain_point_id,
                match_score   = match["match_score"],
                confidence_label = match.get("confidence_label"),
                match_type    = match.get("match_type"),
                matched_terms = ", ".join(match.get("matched_terms") or []),
                is_fallback   = match.get("is_fallback", False),
                notes         = match["notes"]
            )
            session.add(mapping)

        session.commit()

    except Exception as e:
        session.rollback()
        raise e

    finally:
        session.close()


# ------------------------------------------------------------
# Run Full Matching
# ------------------------------------------------------------

def run_vendor_matching(min_confidence: str = "weak", include_fallback: bool = False) -> dict:
    """
    Runs the full vendor matching process using keyword matching.
    No API calls — instant, free, and scalable to 700+ niches.
    """

    print("\nLoopa Intelligence - Vendor Matcher")
    print("=" * 60)

    pain_points = get_all_pain_points()
    vendors     = get_all_vendors()
    total       = len(pain_points)

    print(f"Total pain points : {total}")
    print(f"Total vendors     : {len(vendors)}")
    threshold = CONFIDENCE_THRESHOLDS[min_confidence]
    print(f"Minimum confidence : {min_confidence} ({threshold})")
    print(f"Fallback enabled   : {include_fallback}")
    print("-" * 60)

    success = 0
    failed  = 0

    for index, pain_point in enumerate(pain_points, start=1):

        print(f"[{index}/{total}] {pain_point['pain_point_name']} "
              f"({pain_point['industry']})")

        try:
            # Score all vendors against this pain point
            scored_vendors = []

            for vendor in vendors:
                match = calculate_match(pain_point, vendor)
                score = match["score"]
                if score >= threshold:
                    scored_vendors.append({
                        "vendor_id"     : vendor["id"],
                        "vendor_name"   : vendor["vendor_name"],
                        "match_score"   : score,
                        "confidence_label": match["confidence_label"],
                        "match_type"    : match["match_type"],
                        "matched_terms" : match["matched_terms"],
                        "is_fallback"   : False,
                        "notes"         : generate_match_notes(
                                            pain_point, vendor, match
                                          )
                    })

            # Sort by score and take top 3
            top_matches = sorted(
                scored_vendors,
                key     = lambda x: x["match_score"],
                reverse = True
            )[:3]

            # Optional fallback is explicitly marked as low confidence.
            if not top_matches and include_fallback:
                top_matches = [
                    {
                        "vendor_id"   : v["id"],
                        "vendor_name" : v["vendor_name"],
                        "match_score" : 0.3,
                        "confidence_label": "fallback",
                        "match_type"  : "fallback",
                        "matched_terms": [],
                        "is_fallback" : True,
                        "notes"       : f"Fallback recommendation only. No strong taxonomy or capability match found for {pain_point['pain_point_name']}."
                    }
                    for v in sorted(
                        vendors,
                        key     = lambda x: x["customer_rating"] or 0,
                        reverse = True
                    )[:3]
                ]

            save_matches(pain_point["id"], top_matches)

            for i, match in enumerate(top_matches, start=1):
                print(f"  {i}. {match['vendor_name']} "
                      f"(Score: {match['match_score']} | {match.get('confidence_label')})")

            success += 1

        except Exception as e:
            print(f"  Failed: {str(e)}")
            failed += 1

    print("\n" + "=" * 60)
    print("VENDOR MATCHING COMPLETE")
    print("=" * 60)
    print(f"Total   : {total}")
    print(f"Success : {success}")
    print(f"Failed  : {failed}")
    print("=" * 60)
    return {"total": total, "success": success, "failed": failed}


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Match vendors to Loopa pain points.")
    parser.add_argument(
        "--min-confidence",
        choices=["weak", "medium", "strong"],
        default="weak",
        help="Minimum confidence level to save",
    )
    parser.add_argument(
        "--include-fallback",
        action="store_true",
        help="Save explicitly labeled fallback recommendations when no match clears threshold",
    )
    args = parser.parse_args()

    run_vendor_matching(
        min_confidence=args.min_confidence,
        include_fallback=args.include_fallback,
    )
