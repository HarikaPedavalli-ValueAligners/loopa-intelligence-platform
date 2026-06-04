import csv
import os
import tempfile
import unittest

from agents.contact_seed_qa_agent import run_contact_seed_qa


class ContactSeedQaAgentTests(unittest.TestCase):
    def test_contact_seed_qa_outputs_enrichment_and_icp_scoring(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "contacts.csv")
            output_dir = os.path.join(tmpdir, "data")
            with open(input_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "Priority",
                    "Company",
                    "Website",
                    "HQ",
                    "Employee Count",
                    "Revenue",
                    "Full Name",
                    "Title",
                    "Email",
                    "Phone",
                    "LinkedIn URL",
                    "Target Industries",
                    "Services",
                    "Compliance Tags",
                    "Source",
                ])
                writer.writeheader()
                writer.writerow({
                    "Priority": "1",
                    "Company": "Kelser Corporation",
                    "Website": "https://www.kelsercorp.com",
                    "HQ": "Glastonbury, CT",
                    "Employee Count": "53",
                    "Revenue": "$12.9M",
                    "Full Name": "Barry Kelly",
                    "Title": "President",
                    "Email": "",
                    "Phone": "",
                    "LinkedIn URL": "",
                    "Target Industries": "Healthcare providers; manufacturers",
                    "Services": "Managed IT; cybersecurity; compliance",
                    "Compliance Tags": "HIPAA; NIST",
                    "Source": "ZoomInfo",
                })

            summary = run_contact_seed_qa(input_path, output_date="20260522", output_dir=output_dir)

            self.assertEqual(summary["contacts"], 1)
            self.assertEqual(summary["companies"], 1)
            self.assertEqual(summary["outreach_ready"], 0)
            self.assertEqual(summary["needs_contact_channel"], 1)
            self.assertTrue(os.path.exists(summary["enrichment_path"]))
            self.assertTrue(os.path.exists(summary["scoring_path"]))
            self.assertTrue(os.path.exists(summary["summary_path"]))

            with open(summary["scoring_path"], newline="") as csvfile:
                scored = next(csv.DictReader(csvfile))
            self.assertEqual(scored["state"], "CT")
            self.assertEqual(scored["icp_fit_tier"], "A - Strong ICP Fit")
            self.assertEqual(scored["outreach_readiness_status"], "Needs Contact Channel")


if __name__ == "__main__":
    unittest.main()
