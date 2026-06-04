# NicheRadar Account Discovery Phase 1 Pilot Summary

## Purpose

This pilot moves NicheRadar from niche-level scoring into account-level workflow preparation without fabricating company or contact data.

The first version creates a source-ready discovery queue using the existing `account_leads` schema. Rows are explicitly marked as `Discovery Pending`, meaning they are not outreach-ready leads yet. They represent niche-state discovery tasks that should be populated with real company records once approved sources are connected.

## What Was Built

- Added `agents/account_export_agent.py`.
- Seeds account discovery pilot rows from NicheRadar watchlist niches.
- Exports account-level CSVs using the PRD account fields.
- Adds DQ traceability to exports:
  - `dq_status`
  - `dq_run_id`
  - `dq_quality_score`
- Extends Data Quality Agent with `account_leads` checks.
- Added `agents/account_source_importer.py`.
- Added a CSV import path for Apollo, ZoomInfo, D&B, state registry, or generic account exports.
- Added `data/account_import_template.csv` as the canonical template for account source imports.

## Current Pilot Output

Generated export:

- `data/account_export_20260506_191212.csv`

Pilot scope:

- Candidate niches: 3
- States: CA, TX, NY
- Account discovery rows: 9
- Lead status: `Discovery Pending`

Selected niches:

- Digital Payment Security
- Public Relations Agencies
- Other Scientific and Technical Consulting Services

## Data Quality Result

Latest full DQ result after account pilot:

- Target: `all`
- Status: `pass`
- Quality score: `100.0`
- Rows checked: `14,465`
- Critical findings: `0`
- Warnings: `0`

Account-specific DQ:

- Account rows checked: `9`
- Status: `pass`
- Critical findings: `0`
- Warnings: `0`

## Important Guardrail

The pilot does not invent company names, contacts, emails, or phone numbers.

Rows with `lead_status = Discovery Pending` are allowed to have blank company/contact fields because they are discovery tasks. Once a row becomes a real account lead, Data Quality requires:

- `company_legal_name`
- valid `lead_score`
- state
- linked niche where available
- for Hot / On-fire leads: decision-maker persona and at least one verified contact channel

## Recommended Next Step

Choose the first real account data source:

1. State Secretary of State / business registry source for legal entities.
2. Apollo / ZoomInfo for firmographic and contact enrichment.
3. D&B for revenue/headcount validation.

Recommended pilot path: start with one niche and one state, populate real accounts, then compare data quality and usability before scaling.

The import command shape is:

```bash
.venv/bin/python agents/account_source_importer.py \
  --input path/to/source_accounts.csv \
  --source-type apollo \
  --default-niche-id 8
```

The importer upserts source-verified rows into `account_leads`, derives canonical account IDs when needed, assigns a default lead status from `lead_score`, and runs account-level DQ after import.

## ZoomInfo CSV Header Validation

Hamid's ZoomInfo v1 sample uses these standardized headers:

```text
company_name, company_website, hq_state, industry, company_size, revenue,
contact_full_name, job_title, work_email, email_confidence, direct_phone,
company_phone, contact_linkedin_url, company_linkedin_url, naics_code,
sic_code, company_description, technologies_used, data_freshness,
segment, icp_track, source
```

The importer now supports this shape directly.

Confirmed mapping:

- `company_name` -> `company_legal_name`
- `company_website` -> source/profile context
- `hq_state` -> `state`
- `company_size` -> `employee_count_estimated` using midpoint for ranges such as `201-500`
- `revenue` -> `revenue_estimated_usd` using midpoint for ranges such as `$25M-$50M`
- `contact_full_name` -> `decision_maker_name`
- `job_title` -> `decision_maker_title`
- `work_email` -> `email`
- `direct_phone` / `company_phone` -> `phone`
- `contact_linkedin_url` -> `linkedin_url`
- optional fields such as `email_confidence`, `technologies_used`, `naics_code`, `sic_code`, and `data_freshness` are retained in `source_summary`

The importer can handle a single `contact_full_name` column, so first and last name do not need to be split for v1.

## ZoomInfo Company Master List Import

Nathan/Hamid's IT Consultants/MSP Master List has been imported as company-level account targets, not outreach-ready contact leads.

Source file:

- `/Users/tengkaiyang/Downloads/It Consultants_MSP list - Master List (1).csv`

Import result:

- Source rows: `438`
- Account Target rows created/available: `407`
- Rows skipped: `30`
- Existing duplicate/update row: `1`
- Total `account_leads`: `416`
  - `407` `Account Target`
  - `9` `Discovery Pending`

