import unittest
from unittest.mock import patch

from agents.batch_processor import _apply_seed_identity, process_batch


def fake_research(
    industry,
    sub_industry=None,
    sub_sub_industry=None,
    niche_name=None,
    market_context=None,
    max_retries=2,
):
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

    def test_seed_identity_overrides_model_labels(self):
        data = {
            "industry": "Agriculture",
            "sub_industry": "Crop Production",
            "sub_sub_industry": "Oilseed and Grain Farming",
            "niche_name": "Agricultural Crop Production",
            "geography": "US",
            "naics_code": "111000",
        }
        seed = {
            "id": 329,
            "industry": "Agriculture, Forestry, Fishing and Hunting",
            "sub_industry": "Crop Production",
            "sub_sub_industry": "Oilseed and Grain Farming",
            "sub_sub_sub_industry": "Soybean Farming",
            "sub_sub_sub_sub_industry": "Soybean Farming",
            "niche_name": "Soybean Farming",
            "naics_code": "111110",
        }

        result = _apply_seed_identity(data, seed)

        self.assertEqual(result["niche_name"], "Soybean Farming")
        self.assertEqual(result["naics_code"], "111110")
        self.assertEqual(result["sub_sub_sub_industry"], "Soybean Farming")
        self.assertEqual(result["source_status"], "researched")

    @patch("agents.batch_processor.research_niche_market", side_effect=Exception("Error code: 429 - rate limit reached"))
    def test_process_batch_stops_on_rate_limit(self, _mock_research):
        results = process_batch(
            niche_markets=[
                ("Healthcare", "Hospitals", None),
                ("Finance", "Banking", None),
            ],
            delay_seconds=0,
            save_to_db=False,
            use_database=False,
        )

        self.assertEqual(results["failed"], 1)
        self.assertTrue(results["stopped_early"])
        self.assertEqual(results["stop_reason"], "rate_limit")


if __name__ == "__main__":
    unittest.main()
