import os
import tempfile
import unittest
from unittest.mock import patch

from agents.account_export_agent import (
    DISCOVERY_STATUS,
    build_account_export_rows,
    seed_account_discovery_pilot,
)
from agents.data_quality_agent import run_data_quality
from database.db_manager import get_session
from database.schema import AccountLead, NicheMarket, NicheRadarScore


class AccountExportAgentTests(unittest.TestCase):
    def test_seed_creates_discovery_pending_rows_for_watchlist_niches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    niche = NicheMarket(
                        industry="Healthcare",
                        niche_name="Digital Payment Security",
                        naics_code="522320",
                        geography="US",
                        priority_score=70,
                    )
                    session.add(niche)
                    session.commit()
                    session.add(NicheRadarScore(
                        niche_market_id=niche.id,
                        vulnerability_score=78,
                        payability_score=69,
                        reachability_score=70,
                        nps_va=73,
                        refined_tier="Tier 2 - Build pipeline",
                        refined_tier_rank=2,
                        priority_watchlist_status="Tier 1 Candidate",
                        marketplace_vendor_count_serving_niche=9,
                        top_pain_point_coverage_pct=100,
                        avg_match_score_for_niche=69,
                        vendor_supply_gate_status="tier1_ready",
                    ))
                    session.commit()
                finally:
                    session.close()

                summary = seed_account_discovery_pilot(niche_limit=1, states=["CA", "TX"])
                dq_summary = run_data_quality("account_leads")
                rows = build_account_export_rows()

                self.assertEqual(summary["created"], 2)
                self.assertEqual(dq_summary["status"], "pass")
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row["is_discovery_placeholder"] for row in rows))
                self.assertTrue(all(row["lead_status"] == DISCOVERY_STATUS for row in rows))

    def test_data_quality_blocks_non_placeholder_without_company_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    session.add(AccountLead(
                        account_canonical_id="bad-account",
                        state="CA",
                        lead_status="Hot",
                        lead_score=90,
                    ))
                    session.commit()
                finally:
                    session.close()

                summary = run_data_quality("account_leads")

                self.assertEqual(summary["status"], "fail")
                self.assertGreater(summary["critical_count"], 0)

    def test_build_account_export_rows_can_filter_by_lead_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    session.add_all([
                        AccountLead(
                            account_canonical_id="target-1",
                            company_legal_name="Target One",
                            state="CA",
                            lead_status="Account Target",
                            lead_score=65,
                        ),
                        AccountLead(
                            account_canonical_id="discovery-1",
                            state="TX",
                            lead_status=DISCOVERY_STATUS,
                            lead_score=70,
                        ),
                    ])
                    session.commit()
                finally:
                    session.close()

                rows = build_account_export_rows(lead_status="Account Target")

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["account_canonical_id"], "target-1")
                self.assertEqual(rows[0]["lead_status"], "Account Target")


if __name__ == "__main__":
    unittest.main()