Generated company target export:

- `data/account_target_export_20260519.csv`

Latest account DQ:

- Status: `pass`
- Critical findings: `0`
- Warnings: `0`

Important limitation:

- This Master List is company-level only. It includes company name, website/profile context, state/region, employee/revenue signals, industry fields, company phone, and ZoomInfo/LinkedIn company URLs.
- It does not include contact-level fields such as contact name, title, work email, email verification/confidence, direct phone, or contact LinkedIn.
- Therefore it is usable as the target account pool, but it is not yet the final outreach-ready lead export.

Observed source quality boundary:

- `30` rows were skipped because they were missing company name or state/region.
- The accepted target pool includes both US and non-US regions from ZoomInfo. US state names are normalized to two-letter codes where possible, including `District of Columbia` -> `DC`.

## ZoomInfo Contact Seed Import

Hamid supplied a contact-level seed file:

- `/Users/tengkaiyang/Downloads/value_aligners_zoominfo_contacts_seed.csv`

Import result:

- Source rows: `28`
- Contact rows created: `28`
- Rows skipped: `0`
- Total `account_leads`: `444`
  - `407` `Account Target`
  - `28` `Contact Identified`
  - `9` `Discovery Pending`

Generated contact seed export:

- `data/account_contact_seed_export_20260521.csv`

Latest account DQ after contact seed import:

- Status: `review`
- Critical findings: `0`
- Warnings: `28`
- Checked rows: `444`

Important limitation:

- The seed includes company, HQ, employee/revenue, contact name, and title.
- It does not include email, phone, or LinkedIn URL for any of the 28 contacts.
- These records are therefore stored as `Contact Identified`, not `Outreach Ready`.
- The 28 DQ warnings are intentional guardrails: each contact still needs at least one outreach channel before sales handoff.

ICP check:

- The attached ICP master document's ICP 4 focuses on U.S.-based MSPs, IT consultants, and cybersecurity consultancies serving SMBs in healthcare/manufacturing or regulated industries.
- The 28 contact rows cover `14` U.S.-based companies.
- All 28 contacts are in the ICP 4 employee band of `20-500` employees.
- Titles are C-level / founder / VP / owner / vCIO-style contacts.
- The 14 seed companies did not match the previously imported 407-company Master List by normalized company name, so they are stored as new contact seed records rather than merged into existing `Account Target` rows.
- The only blocking ICP gap is verified contact info: email, phone, or LinkedIn is missing for every contact row.

## Contact Seed QA and Enrichment Prep

While waiting for email, phone, or LinkedIn enrichment, the contact seed has been converted into two operational follow-up files:

- `data/contact_enrichment_request_20260522.csv`
- `data/contact_icp_fit_scoring_20260522.csv`

QA result:

- Contacts reviewed: `28`
- Companies reviewed: `14`
- Outreach-ready contacts: `0`
- Contacts needing email/phone/LinkedIn: `28`
- A-tier ICP fit contacts: `26`
- B-tier ICP fit contacts: `2`

The enrichment request file is designed for Hamid/Nathan to fill the missing contact channels. The ICP scoring file ranks who should be contacted first once those channels are available.

Prepared upgrade path:

- `agents/account_source_importer.py --contact-enrichment-mode` now imports enriched contact rows and automatically promotes rows with email, phone, or LinkedIn to `Outreach Ready`.
- Rows without a verified outreach channel remain `Contact Identified`.
- Account DQ blocks `Outreach Ready` rows that do not have a title and at least one contact channel.

## vCISO Outreach Ready Import

Hamid supplied an outreach-ready vCISO contact file:

- `/Users/tengkaiyang/Downloads/VA_vCISO_Outreach_Contacts.csv`

Import result:

- Source rows: `30`
- Outreach Ready rows created: `30`
- Rows skipped: `0`
- Total `account_leads`: `474`
  - `407` `Account Target`
  - `30` `Outreach Ready`
  - `28` `Contact Identified`
  - `9` `Discovery Pending`

Generated outreach-ready export:

- `data/vciso_outreach_ready_export_20260525.csv`

Outreach-ready field coverage:

- Company: `30/30`
- Contact name: `30/30`
- Title: `30/30`
- Email: `30/30`
- Phone: `30/30`
- LinkedIn URL: `30/30`
- Verified email flag: `30/30`
- Verified phone flag: `30/30`

Important note:

- The latest account-level DQ remains `review` because the older 28 `Contact Identified` rows still lack outreach channels.
- The new 30 `Outreach Ready` rows have all required outreach fields and no missing title/contact-channel issue.
