import os
import tempfile
import unittest
from unittest.mock import patch

from agents.data_quality_agent import (
    expected_priority_watchlist,
    expected_refined_tier,
    expected_supply_gate,
    run_data_quality,
)
from database.db_manager import get_session
from database.schema import (
    AccountLead,
    DataQualityFinding,
    DataQualityRun,
    NicheMarket,
    NicheRadarScore,
    PainPoint,
    Vendor,
    VendorIntelligenceProfile,
    VendorPainPointMap,
)


class DataQualityAgentTests(unittest.TestCase):
    def test_niche_radar_expected_rules_match_phase0_thresholds(self):
        score = NicheRadarScore(
            nps_va=73,
            reachability_score=70,
            marketplace_vendor_count_serving_niche=6,
            top_pain_point_coverage_pct=100,
            avg_match_score_for_niche=55,
        )

        self.assertEqual(expected_supply_gate(score), "tier1_ready")
        self.assertEqual(expected_refined_tier(score), ("Tier 2 - Build pipeline", 2))
        self.assertEqual(expected_priority_watchlist(score), "Tier 1 Candidate")

    def test_data_quality_flags_inconsistent_outputs(self):
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
                        demand_score=80,
                        outbound_score=75,
                        priority_score=70,
                    )
                    vendor = Vendor(
                        vendor_name="Acme Security",
                        company_website="",
                        cyber_category="Identity",
                        target_market="SMB",
                    )
                    session.add_all([niche, vendor])
                    session.commit()

                    pain_point = PainPoint(
                        niche_market_id=niche.id,
                        pain_point_rank=1,
                        severity_score=8,
                    )
                    session.add(pain_point)
                    session.commit()

                    session.add(VendorPainPointMap(
                        vendor_id=vendor.id,
                        pain_point_id=pain_point.id,
                        match_score=1.4,
                        confidence_label="strong",
                    ))
                    session.add(NicheRadarScore(
                        niche_market_id=niche.id,
                        vulnerability_score=80,
                        payability_score=75,
                        reachability_score=70,
                        nps_va=73,
                        refined_tier="Tier 1 - Hunt now",
                        refined_tier_rank=1,
                        priority_watchlist_status="",
                        marketplace_vendor_count_serving_niche=6,
                        top_pain_point_coverage_pct=100,
                        avg_match_score_for_niche=55,
                        vendor_supply_gate_status="review_ready",
                    ))
                    session.add(VendorIntelligenceProfile(
                        vendor_id=vendor.id,
                        vendor_canonical_id="acme-security",
                        canonical_name="Acme Security",
                        readiness_status="Review Ready",
                        trust_score=40,
                        fit_score=40,
                        operational_score=20,
                        vendor_quality_score=40,
                        total_match_count=1,
                    ))
                    session.commit()
                finally:
                    session.close()

                summary = run_data_quality("all")

                session = get_session()
                try:
                    run = session.query(DataQualityRun).one()
                    checks = {finding.check_name for finding in session.query(DataQualityFinding).all()}
                    self.assertEqual(summary["run_id"], run.id)
                    self.assertEqual(summary["status"], "fail")
                    self.assertIn("vendor_match_score_range", checks)
                    self.assertIn("vendor_supply_gate_consistency", checks)
                    self.assertIn("tier_rule_consistency", checks)
                    self.assertIn("review_ready_core_fields", checks)
                finally:
                    session.close()

    def test_contact_identified_without_contact_channel_is_review_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    session.add(AccountLead(
                        account_canonical_id="contact::ct::unknown::kelser::barry-kelly",
                        company_legal_name="Kelser Corporation",
                        state="CT",
                        decision_maker_name="Barry Kelly",
                        decision_maker_title="President",
                        lead_status="Contact Identified",
                        lead_score=0,
                    ))
                    session.commit()
                finally:
                    session.close()

                summary = run_data_quality("account_leads")

                session = get_session()
                try:
                    findings = session.query(DataQualityFinding).all()
                    self.assertEqual(summary["status"], "review")
                    self.assertEqual(summary["critical_count"], 0)
                    self.assertEqual(summary["warning_count"], 1)
                    self.assertEqual(findings[0].check_name, "contact_identified_channel_missing")
                finally:
                    session.close()


if __name__ == "__main__":
    unittest.main()
