import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from agents.account_source_importer import import_account_csv, write_template
from agents.data_quality_agent import run_data_quality
from database.db_manager import get_session
from database.schema import AccountLead, NicheMarket, NicheRadarScore


class AccountSourceImporterTests(unittest.TestCase):
    def test_import_account_csv_creates_real_account_lead(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "accounts.csv")
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
                    niche_id = niche.id
                finally:
                    session.close()

                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=[
                        "niche_market_id",
                        "company_name",
                        "state",
                        "title",
                        "email",
                        "lead_score",
                    ])
                    writer.writeheader()
                    writer.writerow({
                        "niche_market_id": niche_id,
                        "company_name": "Acme Dental Payments LLC",
                        "state": "CA",
                        "title": "Owner",
                        "email": "owner@example.test",
                        "lead_score": "72",
                    })

                summary = import_account_csv(csv_path, source_type="apollo")
                dq_summary = run_data_quality("account_leads")

                session = get_session()
                try:
                    lead = session.query(AccountLead).one()
                    self.assertEqual(summary["created"], 1)
                    self.assertEqual(lead.company_legal_name, "Acme Dental Payments LLC")
                    self.assertEqual(lead.lead_status, "Hot")
                    self.assertEqual(dq_summary["status"], "pass")
                finally:
                    session.close()

    def test_import_account_csv_skips_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "accounts.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=["company_name", "state"])
                    writer.writeheader()
                    writer.writerow({"company_name": "", "state": "CA"})

                summary = import_account_csv(csv_path)

                self.assertEqual(summary["created"], 0)
                self.assertEqual(summary["skipped"], 1)

    def test_import_zoominfo_standard_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "zoominfo.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    niche = NicheMarket(
                        industry="Financial Services",
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
                    niche_id = niche.id
                finally:
                    session.close()

                headers = [
                    "company_name",
                    "company_website",
                    "hq_state",
                    "industry",
                    "company_size",
                    "revenue",
                    "contact_full_name",
                    "job_title",
                    "work_email",
                    "email_confidence",
                    "direct_phone",
                    "company_phone",
                    "contact_linkedin_url",
                    "company_linkedin_url",
                    "naics_code",
                    "sic_code",
                    "company_description",
                    "technologies_used",
                    "data_freshness",
                    "segment",
                    "icp_track",
                    "source",
                ]
                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=headers)
                    writer.writeheader()
                    writer.writerow({
                        "company_name": "Acme Cybersecurity LLC",
                        "company_website": "https://www.acmecyber.example",
                        "hq_state": "CA",
                        "industry": "Computer systems design",
                        "company_size": "201-500",
                        "revenue": "$25M-$50M",
                        "contact_full_name": "Jordan Lee",
                        "job_title": "Director of IT Security",
                        "work_email": "jordan.lee@acmecyber.example",
                        "email_confidence": "Best",
                        "direct_phone": "555-0101",
                        "company_phone": "555-0199",
                        "contact_linkedin_url": "https://www.linkedin.com/in/jordan-lee-example",
                        "company_linkedin_url": "https://www.linkedin.com/company/acme-cyber-example",
                        "naics_code": "541512",
                        "sic_code": "7373",
                        "company_description": "Regional MSSP.",
                        "technologies_used": "Microsoft Azure;Okta;CrowdStrike",
                        "data_freshness": "2026-05-01",
                        "segment": "buyer",
                        "icp_track": "Compliance/GRC",
                        "source": "zoominfo_pilot",
                    })

                summary = import_account_csv(csv_path, source_type="zoominfo", default_niche_id=niche_id)
                dq_summary = run_data_quality("account_leads")

                session = get_session()
                try:
                    lead = session.query(AccountLead).one()
                    self.assertEqual(summary["created"], 1)
                    self.assertEqual(lead.company_legal_name, "Acme Cybersecurity LLC")
                    self.assertEqual(lead.state, "CA")
                    self.assertEqual(lead.employee_count_estimated, 350)
                    self.assertEqual(lead.revenue_estimated_usd, 37500000.0)
                    self.assertEqual(lead.decision_maker_name, "Jordan Lee")
                    self.assertEqual(lead.linkedin_url, "https://www.linkedin.com/in/jordan-lee-example")
                    self.assertIn("technologies_used=Microsoft Azure;Okta;CrowdStrike", lead.source_summary)
                    self.assertEqual(dq_summary["status"], "pass")
                finally:
                    session.close()

    def test_import_zoominfo_company_master_list_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "zoominfo_master.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with patch.dict(os.environ, env, clear=True):
                session = get_session()
                try:
                    niche = NicheMarket(
                        industry="Business Services",
                        niche_name="IT Consultants/MSPs",
                        naics_code="541512",
                        geography="US",
                        priority_score=70,
                    )
                    session.add(niche)
                    session.commit()
                    niche_id = niche.id
                finally:
                    session.close()

                headers = [
                    "ZoomInfo Company ID",
                    "Company Name",
                    "Website",
                    "Revenue Range (in USD)",
                    "Employees",
                    "Employee Range",
                    "Primary Industry",
                    "Primary Sub-Industry",
                    "ZoomInfo Company Profile URL",
                    "LinkedIn Company Profile URL",
                    "Company HQ Phone",
                    "Company State",
                    "Full Address",
                ]
                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=headers)
                    writer.writeheader()
                    writer.writerow({
                        "ZoomInfo Company ID": "347344390",
                        "Company Name": "KirkPatrickPrice",
                        "Website": "www.kirkpatrickprice.com",
                        "Revenue Range (in USD)": "$25 mil. - $50 mil.",
                        "Employees": "200",
                        "Employee Range": "Employees.100to249",
                        "Primary Industry": "Business Services",
                        "Primary Sub-Industry": "Management Consulting",
                        "ZoomInfo Company Profile URL": "https://app.zoominfo.com/#/apps/profile/company/347344390",
                        "LinkedIn Company Profile URL": "http://www.linkedin.com/company/kirkpatrickprice",
                        "Company HQ Phone": "(800) 770-2701",
                        "Company State": "Florida",
                        "Full Address": "1228 E 7th Ave Ste 200, Tampa, Florida, 33605, United States",
                    })

                summary = import_account_csv(
                    csv_path,
                    source_type="zoominfo_master",
                    default_niche_id=niche_id,
                    default_lead_status_value="Account Target",
                )

                session = get_session()
                try:
                    lead = session.query(AccountLead).one()
                    self.assertEqual(summary["created"], 1)
                    self.assertEqual(lead.account_canonical_id, "zoominfo_company::347344390")
                    self.assertEqual(lead.company_legal_name, "KirkPatrickPrice")
                    self.assertEqual(lead.state, "FL")
                    self.assertEqual(lead.employee_count_estimated, 200)
                    self.assertEqual(lead.revenue_estimated_usd, 37500000.0)
                    self.assertEqual(lead.lead_status, "Account Target")
                    self.assertEqual(lead.recommended_track, "ZoomInfo Company Target")
                    self.assertEqual(lead.phone, "(800) 770-2701")
                    self.assertIn("primary_industry=Business Services", lead.source_summary)
                finally:
                    session.close()

    def test_normalizes_district_of_columbia(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "zoominfo_master.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "ZoomInfo Company ID",
                    "Company Name",
                    "Company State",
                ])
                writer.writeheader()
                writer.writerow({
                    "ZoomInfo Company ID": "111",
                    "Company Name": "DC Target",
                    "Company State": "District of Columbia",
                })

            with patch.dict(os.environ, env, clear=True):
                summary = import_account_csv(
                    csv_path,
                    source_type="zoominfo_master",
                    default_lead_status_value="Account Target",
                )
                session = get_session()
                try:
                    lead = session.query(AccountLead).first()
                    self.assertEqual(summary["created"], 1)
                    self.assertEqual(lead.state, "DC")
                finally:
                    session.close()

    def test_import_zoominfo_contact_seed_keeps_multiple_contacts_per_company(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "zoominfo_contacts.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "Company",
                    "Website",
                    "HQ",
                    "Employee Count",
                    "Revenue",
                    "Full Name",
                    "Title",
                    "Target Industries",
                    "Services",
                    "Compliance Tags",
                ])
                writer.writeheader()
                writer.writerow({
                    "Company": "Kelser Corporation",
                    "Website": "https://www.kelsercorp.com",
                    "HQ": "Glastonbury, CT",
                    "Employee Count": "53",
                    "Revenue": "$12.9M",
                    "Full Name": "Barry Kelly",
                    "Title": "President",
                    "Target Industries": "Healthcare",
                    "Services": "Managed IT",
                    "Compliance Tags": "HIPAA",
                })
                writer.writerow({
                    "Company": "Kelser Corporation",
                    "Website": "https://www.kelsercorp.com",
                    "HQ": "Glastonbury, CT",
                    "Employee Count": "53",
                    "Revenue": "$12.9M",
                    "Full Name": "Devin Kelly",
                    "Title": "VP",
                    "Target Industries": "Healthcare",
                    "Services": "Managed IT",
                    "Compliance Tags": "HIPAA",
                })

            with patch.dict(os.environ, env, clear=True):
                summary = import_account_csv(
                    csv_path,
                    source_type="zoominfo_contact_seed",
                    default_lead_status_value="Contact Identified",
                )
                session = get_session()
                try:
                    leads = session.query(AccountLead).order_by(AccountLead.decision_maker_name).all()
                    self.assertEqual(summary["created"], 2)
                    self.assertEqual(len(leads), 2)
                    self.assertEqual({lead.state for lead in leads}, {"CT"})
                    self.assertEqual({lead.decision_maker_name for lead in leads}, {"Barry Kelly", "Devin Kelly"})
                    self.assertTrue(all(lead.lead_status == "Contact Identified" for lead in leads))
                    self.assertTrue(all(lead.recommended_track == "ZoomInfo Contact Seed" for lead in leads))
                    self.assertTrue(all(lead.account_canonical_id.startswith("contact::ct::") for lead in leads))
                    self.assertIn("target_industries=Healthcare", leads[0].source_summary)
                finally:
                    session.close()

    def test_contact_enrichment_mode_promotes_rows_with_contact_channel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "zoominfo_contacts.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "Company",
                    "HQ",
                    "Full Name",
                    "Title",
                    "Email",
                ])
                writer.writeheader()
                writer.writerow({
                    "Company": "Kelser Corporation",
                    "HQ": "Glastonbury, CT",
                    "Full Name": "Barry Kelly",
                    "Title": "President",
                    "Email": "",
                })

            with patch.dict(os.environ, env, clear=True):
                seed_summary = import_account_csv(
                    csv_path,
                    source_type="zoominfo_contact_seed",
                    default_lead_status_value="Contact Identified",
                )

                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=[
                        "Company",
                        "HQ",
                        "Full Name",
                        "Title",
                        "Email",
                    ])
                    writer.writeheader()
                    writer.writerow({
                        "Company": "Kelser Corporation",
                        "HQ": "Glastonbury, CT",
                        "Full Name": "Barry Kelly",
                        "Title": "President",
                        "Email": "barry.kelly@example.test",
                    })

                enrichment_summary = import_account_csv(
                    csv_path,
                    source_type="zoominfo_contact_enrichment",
                    default_lead_status_value="__auto_contact_status__",
                )
                dq_summary = run_data_quality("account_leads")

                session = get_session()
                try:
                    lead = session.query(AccountLead).one()
                    self.assertEqual(seed_summary["created"], 1)
                    self.assertEqual(enrichment_summary["updated"], 1)
                    self.assertEqual(lead.lead_status, "Outreach Ready")
                    self.assertEqual(lead.recommended_track, "ZoomInfo Outreach Ready")
                    self.assertEqual(lead.email, "barry.kelly@example.test")
                    self.assertIsNone(lead.phone)
                    self.assertEqual(dq_summary["status"], "pass")
                finally:
                    session.close()

    def test_contact_enrichment_mode_combines_first_and_last_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "loopa_test.db")
            csv_path = os.path.join(tmpdir, "vciso_contacts.csv")
            env = {"DATABASE_URL": f"sqlite:///{db_path}"}

            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[
                    "id",
                    "category",
                    "first_name",
                    "last_name",
                    "title",
                    "company",
                    "industry",
                    "company_size",
                    "email",
                    "direct_phone",
                    "linkedin_url",
                    "city",
                    "state",
                    "country",
                    "verified_email",
                    "verified_phone",
                    "email_subject",
                    "email_body",
                    "linkedin_message",
                ])
                writer.writeheader()
                writer.writerow({
                    "id": "1",
                    "category": "Cat1_PurePlay_vCISO",
                    "first_name": "Michael",
                    "last_name": "Torres",
                    "title": "Virtual CISO",
                    "company": "SecureShield Advisory",
                    "industry": "Security Products & Services",
                    "company_size": "1-10",
                    "email": "m.torres@example.test",
                    "direct_phone": "+1-512-334-8821",
                    "linkedin_url": "linkedin.com/in/michaeltorres-vciso",
                    "city": "Austin",
                    "state": "TX",
                    "country": "United States",
                    "verified_email": "Yes",
                    "verified_phone": "Yes",
                    "email_subject": "vCISO partnership",
                    "email_body": "Hello Michael",
                    "linkedin_message": "Hi Michael",
                })

            with patch.dict(os.environ, env, clear=True):
                summary = import_account_csv(
                    csv_path,
                    source_type="vciso_outreach_contacts",
                    default_lead_status_value="__auto_contact_status__",
                )
                dq_summary = run_data_quality("account_leads")

                session = get_session()
                try:
                    lead = session.query(AccountLead).one()
                    self.assertEqual(summary["created"], 1)
                    self.assertEqual(lead.decision_maker_name, "Michael Torres")
                    self.assertEqual(lead.lead_status, "Outreach Ready")
                    self.assertEqual(lead.state, "TX")
                    self.assertEqual(lead.employee_count_estimated, 5)
                    self.assertEqual(lead.phone, "+1-512-334-8821")
                    self.assertIn("category=Cat1_PurePlay_vCISO", lead.source_summary)
                    self.assertIn("email_subject=vCISO partnership", lead.source_summary)
                    self.assertEqual(dq_summary["status"], "pass")
                finally:
                    session.close()

    def test_write_template_creates_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "template.csv")
            write_template(path)

            with open(path, newline="") as csvfile:
                headers = next(csv.reader(csvfile))

            self.assertIn("company_legal_name", headers)
            self.assertIn("decision_maker_title", headers)


if __name__ == "__main__":
    unittest.main()
