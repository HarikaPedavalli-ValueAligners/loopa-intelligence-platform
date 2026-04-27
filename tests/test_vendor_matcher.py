import unittest

from agents.vendor_matcher import calculate_match, confidence_label


class VendorMatcherTests(unittest.TestCase):
    def test_synonym_match_scores_identity_vendor(self):
        pain_point = {
            "cyber_category": "Identity & Access",
            "cyber_subcategory": "MFA",
            "pain_point_name": "Weak authentication",
            "description": "Accounts lack multifactor authentication",
        }
        vendor = {
            "cyber_category": "IAM",
            "cyber_subcategory": "Multi factor authentication",
            "threat_types_addressed": "identity access management, MFA",
            "product_description": "Authentication and access controls",
            "customer_rating": 4.5,
        }

        match = calculate_match(pain_point, vendor)

        self.assertGreaterEqual(match["score"], 0.45)
        self.assertIn(match["confidence_label"], {"medium", "strong"})

    def test_confidence_label_thresholds(self):
        self.assertEqual(confidence_label(0.7), "strong")
        self.assertEqual(confidence_label(0.5), "medium")
        self.assertEqual(confidence_label(0.3), "weak")
        self.assertEqual(confidence_label(0.1), "below_threshold")


if __name__ == "__main__":
    unittest.main()
