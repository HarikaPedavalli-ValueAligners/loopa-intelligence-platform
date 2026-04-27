import unittest

from agents.niche_market_agent import (
    calculate_demand_score,
    calculate_outbound_score,
    calculate_priority_score,
    get_priority_tier,
)


class ScoringTests(unittest.TestCase):
    def test_low_readiness_increases_demand(self):
        base = {
            "attack_records": 5,
            "digitalization_level": 5,
            "sme_revenue_contribution": 50,
            "cagr": 10,
            "industry_size": 1000,
            "smb_percentage": 50,
            "estimated_annual_loss": 50,
        }

        low_readiness = calculate_demand_score({**base, "cybersecurity_readiness": 1})
        high_readiness = calculate_demand_score({**base, "cybersecurity_readiness": 10})

        self.assertGreater(low_readiness, high_readiness)

    def test_low_procurement_friction_increases_outbound(self):
        base = {
            "reachability": 5,
            "buyer_role_clarity": 5,
            "time_to_value": 5,
            "vendor_sprawl": 5,
            "offer_fit": 5,
        }

        low_friction = calculate_outbound_score({**base, "procurement_friction": 1})
        high_friction = calculate_outbound_score({**base, "procurement_friction": 10})

        self.assertGreater(low_friction, high_friction)

    def test_priority_score_and_tiers(self):
        self.assertEqual(calculate_priority_score(80, 75), 60)
        self.assertEqual(get_priority_tier(70), 1)
        self.assertEqual(get_priority_tier(50), 2)
        self.assertEqual(get_priority_tier(49.99), 3)


if __name__ == "__main__":
    unittest.main()
