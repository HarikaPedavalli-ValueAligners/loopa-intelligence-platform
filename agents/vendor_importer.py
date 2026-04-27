# agents/vendor_importer.py
# Imports vendor data from Hamid's Excel files into the database.
# Reads both Excel files, cleans the data, removes duplicates,
# and saves all vendors to the vendors table.

import os
import sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import Vendor


# ------------------------------------------------------------
# File Paths
# ------------------------------------------------------------

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data"
)

VENDOR_DATABASE_FILE    = os.path.join(DATA_DIR, "Vendor Database.xlsx")
VENDOR_CLUSTERING_FILE  = os.path.join(DATA_DIR, "Vendor Dataset for Clustering.xlsx")

# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------

def clean_string(value) -> str:
    """Cleans a string value — strips whitespace, handles None."""
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip()


def clean_float(value) -> float:
    """Extracts a float from a string like '4.3 (Gartner)'."""
    if pd.isna(value) or value is None:
        return None
    try:
        return float(str(value).split()[0])
    except:
        return None


def clean_bool(value) -> bool:
    """Converts Yes/No/Available strings to boolean."""
    if pd.isna(value) or value is None:
        return False
    return str(value).strip().lower() in ["yes", "available", "true"]


# ------------------------------------------------------------
# Read Vendor Database Excel
# ------------------------------------------------------------

def read_vendor_database() -> list:
    """
    Reads Vendor Database.xlsx and returns a list of vendor dicts.
    Uses the main sheet which contains full vendor details.
    """

    print("Reading Vendor Database.xlsx...")

    try:
        df = pd.read_excel(
            VENDOR_DATABASE_FILE,
            sheet_name = "Updated Upstream Clients databa",
            header     = 2      # row 3 is the actual header
        )

        vendors = []

        for _, row in df.iterrows():

            # Skip empty rows
            if pd.isna(row.get("Solution Name")) and pd.isna(row.get("Company Name")):
                continue

            vendor = {
                "vendor_name"               : clean_string(row.get("Solution Name") or row.get("Company Name")),
                "company_website"           : clean_string(row.get("Company Website")),
                "company_size"              : clean_string(row.get("Company Size")),
                "year_founded"              : clean_float(row.get("Year Founded")),
                "headquarters"              : clean_string(row.get("Headquarters Location")),
                "status"                    : clean_string(row.get("Status")),
                "cyber_category"            : clean_string(row.get("Category ")),
                "cyber_subcategory"         : clean_string(row.get("Subcategory")),
                "threat_types_addressed"    : clean_string(row.get("Threat Types Addressed")),
                "product_name"              : clean_string(row.get("Product Name")),
                "product_description"       : clean_string(row.get("Product Description")),
                "target_market"             : clean_string(row.get("Target Market")),
                "pricing_model"             : clean_string(row.get("Pricing Model")),
                "supported_platforms"       : clean_string(row.get("Supported Platforms")),
                "deployment_models"         : clean_string(row.get("Deployment Models")),
                "integration_capabilities"  : clean_string(row.get("Integration Capabilities")),
                "compliance_certifications" : clean_string(row.get("Compliance Certifications")),
                "customer_rating"           : clean_float(row.get("Customer Ratings")),
                "active_users"              : clean_string(row.get("Number of Active Users")),
                "api_available"             : clean_bool(row.get("API Availability")),
                "free_trial"                : clean_bool(row.get("Free Trial Availability")),
            }

            # Skip if no vendor name
            if not vendor["vendor_name"]:
                continue

            vendors.append(vendor)

        print(f"  Found {len(vendors)} vendors in Vendor Database.xlsx")
        return vendors

    except Exception as e:
        print(f"  Error reading Vendor Database.xlsx: {e}")
        return []


# ------------------------------------------------------------
# Read Vendor Clustering Excel
# ------------------------------------------------------------

def read_vendor_clustering() -> list:
    """
    Reads Vendor_Dataset_for_Clustering.xlsx and returns
    a list of vendor dicts. Used to supplement missing data.
    """

    print("Reading Vendor_Dataset_for_Clustering.xlsx...")

    try:
        df = pd.read_excel(
            VENDOR_CLUSTERING_FILE,
            sheet_name = "Vendor DB",
            header     = 0
        )

        vendors = []

        for _, row in df.iterrows():

            if pd.isna(row.get("Vendor Name")):
                continue

            vendor = {
                "vendor_name"               : clean_string(row.get("Vendor Name")),
                "company_size"              : clean_string(row.get("Company Size")),
                "year_founded"              : clean_float(row.get("Year Founded")),
                "headquarters"              : clean_string(row.get("Headquarters Location")),
                "status"                    : clean_string(row.get("Status")),
                "cyber_category"            : clean_string(row.get("Cybersecurity Category ")),
                "cyber_subcategory"         : clean_string(row.get(" Cybersecurity Subcategory")),
                "threat_types_addressed"    : clean_string(row.get("Threat Types Addressed")),
                "target_market"             : clean_string(row.get("Target Market")),
                "supported_platforms"       : clean_string(row.get("Supported Platforms")),
                "compliance_certifications" : clean_string(row.get(" Certifications")),
                "customer_rating"           : clean_float(row.get("Customer Ratings")),
                "deployment_models"         : clean_string(row.get("Deployment Models")),
                "integration_capabilities"  : clean_string(row.get("Integration Capabilities")),
            }

            if not vendor["vendor_name"]:
                continue

            vendors.append(vendor)

        print(f"  Found {len(vendors)} vendors in Vendor_Dataset_for_Clustering.xlsx")
        return vendors

    except Exception as e:
        print(f"  Error reading Vendor_Dataset_for_Clustering.xlsx: {e}")
        return []


