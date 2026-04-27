import unittest
from unittest.mock import patch

from agents.batch_processor import process_batch


def fake_research(industry, sub_industry=None, sub_sub_industry=None, max_retries=2):
    return {
        "industry": industry,
        "sub_industry": sub_industry or "",
        "sub_sub_industry": sub_sub_industry or "",
        "demand_score": 80,
        "outbound_score": 70,
        "priority_score": 56,
        "priority_tier": 2,
        "top_pain_points": [{"pain_point": "Ransomware"}],
    }


class BatchProcessorTests(unittest.TestCase):
    @patch("agents.batch_processor.research_niche_market", side_effect=fake_research)
    def test_process_batch_supports_explicit_limit_without_db(self, _mock_research):
        results = process_batch(
            niche_markets=[
                ("Healthcare", "Hospitals", None),
                ("Finance", "Banking", None),
            ],
            delay_seconds=0,
            save_to_db=False,
            limit=1,
            use_database=False,
        )

        self.assertEqual(results["total"], 1)
        self.assertEqual(results["success"], 1)
        self.assertEqual(results["failed"], 0)


if __name__ == "__main__":
    unittest.main()
