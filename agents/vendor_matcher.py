# agents/vendor_matcher.py
# Matches vendors to pain points using keyword-based matching.
# No AI API calls — fast, free, and reliable at any scale.
# Matches based on cybersecurity category and threat type overlap.

import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import (
    PainPoint, Vendor, VendorPainPointMap
)


# ------------------------------------------------------------
# Keyword Matching Logic
# ------------------------------------------------------------

def calculate_match_score(pain_point: dict, vendor: dict) -> float:
    """
    Calculates a match score between a pain point and vendor
    using keyword overlap across category, subcategory,
    and threat type fields.

    Args:
        pain_point : Pain point dictionary from database.
        vendor     : Vendor dictionary from database.

    Returns:
        Match score as a float between 0.0 and 1.0.
    """

    score = 0.0

    # Prepare text fields for comparison
    pp_category     = (pain_point.get("cyber_category") or "").lower()
    pp_subcategory  = (pain_point.get("cyber_subcategory") or "").lower()
    pp_name         = (pain_point.get("pain_point_name") or "").lower()
    pp_description  = (pain_point.get("description") or "").lower()

    v_category      = (vendor.get("cyber_category") or "").lower()
    v_subcategory   = (vendor.get("cyber_subcategory") or "").lower()
    v_threats       = (vendor.get("threat_types_addressed") or "").lower()
    v_description   = (vendor.get("product_description") or "").lower()
    v_name          = (vendor.get("vendor_name") or "").lower()

    # Category match — highest weight
    if pp_category and v_category:
        pp_words = set(pp_category.split())
        v_words  = set(v_category.split())
        overlap  = len(pp_words & v_words)
        if overlap > 0:
            score += 0.40 * min(overlap / max(len(pp_words), 1), 1.0)

    # Subcategory match
    if pp_subcategory and v_subcategory:
        pp_words = set(pp_subcategory.split())
        v_words  = set(v_subcategory.split())
        overlap  = len(pp_words & v_words)
        if overlap > 0:
            score += 0.25 * min(overlap / max(len(pp_words), 1), 1.0)

    # Threat type match
    if pp_name and v_threats:
        pp_words = set(pp_name.replace("-", " ").split())
        v_words  = set(v_threats.replace(",", " ").split())
        overlap  = len(pp_words & v_words)
        if overlap > 0:
            score += 0.20 * min(overlap / max(len(pp_words), 1), 1.0)

    # Description keyword match
    combined_pp = f"{pp_name} {pp_description}"
    combined_v  = f"{v_threats} {v_description}"

    pp_words    = set(combined_pp.split())
    v_words     = set(combined_v.split())
    overlap     = len(pp_words & v_words)

    if overlap > 0:
        score += 0.15 * min(overlap / max(len(pp_words), 1), 1.0)

    # Boost score if vendor has a rating
    if vendor.get("customer_rating") and vendor["customer_rating"] > 4.0:
        score = min(score * 1.1, 1.0)

    return round(score, 3)


def generate_match_notes(pain_point: dict, vendor: dict, score: float) -> str:
    """
    Generates a human-readable explanation for why a vendor
    matches a specific pain point.
    """
    v_category  = vendor.get("cyber_category") or "cybersecurity"
    v_threats   = vendor.get("threat_types_addressed") or "various threats"
    pp_name     = pain_point.get("pain_point_name") or "this threat"
    rating      = vendor.get("customer_rating")
    rating_str  = f" with a {rating} customer rating" if rating else ""

    return (
        f"{vendor['vendor_name']} specializes in {v_category} "
        f"addressing {v_threats}{rating_str}, "
        f"making it a strong fit for {pp_name}."
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

def run_vendor_matching() -> None:
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
                score = calculate_match_score(pain_point, vendor)
                if score > 0:
                    scored_vendors.append({
                        "vendor_id"     : vendor["id"],
                        "vendor_name"   : vendor["vendor_name"],
                        "match_score"   : score,
                        "notes"         : generate_match_notes(
                                            pain_point, vendor, score
                                          )
                    })

            # Sort by score and take top 3
            top_matches = sorted(
                scored_vendors,
                key     = lambda x: x["match_score"],
                reverse = True
            )[:3]

            # If no keyword matches found use top rated vendors
            if not top_matches:
                top_matches = [
                    {
                        "vendor_id"   : v["id"],
                        "vendor_name" : v["vendor_name"],
                        "match_score" : 0.3,
                        "notes"       : f"General cybersecurity vendor recommended for {pain_point['pain_point_name']}."
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
                      f"(Score: {match['match_score']})")

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


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":
    run_vendor_matching()