# ------------------------------------------------------------
# Merge and Deduplicate
# ------------------------------------------------------------

def merge_vendors(primary: list, secondary: list) -> list:
    """
    Merges two vendor lists.
    Primary list takes precedence.
    Duplicates are removed by vendor name.
    """

    merged = {}

    # Add secondary first (lower priority)
    for vendor in secondary:
        name = vendor["vendor_name"].lower().strip()
        if name:
            merged[name] = vendor

    # Add primary on top (higher priority — overwrites duplicates)
    for vendor in primary:
        name = vendor["vendor_name"].lower().strip()
        if name:
            merged[name] = vendor

    result = list(merged.values())
    print(f"\n  Total unique vendors after merge: {len(result)}")
    return result


# ------------------------------------------------------------
# Save to Database
# ------------------------------------------------------------

def save_vendors(vendors: list) -> int:
    """
    Saves all vendors to the database.
    Updates existing vendors, creates new ones.

    Returns:
        Number of vendors saved.
    """

    session = get_session()
    saved   = 0
    updated = 0

    try:
        for vendor_data in vendors:

            # Check if vendor already exists
            existing = session.query(Vendor).filter_by(
                vendor_name = vendor_data["vendor_name"]
            ).first()

            vendor = existing if existing else Vendor()

            # Map data to model
            vendor.vendor_name               = vendor_data.get("vendor_name")
            vendor.company_website           = vendor_data.get("company_website")
            vendor.company_size              = vendor_data.get("company_size")
            vendor.year_founded              = int(vendor_data["year_founded"]) if vendor_data.get("year_founded") else None
            vendor.headquarters              = vendor_data.get("headquarters")
            vendor.status                    = vendor_data.get("status")
            vendor.cyber_category            = vendor_data.get("cyber_category")
            vendor.cyber_subcategory         = vendor_data.get("cyber_subcategory")
            vendor.threat_types_addressed    = vendor_data.get("threat_types_addressed")
            vendor.product_name              = vendor_data.get("product_name")
            vendor.product_description       = vendor_data.get("product_description")
            vendor.target_market             = vendor_data.get("target_market")
            vendor.pricing_model             = vendor_data.get("pricing_model")
            vendor.supported_platforms       = vendor_data.get("supported_platforms")
            vendor.deployment_models         = vendor_data.get("deployment_models")
            vendor.integration_capabilities  = vendor_data.get("integration_capabilities")
            vendor.compliance_certifications = vendor_data.get("compliance_certifications")
            vendor.customer_rating           = vendor_data.get("customer_rating")
            vendor.active_users              = vendor_data.get("active_users")
            vendor.api_available             = vendor_data.get("api_available", False)
            vendor.free_trial                = vendor_data.get("free_trial", False)

            if not existing:
                session.add(vendor)
                saved += 1
            else:
                updated += 1

        session.commit()
        print(f"  New vendors saved  : {saved}")
        print(f"  Existing updated   : {updated}")
        return saved + updated

    except Exception as e:
        session.rollback()
        raise e

    finally:
        session.close()


# ------------------------------------------------------------
# Display Sample
# ------------------------------------------------------------

def display_sample(vendors: list, count: int = 5) -> None:
    """Shows a sample of imported vendors."""

    print(f"\nSample of imported vendors:")
    print("-" * 60)

    for vendor in vendors[:count]:
        print(f"  Vendor   : {vendor['vendor_name']}")
        print(f"  Category : {vendor['cyber_category']} > {vendor['cyber_subcategory']}")
        print(f"  Market   : {vendor['target_market']}")
        print(f"  Rating   : {vendor['customer_rating']}")
        print()


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------

if __name__ == "__main__":

    from database.db_manager import get_database_stats

    print("\nLoopa Intelligence - Vendor Importer")
    print("=" * 60)

    # Read both Excel files
    primary   = read_vendor_database()
    secondary = read_vendor_clustering()

    # Merge and deduplicate
    all_vendors = merge_vendors(primary, secondary)

    # Show sample
    display_sample(all_vendors)

    # Save to database
    print("Saving to database...")
    total = save_vendors(all_vendors)
    print(f"\nDone. Total vendors in database: {total}")

    # Show updated stats
    print()
    get_database_stats()