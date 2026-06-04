import os
import tempfile
import unittest
from unittest.mock import patch

from agents.vendor_scope_agent import (
    TOTAL_VENDOR_VARIABLES,
    VENDOR_VARIABLE_CATALOG,
    build_vendor_intelligence_rows,
    normalize_domain,
    run_vendor_scope_seed,
)
from database.db_manager import get_session
from database.schema import (
    NicheMarket,
    PainPoint,
    Vendor,
    VendorIntelligenceProfile,
    VendorIntelligenceVariable,
    VendorPainPointMap,
)


class VendorScopeAgentTests(unittest.TestCase):
    def test_normalize_domain_handles_full_url_and_www(self):
        self.assertEqual(
            normalize_domain("https://www.example.com/products?x=1"),
            "example.com",
        )
        self.assertEqual(normalize_domain("vendor.ai"), "vendor.ai")

    def test_vendor_variable_catalog_matches_prd_count(self):
        self.assertEqual(len(VENDOR_VARIABLE_CATALOG), TOTAL_VENDOR_VARIABLES)
        self.assertIn("vendor_category", {item.name for item in VENDOR_VARIABLE_CATALOG})
        self.assertIn("va_close_rate", {item.name for item in VENDOR_VARIABLE_CATALOG})

    def test_seed_creates_profile_variables_and_export_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    niche = NicheMarket(
                        industry="Healthcare",
                        niche_name="Dental Clinics",
                        geography="US",
                        priority_score=80,
                    )
                    vendor = Vendor(
                        vendor_name="Acme Security",
                        company_website="https://www.acmesecurity.test",
                        company_size="11-50",
                        year_founded=2018,
                        headquarters="US",
                        cyber_category="Identity & Access Management",
                        cyber_subcategory="MFA",
                        threat_types_addressed="MFA, phishing, account takeover",
                        product_description="Identity security for SMBs",
                        target_market="SMB",
                        pricing_model="subscription",
                        deployment_models="SaaS",
                        compliance_certifications="SOC2 Type II",
                        customer_rating=4.6,
                        free_trial=True,
                        status="active",
                    )
                    session.add_all([niche, vendor])
                    session.commit()

                    pain_point = PainPoint(
                        niche_market_id=niche.id,
                        industry="Healthcare",
                        pain_point_name="Account takeover",
                        pain_point_rank=1,
                        cyber_category="Identity & Access",
                        cyber_subcategory="MFA",
                        severity_score=9,
                    )
                    session.add(pain_point)
                    session.commit()

                    session.add(VendorPainPointMap(
                        vendor_id=vendor.id,
                        pain_point_id=pain_point.id,
                        match_score=0.7,
                        confidence_label="strong",
                        match_type="category_and_capability",
                    ))
                    session.commit()
                finally:
                    session.close()

                summary = run_vendor_scope_seed()
                rows = build_vendor_intelligence_rows()

                session = get_session()
                try:
                    profile = session.query(VendorIntelligenceProfile).one()
                    variables = session.query(VendorIntelligenceVariable).all()
                    self.assertEqual(summary["processed"], 1)
                    self.assertEqual(profile.primary_domain, "acmesecurity.test")
                    self.assertGreater(profile.vendor_quality_score, 0)
                    self.assertEqual(profile.readiness_status, "Review Ready")
                    self.assertTrue(any(v.variable_name == "vendor_category" for v in variables))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["vendor_name"], "Acme Security")
                finally:
                    session.close()


if __name__ == "__main__":
    unittest.main()
