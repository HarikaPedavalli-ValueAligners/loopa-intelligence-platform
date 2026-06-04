import os
import tempfile
import unittest
from unittest.mock import patch

from agents.niche_radar_agent import (
    NICHE_VARIABLE_CATALOG,
    TOTAL_NICHE_VARIABLES,
    build_niche_radar_rows,
    run_niche_radar_seed,
    score_niche,
)
from database.db_manager import get_session
from database.schema import (
    NicheMarket,
    NicheRadarScore,
    NicheRadarVariable,
    PainPoint,
    Vendor,
    VendorPainPointMap,
)


class NicheRadarAgentTests(unittest.TestCase):
    def test_niche_variable_catalog_matches_prd_count(self):
        self.assertEqual(len(NICHE_VARIABLE_CATALOG), TOTAL_NICHE_VARIABLES)
        names = {item.name for item in NICHE_VARIABLE_CATALOG}
        self.assertIn("marketplace_vendor_count_serving_niche", names)
        self.assertIn("state_specific_regulatory_flags", names)

    def test_score_niche_promotes_strong_supply_to_tier_one(self):
        niche = NicheMarket(
            demand_score=90,
            outbound_score=85,
            attack_records=8,
            digitalization_level=8,
            buyer_role_clarity=9,
            budget_proxy=8,
            offer_fit=9,
            procurement_friction=2,
            reachability=8,
            time_to_value=8,
            likely_compliance_regimes="HIPAA; PCI DSS",
        )
        supply = {
            "vendor_count": 6,
            "coverage_pct": 100,
            "avg_match_score": 55,
        }

        pain_points = [
            PainPoint(pain_point_rank=1, severity_score=9),
            PainPoint(pain_point_rank=2, severity_score=9),
            PainPoint(pain_point_rank=3, severity_score=8),
        ]

        result = score_niche(niche, pain_points, supply)

        self.assertEqual(result["refined_tier"], "Tier 1 - Hunt now")
        self.assertEqual(result["priority_watchlist_status"], "")
        self.assertEqual(result["vendor_supply_gate_status"], "tier1_ready")
        self.assertGreaterEqual(result["nps_va"], 75)

    def test_score_niche_marks_tier_one_candidate_without_promoting(self):
        niche = NicheMarket(
            demand_score=72,
            outbound_score=70,
            attack_records=7,
            digitalization_level=7,
            buyer_role_clarity=7,
            budget_proxy=6,
            offer_fit=7,
            procurement_friction=2,
            reachability=7,
            time_to_value=7,
            likely_compliance_regimes="HIPAA",
        )
        supply = {
            "vendor_count": 6,
            "coverage_pct": 100,
            "avg_match_score": 55,
        }
        pain_points = [
            PainPoint(pain_point_rank=1, severity_score=7),
            PainPoint(pain_point_rank=2, severity_score=7),
            PainPoint(pain_point_rank=3, severity_score=7),
        ]

        result = score_niche(niche, pain_points, supply)

        self.assertEqual(result["refined_tier"], "Tier 2 - Build pipeline")
        self.assertEqual(result["priority_watchlist_status"], "Tier 1 Candidate")
        self.assertGreaterEqual(result["nps_va"], 65)
        self.assertLess(result["nps_va"], 75)

    def test_seed_creates_score_variables_and_export_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    niche = NicheMarket(
                        industry="Healthcare",
                        sub_industry="Clinics",
                        niche_name="Dental Clinics",
                        naics_code="621210",
                        geography="US",
                        demand_score=72,
                        outbound_score=70,
                        priority_score=72,
                        priority_tier=1,
                        attack_records=8,
                        digitalization_level=8,
                        buyer_role_clarity=8,
                        budget_proxy=7,
                        offer_fit=8,
                        procurement_friction=2,
                        reachability=8,
                        time_to_value=8,
                        primary_buyer_role="Owner/Operator; Compliance Lead",
                        likely_compliance_regimes="HIPAA",
                        recommended_cyber_themes="identity; compliance; data protection",
                    )
                    vendor_one = Vendor(
                        vendor_name="DentalSec",
                        cyber_category="Identity & Access Management",
                        cyber_subcategory="MFA",
                        target_market="SMB",
                    )
                    vendor_two = Vendor(
                        vendor_name="ClinicShield",
                        cyber_category="Data Security",
                        cyber_subcategory="DLP",
                        target_market="SMB",
                    )
                    session.add_all([niche, vendor_one, vendor_two])
                    session.commit()

                    points = [
                        PainPoint(
                            niche_market_id=niche.id,
                            industry="Healthcare",
                            sub_industry="Clinics",
                            pain_point_name=f"Pain {index}",
                            pain_point_rank=index,
                            cyber_category="Identity & Access",
                            cyber_subcategory="MFA",
                            severity_score=9,
                        )
                        for index in range(1, 4)
                    ]
                    session.add_all(points)
                    session.commit()

                    for point in points:
                        session.add(VendorPainPointMap(
                            vendor_id=vendor_one.id,
                            pain_point_id=point.id,
                            match_score=0.7,
                            confidence_label="strong",
                            match_type="category_and_capability",
                        ))
                        session.add(VendorPainPointMap(
                            vendor_id=vendor_two.id,
                            pain_point_id=point.id,
                            match_score=0.5,
                            confidence_label="medium",
                            match_type="taxonomy",
                        ))
                    session.commit()
                finally:
                    session.close()

                summary = run_niche_radar_seed()
                rows = build_niche_radar_rows()

                session = get_session()
                try:
                    score = session.query(NicheRadarScore).one()
                    variables = session.query(NicheRadarVariable).all()
                    self.assertEqual(summary["processed"], 1)
                    self.assertGreater(score.nps_va, 0)
                    self.assertEqual(score.vendor_supply_gate_status, "review_ready")
                    self.assertEqual(score.priority_watchlist_status, "Tier 2 - Priority Watchlist")
                    self.assertTrue(any(v.variable_name == "naics_code" for v in variables))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["niche_market"], "Dental Clinics")
                    self.assertEqual(rows[0]["priority_watchlist_status"], "Tier 2 - Priority Watchlist")
                finally:
                    session.close()


if __name__ == "__main__":
    unittest.main()
