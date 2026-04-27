import json
import unittest

from agents.niche_market_agent import (
    ResearchValidationError,
    strip_json_response,
    validate_research_output,
)


def valid_payload():
    return {
        "industry": "Healthcare",
        "sub_industry": "Hospitals",
        "sub_sub_industry": "",
        "niche_name": "Hospital Cybersecurity",
        "geography": "US",
        "naics_code": "622110",
        "avg_employee_count_min": 50,
        "avg_employee_count_max": 500,
        "attack_records": 8,
        "digitalization_level": 9,
        "sme_revenue_contribution": 40,
        "cagr": 6,
        "cybersecurity_readiness": 4,
        "industry_size": 120,
        "smb_percentage": 65,
        "estimated_annual_loss": 3,
        "regulatory_complexity": 8,
        "common_cyber_risks": "Ransomware, phishing, data breach",
        "reachability": 7,
        "buyer_role_clarity": 8,
        "procurement_friction": 5,
        "time_to_value": 7,
        "vendor_sprawl": 6,
        "budget_proxy": 7,
        "offer_fit": 8,
        "compliance_audit_drivers": "Yes",
        "compliance_audit_notes": "HIPAA",
        "icp_headcount_min": 50,
        "icp_headcount_max": 250,
        "icp_description": "Regional providers with small security teams.",
        "assumptions_notes": "Estimated from market norms.",
        "top_pain_points": [
            {
                "rank": 1,
                "pain_point": "Ransomware",
                "description": "Operational disruption",
                "cyber_category": "Endpoint Security",
                "cyber_subcategory": "Ransomware Protection",
                "severity_score": 9,
                "growth_rate": 12,
            },
            {
                "rank": 2,
                "pain_point": "Phishing",
                "description": "Credential theft",
                "cyber_category": "Email Security",
                "cyber_subcategory": "Anti-Phishing",
                "severity_score": 8,
                "growth_rate": 10,
            },
            {
                "rank": 3,
                "pain_point": "Data breach",
                "description": "Protected data exposure",
                "cyber_category": "Data Security",
                "cyber_subcategory": "DLP",
                "severity_score": 8,
                "growth_rate": 9,
            },
        ],
    }


class ResearchValidationTests(unittest.TestCase):
    def test_strip_json_response_handles_fenced_json(self):
        raw = "```json\n" + json.dumps(valid_payload()) + "\n```"
        stripped = strip_json_response(raw)
        self.assertEqual(json.loads(stripped)["industry"], "Healthcare")

    def test_valid_payload_passes(self):
        data = validate_research_output(valid_payload())
        self.assertEqual(data["attack_records"], 8)

    def test_out_of_range_score_fails(self):
        payload = valid_payload()
        payload["reachability"] = 11
        with self.assertRaises(ResearchValidationError):
            validate_research_output(payload)

    def test_missing_pain_points_fail(self):
        payload = valid_payload()
        payload["top_pain_points"] = payload["top_pain_points"][:2]
        with self.assertRaises(ResearchValidationError):
            validate_research_output(payload)


if __name__ == "__main__":
    unittest.main()
