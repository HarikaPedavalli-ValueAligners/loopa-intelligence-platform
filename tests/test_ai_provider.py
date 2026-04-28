import json
import unittest
from unittest.mock import patch

from agents.niche_market_agent import (
    _google_generation_config,
    get_ai_provider_order,
    research_niche_market,
)
from agents.batch_processor import _configured_ai_label


def research_payload():
    return {
        "industry": "Healthcare",
        "sub_industry": "Hospitals",
        "sub_sub_industry": "",
        "niche_name": "Hospitals",
        "geography": "US",
        "naics_code": "622110",
        "avg_employee_count_min": 100,
        "avg_employee_count_max": 2000,
        "attack_records": 8,
        "digitalization_level": 8,
        "sme_revenue_contribution": 60,
        "cagr": 8,
        "cybersecurity_readiness": 4,
        "industry_size": 500,
        "smb_percentage": 70,
        "estimated_annual_loss": 10,
        "regulatory_complexity": 9,
        "common_cyber_risks": "Ransomware, Phishing, Data Breach",
        "reachability": 7,
        "buyer_role_clarity": 8,
        "procurement_friction": 6,
        "time_to_value": 8,
        "vendor_sprawl": 6,
        "budget_proxy": 8,
        "offer_fit": 9,
        "compliance_audit_drivers": "Yes",
        "compliance_audit_notes": "HIPAA audits, cyber insurance renewals",
        "icp_headcount_min": 100,
        "icp_headcount_max": 2000,
        "icp_description": "Hospitals with regulated patient data and active IT operations.",
        "assumptions_notes": "Test payload.",
        "top_pain_points": [
            {
                "rank": 1,
                "pain_point": "Ransomware",
                "description": "Operational disruption from ransomware.",
                "cyber_category": "Endpoint Security",
                "cyber_subcategory": "Ransomware Protection",
                "severity_score": 9,
                "growth_rate": 15,
            },
            {
                "rank": 2,
                "pain_point": "Phishing",
                "description": "Credential theft from phishing.",
                "cyber_category": "Email Security",
                "cyber_subcategory": "Phishing Protection",
                "severity_score": 8,
                "growth_rate": 12,
            },
            {
                "rank": 3,
                "pain_point": "Data Breach",
                "description": "Unauthorized access to patient data.",
                "cyber_category": "Data Security",
                "cyber_subcategory": "Data Loss Prevention",
                "severity_score": 8,
                "growth_rate": 10,
            },
        ],
    }


class AIProviderTests(unittest.TestCase):
    def test_default_provider_is_groq_only(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(get_ai_provider_order(), ["groq"])

    def test_openai_provider_keeps_groq_fallback(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "openai", "AI_ENABLE_FALLBACK": "true"}, clear=True):
            self.assertEqual(get_ai_provider_order(), ["openai", "groq"])

    def test_gemini_provider_keeps_groq_fallback(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "gemini", "AI_ENABLE_FALLBACK": "true"}, clear=True):
            self.assertEqual(get_ai_provider_order(), ["gemini", "groq"])

    def test_vertex_provider_keeps_groq_fallback(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "vertex", "AI_ENABLE_FALLBACK": "true"}, clear=True):
            self.assertEqual(get_ai_provider_order(), ["vertex", "groq"])

    def test_configured_ai_label_supports_google_providers(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "gemini", "GEMINI_MODEL": "gemini-3-pro-preview"}, clear=True):
            self.assertEqual(_configured_ai_label(), "gemini:gemini-3-pro-preview")
        with patch.dict("os.environ", {"AI_PROVIDER": "vertex", "VERTEX_MODEL": "gemini-2.5-pro"}, clear=True):
            self.assertEqual(_configured_ai_label(), "vertex:gemini-2.5-pro")

    def test_google_generation_config_supports_thinking_budget(self):
        with patch.dict("os.environ", {"GEMINI_THINKING_BUDGET": "8192"}, clear=True):
            self.assertEqual(
                _google_generation_config("gemini")["thinking_config"],
                {"thinking_budget": 8192},
            )

    @patch("agents.niche_market_agent.generate_ai_response")
    def test_research_records_ai_provider_metadata(self, mock_generate):
        mock_generate.return_value = (
            json.dumps(research_payload()),
            "openai",
            "gpt-4o-mini",
        )

        result = research_niche_market("Healthcare", "Hospitals", max_retries=0)

        self.assertEqual(result["ai_provider"], "openai")
        self.assertEqual(result["ai_model"], "gpt-4o-mini")
        self.assertIn(result["priority_tier"], {1, 2, 3})
        self.assertIsNotNone(result["priority_score"])


if __name__ == "__main__":
    unittest.main()
